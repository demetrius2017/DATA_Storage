"""
PRODUCTION BATCH INGESTOR FOR ORDERBOOK DATA
Асинхронный инжестор с шардированием WebSocket потоков и батч-записью в PostgreSQL
Поддерживает до 200 торговых пар с мониторингом и восстановлением соединений
"""

import asyncio
import asyncpg
import websockets
import json
import logging
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict, deque
import aiohttp
from contextlib import asynccontextmanager
import signal
import sys
import os
from urllib.parse import urlparse

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/batch_ingestor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class BatchBuffer:
    """Буфер для батчевой записи данных"""
    book_ticker: List[Dict[str, Any]] = field(default_factory=list)
    trades: List[Dict[str, Any]] = field(default_factory=list)
    depth_events: List[Dict[str, Any]] = field(default_factory=list)
    
    max_size: int = 500  # Максимальный размер батча
    max_age_seconds: int = 10  # Максимальный возраст батча
    created_at: float = field(default_factory=time.time)
    
    def is_ready_for_flush(self) -> bool:
        """Проверка готовности батча к записи"""
        total_records = len(self.book_ticker) + len(self.trades) + len(self.depth_events)
        age = time.time() - self.created_at
        return total_records >= self.max_size or age >= self.max_age_seconds
    
    def clear(self):
        """Очистка буфера"""
        self.book_ticker.clear()
        self.trades.clear() 
        self.depth_events.clear()
        self.created_at = time.time()

@dataclass
class StreamConfig:
    """Конфигурация WebSocket потока"""
    symbols: List[str]
    channels: List[str]  # ['bookTicker', 'aggTrade', 'depth5@100ms']
    shard_id: int
    max_reconnect_attempts: int = 10
    reconnect_delay: float = 5.0

class DatabaseManager:
    """Менеджер подключений к PostgreSQL"""
    
    def __init__(self, connection_string: str, pool_size: int = 10):
        self.connection_string = connection_string
        self.pool_size = pool_size
        self.pool: Optional[asyncpg.Pool] = None
        self.symbol_cache: Dict[str, int] = {}
        
    async def initialize(self):
        """Инициализация пула соединений и кэша символов"""
        logger.info("Инициализация пула соединений PostgreSQL...")
        self.pool = await asyncpg.create_pool(
            self.connection_string,
            min_size=2,
            max_size=self.pool_size,
            command_timeout=30
        )
        
        # Заполнение кэша символов
        await self._load_symbol_cache()
        logger.info(f"Загружено {len(self.symbol_cache)} символов в кэш")
        
    async def _load_symbol_cache(self):
        """Загрузка символов в кэш"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, symbol FROM marketdata.symbols WHERE is_active = true")
            self.symbol_cache = {row['symbol']: row['id'] for row in rows}
    
    async def get_or_create_symbol_id(self, symbol: str) -> int:
        """Получение или создание ID символа"""
        if symbol in self.symbol_cache:
            return self.symbol_cache[symbol]
            
        async with self.pool.acquire() as conn:
            # Попытка вставки нового символа
            try:
                symbol_id = await conn.fetchval("""
                    INSERT INTO marketdata.symbols (exchange, symbol, base_asset, quote_asset)
                    VALUES ('binance-futures', $1, split_part($1, 'USDT', 1), 'USDT')
                    ON CONFLICT (exchange, symbol) 
                    DO UPDATE SET updated_at = NOW()
                    RETURNING id
                """, symbol)
                
                if symbol_id is None:
                    # Символ уже существует, получаем его ID
                    symbol_id = await conn.fetchval(
                        "SELECT id FROM marketdata.symbols WHERE exchange = 'binance-futures' AND symbol = $1",
                        symbol
                    )
                
                self.symbol_cache[symbol] = symbol_id
                return symbol_id
                
            except Exception as e:
                logger.error(f"Ошибка при создании символа {symbol}: {e}")
                raise
    
    async def batch_insert_book_ticker(self, records: List[Dict[str, Any]]):
        """Батчевая вставка book_ticker записей"""
        if not records:
            return
            
        async with self.pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO marketdata.book_ticker 
                (ts_exchange, ts_ingest, symbol_id, update_id, best_bid, best_ask, bid_qty, ask_qty)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (symbol_id, ts_exchange, ts_ingest) DO NOTHING
            """, [
                (
                    datetime.fromtimestamp(r['ts_exchange'] / 1000, tz=timezone.utc),
                    datetime.fromtimestamp(r['ts_ingest'] / 1000, tz=timezone.utc), 
                    r['symbol_id'],
                    r.get('update_id'),
                    r['best_bid'],
                    r['best_ask'],
                    r['bid_qty'],
                    r['ask_qty']
                ) for r in records
            ])
            
    async def batch_insert_trades(self, records: List[Dict[str, Any]]):
        """Батчевая вставка trades записей"""
        if not records:
            return
            
        async with self.pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO marketdata.trades
                (ts_exchange, ts_ingest, symbol_id, agg_trade_id, price, qty, is_buyer_maker)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (symbol_id, agg_trade_id) DO NOTHING
            """, [
                (
                    datetime.fromtimestamp(r['ts_exchange'] / 1000, tz=timezone.utc),
                    datetime.fromtimestamp(r['ts_ingest'] / 1000, tz=timezone.utc),
                    r['symbol_id'],
                    r['agg_trade_id'],
                    r['price'],
                    r['qty'],
                    r['is_buyer_maker']
                ) for r in records
            ])
            
    async def batch_insert_depth_events(self, records: List[Dict[str, Any]]):
        """Батчевая вставка depth_events записей"""
        if not records:
            return
            
        async with self.pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO marketdata.depth_events
                (ts_exchange, ts_ingest, symbol_id, first_update_id, final_update_id, 
                 prev_final_update_id, bids, asks)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (symbol_id, final_update_id) DO NOTHING
            """, [
                (
                    datetime.fromtimestamp(r['ts_exchange'] / 1000, tz=timezone.utc),
                    datetime.fromtimestamp(r['ts_ingest'] / 1000, tz=timezone.utc),
                    r['symbol_id'],
                    r['first_update_id'],
                    r['final_update_id'],
                    r.get('prev_final_update_id'),
                    json.dumps(r['bids']),
                    json.dumps(r['asks'])
                ) for r in records
            ])

    async def close(self):
        """Закрытие пула соединений"""
        if self.pool:
            await self.pool.close()

