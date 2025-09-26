#!/usr/bin/env python3
"""
🚀 Multi-Stream Market Data Collector
Сбор реальных данных с Binance по 200+ парам в PostgreSQL

Поддерживает:
- bookTicker (top-of-book) 
- aggTrade (агрегированные сделки)
- depth@100ms (глубина рынка для топ-пар)
- Шардирование WebSocket соединений
- Batch PostgreSQL ingestion
- Отказоустойчивость и мониторинг
"""

import asyncio
import asyncpg
import json
import logging
import websockets
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager
import signal
import sys
from pathlib import Path
import os

# Подхватываем переменные окружения из .env.production или .env (если доступны)
try:
    from collector.config.settings import load_env_file
    _root = Path(__file__).resolve().parents[2]
    for _candidate in [
        _root / ".env.production",
        _root / ".env"
    ]:
        if _candidate.exists():
            load_env_file(str(_candidate))
            break
except Exception:
    # Тихо игнорируем, если модуль/файлы недоступны — окружение может быть уже задано снаружи
    pass

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/multistream_collector.log')
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class MarketDataEvent:
    """Базовый класс для market data событий"""
    symbol: str
    exchange: str
    ts_exchange: datetime
    ts_ingest: datetime
    event_type: str  # 'bookTicker', 'aggTrade', 'depthUpdate'

@dataclass 
class BookTickerEvent(MarketDataEvent):
    """Событие bookTicker"""
    update_id: Optional[int]
    best_bid: float
    best_ask: float
    bid_qty: float
    ask_qty: float
    
    @property
    def spread(self) -> float:
        return self.best_ask - self.best_bid
    
    @property
    def mid(self) -> float:
        return (self.best_ask + self.best_bid) / 2

@dataclass
class TradeEvent(MarketDataEvent):
    """Событие aggTrade"""
    agg_trade_id: int
    price: float
    qty: float
    is_buyer_maker: bool

@dataclass
class DepthEvent(MarketDataEvent):
    """Событие depth update"""
    first_update_id: int
    final_update_id: int
    prev_final_update_id: Optional[int]
    bids: List[List[str]]  # [[price, qty], ...]
    asks: List[List[str]]  # [[price, qty], ...]

@dataclass
class MarkPriceEvent(MarketDataEvent):
    """Событие mark price / index price"""
    event_type: Optional[str]
    mark_price: Optional[float]
    index_price: Optional[float]
    est_settlement_price: Optional[float]
    funding_rate: Optional[float]
    next_funding_time: Optional[datetime]

@dataclass
class ForceOrderEvent(MarketDataEvent):
    """Событие ликвидации (forceOrder)"""
    event_type: Optional[str]
    side: Optional[str]   # BUY/SELL
    price: Optional[float]
    qty: Optional[float]
    raw: dict

