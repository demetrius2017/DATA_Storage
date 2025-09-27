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
import ssl

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
    orderbook_topn: List[Dict[str, Any]] = field(default_factory=list)
    
    max_size: int = 500  # Максимальный размер батча
    max_age_seconds: int = 10  # Максимальный возраст батча
    created_at: float = field(default_factory=time.time)
    
    def is_ready_for_flush(self) -> bool:
        """Проверка готовности батча к записи"""
        total_records = (
            len(self.book_ticker) + len(self.trades) + len(self.depth_events) + len(self.orderbook_topn)
        )
        age = time.time() - self.created_at
        return total_records >= self.max_size or age >= self.max_age_seconds
    
    def clear(self):
        """Очистка буфера"""
        self.book_ticker.clear()
        self.trades.clear() 
        self.depth_events.clear()
        self.orderbook_topn.clear()
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
        # Настраиваем SSL для DigitalOcean (sslmode=require) из connection_string
        ssl_ctx = None
        try:
            parsed = urlparse(self.connection_string)
            # parse query manually (asyncpg doesn't honor sslmode in DSN), fallback to require
            query = {}
            if parsed.query:
                for part in parsed.query.split('&'):
                    if not part:
                        continue
                    k, _, v = part.partition('=')
                    query[k] = v
            sslmode = (query.get('sslmode') or os.getenv('DB_SSLMODE') or 'require').lower()
            if sslmode in ('require', 'verify-none'):
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                ssl_ctx = ctx
            elif sslmode in ('verify-full', 'verify-ca'):
                cafile = os.getenv('DB_SSLROOTCERT')
                if cafile and os.path.exists(cafile):
                    ctx = ssl.create_default_context(cafile=cafile)
                else:
                    ctx = ssl.create_default_context()
                ctx.check_hostname = True
                ctx.verify_mode = ssl.CERT_REQUIRED
                ssl_ctx = ctx
            else:
                ssl_ctx = False
        except Exception as e:
            logger.warning(f"Не удалось настроить SSL контекст: {e}. Будет использована стандартная конфигурация.")
            ssl_ctx = None

        self.pool = await asyncpg.create_pool(
            dsn=self.connection_string,
            ssl=ssl_ctx,
            min_size=2,
            max_size=self.pool_size,
            command_timeout=30,
            init=self._init_connection
        )
        
        # Заполнение кэша символов
        await self._load_symbol_cache()
        logger.info(f"Загружено {len(self.symbol_cache)} символов в кэш")
        
    async def _load_symbol_cache(self):
        """Загрузка символов в кэш"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, symbol FROM marketdata.symbols WHERE is_active = true")
            self.symbol_cache = {row['symbol']: row['id'] for row in rows}

    async def _init_connection(self, conn: asyncpg.Connection):
        """Инициализация параметров сессии Postgres для инжестора."""
        try:
            # Жестко ограничим время выполнения и укажем имя приложения
            await conn.execute("SET LOCAL statement_timeout = '15s';")
            await conn.execute("SET LOCAL lock_timeout = '5s';")
            await conn.execute("SET LOCAL idle_in_transaction_session_timeout = '10s';")
            await conn.execute("SET LOCAL application_name = 'collector_ingestor';")
        except Exception:
            pass

    async def get_or_create_symbol_id(self, symbol: str) -> int:
        """Получение или создание ID символа (живая БД)."""
        if symbol in self.symbol_cache:
            return self.symbol_cache[symbol]

        if self.pool is None:
            raise RuntimeError("Database connection pool is not initialized (pool=None)")

        async with self.pool.acquire() as conn:
            try:
                symbol_id = await conn.fetchval(
                    """
                    INSERT INTO marketdata.symbols (exchange, symbol, base_asset, quote_asset)
                    VALUES ('binance-futures', $1, split_part($1, 'USDT', 1), 'USDT')
                    ON CONFLICT (exchange, symbol) 
                    DO UPDATE SET updated_at = NOW()
                    RETURNING id
                    """,
                    symbol,
                )

                if symbol_id is None:
                    # Символ уже существует, получаем его ID
                    symbol_id = await conn.fetchval(
                        "SELECT id FROM marketdata.symbols WHERE exchange = 'binance-futures' AND symbol = $1",
                        symbol,
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
        if self.pool is None:
            raise RuntimeError("Database connection pool is not initialized (pool=None)")

        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO marketdata.book_ticker 
                (ts_exchange, ts_ingest, symbol_id, update_id, best_bid, best_ask, bid_qty, ask_qty, spread, mid)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT DO NOTHING
                """,
                [
                    (
                        datetime.fromtimestamp(r['ts_exchange'] / 1000, tz=timezone.utc),
                        datetime.fromtimestamp(r['ts_ingest'] / 1000, tz=timezone.utc), 
                        r['symbol_id'],
                        r.get('update_id'),
                        r['best_bid'],
                        r['best_ask'],
                        r['bid_qty'],
                        r['ask_qty'],
                        float(r['best_ask']) - float(r['best_bid']),
                        (float(r['best_ask']) + float(r['best_bid'])) / 2.0,
                    )
                    for r in records
                ],
            )

    async def batch_insert_trades(self, records: List[Dict[str, Any]]):
        """Батчевая вставка trades записей"""
        if not records:
            return
        if self.pool is None:
            raise RuntimeError("Database connection pool is not initialized (pool=None)")

        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO marketdata.trades
                (ts_exchange, ts_ingest, symbol_id, agg_trade_id, price, qty, is_buyer_maker)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT DO NOTHING
                """,
                [
                    (
                        datetime.fromtimestamp(r['ts_exchange'] / 1000, tz=timezone.utc),
                        datetime.fromtimestamp(r['ts_ingest'] / 1000, tz=timezone.utc),
                        r['symbol_id'],
                        r['agg_trade_id'],
                        r['price'],
                        r['qty'],
                        r['is_buyer_maker'],
                    )
                    for r in records
                ],
            )

    async def batch_insert_depth_events(self, records: List[Dict[str, Any]]):
        """Батчевая вставка depth_events записей"""
        if not records:
            return
        if self.pool is None:
            raise RuntimeError("Database connection pool is not initialized (pool=None)")

        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO marketdata.depth_events
                (ts_exchange, ts_ingest, symbol_id, first_update_id, final_update_id, 
                 prev_final_update_id, bids, asks)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT DO NOTHING
                """,
                [
                    (
                        datetime.fromtimestamp(r['ts_exchange'] / 1000, tz=timezone.utc),
                        datetime.fromtimestamp(r['ts_ingest'] / 1000, tz=timezone.utc),
                        r['symbol_id'],
                        r['first_update_id'],
                        r['final_update_id'],
                        r.get('prev_final_update_id'),
                        json.dumps(r['bids']),
                        json.dumps(r['asks']),
                    )
                    for r in records
                ],
            )

    async def batch_insert_orderbook_topn(self, records: List[Dict[str, Any]]):
        """Батчевая вставка снимков topN (orderbook_topN)"""
        if not records:
            return
        if self.pool is None:
            raise RuntimeError("Database connection pool is not initialized (pool=None)")

        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO marketdata.orderbook_topN (
                    ts_exchange, symbol_id,
                    b1_price, b1_qty, b2_price, b2_qty, b3_price, b3_qty, b4_price, b4_qty, b5_price, b5_qty,
                    a1_price, a1_qty, a2_price, a2_qty, a3_price, a3_qty, a4_price, a4_qty, a5_price, a5_qty,
                    microprice, i1, i5, wall_size_bid, wall_size_ask, wall_dist_bid_bps, wall_dist_ask_bps, ofi_1s
                ) VALUES (
                    to_timestamp($1/1000.0), $2,
                    $3,$4,$5,$6,$7,$8,$9,$10,$11,$12,
                    $13,$14,$15,$16,$17,$18,$19,$20,$21,$22,
                    $23,$24,$25,$26,$27,$28,$29,$30
                )
                ON CONFLICT (symbol_id, ts_exchange) DO NOTHING
                """,
                [
                    (
                        r['ts_exchange'], r['symbol_id'],
                        r.get('b1_price'), r.get('b1_qty'), r.get('b2_price'), r.get('b2_qty'), r.get('b3_price'), r.get('b3_qty'),
                        r.get('b4_price'), r.get('b4_qty'), r.get('b5_price'), r.get('b5_qty'),
                        r.get('a1_price'), r.get('a1_qty'), r.get('a2_price'), r.get('a2_qty'), r.get('a3_price'), r.get('a3_qty'),
                        r.get('a4_price'), r.get('a4_qty'), r.get('a5_price'), r.get('a5_qty'),
                        r.get('microprice'), r.get('i1'), r.get('i5'), r.get('wall_size_bid'), r.get('wall_size_ask'),
                        r.get('wall_dist_bid_bps'), r.get('wall_dist_ask_bps'), r.get('ofi_1s'),
                    ) for r in records
                ]
            )

    async def close(self):
        """Закрытие пула соединений"""
        if self.pool:
            await self.pool.close()


class NullDatabaseManager(DatabaseManager):
    """Null-обработчик БД для локального dry-run: эмулирует интерфейс без подключений."""
    def __init__(self):
        # not calling super().__init__ on purpose, avoid pool setup
        self.pool = None
        self.symbol_cache: Dict[str, int] = {}
        self._id_seq = 1

    async def initialize(self):
        logger.info("DRY-RUN: БД не используется, записи не будут сохраняться")
        self.symbol_cache = {}

    async def _load_symbol_cache(self):
        # no-op for dry run
        return

    async def get_or_create_symbol_id(self, symbol: str) -> int:
        """Эфемерная выдача ID без обращений к БД."""
        sid = self.symbol_cache.get(symbol)
        if sid is None:
            sid = self._id_seq
            self._id_seq += 1
            self.symbol_cache[symbol] = sid
        return sid

    async def batch_insert_book_ticker(self, records: List[Dict[str, Any]]):
        if not records:
            return
        logger.info(f"DRY-RUN: book_ticker x{len(records)} (не сохраняем)")

    async def batch_insert_trades(self, records: List[Dict[str, Any]]):
        if not records:
            return
        logger.info(f"DRY-RUN: trades x{len(records)} (не сохраняем)")

    async def batch_insert_depth_events(self, records: List[Dict[str, Any]]):
        if not records:
            return
        logger.info(f"DRY-RUN: depth_events x{len(records)} (не сохраняем)")

    async def close(self):
        logger.info("DRY-RUN: закрывать нечего")

    async def batch_insert_orderbook_topn(self, records: List[Dict[str, Any]]):
        if not records:
            return
        logger.info(f"DRY-RUN: orderbook_topN x{len(records)} (не сохраняем)")
    
    async def batch_insert_book_ticker(self, records: List[Dict[str, Any]]):
        """Батчевая вставка book_ticker записей"""
        if not records:
            return
        if self.pool is None:
            if os.getenv('DRY_RUN', 'false').lower() in ('1', 'true', 'yes'):
                logger.info(f"DRY-RUN: book_ticker x{len(records)} (не сохраняем)")
                return
            raise RuntimeError("Database connection pool is not initialized (pool=None)")

        async with self.pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO marketdata.book_ticker 
                (ts_exchange, ts_ingest, symbol_id, update_id, best_bid, best_ask, bid_qty, ask_qty, spread, mid)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT DO NOTHING
            """, [
                (
                    datetime.fromtimestamp(r['ts_exchange'] / 1000, tz=timezone.utc),
                    datetime.fromtimestamp(r['ts_ingest'] / 1000, tz=timezone.utc), 
                    r['symbol_id'],
                    r.get('update_id'),
                    r['best_bid'],
                    r['best_ask'],
                    r['bid_qty'],
                    r['ask_qty'],
                    float(r['best_ask']) - float(r['best_bid']),
                    (float(r['best_ask']) + float(r['best_bid'])) / 2.0
                ) for r in records
            ])
            
    async def batch_insert_trades(self, records: List[Dict[str, Any]]):
        """Батчевая вставка trades записей"""
        if not records:
            return
        if self.pool is None:
            if os.getenv('DRY_RUN', 'false').lower() in ('1', 'true', 'yes'):
                logger.info(f"DRY-RUN: trades x{len(records)} (не сохраняем)")
                return
            raise RuntimeError("Database connection pool is not initialized (pool=None)")

        async with self.pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO marketdata.trades
                (ts_exchange, ts_ingest, symbol_id, agg_trade_id, price, qty, is_buyer_maker)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT DO NOTHING
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
        if self.pool is None:
            if os.getenv('DRY_RUN', 'false').lower() in ('1', 'true', 'yes'):
                logger.info(f"DRY-RUN: depth_events x{len(records)} (не сохраняем)")
                return
            raise RuntimeError("Database connection pool is not initialized (pool=None)")

        async with self.pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO marketdata.depth_events
                (ts_exchange, ts_ingest, symbol_id, first_update_id, final_update_id, 
                 prev_final_update_id, bids, asks)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT DO NOTHING
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
        # Инициализация TopNBuilder для реконструкции стакана
        self.topn_builder = None
        try:
            from collector.processing.topn_builder import TopNBuilder
            parsed = urlparse(self.ws_base_url)
            rest_host = f"https://{parsed.netloc}" if parsed.netloc else "https://fapi.binance.com"
            self.topn_builder = TopNBuilder(rest_base_url=rest_host)
            logger.info(f"TopNBuilder инициализирован, REST base: {rest_host}")
        except Exception as e:
            logger.warning(f"TopNBuilder не инициализирован: {e}")
        
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
                # Компактный лог подписок: общее количество и первые несколько примеров
                if len(streams) > 6:
                    sample = ", ".join(streams[:3] + ["..."] + streams[-3:])
                else:
                    sample = ", ".join(streams)
                logger.info(f"Шард {shard_id}: подписка на {len(streams)} stream(s): {sample}")
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
            # Параллельно строим top-5 снапшот
            if self.topn_builder is not None:
                try:
                    rec_topn = await self.topn_builder.process_event(symbol, data, symbol_id)
                    if rec_topn:
                        self.buffers[shard_id].orderbook_topn.append(rec_topn)
                except Exception as be:
                    logger.debug(f"TopNBuilder skip for {symbol}: {be}")
            
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
            if buffer.orderbook_topn:
                # Пишем после raw событий, но в той же пачке
                tasks.append(self.db_manager.batch_insert_orderbook_topn(buffer.orderbook_topn.copy()))
                
            if tasks:
                await asyncio.gather(*tasks)
                
                total_records = (
                    len(buffer.book_ticker) + len(buffer.trades) + len(buffer.depth_events) + len(buffer.orderbook_topn)
                )
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
    DRY_RUN = os.getenv('DRY_RUN', 'false').lower() in ('1', 'true', 'yes')
    
    # 200 основных торговых пар
    # Переопределение списка символов через ENV SYMBOLS (через запятую)
    env_symbols = os.getenv('SYMBOLS')
    if env_symbols:
        SYMBOLS = [s.strip().upper() for s in env_symbols.split(',') if s.strip()]
    else:
        SYMBOLS = [
            'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'SOLUSDT', 'XRPUSDT', 'DOTUSDT',
            'DOGEUSDT', 'AVAXUSDT', 'MATICUSDT', 'SHIBUSDT', 'LTCUSDT', 'TRXUSDT', 'UNIUSDT',
            'LINKUSDT', 'BCHUSDT', 'XLMUSDT', 'ATOMUSDT', 'ETCUSDT', 'FILUSDT', 'VETUSDT',
            'ICPUSDT', 'FTMUSDT', 'HBARUSDT', 'ALGOUSDT', 'THETAUSDT', 'XMRUSDT', 'EOSUSDT',
            'AAVEUSDT', 'MKRUSDT', 'KLAYUSDT', 'AXSUSDT', 'SANDUSDT', 'MANAUSDT', 'IOTAUSDT',
            # ... еще 165 символов
        ]
    
    # Переопределение каналов через ENV CHANNELS (через запятую)
    env_channels = os.getenv('CHANNELS')
    if env_channels:
        CHANNELS = [c.strip() for c in env_channels.split(',') if c.strip()]
    else:
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

    # Если DRY_RUN активен — подменим менеджер БД на NullDatabaseManager
    if DRY_RUN:
        ingestor.db_manager = NullDatabaseManager()
        logger.info("DRY-RUN активирован: PostgreSQL запись отключена")
    
    # Настройка graceful shutdown
    def signal_handler():
        logger.info("Получен сигнал SIGINT/SIGTERM")
        asyncio.create_task(shutdown(ingestor))
        
    signal.signal(signal.SIGINT, lambda s, f: signal_handler())
    signal.signal(signal.SIGTERM, lambda s, f: signal_handler())
    
    try:
        await ingestor.start()

        # Поддержка ограниченного по времени прогона через ENV DURATION_SECONDS
        duration = int(os.getenv('DURATION_SECONDS', '0'))
        if duration > 0:
            logger.info(f"Ограниченный прогон: {duration} сек")
            await asyncio.sleep(duration)
        else:
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