class WebSocketStreamManager:
    """Менеджер WebSocket потоков с шардированием"""
    
    def __init__(self, db_manager: DatabaseManager, stream_configs: List[StreamConfig], ws_base_url: Optional[str] = None):
        self.db_manager = db_manager
        self.stream_configs = stream_configs
        self.buffers: Dict[int, BatchBuffer] = {}
        self.running = False
        self.tasks: List[asyncio.Task] = []
        # Базовый WS URL (из env), по умолчанию Binance Futures
        self.ws_base_url = (ws_base_url or os.getenv('BINANCE_WS_URL', 'wss://fstream.binance.com/ws/')).strip()
        logger.info(f"Binance WS base set to: {self.ws_base_url}")
        
        # Статистика
        self.stats = {
            'messages_received': defaultdict(int),
            'messages_processed': defaultdict(int),
            'batch_writes': defaultdict(int),
            'errors': defaultdict(int),
            'last_message_time': defaultdict(float)
        }
        
    async def start(self):
        """Запуск всех WebSocket потоков"""
        logger.info(f"Запуск {len(self.stream_configs)} WebSocket потоков...")
        self.running = True
        
        # Создание буферов для каждого шарда
        for config in self.stream_configs:
            self.buffers[config.shard_id] = BatchBuffer()
            
        # Запуск потоков для каждого шарда
        for config in self.stream_configs:
            task = asyncio.create_task(self._run_stream_shard(config))
            self.tasks.append(task)
            
        # Запуск задачи периодической записи
        flush_task = asyncio.create_task(self._periodic_flush())
        self.tasks.append(flush_task)
        
        # Запуск задачи статистики
        stats_task = asyncio.create_task(self._periodic_stats())
        self.tasks.append(stats_task)
        
        logger.info("Все WebSocket потоки запущены")
        
    async def _run_stream_shard(self, config: StreamConfig):
        """Запуск одного WebSocket потока (шарда)"""
        shard_id = config.shard_id
        attempt = 0
        
        while self.running and attempt < config.max_reconnect_attempts:
            try:
                logger.info(f"Подключение шарда {shard_id} (попытка {attempt + 1})")
                
                # Формирование URL для combined streams
                streams = []
                for symbol in config.symbols:
                    for channel in config.channels:
                        streams.append(f"{symbol.lower()}@{channel}")
                
                stream_names = "/".join(streams)
                # Построение combined stream URL на основе базового ws хоста
                # Принимаем base вида wss://fstream.binance.com/ws/ или wss://fstream.binance.com
                parsed = urlparse(self.ws_base_url)
                host = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else self.ws_base_url.rstrip('/')
                url = f"{host}/stream?streams={stream_names}"
                
                async with websockets.connect(url) as websocket:
                    logger.info(f"Шард {shard_id} подключен, символы: {config.symbols}")
                    attempt = 0  # Сброс счетчика при успешном подключении
                    
                    async for message in websocket:
                        if not self.running:
                            break
                            
                        try:
                            await self._process_message(shard_id, json.loads(message))
                            self.stats['messages_received'][shard_id] += 1
                            self.stats['last_message_time'][shard_id] = time.time()
                            
                        except json.JSONDecodeError as e:
                            logger.error(f"Ошибка JSON в шарде {shard_id}: {e}")
                            self.stats['errors'][shard_id] += 1
                        except Exception as e:
                            logger.error(f"Ошибка обработки сообщения в шарде {shard_id}: {e}")
                            self.stats['errors'][shard_id] += 1
                            
            except Exception as e:
                attempt += 1
                logger.error(f"Ошибка подключения шарда {shard_id}: {e}")
                if attempt < config.max_reconnect_attempts:
                    logger.info(f"Переподключение шарда {shard_id} через {config.reconnect_delay} сек...")
                    await asyncio.sleep(config.reconnect_delay)
                else:
                    logger.error(f"Превышено максимальное количество попыток для шарда {shard_id}")
                    
        logger.warning(f"Шард {shard_id} остановлен")
    
    async def _process_message(self, shard_id: int, message: Dict[str, Any]):
        """Обработка сообщения от WebSocket"""
        if 'data' not in message or 'stream' not in message:
            return
            
        data = message['data']
        stream = message['stream']
        
        # Определение типа события
        if '@bookTicker' in stream:
            await self._process_book_ticker(shard_id, data)
        elif '@aggTrade' in stream:
            await self._process_agg_trade(shard_id, data)
        elif '@depth' in stream:
            await self._process_depth_update(shard_id, data)
        else:
            logger.debug(f"Неизвестный тип потока: {stream}")
            
        self.stats['messages_processed'][shard_id] += 1
        
    async def _process_book_ticker(self, shard_id: int, data: Dict[str, Any]):
        """Обработка book ticker события"""
        try:
            symbol = data['s']
            symbol_id = await self.db_manager.get_or_create_symbol_id(symbol)
            
            record = {
                'ts_exchange': data['E'],
                'ts_ingest': int(time.time() * 1000),
                'symbol_id': symbol_id,
                'update_id': data.get('u'),
                'best_bid': float(data['b']),
                'best_ask': float(data['a']),
                'bid_qty': float(data['B']),
                'ask_qty': float(data['A'])
            }
            
            self.buffers[shard_id].book_ticker.append(record)
            
        except Exception as e:
            logger.error(f"Ошибка обработки book_ticker: {e}")
            self.stats['errors'][shard_id] += 1
            
    async def _process_agg_trade(self, shard_id: int, data: Dict[str, Any]):
        """Обработка aggTrade события"""
        try:
            symbol = data['s']
            symbol_id = await self.db_manager.get_or_create_symbol_id(symbol)
            
            record = {
                'ts_exchange': data['E'],
                'ts_ingest': int(time.time() * 1000),
                'symbol_id': symbol_id,
                'agg_trade_id': data['a'],
                'price': float(data['p']),
                'qty': float(data['q']),
                'is_buyer_maker': data['m']
            }
            
            self.buffers[shard_id].trades.append(record)
            
        except Exception as e:
            logger.error(f"Ошибка обработки aggTrade: {e}")
            self.stats['errors'][shard_id] += 1
            
    async def _process_depth_update(self, shard_id: int, data: Dict[str, Any]):
        """Обработка depth update события"""
        try:
            symbol = data['s']
            symbol_id = await self.db_manager.get_or_create_symbol_id(symbol)
            
            record = {
                'ts_exchange': data['E'],
                'ts_ingest': int(time.time() * 1000),
                'symbol_id': symbol_id,
                'first_update_id': data['U'],
                'final_update_id': data['u'],
                'prev_final_update_id': data.get('pu'),
                'bids': data['b'],
                'asks': data['a']
            }
            
            self.buffers[shard_id].depth_events.append(record)
            
        except Exception as e:
            logger.error(f"Ошибка обработки depth: {e}")
            self.stats['errors'][shard_id] += 1
    
    async def _periodic_flush(self):
        """Периодическая запись буферов в БД"""
        while self.running:
            try:
                for shard_id, buffer in self.buffers.items():
                    if buffer.is_ready_for_flush():
                        await self._flush_buffer(shard_id, buffer)
                        
                await asyncio.sleep(1)  # Проверка каждую секунду
                
            except Exception as e:
                logger.error(f"Ошибка в periodic_flush: {e}")
                await asyncio.sleep(5)
                
    async def _flush_buffer(self, shard_id: int, buffer: BatchBuffer):
        """Запись буфера в БД"""
        try:
            start_time = time.time()
            
            # Параллельная запись всех типов данных
            tasks = []
            
            if buffer.book_ticker:
                tasks.append(self.db_manager.batch_insert_book_ticker(buffer.book_ticker.copy()))
            if buffer.trades:
                tasks.append(self.db_manager.batch_insert_trades(buffer.trades.copy()))
            if buffer.depth_events:
                tasks.append(self.db_manager.batch_insert_depth_events(buffer.depth_events.copy()))
                
            if tasks:
                await asyncio.gather(*tasks)
                
                total_records = len(buffer.book_ticker) + len(buffer.trades) + len(buffer.depth_events)
                flush_time = time.time() - start_time
                
                logger.info(f"Шард {shard_id}: записано {total_records} записей за {flush_time:.3f}с")
                self.stats['batch_writes'][shard_id] += 1
                
            buffer.clear()
            
        except Exception as e:
            logger.error(f"Ошибка записи буфера шарда {shard_id}: {e}")
            self.stats['errors'][shard_id] += 1
            
    async def _periodic_stats(self):
        """Периодический вывод статистики"""
        while self.running:
            try:
                await asyncio.sleep(60)  # Каждую минуту
                
                logger.info("=== СТАТИСТИКА ИНЖЕСТОРА ===")
                total_messages = sum(self.stats['messages_received'].values())
                total_processed = sum(self.stats['messages_processed'].values())
                total_errors = sum(self.stats['errors'].values())
                total_batches = sum(self.stats['batch_writes'].values())
                
                logger.info(f"Всего сообщений: {total_messages}")
                logger.info(f"Обработано: {total_processed}")
                logger.info(f"Ошибок: {total_errors}")
                logger.info(f"Батчей записано: {total_batches}")
                
                # Статистика по шардам
                for shard_id in self.stats['messages_received']:
                    last_msg = self.stats['last_message_time'][shard_id]
                    if last_msg > 0:
                        lag = time.time() - last_msg
                        status = "OK" if lag < 30 else "STALE"
                        logger.info(f"Шард {shard_id}: {status}, lag: {lag:.1f}с")
                        
            except Exception as e:
                logger.error(f"Ошибка в periodic_stats: {e}")
    
    async def stop(self):
        """Остановка всех потоков"""
        logger.info("Остановка WebSocket потоков...")
        self.running = False
        
        # Финальная запись всех буферов
        for shard_id, buffer in self.buffers.items():
            await self._flush_buffer(shard_id, buffer)
            
        # Отмена всех задач
        for task in self.tasks:
            task.cancel()
            
        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("Все WebSocket потоки остановлены")

