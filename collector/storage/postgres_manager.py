"""
🗄️ PostgreSQL Manager для OrderBook Collector
Асинхронное управление данными orderbook в PostgreSQL с connection pooling
"""

import asyncio
import asyncpg
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import os
from contextlib import asynccontextmanager
import ssl

@dataclass
class OrderBookData:
    """Структура данных orderbook для хранения в PostgreSQL"""
    symbol: str
    timestamp: float
    event_time: int
    first_update_id: int
    final_update_id: int
    bids: List[List[str]]
    asks: List[List[str]]
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь для JSON"""
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp,
            'event_time': self.event_time,
            'first_update_id': self.first_update_id,
            'final_update_id': self.final_update_id,
            'bids': self.bids,
            'asks': self.asks
        }

class PostgreSQLManager:
    """
    Менеджер PostgreSQL для OrderBook данных
    Поддерживает connection pooling, batch операции и мониторинг
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.pool: Optional[asyncpg.Pool] = None
        self.logger = logging.getLogger(__name__)
        self._batch_buffer: List[OrderBookData] = []
        self._batch_size = config.get('batch_size', 100)
        self._flush_interval = config.get('flush_interval', 5)
        self._last_flush = datetime.now()
        self._stats = {
            'total_inserts': 0,
            'batch_inserts': 0,
            'failed_inserts': 0,
            'connection_errors': 0,
            'last_insert_time': None
        }
        
    async def initialize(self) -> bool:
        """Инициализация connection pool и создание таблиц"""
        try:
            self.logger.info("🔌 Инициализация PostgreSQL connection pool...")
            
            # Параметры подключения
            # SSL configuration according to sslmode
            sslmode = (
                self.config.get('sslmode')
                or os.getenv('DB_SSLMODE')
                or 'require'
            ).lower()

            ssl_context: ssl.SSLContext | bool
            if sslmode in ('disable', 'allow', 'prefer'):
                # allow unencrypted (not recommended); here we set False to let asyncpg decide
                ssl_context = False
            elif sslmode in ('require', 'verify-none'):
                # Encrypt without verifying server cert (closest to libpq require)
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                ssl_context = ctx
            elif sslmode in ('verify-full', 'verify-ca'):
                # Strict verification using system CAs (or custom CA via SSLROOTCERT)
                cafile = os.getenv('DB_SSLROOTCERT')
                if cafile and os.path.exists(cafile):
                    ctx = ssl.create_default_context(cafile=cafile)
                else:
                    ctx = ssl.create_default_context()
                ctx.check_hostname = True
                ctx.verify_mode = ssl.CERT_REQUIRED
                ssl_context = ctx
            else:
                # Fallback to require semantics
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                ssl_context = ctx

            connection_params = {
                'host': self.config['host'],
                'port': self.config['port'],
                'database': self.config['name'],
                'user': self.config['user'],
                'password': self.config['password'],
                'ssl': ssl_context,
                'min_size': max(1, self.config.get('pool_size', 20) // 10),  # Минимум 1, максимум pool_size/10
                'max_size': self.config.get('pool_size', 20),
                'command_timeout': self.config.get('pool_timeout', 60),  # Увеличил таймаут
                'server_settings': {
                    'jit': 'off',  # Отключаем JIT для стабильности
                    'application_name': 'orderbook_collector'
                }
            }
            
            # Создание pool
            self.pool = await asyncpg.create_pool(**connection_params)
            
            # Тест подключения
            async with self.pool.acquire() as conn:
                version = await conn.fetchval('SELECT version()')
                self.logger.info(f"✅ PostgreSQL подключен: {version}")
            
            # Создание схемы данных
            await self._create_schema()
            
            self.logger.info("🎯 PostgreSQL Manager готов к работе")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка инициализации PostgreSQL: {e}")
            self._stats['connection_errors'] += 1
            return False
    
    async def _create_schema(self):
        """Создание таблиц и индексов для orderbook данных"""
        
        schema_sql = """
        -- Основная таблица orderbook данных
        CREATE TABLE IF NOT EXISTS orderbook_data (
            id BIGSERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            timestamp DOUBLE PRECISION NOT NULL,
            event_time BIGINT NOT NULL,
            first_update_id BIGINT NOT NULL,
            final_update_id BIGINT NOT NULL,
            bids JSONB NOT NULL,
            asks JSONB NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            
            -- Индексы для быстрого поиска
            CONSTRAINT unique_symbol_update_id UNIQUE (symbol, final_update_id)
        );
        
        -- Индексы для производительности
        CREATE INDEX IF NOT EXISTS idx_orderbook_symbol_timestamp 
        ON orderbook_data (symbol, timestamp DESC);
        
        CREATE INDEX IF NOT EXISTS idx_orderbook_timestamp 
        ON orderbook_data (timestamp DESC);
        
        CREATE INDEX IF NOT EXISTS idx_orderbook_symbol_event_time 
        ON orderbook_data (symbol, event_time DESC);
        
        -- Индекс для удаления старых данных
        CREATE INDEX IF NOT EXISTS idx_orderbook_created_at 
        ON orderbook_data (created_at);
        
        -- Статистическая таблица для мониторинга
        CREATE TABLE IF NOT EXISTS collection_stats (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            records_count BIGINT DEFAULT 0,
            last_update TIMESTAMP DEFAULT NOW(),
            avg_records_per_minute DOUBLE PRECISION DEFAULT 0,
            
            CONSTRAINT unique_symbol_stats UNIQUE (symbol)
        );
        """
        
        async with self.pool.acquire() as conn:
            await conn.execute(schema_sql)
            self.logger.info("✅ Схема PostgreSQL создана/обновлена")
    
    async def store_orderbook(self, data: OrderBookData) -> bool:
        """Сохранение orderbook данных (добавление в batch buffer)"""
        try:
            # Добавляем в буфер
            self._batch_buffer.append(data)
            
            # Проверяем условия для flush
            should_flush = (
                len(self._batch_buffer) >= self._batch_size or
                (datetime.now() - self._last_flush).seconds >= self._flush_interval
            )
            
            if should_flush:
                await self._flush_batch()
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка сохранения orderbook: {e}")
            self._stats['failed_inserts'] += 1
            return False
    
    async def _flush_batch(self) -> bool:
        """Массовая вставка данных из буфера в PostgreSQL"""
        if not self._batch_buffer:
            return True
        if not self.pool:
            self.logger.error("❌ Ошибка batch flush: connection pool is not initialized")
            # do not drop data silently; keep in buffer for later retry
            return False
        
        try:
            self.logger.debug(f"📦 Flush batch: {len(self._batch_buffer)} записей")
            
            # Подготовка данных для batch insert
            records = []
            for data in self._batch_buffer:
                records.append((
                    data.symbol,
                    data.timestamp,
                    data.event_time,
                    data.first_update_id,
                    data.final_update_id,
                    json.dumps(data.bids),
                    json.dumps(data.asks)
                ))
            
            # Batch INSERT с ON CONFLICT
            insert_sql = """
                INSERT INTO orderbook_data (
                    symbol, timestamp, event_time, first_update_id, 
                    final_update_id, bids, asks
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (symbol, final_update_id) DO NOTHING
            """
            
            async with self.pool.acquire() as conn:
                # Выполняем batch insert
                await conn.executemany(insert_sql, records)
                
                # Обновляем статистику
                await self._update_stats(conn, len(records))
            
            # Обновляем внутреннюю статистику
            self._stats['total_inserts'] += len(records)
            self._stats['batch_inserts'] += 1
            self._stats['last_insert_time'] = datetime.now()
            
            # Очищаем буфер
            self._batch_buffer.clear()
            self._last_flush = datetime.now()
            
            self.logger.debug(f"✅ Batch flush завершен: {len(records)} записей")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка batch flush: {e}")
            self._stats['failed_inserts'] += len(self._batch_buffer)
            self._batch_buffer.clear()  # Очищаем буфер даже при ошибке
            return False
    
    async def _update_stats(self, conn: asyncpg.Connection, records_count: int):
        """Обновление статистики в базе данных"""
        try:
            # Группируем записи по символам
            symbol_counts = {}
            for data in self._batch_buffer[-records_count:]:
                symbol_counts[data.symbol] = symbol_counts.get(data.symbol, 0) + 1
            
            # Обновляем статистику для каждого символа
            for symbol, count in symbol_counts.items():
                await conn.execute("""
                    INSERT INTO collection_stats (symbol, records_count, last_update)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (symbol) DO UPDATE SET
                        records_count = collection_stats.records_count + $2,
                        last_update = NOW()
                """, symbol, count)
            
        except Exception as e:
            self.logger.error(f"⚠️ Ошибка обновления статистики: {e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Получение статистики работы"""
        try:
            stats = self._stats.copy()
            
            if self.pool:
                async with self.pool.acquire() as conn:
                    # Общая статистика
                    total_records = await conn.fetchval(
                        "SELECT SUM(records_count) FROM collection_stats"
                    ) or 0
                    
                    # Статистика по символам
                    symbol_stats = await conn.fetch("""
                        SELECT symbol, records_count, last_update,
                               avg_records_per_minute
                        FROM collection_stats
                        ORDER BY records_count DESC
                    """)
                    
                    stats.update({
                        'total_records_in_db': total_records,
                        'symbols_stats': [dict(row) for row in symbol_stats],
                        'buffer_size': len(self._batch_buffer),
                        'pool_size': self.pool.get_size(),
                        'pool_idle': self.pool.get_idle_size()
                    })
            
            return stats
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения статистики: {e}")
            return self._stats.copy()
    
    async def get_recent_data(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Получение последних данных orderbook для символа"""
        try:
            async with self.pool.acquire() as conn:
                records = await conn.fetch("""
                    SELECT symbol, timestamp, event_time, first_update_id,
                           final_update_id, bids, asks, created_at
                    FROM orderbook_data
                    WHERE symbol = $1
                    ORDER BY timestamp DESC
                    LIMIT $2
                """, symbol, limit)
                
                return [
                    {
                        'symbol': row['symbol'],
                        'timestamp': row['timestamp'],
                        'event_time': row['event_time'],
                        'first_update_id': row['first_update_id'],
                        'final_update_id': row['final_update_id'],
                        'bids': json.loads(row['bids']),
                        'asks': json.loads(row['asks']),
                        'created_at': row['created_at'].isoformat()
                    }
                    for row in records
                ]
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения данных для {symbol}: {e}")
            return []
    
    async def cleanup_old_data(self, retention_days: int = 30) -> int:
        """Очистка старых данных"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute("""
                    DELETE FROM orderbook_data
                    WHERE created_at < NOW() - INTERVAL '%s days'
                """, retention_days)
                
                deleted_count = int(result.split()[-1])
                self.logger.info(f"🧹 Удалено {deleted_count} старых записей (>{retention_days} дней)")
                return deleted_count
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка очистки данных: {e}")
            return 0
    
    async def health_check(self) -> Dict[str, bool]:
        """Проверка состояния PostgreSQL соединения"""
        health = {
            'pool_connected': False,
            'database_accessible': False,
            'schema_valid': False
        }
        
        try:
            if self.pool:
                health['pool_connected'] = True
                
                async with self.pool.acquire() as conn:
                    # Тест базового запроса
                    await conn.fetchval('SELECT 1')
                    health['database_accessible'] = True
                    
                    # Проверка существования таблиц
                    tables_exist = await conn.fetchval("""
                        SELECT COUNT(*) FROM information_schema.tables
                        WHERE table_name IN ('orderbook_data', 'collection_stats')
                    """)
                    health['schema_valid'] = (tables_exist == 2)
            
        except Exception as e:
            self.logger.error(f"❌ Health check failed: {e}")
        
        return health
    
    async def force_flush(self) -> bool:
        """Принудительная запись буфера в базу"""
        return await self._flush_batch()
    
    async def close(self):
        """Закрытие соединений и финальный flush"""
        try:
            # Финальный flush данных
            if self._batch_buffer:
                await self._flush_batch()
            
            # Закрытие pool
            if self.pool:
                await self.pool.close()
                self.logger.info("🔌 PostgreSQL pool закрыт")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка закрытия PostgreSQL: {e}")

    @asynccontextmanager
    async def transaction(self):
        """Контекстный менеджер для транзакций"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                yield conn

# Utility functions
def create_orderbook_data(symbol: str, raw_data: Dict[str, Any]) -> OrderBookData:
    """Создание OrderBookData из сырых данных Binance"""
    return OrderBookData(
        symbol=symbol,
        timestamp=raw_data.get('E', 0) / 1000.0,  # Event time в секундах
        event_time=raw_data.get('E', 0),
        first_update_id=raw_data.get('U', 0),
        final_update_id=raw_data.get('u', 0),
        bids=raw_data.get('b', []),
        asks=raw_data.get('a', [])
    )

async def test_postgres_manager():
    """Тестирование PostgreSQL Manager"""
    from dotenv import load_dotenv
    load_dotenv()
    
    config = {
        'host': os.getenv('DB_HOST'),
        'port': int(os.getenv('DB_PORT', 25060)),
        'name': os.getenv('DB_NAME'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'batch_size': 10,
        'flush_interval': 2,
        'pool_size': 5
    }
    
    manager = PostgreSQLManager(config)
    
    try:
        # Инициализация
        await manager.initialize()
        
        # Тестовые данные
        test_data = OrderBookData(
            symbol='BTCUSDT',
            timestamp=datetime.now().timestamp(),
            event_time=int(datetime.now().timestamp() * 1000),
            first_update_id=12345,
            final_update_id=12346,
            bids=[['50000.00', '0.1'], ['49999.99', '0.2']],
            asks=[['50000.01', '0.15'], ['50000.02', '0.25']]
        )
        
        # Сохранение данных
        await manager.store_orderbook(test_data)
        await manager.force_flush()
        
        # Проверка статистики
        stats = await manager.get_stats()
        print(f"📊 Статистика: {stats}")
        
        # Health check
        health = await manager.health_check()
        print(f"🏥 Health: {health}")
        
        print("✅ PostgreSQL Manager тест прошел успешно!")
        
    finally:
        await manager.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_postgres_manager())