class SymbolManager:
    """Управление списком символов и их конфигурацией"""
    
    def __init__(self, pg_pool: asyncpg.Pool):
        self.pg_pool = pg_pool
        self.symbols: Dict[str, int] = {}  # symbol -> symbol_id
        self.top_symbols: Set[str] = set()  # Топ символы для depth
        
    async def load_symbols(self):
        """Загрузка символов из БД"""
        async with self.pg_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, symbol FROM marketdata.symbols 
                WHERE is_active = true AND exchange = 'binance-futures'
            """)
            
        self.symbols = {row['symbol']: row['id'] for row in rows}
        
        # Определяем топ-символы для depth (пока топ-10)
        top_symbols_list = [
            'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOTUSDT',
            'BNBUSDT', 'XRPUSDT', 'AVAXUSDT', 'MATICUSDT', 'LINKUSDT'
        ]
        self.top_symbols = {s for s in top_symbols_list if s in self.symbols}
        
        logger.info(f"📊 Загружено символов: {len(self.symbols)}")
        logger.info(f"🔝 Топ-символы для depth: {list(self.top_symbols)}")

class BatchProcessor:
    """Batch обработка и запись в PostgreSQL"""
    
    def __init__(self, pg_pool: asyncpg.Pool, batch_size: int = 100):
        self.pg_pool = pg_pool
        self.batch_size = batch_size
        self.buffers = {
            'book_ticker': [],
            'trades': [],
            'depth_events': [],
            'mark_price': [],
            'force_orders': []
        }
        self.stats = {
            'book_ticker': {'processed': 0, 'failed': 0},
            'trades': {'processed': 0, 'failed': 0},
            'depth_events': {'processed': 0, 'failed': 0},
            'mark_price': {'processed': 0, 'failed': 0},
            'force_orders': {'processed': 0, 'failed': 0}
        }
        
    async def add_event(self, event: MarketDataEvent, symbol_id: int):
        """Добавление события в соответствующий буфер"""
        try:
            if isinstance(event, BookTickerEvent):
                self.buffers['book_ticker'].append((
                    event.ts_exchange, event.ts_ingest, symbol_id, event.update_id,
                    event.best_bid, event.best_ask, event.bid_qty, event.ask_qty,
                    event.spread, event.mid
                ))
                
            elif isinstance(event, TradeEvent):
                self.buffers['trades'].append((
                    event.ts_exchange, event.ts_ingest, symbol_id, event.agg_trade_id,
                    event.price, event.qty, event.is_buyer_maker
                ))
                
            elif isinstance(event, DepthEvent):
                self.buffers['depth_events'].append((
                    event.ts_exchange, event.ts_ingest, symbol_id,
                    event.first_update_id, event.final_update_id, event.prev_final_update_id,
                    json.dumps(event.bids), json.dumps(event.asks)
                ))
            elif isinstance(event, MarkPriceEvent):
                self.buffers['mark_price'].append((
                    event.ts_exchange, event.ts_ingest, symbol_id,
                    event.event_type, event.mark_price, event.index_price,
                    event.est_settlement_price, event.funding_rate, event.next_funding_time
                ))
            elif isinstance(event, ForceOrderEvent):
                self.buffers['force_orders'].append((
                    event.ts_exchange, event.ts_ingest, symbol_id,
                    event.side, event.price, event.qty, json.dumps(event.raw)
                ))
            
            # Проверяем необходимость flush
            for table_name, buffer in self.buffers.items():
                if len(buffer) >= self.batch_size:
                    await self._flush_buffer(table_name)
                    
        except Exception as e:
            logger.error(f"❌ Ошибка добавления события {event.event_type}: {e}")
            
    async def _flush_buffer(self, table_name: str):
        """Запись буфера в PostgreSQL"""
        buffer = self.buffers[table_name]
        if not buffer:
            return
            
        try:
            async with self.pg_pool.acquire() as conn:
                if table_name == 'book_ticker':
                    await conn.executemany("""
                        INSERT INTO marketdata.book_ticker (
                            ts_exchange, ts_ingest, symbol_id, update_id,
                            best_bid, best_ask, bid_qty, ask_qty, spread, mid
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """, buffer)
                    
                elif table_name == 'trades':
                    await conn.executemany("""
                        INSERT INTO marketdata.trades (
                            ts_exchange, ts_ingest, symbol_id, agg_trade_id,
                            price, qty, is_buyer_maker
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT DO NOTHING
                    """, buffer)
                    
                elif table_name == 'depth_events':
                    await conn.executemany("""
                        INSERT INTO marketdata.depth_events (
                            ts_exchange, ts_ingest, symbol_id,
                            first_update_id, final_update_id, prev_final_update_id,
                            bids, asks
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        ON CONFLICT DO NOTHING
                    """, buffer)
                elif table_name == 'mark_price':
                    await conn.executemany("""
                        INSERT INTO marketdata.mark_price (
                            ts_exchange, ts_ingest, symbol_id, event_type,
                            mark_price, index_price, est_settlement_price,
                            funding_rate, next_funding_time
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        ON CONFLICT DO NOTHING
                    """, buffer)
                elif table_name == 'force_orders':
                    await conn.executemany("""
                        INSERT INTO marketdata.force_orders (
                            ts_exchange, ts_ingest, symbol_id, side, price, qty, raw
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT DO NOTHING
                    """, buffer)
            
            logger.debug(f"✅ Flush {table_name}: {len(buffer)} записей")
            self.stats[table_name]['processed'] += len(buffer)
            self.buffers[table_name].clear()
            
        except Exception as e:
            logger.error(f"❌ Ошибка flush {table_name}: {e}")
            self.stats[table_name]['failed'] += len(buffer)
            self.buffers[table_name].clear()
    
    async def flush_all(self):
        """Принудительный flush всех буферов"""
        for table_name in self.buffers:
            await self._flush_buffer(table_name)
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики"""
        return dict(self.stats)

class WebSocketStream:
    """Управление одним WebSocket соединением"""
    
    def __init__(self, stream_url: str, symbols: List[str], 
                 symbol_manager: SymbolManager, batch_processor: BatchProcessor):
        self.stream_url = stream_url
        self.symbols = symbols
        self.symbol_manager = symbol_manager
        self.batch_processor = batch_processor
        self.websocket = None
        self.running = False
        
    async def start(self):
        """Запуск WebSocket потока"""
        self.running = True
        
        while self.running:
            try:
                logger.info(f"🔗 Подключение к WebSocket: {len(self.symbols)} символов")
                
                async with websockets.connect(self.stream_url) as websocket:
                    self.websocket = websocket
                    
                    async for message in websocket:
                        if not self.running:
                            break
                            
                        await self._process_message(message)
                        
            except Exception as e:
                logger.error(f"❌ WebSocket ошибка: {e}")
                if self.running:
                    logger.info("🔄 Переподключение через 5 секунд...")
                    await asyncio.sleep(5)
    
    async def _process_message(self, message: str):
        """Обработка WebSocket сообщения"""
        try:
            data = json.loads(message)
            
            # Пропускаем служебные сообщения
            if 'stream' not in data or 'data' not in data:
                return
            
            stream_name = data['stream']
            event_data = data['data']
            
            # Парсинг символа из stream name
            if '@bookTicker' in stream_name:
                symbol = stream_name.replace('@bookTicker', '').upper()
                event = await self._parse_book_ticker(symbol, event_data)
            elif '@aggTrade' in stream_name:
                symbol = stream_name.replace('@aggTrade', '').upper()
                event = await self._parse_agg_trade(symbol, event_data)
            elif '@depth' in stream_name:
                symbol = stream_name.split('@')[0].upper()
                event = await self._parse_depth(symbol, event_data)
            elif '@markPrice' in stream_name:
                # может приходить как per-symbol поток
                symbol = (event_data.get('s') or stream_name.split('@')[0]).upper()
                event = await self._parse_mark_price(symbol, event_data)
            elif '@forceOrder' in stream_name:
                # forceOrder содержит order в поле 'o'
                o = event_data.get('o', {})
                symbol = (o.get('s') or event_data.get('s') or stream_name.split('@')[0]).upper()
                event = await self._parse_force_order(symbol, event_data)
            else:
                return
            
            if event and symbol in self.symbol_manager.symbols:
                symbol_id = self.symbol_manager.symbols[symbol]
                await self.batch_processor.add_event(event, symbol_id)
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщения: {e}")
    
    async def _parse_book_ticker(self, symbol: str, data: Dict) -> Optional[BookTickerEvent]:
        """Парсинг bookTicker события"""
        try:
            return BookTickerEvent(
                symbol=symbol,
                exchange='binance-futures',
                ts_exchange=datetime.fromtimestamp(data['E'] / 1000, tz=timezone.utc),
                ts_ingest=datetime.now(tz=timezone.utc),
                event_type='bookTicker',
                update_id=data.get('u'),
                best_bid=float(data['b']),
                best_ask=float(data['a']),
                bid_qty=float(data['B']),
                ask_qty=float(data['A'])
            )
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга bookTicker {symbol}: {e}")
            return None
    
    async def _parse_agg_trade(self, symbol: str, data: Dict) -> Optional[TradeEvent]:
        """Парсинг aggTrade события"""
        try:
            return TradeEvent(
                symbol=symbol,
                exchange='binance-futures',
                ts_exchange=datetime.fromtimestamp(data['E'] / 1000, tz=timezone.utc),
                ts_ingest=datetime.now(tz=timezone.utc),
                event_type='aggTrade',
                agg_trade_id=data['a'],
                price=float(data['p']),
                qty=float(data['q']),
                is_buyer_maker=data['m']
            )
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга aggTrade {symbol}: {e}")
            return None
    
    async def _parse_depth(self, symbol: str, data: Dict) -> Optional[DepthEvent]:
        """Парсинг depth события"""
        try:
            return DepthEvent(
                symbol=symbol,
                exchange='binance-futures',
                ts_exchange=datetime.fromtimestamp(data['E'] / 1000, tz=timezone.utc),
                ts_ingest=datetime.now(tz=timezone.utc),
                event_type='depthUpdate',
                first_update_id=data['U'],
                final_update_id=data['u'],
                prev_final_update_id=data.get('pu'),
                bids=data['b'],
                asks=data['a']
            )
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга depth {symbol}: {e}")
            return None

    async def _parse_mark_price(self, symbol: str, data: Dict) -> Optional[MarkPriceEvent]:
        """Парсинг markPrice@1s события"""
        try:
            ts_ex = datetime.fromtimestamp((data.get('E') or 0) / 1000, tz=timezone.utc)
            return MarkPriceEvent(
                symbol=symbol,
                exchange='binance-futures',
                ts_exchange=ts_ex,
                ts_ingest=datetime.now(tz=timezone.utc),
                event_type=data.get('e'),
                mark_price=float(data['p']) if data.get('p') is not None else None,
                index_price=float(data['i']) if data.get('i') is not None else None,
                est_settlement_price=float(data['P']) if data.get('P') is not None else None,
                funding_rate=float(data['r']) if data.get('r') is not None else None,
                next_funding_time=(datetime.fromtimestamp(data['T']/1000, tz=timezone.utc) if data.get('T') else None)
            )
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга markPrice {symbol}: {e}")
            return None

    async def _parse_force_order(self, symbol: str, data: Dict) -> Optional[ForceOrderEvent]:
        """Парсинг forceOrder события (ликвидации)"""
        try:
            o = data.get('o', {})
            ts_ms = data.get('E') or o.get('T') or 0
            return ForceOrderEvent(
                symbol=symbol,
                exchange='binance-futures',
                ts_exchange=datetime.fromtimestamp(ts_ms/1000, tz=timezone.utc),
                ts_ingest=datetime.now(tz=timezone.utc),
                event_type='forceOrder',
                side=o.get('S'),
                price=(float(o['p']) if o.get('p') is not None else None),
                qty=(float(o['q']) if o.get('q') is not None else None),
                raw=data
            )
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга forceOrder {symbol}: {e}")
            return None
    
    async def stop(self):
        """Остановка WebSocket потока"""
        self.running = False
        if self.websocket:
            await self.websocket.close()

class MultiStreamCollector:
    """Основной класс для multi-stream сбора данных"""
    
    def __init__(self, pg_connection_string: str, batch_size: int = 100):
        self.pg_connection_string = pg_connection_string
        self.batch_size = batch_size
        self.pg_pool: Optional[asyncpg.Pool] = None
        self.symbol_manager: Optional[SymbolManager] = None
        self.batch_processor: Optional[BatchProcessor] = None
        self.streams: List[WebSocketStream] = []
        self.running = False
        self.stats_task: Optional[asyncio.Task] = None
        
    async def initialize(self):
        """Инициализация коллектора"""
        logger.info("🚀 Инициализация Multi-Stream Collector")
        
        # PostgreSQL подключение
        self.pg_pool = await asyncpg.create_pool(
            self.pg_connection_string,
            min_size=5,
            max_size=20,
            command_timeout=30
        )
        logger.info("✅ PostgreSQL pool создан")
        
        # Инициализация компонентов
        self.symbol_manager = SymbolManager(self.pg_pool)
        await self.symbol_manager.load_symbols()
        
        self.batch_processor = BatchProcessor(self.pg_pool, self.batch_size)
        
        # Создание WebSocket потоков
        await self._create_streams()
        
    async def _create_streams(self):
        """Создание WebSocket потоков с шардированием"""
        all_symbols = list(self.symbol_manager.symbols.keys())
        top_symbols = list(self.symbol_manager.top_symbols)
        
        # Шардирование символов по потокам
        chunk_size = 50  # Символов на поток
        symbol_chunks = [all_symbols[i:i + chunk_size] 
                        for i in range(0, len(all_symbols), chunk_size)]
        
        base_url = "wss://fstream.binance.com/stream?streams="
        
        # bookTicker потоки
        for i, symbols in enumerate(symbol_chunks):
            streams = [f"{s.lower()}@bookTicker" for s in symbols]
            url = base_url + "/".join(streams)
            
            stream = WebSocketStream(
                url, symbols, self.symbol_manager, self.batch_processor
            )
            self.streams.append(stream)
            logger.info(f"📡 bookTicker поток {i+1}: {len(symbols)} символов")
        
        # aggTrade потоки  
        for i, symbols in enumerate(symbol_chunks):
            streams = [f"{s.lower()}@aggTrade" for s in symbols]
            url = base_url + "/".join(streams)
            
            stream = WebSocketStream(
                url, symbols, self.symbol_manager, self.batch_processor
            )
            self.streams.append(stream)
            logger.info(f"📈 aggTrade поток {i+1}: {len(symbols)} символов")
        
        # depth поток для топ-символов (diff depth @100ms)
        if top_symbols:
            depth_streams = [f"{s.lower()}@depth@100ms" for s in top_symbols]
            url = base_url + "/".join(depth_streams)
            stream = WebSocketStream(url, top_symbols, self.symbol_manager, self.batch_processor)
            self.streams.append(stream)
            logger.info(f"🧊 depth поток (@100ms): {len(top_symbols)} топ-символов")

        # markPrice@1s потоки (включаем по флагу окружения)
        enable_mark = (os.environ.get('ENABLE_MARK_PRICE', 'true').lower() == 'true')
        if enable_mark:
            for i, symbols in enumerate(symbol_chunks):
                streams = [f"{s.lower()}@markPrice@1s" for s in symbols]
                url = base_url + "/".join(streams)
                stream = WebSocketStream(url, symbols, self.symbol_manager, self.batch_processor)
                self.streams.append(stream)
                logger.info(f"🏷️ markPrice поток {i+1}: {len(symbols)} символов")

        # forceOrder потоки (включаем по флагу окружения)
        enable_force = (os.environ.get('ENABLE_FORCE_ORDER', 'true').lower() == 'true')
        if enable_force:
            for i, symbols in enumerate(symbol_chunks):
                streams = [f"{s.lower()}@forceOrder" for s in symbols]
                url = base_url + "/".join(streams)
                stream = WebSocketStream(url, symbols, self.symbol_manager, self.batch_processor)
                self.streams.append(stream)
                logger.info(f"⚠️ forceOrder поток {i+1}: {len(symbols)} символов")
        
        logger.info(f"🎯 Создано {len(self.streams)} WebSocket потоков")
    
    async def start(self):
        """Запуск коллектора"""
        logger.info("▶️ Запуск Multi-Stream Collector")
        self.running = True
        
        # Запуск всех потоков
        tasks = []
        for i, stream in enumerate(self.streams):
            task = asyncio.create_task(stream.start())
            tasks.append(task)
            logger.info(f"🔴 Поток {i+1} запущен")
        
        # Запуск статистики
        self.stats_task = asyncio.create_task(self._stats_loop())
        
        # Ожидание завершения
        try:
            await asyncio.gather(*tasks, self.stats_task)
        except asyncio.CancelledError:
            logger.info("⏹️ Получен сигнал остановки")
        finally:
            await self.stop()
    
    async def _stats_loop(self):
        """Периодический вывод статистики"""
        while self.running:
            try:
                await asyncio.sleep(60)  # Каждую минуту
                
                stats = self.batch_processor.get_stats()
                
                logger.info("📊 СТАТИСТИКА СБОРА ДАННЫХ:")
                for table, table_stats in stats.items():
                    processed = table_stats['processed']
                    failed = table_stats['failed']
                    logger.info(f"  {table}: {processed} ✅ / {failed} ❌")
                
                # Flush буферов
                await self.batch_processor.flush_all()
                
            except Exception as e:
                logger.error(f"❌ Ошибка в stats_loop: {e}")
    
    async def stop(self):
        """Остановка коллектора"""
        logger.info("🛑 Остановка Multi-Stream Collector")
        self.running = False
        
        # Остановка потоков
        for stream in self.streams:
            await stream.stop()
        
        # Остановка статистики
        if self.stats_task:
            self.stats_task.cancel()
        
        # Финальный flush
        if self.batch_processor:
            await self.batch_processor.flush_all()
            final_stats = self.batch_processor.get_stats()
            logger.info(f"📊 Финальная статистика: {final_stats}")
        
        # Закрытие пула
        if self.pg_pool:
            await self.pg_pool.close()
        
        logger.info("✅ Multi-Stream Collector остановлен")

def setup_signal_handlers(collector: MultiStreamCollector):
    """Настройка обработчиков сигналов"""
    def signal_handler(signum, frame):
        logger.info(f"📨 Получен сигнал {signum}")
        asyncio.create_task(collector.stop())
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

async def main():
    """Главная функция"""
    # Создание директории для логов
    Path("logs").mkdir(exist_ok=True)
    
    # PostgreSQL connection string для Digital Ocean
    pg_connection_string = os.getenv(
        "DATABASE_URL",
        "postgresql://user:password@host:port/database?sslmode=require"
    )
    
    collector = MultiStreamCollector(
        pg_connection_string=pg_connection_string,
        batch_size=100
    )
    
    setup_signal_handlers(collector)
    
    try:
        await collector.initialize()
        await collector.start()
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
        await collector.stop()

if __name__ == "__main__":
    asyncio.run(main())