class BatchIngestor:
    """Главный класс инжестора"""
    
    def __init__(self, 
                 db_connection_string: str,
                 symbols: List[str],
                 channels: List[str] = None,
                 shards_count: int = 4,
                 ws_base_url: Optional[str] = None):
        
        self.db_connection_string = db_connection_string
        self.symbols = symbols
        self.channels = channels or ['bookTicker', 'aggTrade']
        self.shards_count = min(shards_count, len(symbols))
        self.ws_base_url = (ws_base_url or os.getenv('BINANCE_WS_URL', 'wss://fstream.binance.com/ws/')).strip()
        
        self.db_manager = DatabaseManager(db_connection_string)
        self.stream_manager = None
        
    async def start(self):
        """Запуск инжестора"""
        logger.info("Запуск BatchIngestor...")
        
        # Инициализация БД
        await self.db_manager.initialize()
        
        # Создание конфигураций шардов
        stream_configs = self._create_stream_configs()
        
        # Запуск stream manager
        self.stream_manager = WebSocketStreamManager(self.db_manager, stream_configs, ws_base_url=self.ws_base_url)
        await self.stream_manager.start()
        
        logger.info("BatchIngestor запущен")
        
    def _create_stream_configs(self) -> List[StreamConfig]:
        """Создание конфигураций для шардов"""
        configs = []
        symbols_per_shard = len(self.symbols) // self.shards_count
        
        for shard_id in range(self.shards_count):
            start_idx = shard_id * symbols_per_shard
            end_idx = (shard_id + 1) * symbols_per_shard
            
            # Последний шард берет оставшиеся символы
            if shard_id == self.shards_count - 1:
                end_idx = len(self.symbols)
                
            shard_symbols = self.symbols[start_idx:end_idx]
            
            if shard_symbols:  # Только если есть символы
                configs.append(StreamConfig(
                    symbols=shard_symbols,
                    channels=self.channels,
                    shard_id=shard_id
                ))
                
        return configs
        
    async def stop(self):
        """Остановка инжестора"""
        logger.info("Остановка BatchIngestor...")
        
        if self.stream_manager:
            await self.stream_manager.stop()
            
        await self.db_manager.close()
        logger.info("BatchIngestor остановлен")

