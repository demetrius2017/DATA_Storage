#!/usr/bin/env python3
"""
Docker Entrypoint для PostgreSQL OrderBook Collector
Инициализация базы данных и запуск сбора данных с 200 символами MM фокуса
"""

import asyncio
import os
import sys
import logging
import signal
import time
from pathlib import Path
from datetime import timedelta
import aiohttp
from typing import cast

# Добавляем корневую папку в PYTHONPATH
sys.path.insert(0, '/app')

from collector.config.symbols_mm_focused import SYMBOLS_200, validate_symbols
from collector.ingestion.batch_ingestor import BatchIngestor
from collector.monitoring.health_monitor import MonitoringSystem
from collector.database.connection import DatabaseConnection

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/app/logs/collector.log')
    ]
)
logger = logging.getLogger(__name__)

class ProductionCollector:
    """Главный класс для production развертывания"""
    
    def __init__(self):
        # Несколько инжесторов: основной (bt/tr) и опциональный для depth
        self.ingestors = []
        self.monitoring_system = None
        self.db_connection = None
        self.shutdown_event = asyncio.Event()
        self.active_symbols = []
        
        # Environment variables
        self.database_url = os.getenv('DATABASE_URL')
        self.batch_size = int(os.getenv('BATCH_SIZE', '500'))
        self.flush_interval = int(os.getenv('FLUSH_INTERVAL', '30'))
        self.shards = int(os.getenv('SHARDS', '5'))
        self.monitoring_port = int(os.getenv('MONITORING_PORT', '8000'))
        self.binance_base_url = os.getenv('BINANCE_BASE_URL', 'https://fapi.binance.com').strip()
        self.binance_ws_url = os.getenv('BINANCE_WS_URL', 'wss://fstream.binance.com/ws/').strip()
        # Управление количеством символов и стартовой точкой
        self.total_symbols_limit = None
        try:
            _lim = os.getenv('TOTAL_SYMBOLS', '').strip()
            if _lim:
                self.total_symbols_limit = max(0, int(_lim))
        except Exception:
            self.total_symbols_limit = None
        self.starting_symbol = os.getenv('STARTING_SYMBOL', 'SOLUSDT').strip().upper()
        # Depth настройки
        self.enable_depth = os.getenv('ENABLE_DEPTH', 'false').strip().lower() in ('1', 'true', 'yes')
        self.depth_top_symbols_env = os.getenv('DEPTH_TOP_SYMBOLS', '')
        # Доп. каналы markPrice/forceOrder (по умолчанию не включаем в этом процессе, можно запускать отдельным воркером)
        self.enable_mark_price = os.getenv('ENABLE_MARK_PRICE', 'false').strip().lower() in ('1','true','yes')
        self.enable_force_order = os.getenv('ENABLE_FORCE_ORDER', 'false').strip().lower() in ('1','true','yes')
        # Watchdog зависших запросов
        self.enable_db_watchdog = os.getenv('ENABLE_DB_WATCHDOG', 'true').strip().lower() in ('1','true','yes')
        try:
            self.db_watchdog_interval = int(os.getenv('DB_WATCHDOG_INTERVAL', '60'))  # сек
            self.db_watchdog_threshold = int(os.getenv('DB_WATCHDOG_THRESHOLD', '120'))  # сек
        except Exception:
            self.db_watchdog_interval = 60
            self.db_watchdog_threshold = 120
        
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable is required")
        # Для тайпчекера и дальнейшего использования как str
        self.database_url = cast(str, self.database_url)
    
    async def init_database(self):
        """Инициализация базы данных и создание схемы"""
        logger.info("🔧 Initializing database connection...")
        db_url: str = str(self.database_url)
        self.db_connection = DatabaseConnection(db_url)
        await self.db_connection.connect()
        
        # Создание схемы если не существует
        schema_file = Path('/app/collector/database/schema.sql')
        if schema_file.exists():
            logger.info("📋 Creating database schema...")
            try:
                with open(schema_file, 'r') as f:
                    schema_sql = f.read()
                # Понижаем lock_timeout на сессию, чтобы не зависать на конфликтующих объектах
                try:
                    await self.db_connection.execute_script("SET lock_timeout TO '5s';")
                except Exception:
                    pass
                await self.db_connection.execute_script(schema_sql)
                logger.info("✅ Database schema created successfully")
            except Exception as e:
                # Не фейлим весь запуск: схемы уже есть, ошибок блокировок достаточно для пропуска
                logger.warning(f"⚠️ Schema creation skipped due to error: {e}")

            # Доп. гарантия: уникальный индекс для поддержки ON CONFLICT на depth_events
            # В проде мог быть развёрнут ранний вариант без PK/unique — создаём idempotent-индекс
            try:
                ensure_idx_sql = (
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_depth_events_symbol_time_final
                    ON marketdata.depth_events (symbol_id, ts_exchange, final_update_id);
                    """
                )
                await self.db_connection.execute_script(ensure_idx_sql)
                logger.info("✅ Ensured unique index on marketdata.depth_events (symbol_id, ts_exchange, final_update_id)")
            except Exception as e:
                logger.error(f"❌ Failed to ensure unique index for depth_events: {e}")
        else:
            logger.warning("⚠️ Schema file not found, skipping schema creation")
    
    async def validate_symbols_config(self):
        """Валидация конфигурации символов"""
        logger.info("🎯 Validating Market Maker symbols configuration...")
        
        try:
            validate_symbols()
            logger.info(f"✅ Validated {len(SYMBOLS_200)} symbols for MM analysis")
            logger.info(f"📊 Starting with: {SYMBOLS_200[0]}")
            logger.info(f"📊 Ultra low-cap symbols: {len(SYMBOLS_200[-30:])}")

            # Фильтрация по реально доступным Binance Futures USDT-перпам
            # Сначала фильтруем кандидатов по доступности на Binance Futures
            resolved = await self._resolve_futures_symbols(SYMBOLS_200)
            logger.info(f"✅ Resolved {len(resolved)} valid Futures symbols out of {len(SYMBOLS_200)}")
            # Порядок: используем исходный порядок SYMBOLS_200 (убывание ликвидности),
            # но ротируем так, чтобы STARTING_SYMBOL был первым, а далее — менее ликвидные
            base_order = [s for s in SYMBOLS_200 if s in set(resolved)]
            if self.starting_symbol in base_order:
                idx = base_order.index(self.starting_symbol)
                ordered = base_order[idx:] + base_order[:idx]
            else:
                ordered = base_order
            # Лимит количества символов TOTAL_SYMBOLS (если указан)
            if self.total_symbols_limit and self.total_symbols_limit > 0:
                self.active_symbols = ordered[: self.total_symbols_limit]
            else:
                self.active_symbols = ordered
            logger.info(
                f"📊 Active symbols configured: {len(self.active_symbols)} (start='{self.starting_symbol}', limit={self.total_symbols_limit})"
            )
            if len(self.active_symbols) < len(SYMBOLS_200):
                missing = len(SYMBOLS_200) - len(self.active_symbols)
                logger.warning(f"⚠️ Filtered out {missing} symbols not present on Binance Futures USDT-perp")
        except Exception as e:
            logger.error(f"❌ Symbol validation failed: {e}")
            raise

    async def _resolve_futures_symbols(self, candidates):
        """Запросить список доступных USDT-перпетуальных символов на Binance Futures и отфильтровать кандидатов."""
        base = self.binance_base_url.rstrip('/')
        url = f"{base}/fapi/v1/exchangeInfo"
        timeout = aiohttp.ClientTimeout(total=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    symbols = data.get('symbols', [])
                    allowed = set(
                        s.get('symbol') for s in symbols
                        if s.get('contractType') in ('PERPETUAL', 'CURRENT_QUARTER', 'NEXT_QUARTER')
                        and s.get('status') == 'TRADING'
                        and s.get('quoteAsset') == 'USDT'
                    )
                    filtered = [sym for sym in candidates if sym in allowed]
                    return filtered
        except Exception as e:
            logger.error(f"❌ Failed to resolve futures symbols from {url}: {e}. Fallback to original list.")
            return list(candidates)
    
    async def start_batch_ingestores(self):
        """Запуск batch инжесторов: основной (bt/tr) + depth@100ms для всех активных символов по умолчанию.

        Политика:
        - Если ENABLE_DEPTH=false → depth не запускаем.
        - Если DEPTH_TOP_SYMBOLS непустой → используем его как явный override (фильтруем по active_symbols), иначе берём все active_symbols.
        - Это убирает скрытое ограничение «только топ-10»: теперь по умолчанию собирается FULL DATA по всем включённым символам.
        """
        logger.info("🚀 Starting PostgreSQL batch ingestors...")
        logger.info(f"🌐 Binance REST: {self.binance_base_url}")
        logger.info(f"🌐 Binance WS:   {self.binance_ws_url}")

        # 1) Основной инжестор: bookTicker + aggTrade для всех активных символов
        channels_main = ['bookTicker', 'aggTrade']
        symbols_main = self.active_symbols if self.active_symbols else SYMBOLS_200
        db_url: str = str(self.database_url)
        main_ingestor = BatchIngestor(
            db_connection_string=db_url,
            symbols=symbols_main,
            channels=channels_main,
            shards_count=self.shards,
            ws_base_url=self.binance_ws_url,
        )
        self.ingestors.append(main_ingestor)
        asyncio.create_task(main_ingestor.start())
        logger.info(f"✅ Main ingestor (bt/tr) started with {len(symbols_main)} symbols")

    # 2) Depth-инжестор: diff depth@100ms для всех активных символов по умолчанию (FULL DATA)
        if self.enable_depth:
            # FULL DATA по всем активным символам: игнорируем DEPTH_TOP_SYMBOLS, чтобы не было скрытых ограничений
            depth_symbols = list(self.active_symbols) if self.active_symbols else list(SYMBOLS_200)

            if depth_symbols:
                db_url: str = str(self.database_url)
                # Шардирование: 1 шард на каждые ~20 символов, минимум 1, максимум 5
                shards_for_depth = max(1, min(5, (len(depth_symbols) + 19) // 20))
                depth_ingestor = BatchIngestor(
                    db_connection_string=db_url,
                    symbols=depth_symbols,
                    channels=['depth@100ms'],
                    shards_count=shards_for_depth,
                    ws_base_url=self.binance_ws_url,
                )
                self.ingestors.append(depth_ingestor)
                asyncio.create_task(depth_ingestor.start())
                logger.info(f"🧊 Depth ingestor started for {len(depth_symbols)} symbols (FULL DATA, shards={shards_for_depth})")
            else:
                logger.warning("ENABLE_DEPTH=true, но список depth символов пуст — depth не запущен")

        # 3) Опционально: отдельный multi-stream воркер для markPrice/forceOrder
        # Чтобы избежать дублирования, в этом воркере отключаем base-каналы и depth.
        if self.enable_mark_price or self.enable_force_order:
            try:
                os.environ.setdefault('ENABLE_BOOK_TICKER', 'false')
                os.environ.setdefault('ENABLE_AGG_TRADE', 'false')
                os.environ.setdefault('ENABLE_DEPTH_TOP', 'false')
                os.environ['ENABLE_MARK_PRICE'] = 'true' if self.enable_mark_price else 'false'
                os.environ['ENABLE_FORCE_ORDER'] = 'true' if self.enable_force_order else 'false'
                from collector.ingestion.multi_stream_collector import MultiStreamCollector
                ms = MultiStreamCollector(db_url, batch_size=200)
                self.ingestors.append(ms)  # для унифицированного shutdown
                asyncio.create_task(ms.initialize())
                asyncio.create_task(ms.start())
                logger.info(f"🏷️ MultiStream worker started (markPrice={self.enable_mark_price}, forceOrder={self.enable_force_order})")
            except Exception as e:
                logger.error(f"❌ Failed to start MultiStream worker for mark/force: {e}")
    
    async def start_health_monitor(self):
        """Запуск health monitoring dashboard"""
        logger.info("📊 Starting health monitoring dashboard...")
        
        # Используем MonitoringSystem, который поднимает aiohttp dashboard с /health
        self.monitoring_system = MonitoringSystem(
            db_connection_string=str(self.database_url),
            dashboard_port=self.monitoring_port
        )
        
        # Запуск в background task
        asyncio.create_task(self.monitoring_system.start())
        logger.info(f"✅ Monitoring system started on port {self.monitoring_port}")

        # Запускаем watchdog для зависших запросов в БД
        if self.enable_db_watchdog:
            asyncio.create_task(self._db_watchdog())
            logger.info(
                f"🛡️ DB watchdog enabled: interval={self.db_watchdog_interval}s, threshold={self.db_watchdog_threshold}s"
            )

    async def _db_watchdog(self):
        """Периодически проверяет pg_stat_activity и отменяет висячие запросы > threshold."""
        while True:
            try:
                import asyncpg, ssl
                from urllib.parse import urlparse
                # Настроим ssl как в init_database
                ssl_ctx = None
                try:
                    parsed = urlparse(self.database_url)
                    query = {}
                    qstr = str(getattr(parsed, 'query', '') or '')
                    if qstr:
                        for part in qstr.split("&"):
                            if not part:
                                continue
                            if "=" in part:
                                k, v = part.split("=", 1)
                            else:
                                k, v = part, ''
                            query[k] = v
                    sslmode = (query.get('sslmode') or 'require').lower()
                    if sslmode in ('disable', 'allow', 'prefer'):
                        ssl_ctx = False
                    elif sslmode in ('require','verify-none'):
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                        ssl_ctx = ctx
                    elif sslmode in ('verify-full','verify-ca'):
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = True
                        ctx.verify_mode = ssl.CERT_REQUIRED
                        ssl_ctx = ctx
                except Exception:
                    ssl_ctx = None

                conn = await asyncpg.connect(self.database_url, ssl=ssl_ctx)
                try:
                    # Находим активные запросы, висящие дольше threshold, исключая системные/наш мониторинг
                    rows = await conn.fetch(
                        """
                        SELECT pid, now() - query_start AS duration, state, application_name, query
                        FROM pg_stat_activity
                        WHERE datname = current_database()
                          AND state = 'active'
                          AND now() - query_start > $1::interval
                          AND application_name NOT IN ('collector_monitor')
                          AND query NOT ILIKE '%pg_stat_activity%'
                        ORDER BY duration DESC
                        LIMIT 20
                        """,
                        timedelta(seconds=self.db_watchdog_threshold),
                    )
                    for r in rows:
                        pid = r['pid']
                        dur = r['duration']
                        app = r['application_name']
                        logger.warning(f"⚠️ Cancelling long-running query pid={pid}, app='{app}', duration={dur}")
                        try:
                            await conn.execute("SELECT pg_cancel_backend($1)", pid)
                        except Exception as ce:
                            logger.error(f"❌ Failed to cancel pid={pid}: {ce}")
                finally:
                    await conn.close()
            except Exception as e:
                logger.error(f"DB watchdog error: {e}")
            await asyncio.sleep(self.db_watchdog_interval)
    
    async def wait_for_shutdown(self):
        """Ожидание сигнала на завершение"""
        def signal_handler(signum, frame):
            logger.info(f"📡 Received signal {signum}, initiating shutdown...")
            self.shutdown_event.set()
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        await self.shutdown_event.wait()
    
    async def cleanup(self):
        """Graceful shutdown всех компонентов"""
        logger.info("🔄 Starting graceful shutdown...")
        
        tasks = []
        # Останавливаем все инжесторы
        for ing in self.ingestors:
            try:
                tasks.append(ing.stop())
            except Exception:
                pass
        
        if self.monitoring_system:
            tasks.append(self.monitoring_system.stop())
        
        if self.db_connection:
            tasks.append(self.db_connection.close())
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info("✅ Cleanup completed")
    
    async def run(self):
        """Главный цикл приложения"""
        try:
            logger.info("🚀 Starting PostgreSQL OrderBook Collector (Production)")
            logger.info(f"🎯 Market Maker Analysis Focus: {len(SYMBOLS_200)} symbols")
            
            # Инициализация
            await self.validate_symbols_config()
            await self.init_database()
            
            # Запуск компонентов
            await self.start_batch_ingestores()
            await self.start_health_monitor()
            
            logger.info("🎉 All components started successfully!")
            logger.info(f"📊 Monitoring: http://localhost:{self.monitoring_port}/health")
            logger.info("🔄 Press Ctrl+C to stop")
            
            # Ожидание завершения
            await self.wait_for_shutdown()
            
        except Exception as e:
            logger.error(f"💥 Fatal error: {e}")
            sys.exit(1)
        finally:
            await self.cleanup()

async def main():
    """Entrypoint для Docker контейнера"""
    # Создание необходимых директорий
    os.makedirs('/app/logs', exist_ok=True)
    os.makedirs('/app/data', exist_ok=True)
    
    # Ожидание доступности PostgreSQL
    logger.info("⏳ Waiting for PostgreSQL to be ready...")
    for attempt in range(30):
        try:
            # Простая проверка доступности БД
            import asyncpg, ssl
            from urllib.parse import urlparse
            database_url = os.getenv('DATABASE_URL')
            # Honor sslmode=require for DO Postgres
            ssl_ctx = None
            try:
                parsed = urlparse(database_url or '')
                query = {}
                if parsed and parsed.query:
                    for part in parsed.query.split('&'):
                        if not part:
                            continue
                        k, _, v = part.partition('=')
                        query[k] = v
                sslmode = (query.get('sslmode') or 'require').lower()
                if sslmode in ('disable', 'allow', 'prefer'):
                    ssl_ctx = False
                elif sslmode in ('require', 'verify-none'):
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    ssl_ctx = ctx
                elif sslmode in ('verify-full', 'verify-ca'):
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = True
                    ctx.verify_mode = ssl.CERT_REQUIRED
                    ssl_ctx = ctx
            except Exception:
                ssl_ctx = None
            conn = await asyncpg.connect(database_url, ssl=ssl_ctx)
            await conn.close()
            logger.info("✅ PostgreSQL is ready!")
            break
        except Exception as e:
            if attempt == 29:
                logger.error(f"❌ PostgreSQL not available after 30 attempts: {e}")
                sys.exit(1)
            # Периодически печатаем причину, чтобы упростить диагностику (например, firewall/SSL)
            if attempt == 0 or (attempt + 1) % 5 == 0:
                logger.warning(f"⏳ Attempt {attempt + 1}/30: PostgreSQL not ready: {e}")
            else:
                logger.info(f"⏳ Attempt {attempt + 1}/30: PostgreSQL not ready, waiting...")
            time.sleep(2)
    
    # Запуск collector
    collector = ProductionCollector()
    await collector.run()

if __name__ == "__main__":
    asyncio.run(main())