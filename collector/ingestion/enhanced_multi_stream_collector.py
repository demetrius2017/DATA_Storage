"""
🚀 ENHANCED MULTI-STREAM COLLECTOR V2.0
=======================================

Улучшенная версия коллектора с:
- Advanced error handling & exponential backoff
- 200+ символов с эффективным шардированием 
- Circuit breaker patterns
- Comprehensive monitoring & health checks
- Automatic symbol loading в PostgreSQL
"""

import asyncio
import logging
import signal
import json
import time
import random
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

import asyncpg
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.symbols_config import (
    get_symbol_shards, ALL_SYMBOLS, RATE_LIMITS
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/enhanced_collector.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting" 
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"

@dataclass
class StreamMetrics:
    symbols_count: int = 0
    messages_received: int = 0
    messages_processed: int = 0
    messages_failed: int = 0
    last_message_time: Optional[float] = None
    connection_state: ConnectionState = ConnectionState.DISCONNECTED
    reconnect_count: int = 0
    last_error: Optional[str] = None

@dataclass
class BatchBuffer:
    table_name: str
    data: List[tuple]
    max_size: int
    last_flush: float
    flush_interval: float
    
    def should_flush(self) -> bool:
        return (
            len(self.data) >= self.max_size or
            time.time() - self.last_flush >= self.flush_interval
        )
    
    def add(self, record: tuple):
        self.data.append(record)
    
    def clear(self):
        self.data.clear()
        self.last_flush = time.time()

class CircuitBreaker:
    """Circuit breaker для предотвращения каскадных отказов"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func):
        """Декоратор для обёртки функций в circuit breaker"""
        async def wrapper(*args, **kwargs):
            if self.state == 'OPEN':
                if self.last_failure_time and time.time() - self.last_failure_time < self.recovery_timeout:
                    raise Exception("Circuit breaker is OPEN")
                else:
                    self.state = 'HALF_OPEN'
            
            try:
                result = await func(*args, **kwargs)
                if self.state == 'HALF_OPEN':
                    self.state = 'CLOSED'
                    self.failure_count = 0
                return result
            except Exception as e:
                self.failure_count += 1
                self.last_failure_time = time.time()
                
                if self.failure_count >= self.failure_threshold:
                    self.state = 'OPEN'
                    logger.error(f"Circuit breaker opened after {self.failure_count} failures")
                
                raise e
        
        return wrapper

class EnhancedWebSocketStream:
    """Улучшенный WebSocket поток с advanced error handling"""
    
    def __init__(self, stream_id: str, symbols: List[str], stream_type: str, 
                 batch_processor, priority: str = 'medium'):
        self.stream_id = stream_id
        self.symbols = symbols
        self.stream_type = stream_type
        self.batch_processor = batch_processor
        self.priority = priority
        
        self.metrics = StreamMetrics(symbols_count=len(symbols))
        self.circuit_breaker = CircuitBreaker()
        
        self.websocket = None
        self.reconnect_delays = RATE_LIMITS['reconnect_delay']
        self.current_delay_index = 0
        self.max_reconnect_attempts = 10
        
        self.should_stop = False
        
    def _build_stream_url(self) -> str:
        """Строит URL для WebSocket подключения"""
        base_url = "wss://fstream.binance.com/ws/"
        
        if self.stream_type == 'bookTicker':
            streams = [f"{symbol.lower()}@bookTicker" for symbol in self.symbols]
        elif self.stream_type == 'aggTrade':
            streams = [f"{symbol.lower()}@aggTrade" for symbol in self.symbols]
        elif self.stream_type.startswith('depth'):
            streams = [f"{symbol.lower()}@{self.stream_type}" for symbol in self.symbols]
        else:
            raise ValueError(f"Неизвестный тип потока: {self.stream_type}")
        
        return base_url + "/".join(streams)
    
    async def _connect(self) -> bool:
        """Подключение к WebSocket с retry logic"""
        self.metrics.connection_state = ConnectionState.CONNECTING
        
        try:
            url = self._build_stream_url()
            logger.info(f"🔗 [{self.stream_id}] Подключение к {len(self.symbols)} символов ({self.stream_type})")
            
            self.websocket = await websockets.connect(
                url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            )
            
            self.metrics.connection_state = ConnectionState.CONNECTED
            self.current_delay_index = 0  # Сброс задержки при успешном подключении
            logger.info(f"✅ [{self.stream_id}] Подключено к WebSocket")
            return True
            
        except Exception as e:
            self.metrics.connection_state = ConnectionState.FAILED
            self.metrics.last_error = str(e)
            logger.error(f"❌ [{self.stream_id}] Ошибка подключения: {e}")
            return False
    
    async def _handle_message(self, message: str):
        """Обработка входящего сообщения с circuit breaker"""
        try:
            data = json.loads(message)
            self.metrics.messages_received += 1
            self.metrics.last_message_time = time.time()
            
            # Обработка через circuit breaker
            await self.circuit_breaker.call(self._process_message)(data)
            self.metrics.messages_processed += 1
            
        except Exception as e:
            self.metrics.messages_failed += 1
            self.metrics.last_error = str(e)
            logger.error(f"❌ [{self.stream_id}] Ошибка обработки сообщения: {e}")
    
    async def _process_message(self, data: dict):
        """Обработка конкретного типа сообщения"""
        if 'stream' in data:
            # Multi-stream формат
            stream_name = data['stream']
            event_data = data['data']
        else:
            # Single stream формат
            event_data = data
            stream_name = self.stream_type
        
        # Определяем тип события и передаём в batch processor
        if '@bookTicker' in stream_name:
            await self.batch_processor.add_book_ticker_event(event_data)
        elif '@aggTrade' in stream_name:
            await self.batch_processor.add_trade_event(event_data)
        elif '@depth' in stream_name:
            await self.batch_processor.add_depth_event(event_data)
    
    async def _reconnect_with_backoff(self) -> bool:
        """Переподключение с exponential backoff"""
        if self.current_delay_index >= len(self.reconnect_delays):
            logger.error(f"❌ [{self.stream_id}] Превышено максимальное количество попыток переподключения")
            return False
        
        delay = self.reconnect_delays[self.current_delay_index]
        self.current_delay_index += 1
        
        logger.info(f"🔄 [{self.stream_id}] Переподключение через {delay} секунд...")
        await asyncio.sleep(delay)
        
        self.metrics.reconnect_count += 1
        self.metrics.connection_state = ConnectionState.RECONNECTING
        
        return await self._connect()
    
    async def run(self):
        """Основной цикл работы потока"""
        logger.info(f"🚀 [{self.stream_id}] Запуск потока: {len(self.symbols)} символов, {self.stream_type}")
        
        while not self.should_stop:
            try:
                # Подключение
                if not await self._connect():
                    if not await self._reconnect_with_backoff():
                        break
                    continue
                
                # Основной цикл получения сообщений
                if self.websocket:
                    async for message in self.websocket:
                        if self.should_stop:
                            break
                        
                        await self._handle_message(message)
                    
            except ConnectionClosed:
                logger.warning(f"⚠️ [{self.stream_id}] WebSocket подключение закрыто")
                if not self.should_stop and not await self._reconnect_with_backoff():
                    break
                    
            except WebSocketException as e:
                logger.error(f"❌ [{self.stream_id}] WebSocket ошибка: {e}")
                if not await self._reconnect_with_backoff():
                    break
                    
            except Exception as e:
                logger.error(f"❌ [{self.stream_id}] Неожиданная ошибка: {e}")
                if not await self._reconnect_with_backoff():
                    break
        
        # Закрытие подключения
        if self.websocket:
            await self.websocket.close()
        
        self.metrics.connection_state = ConnectionState.DISCONNECTED
        logger.info(f"🛑 [{self.stream_id}] Поток остановлен")
    
    def stop(self):
        """Остановка потока"""
        self.should_stop = True

class EnhancedBatchProcessor:
    """Улучшенный batch processor с adaptive batching"""
    
    def __init__(self, pg_pool):
        self.pg_pool = pg_pool
        self.symbol_id_cache = {}
        
        # Настройка буферов с разными параметрами
        self.buffers = {
            'book_ticker': BatchBuffer('book_ticker', [], 1000, time.time(), 5.0),
            'trades': BatchBuffer('trades', [], 500, time.time(), 3.0),
            'depth_events': BatchBuffer('depth_events', [], 100, time.time(), 2.0)
        }
        
        self.stats = {
            'book_ticker': {'success': 0, 'failed': 0},
            'trades': {'success': 0, 'failed': 0},
            'depth_events': {'success': 0, 'failed': 0}
        }
        
        # Запуск фонового процесса flush
        self.flush_task = None
        
    async def start(self):
        """Запуск фонового процесса flush"""
        await self._load_symbol_cache()
        self.flush_task = asyncio.create_task(self._periodic_flush())
        
    async def stop(self):
        """Остановка и финальный flush"""
        if self.flush_task:
            self.flush_task.cancel()
        
        # Финальный flush всех буферов
        for buffer_name in self.buffers:
            await self._flush_buffer(buffer_name)
    
    async def _load_symbol_cache(self):
        """Загрузка кэша symbol_id из PostgreSQL"""
        async with self.pg_pool.acquire() as conn:
            symbols = await conn.fetch('SELECT id, symbol FROM marketdata.symbols')
            self.symbol_id_cache = {row['symbol']: row['id'] for row in symbols}
            logger.info(f"📊 Загружено {len(self.symbol_id_cache)} символов в кэш")
    
    async def _get_symbol_id(self, symbol: str) -> int:
        """Получение symbol_id с автоматическим добавлением новых символов"""
        if symbol in self.symbol_id_cache:
            return self.symbol_id_cache[symbol]
        
        # Добавляем новый символ
        async with self.pg_pool.acquire() as conn:
            symbol_id = await conn.fetchval("""
                INSERT INTO marketdata.symbols (exchange, symbol, is_active)
                VALUES ('binance-futures', $1, true)
                ON CONFLICT (exchange, symbol) DO UPDATE SET updated_at = now()
                RETURNING id
            """, symbol)
            
            self.symbol_id_cache[symbol] = symbol_id
            logger.info(f"➕ Добавлен новый символ: {symbol} (ID: {symbol_id})")
            return symbol_id
    
    async def add_book_ticker_event(self, data: dict):
        """Добавление book ticker события в буфер"""
        try:
            symbol = data['s']
            symbol_id = await self._get_symbol_id(symbol)
            
            ts_exchange = datetime.fromtimestamp(data['E'] / 1000, tz=timezone.utc)
            ts_ingest = datetime.now(timezone.utc)
            
            # Расчёт derived полей
            best_bid = float(data['b'])
            best_ask = float(data['a'])
            bid_qty = float(data['B'])
            ask_qty = float(data['A'])
            spread = best_ask - best_bid
            mid = (best_ask + best_bid) / 2
            
            record = (
                ts_exchange, ts_ingest, symbol_id, None,  # update_id из stream может быть None
                best_bid, best_ask, bid_qty, ask_qty, spread, mid
            )
            
            self.buffers['book_ticker'].add(record)
            
            # Проверка на необходимость flush
            if self.buffers['book_ticker'].should_flush():
                await self._flush_buffer('book_ticker')
                
        except Exception as e:
            logger.error(f"❌ Ошибка добавления book_ticker события: {e}")
    
    async def add_trade_event(self, data: dict):
        """Добавление trade события в буфер"""
        try:
            symbol = data['s']
            symbol_id = await self._get_symbol_id(symbol)
            
            ts_exchange = datetime.fromtimestamp(data['T'] / 1000, tz=timezone.utc)
            ts_ingest = datetime.now(timezone.utc)
            
            record = (
                ts_exchange, ts_ingest, symbol_id, int(data['a']),
                float(data['p']), float(data['q']), data['m']
            )
            
            self.buffers['trades'].add(record)
            
            if self.buffers['trades'].should_flush():
                await self._flush_buffer('trades')
                
        except Exception as e:
            logger.error(f"❌ Ошибка добавления trade события: {e}")
    
    async def add_depth_event(self, data: dict):
        """Добавление depth события в буфер"""
        try:
            symbol = data['s']
            symbol_id = await self._get_symbol_id(symbol)
            
            ts_exchange = datetime.fromtimestamp(data['E'] / 1000, tz=timezone.utc)
            ts_ingest = datetime.now(timezone.utc)
            
            record = (
                ts_exchange, ts_ingest, symbol_id,
                int(data['U']), int(data['u']), int(data.get('pu', 0)),
                json.dumps(data['b']), json.dumps(data['a'])
            )
            
            self.buffers['depth_events'].add(record)
            
            if self.buffers['depth_events'].should_flush():
                await self._flush_buffer('depth_events')
                
        except Exception as e:
            logger.error(f"❌ Ошибка добавления depth события: {e}")
    
    async def _flush_buffer(self, table_name: str):
        """Flush буфера в PostgreSQL"""
        buffer = self.buffers[table_name]
        if not buffer.data:
            return
        
        try:
            async with self.pg_pool.acquire() as conn:
                if table_name == 'book_ticker':
                    await conn.executemany("""
                        INSERT INTO marketdata.book_ticker (
                            ts_exchange, ts_ingest, symbol_id, update_id,
                            best_bid, best_ask, bid_qty, ask_qty, spread, mid
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """, buffer.data)
                    
                elif table_name == 'trades':
                    await conn.executemany("""
                        INSERT INTO marketdata.trades (
                            ts_exchange, ts_ingest, symbol_id, agg_trade_id,
                            price, qty, is_buyer_maker
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (symbol_id, ts_exchange, agg_trade_id) DO NOTHING
                    """, buffer.data)
                    
                elif table_name == 'depth_events':
                    await conn.executemany("""
                        INSERT INTO marketdata.depth_events (
                            ts_exchange, ts_ingest, symbol_id,
                            first_update_id, final_update_id, prev_final_update_id,
                            bids, asks
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        ON CONFLICT (symbol_id, ts_exchange, final_update_id) DO NOTHING
                    """, buffer.data)
                
                self.stats[table_name]['success'] += len(buffer.data)
                logger.info(f"✅ Записано {len(buffer.data)} записей в {table_name}")
                
        except Exception as e:
            self.stats[table_name]['failed'] += len(buffer.data)
            logger.error(f"❌ Ошибка flush {table_name}: {e}")
        
        buffer.clear()
    
    async def _periodic_flush(self):
        """Периодический flush буферов"""
        while True:
            try:
                await asyncio.sleep(1)  # Проверка каждую секунду
                
                for table_name, buffer in self.buffers.items():
                    if buffer.should_flush():
                        await self._flush_buffer(table_name)
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Ошибка periodic flush: {e}")

class EnhancedMultiStreamCollector:
    """Главный класс улучшенного multi-stream коллектора"""
    
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.pg_pool = None
        self.batch_processor = None
        self.streams = []
        self.should_stop = False
        
        # Статистика
        self.start_time = time.time()
        self.total_symbols = 0
        
    async def initialize(self):
        """Инициализация коллектора"""
        logger.info("🚀 Инициализация Enhanced Multi-Stream Collector v2.0")
        
        # Создание connection pool
        self.pg_pool = await asyncpg.create_pool(
            self.connection_string,
            min_size=5,
            max_size=20,
            command_timeout=60
        )
        logger.info("✅ PostgreSQL pool создан")
        
        # Инициализация batch processor
        self.batch_processor = EnhancedBatchProcessor(self.pg_pool)
        await self.batch_processor.start()
        
        # Загрузка всех символов в PostgreSQL
        await self._ensure_all_symbols_loaded()
        
        # Создание WebSocket потоков
        await self._create_streams()
        
    async def _ensure_all_symbols_loaded(self):
        """Загрузка всех символов в PostgreSQL"""
        async with self.pg_pool.acquire() as conn:
            for symbol in ALL_SYMBOLS:
                await conn.execute("""
                    INSERT INTO marketdata.symbols (exchange, symbol, is_active)
                    VALUES ('binance-futures', $1, true)
                    ON CONFLICT (exchange, symbol) DO NOTHING
                """, symbol)
        
        count = await self.pg_pool.fetchval('SELECT COUNT(*) FROM marketdata.symbols WHERE is_active = true')
        logger.info(f"📊 Загружено символов в БД: {count}")
        
    async def _create_streams(self):
        """Создание WebSocket потоков на основе конфигурации"""
        shards = get_symbol_shards()
        self.total_symbols = len(ALL_SYMBOLS)
        
        logger.info(f"🎯 Создание {len(shards)} WebSocket потоков для {self.total_symbols} символов")
        
        for i, shard in enumerate(shards):
            stream_id = f"stream_{i+1}_{shard['priority']}_{shard['stream_type']}"
            
            stream = EnhancedWebSocketStream(
                stream_id=stream_id,
                symbols=shard['symbols'],
                stream_type=shard['stream_type'],
                batch_processor=self.batch_processor,
                priority=shard['priority']
            )
            
            self.streams.append(stream)
        
        logger.info(f"✅ Создано {len(self.streams)} потоков")
        
    async def start(self):
        """Запуск коллектора"""
        logger.info("▶️ Запуск Enhanced Multi-Stream Collector")
        
        # Запуск всех потоков
        tasks = []
        for stream in self.streams:
            task = asyncio.create_task(stream.run())
            tasks.append(task)
            logger.info(f"🔴 {stream.stream_id} запущен")
        
        # Мониторинг и статистика
        stats_task = asyncio.create_task(self._stats_monitor())
        tasks.append(stats_task)
        
        # Ожидание завершения всех задач
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"❌ Ошибка в основном цикле: {e}")
        
    async def _stats_monitor(self):
        """Мониторинг статистики"""
        while not self.should_stop:
            await asyncio.sleep(60)  # Каждую минуту
            
            try:
                # Сбор метрик
                total_messages = sum(s.metrics.messages_processed for s in self.streams)
                active_streams = len([s for s in self.streams if s.metrics.connection_state == ConnectionState.CONNECTED])
                
                logger.info("📊 СТАТИСТИКА:")
                logger.info(f"   Активных потоков: {active_streams}/{len(self.streams)}")
                logger.info(f"   Всего обработано сообщений: {total_messages:,}")
                logger.info(f"   Время работы: {int(time.time() - self.start_time)} секунд")
                
                # Статистика batch processor
                for table, stats in self.batch_processor.stats.items():
                    logger.info(f"   {table}: {stats['success']:,} ✅ / {stats['failed']:,} ❌")
                
            except Exception as e:
                logger.error(f"❌ Ошибка мониторинга: {e}")
    
    def stop(self):
        """Остановка коллектора"""
        logger.info("🛑 Остановка Enhanced Multi-Stream Collector")
        self.should_stop = True
        
        for stream in self.streams:
            stream.stop()
    
    async def cleanup(self):
        """Очистка ресурсов"""
        if self.batch_processor:
            await self.batch_processor.stop()
        
        if self.pg_pool:
            await self.pg_pool.close()
        
        logger.info("✅ Очистка ресурсов завершена")

async def main():
    """Главная функция"""
    # PostgreSQL connection string
    connection_string = 'postgresql://user:password@host:port/database'
    
    collector = EnhancedMultiStreamCollector(connection_string)
    
    # Обработка сигналов
    def signal_handler(signum, frame):
        logger.info(f"📨 Получен сигнал {signum}")
        collector.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await collector.initialize()
        await collector.start()
    except KeyboardInterrupt:
        logger.info("⏹️ Получен сигнал остановки")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
    finally:
        await collector.cleanup()

if __name__ == "__main__":
    asyncio.run(main())