# Функция для graceful shutdown
async def shutdown(ingestor: BatchIngestor):
    """Graceful shutdown"""
    logger.info("Получен сигнал завершения")
    await ingestor.stop()

# MAIN ФУНКЦИЯ ДЛЯ ЗАПУСКА
async def main():
    """Главная функция"""
    
    # Конфигурация
    DB_CONNECTION = os.getenv('DATABASE_URL', 
        'postgresql://postgres:password@localhost:5432/marketdata')
    
    # 200 основных торговых пар
    SYMBOLS = [
        'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'SOLUSDT', 'XRPUSDT', 'DOTUSDT',
        'DOGEUSDT', 'AVAXUSDT', 'MATICUSDT', 'SHIBUSDT', 'LTCUSDT', 'TRXUSDT', 'UNIUSDT',
        'LINKUSDT', 'BCHUSDT', 'XLMUSDT', 'ATOMUSDT', 'ETCUSDT', 'FILUSDT', 'VETUSDT',
        'ICPUSDT', 'FTMUSDT', 'HBARUSDT', 'ALGOUSDT', 'THETAUSDT', 'XMRUSDT', 'EOSUSDT',
        'AAVEUSDT', 'MKRUSDT', 'KLAYUSDT', 'AXSUSDT', 'SANDUSDT', 'MANAUSDT', 'IOTAUSDT',
        # ... еще 165 символов
    ]
    
    CHANNELS = ['bookTicker', 'aggTrade']  # Начинаем с легких каналов
    SHARDS_COUNT = 5
    
    # Создание директории для логов
    os.makedirs('logs', exist_ok=True)
    
    # Создание инжестора
    ingestor = BatchIngestor(
        db_connection_string=DB_CONNECTION,
        symbols=SYMBOLS[:50],  # Начинаем с 50 символов для тестирования
        channels=CHANNELS,
        shards_count=SHARDS_COUNT
    )
    
    # Настройка graceful shutdown
    def signal_handler():
        logger.info("Получен сигнал SIGINT/SIGTERM")
        asyncio.create_task(shutdown(ingestor))
        
    signal.signal(signal.SIGINT, lambda s, f: signal_handler())
    signal.signal(signal.SIGTERM, lambda s, f: signal_handler())
    
    try:
        await ingestor.start()
        
        # Ожидание завершения
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Завершение по Ctrl+C")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        await ingestor.stop()

if __name__ == "__main__":
    asyncio.run(main())