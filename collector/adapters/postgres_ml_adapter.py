"""
PostgreSQL Data Adapter for ML Pipeline Integration
Заменяет Parquet файлы на прямые запросы к PostgreSQL для "вчерашнего" обучения
"""

import asyncio
import asyncpg
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta, timezone
from typing import List, Optional, Dict, Any, Tuple
import logging
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)

@dataclass
class SymbolConfig:
    """Конфигурация символа для ML"""
    symbol: str
    symbol_id: int
    base_asset: str
    quote_asset: str
    is_active: bool

class PostgresMLAdapter:
    """
    Адаптер PostgreSQL для ML pipeline
    Обеспечивает совместимость с существующим кодом, заменяя Parquet на PostgreSQL
    """
    
    def __init__(self, connection_string: str, pool_size: int = 5):
        self.connection_string = connection_string
        self.pool_size = pool_size
        self.pool: Optional[asyncpg.Pool] = None
        self.symbols_cache: Dict[str, SymbolConfig] = {}
        
    async def initialize(self):
        """Инициализация подключения и кэширование символов"""
        logger.info("Инициализация PostgreSQL ML адаптера...")
        
        self.pool = await asyncpg.create_pool(
            self.connection_string,
            min_size=1,
            max_size=self.pool_size,
            command_timeout=60
        )
        
        await self._load_symbols_cache()
        logger.info(f"Загружено {len(self.symbols_cache)} символов")
        
    async def _load_symbols_cache(self):
        """Загрузка символов в кэш"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, symbol, base_asset, quote_asset, is_active 
                FROM marketdata.symbols 
                WHERE is_active = true
                ORDER BY symbol
            """)
            
            for row in rows:
                self.symbols_cache[row['symbol']] = SymbolConfig(
                    symbol=row['symbol'],
                    symbol_id=row['id'],
                    base_asset=row['base_asset'],
                    quote_asset=row['quote_asset'],
                    is_active=row['is_active']
                )
    
    async def get_yesterday_training_data(self, 
                                        symbols: List[str] = None,
                                        target_date: date = None) -> pd.DataFrame:
        """
        Получение данных за указанную дату для обучения ML
        Заменяет загрузку из Parquet файлов
        """
        if target_date is None:
            target_date = date.today() - timedelta(days=1)
            
        logger.info(f"Загрузка данных за {target_date} для символов: {symbols}")
        
        symbol_ids = None
        if symbols:
            symbol_ids = [self.symbols_cache[s].symbol_id for s in symbols if s in self.symbols_cache]
            
        async with self.pool.acquire() as conn:
            query = """
            SELECT 
                bt.ts_second,
                s.symbol,
                bt.symbol_id,
                bt.mid_open,
                bt.mid_high,
                bt.mid_low, 
                bt.mid_close,
                bt.spread_mean,
                bt.spread_min,
                bt.spread_max,
                bt.spread_std,
                bt.total_qty_mean,
                bt.update_count,
                bt.avg_latency_ms,
                
                -- Trade данные (если есть)
                COALESCE(tr.trade_count, 0) as trade_count,
                COALESCE(tr.vol_sum, 0) as volume,
                COALESCE(tr.vwap, bt.mid_close) as vwap,
                COALESCE(tr.buy_vol, 0) as buy_volume,
                COALESCE(tr.sell_vol, 0) as sell_volume,
                
                -- Производные фичи
                CASE 
                    WHEN tr.buy_vol + tr.sell_vol > 0 
                    THEN (tr.buy_vol - tr.sell_vol) / (tr.buy_vol + tr.sell_vol)
                    ELSE 0 
                END as buy_sell_imbalance,
                
                EXTRACT(EPOCH FROM bt.ts_second) as timestamp,
                EXTRACT(HOUR FROM bt.ts_second) as hour,
                EXTRACT(DOW FROM bt.ts_second) as day_of_week
                
            FROM marketdata.bt_1s bt
            LEFT JOIN marketdata.trade_1s tr ON (
                bt.ts_second = tr.ts_second AND 
                bt.symbol_id = tr.symbol_id
            )
            JOIN marketdata.symbols s ON bt.symbol_id = s.id
            WHERE 
                bt.ts_second >= $1::DATE 
                AND bt.ts_second < ($1::DATE + INTERVAL '1 day')
                AND ($2::BIGINT[] IS NULL OR bt.symbol_id = ANY($2))
                AND s.is_active = true
            ORDER BY bt.symbol_id, bt.ts_second
            """
            
            rows = await conn.fetch(query, target_date, symbol_ids)
            
        if not rows:
            logger.warning(f"Нет данных за {target_date}")
            return pd.DataFrame()
            
        df = pd.DataFrame(rows)
        logger.info(f"Загружено {len(df)} записей за {target_date}")
        
        return df
    
    async def get_features_for_ml(self, 
                                symbols: List[str],
                                start_date: date,
                                end_date: date,
                                include_depth: bool = False) -> pd.DataFrame:
        """
        Получение фичей для ML обучения за период
        Аналог существующих feature engineering pipeline
        """
        logger.info(f"Загрузка фичей за {start_date} - {end_date}")
        
        symbol_ids = [self.symbols_cache[s].symbol_id for s in symbols if s in self.symbols_cache]
        
        async with self.pool.acquire() as conn:
            # Базовые фичи из aggregates
            base_query = """
            WITH hourly_stats AS (
                SELECT 
                    date_trunc('hour', bt.ts_second) as hour_bucket,
                    bt.symbol_id,
                    s.symbol,
                    
                    -- OHLC
                    FIRST(bt.mid_open, bt.ts_second) as h_open,
                    MAX(bt.mid_high) as h_high,
                    MIN(bt.mid_low) as h_low,
                    LAST(bt.mid_close, bt.ts_second) as h_close,
                    
                    -- Volume & activity
                    SUM(COALESCE(tr.vol_sum, 0)) as h_volume,
                    AVG(bt.spread_mean) as h_avg_spread,
                    STDDEV(bt.mid_close) as h_volatility,
                    SUM(bt.update_count) as h_updates,
                    
                    -- Trade balance
                    SUM(COALESCE(tr.buy_vol, 0)) as h_buy_vol,
                    SUM(COALESCE(tr.sell_vol, 0)) as h_sell_vol
                    
                FROM marketdata.bt_1s bt
                LEFT JOIN marketdata.trade_1s tr ON (
                    bt.ts_second = tr.ts_second AND bt.symbol_id = tr.symbol_id
                )
                JOIN marketdata.symbols s ON bt.symbol_id = s.id
                WHERE 
                    bt.ts_second >= $1::DATE
                    AND bt.ts_second < ($2::DATE + INTERVAL '1 day')
                    AND bt.symbol_id = ANY($3)
                GROUP BY hour_bucket, bt.symbol_id, s.symbol
            )
            SELECT 
                hour_bucket,
                symbol_id,
                symbol,
                h_open, h_high, h_low, h_close,
                h_volume,
                h_avg_spread,
                h_volatility,
                h_updates,
                
                -- Returns
                (h_close - h_open) / h_open as h_return,
                (h_high - h_low) / h_open as h_range,
                
                -- Volume features  
                CASE WHEN h_buy_vol + h_sell_vol > 0 
                     THEN h_buy_vol / (h_buy_vol + h_sell_vol) 
                     ELSE 0.5 END as h_buy_ratio,
                     
                -- Lag features (previous hour)
                LAG(h_close, 1) OVER (PARTITION BY symbol_id ORDER BY hour_bucket) as prev_h_close,
                LAG(h_volume, 1) OVER (PARTITION BY symbol_id ORDER BY hour_bucket) as prev_h_volume,
                
                EXTRACT(EPOCH FROM hour_bucket) as timestamp
                
            FROM hourly_stats
            ORDER BY symbol_id, hour_bucket
            """
            
            rows = await conn.fetch(base_query, start_date, end_date, symbol_ids)
            
        if not rows:
            logger.warning(f"Нет данных за период {start_date} - {end_date}")
            return pd.DataFrame()
            
        df = pd.DataFrame(rows)
        
        # Добавление технических индикаторов
        df = self._add_technical_indicators(df)
        
        # Depth features (если запрошено)
        if include_depth:
            depth_df = await self._get_depth_features(symbol_ids, start_date, end_date)
            if not depth_df.empty:
                df = df.merge(depth_df, on=['hour_bucket', 'symbol_id'], how='left')
        
        logger.info(f"Сформировано {len(df)} записей фичей")
        return df
    
    def _add_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Добавление технических индикаторов"""
        if df.empty:
            return df
            
        # Группировка по символам для расчета индикаторов
        def calculate_indicators(group):
            # Simple Moving Averages
            group['sma_5'] = group['h_close'].rolling(5).mean()
            group['sma_20'] = group['h_close'].rolling(20).mean()
            
            # RSI
            delta = group['h_close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            group['rsi'] = 100 - (100 / (1 + rs))
            
            # MACD  
            ema_12 = group['h_close'].ewm(span=12).mean()
            ema_26 = group['h_close'].ewm(span=26).mean()
            group['macd'] = ema_12 - ema_26
            group['macd_signal'] = group['macd'].ewm(span=9).mean()
            
            # Bollinger Bands
            sma_20 = group['h_close'].rolling(20).mean()
            std_20 = group['h_close'].rolling(20).std()
            group['bb_upper'] = sma_20 + (std_20 * 2)
            group['bb_lower'] = sma_20 - (std_20 * 2)
            group['bb_position'] = (group['h_close'] - group['bb_lower']) / (group['bb_upper'] - group['bb_lower'])
            
            return group
        
        df = df.groupby('symbol_id').apply(calculate_indicators).reset_index(drop=True)
        return df
    
    async def _get_depth_features(self, 
                                symbol_ids: List[int], 
                                start_date: date, 
                                end_date: date) -> pd.DataFrame:
        """Получение depth features (если есть orderbook_top5 данные)"""
        try:
            async with self.pool.acquire() as conn:
                # Проверка наличия depth данных
                has_depth = await conn.fetchval("""
                    SELECT EXISTS(
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_schema = 'marketdata' 
                        AND table_name = 'orderbook_top5'
                    )
                """)
                
                if not has_depth:
                    return pd.DataFrame()
                
                query = """
                SELECT 
                    date_trunc('hour', ts_exchange) as hour_bucket,
                    symbol_id,
                    
                    -- Imbalance features
                    AVG(i1) as avg_i1,
                    AVG(i5) as avg_i5,
                    AVG(microprice) as avg_microprice,
                    AVG(wall_size_bps) as avg_wall_size,
                    
                    -- Spread features
                    AVG(a1_price - b1_price) as avg_spread,
                    STDDEV(a1_price - b1_price) as spread_volatility
                    
                FROM marketdata.orderbook_top5
                WHERE 
                    ts_exchange >= $1::DATE
                    AND ts_exchange < ($2::DATE + INTERVAL '1 day')
                    AND symbol_id = ANY($3)
                GROUP BY hour_bucket, symbol_id
                ORDER BY symbol_id, hour_bucket
                """
                
                rows = await conn.fetch(query, start_date, end_date, symbol_ids)
                return pd.DataFrame(rows)
                
        except Exception as e:
            logger.warning(f"Не удалось загрузить depth features: {e}")
            return pd.DataFrame()
    
    async def get_real_time_features(self, symbols: List[str], lookback_minutes: int = 60) -> pd.DataFrame:
        """
        Получение real-time фичей для live предсказаний
        Аналог real-time inference в существующем коде
        """
        symbol_ids = [self.symbols_cache[s].symbol_id for s in symbols if s in self.symbols_cache]
        
        async with self.pool.acquire() as conn:
            query = """
            SELECT 
                bt.ts_second,
                s.symbol,
                bt.symbol_id,
                bt.mid_close as price,
                bt.spread_mean as spread,
                bt.total_qty_mean as liquidity,
                bt.update_count,
                
                COALESCE(tr.vol_sum, 0) as volume,
                COALESCE(tr.vwap, bt.mid_close) as vwap,
                
                -- Short term indicators
                AVG(bt.mid_close) OVER (
                    PARTITION BY bt.symbol_id 
                    ORDER BY bt.ts_second 
                    ROWS BETWEEN 300 PRECEDING AND CURRENT ROW
                ) as sma_5min,
                
                STDDEV(bt.mid_close) OVER (
                    PARTITION BY bt.symbol_id 
                    ORDER BY bt.ts_second 
                    ROWS BETWEEN 300 PRECEDING AND CURRENT ROW  
                ) as volatility_5min,
                
                EXTRACT(EPOCH FROM bt.ts_second) as timestamp
                
            FROM marketdata.bt_1s bt
            LEFT JOIN marketdata.trade_1s tr ON (
                bt.ts_second = tr.ts_second AND bt.symbol_id = tr.symbol_id
            )
            JOIN marketdata.symbols s ON bt.symbol_id = s.id
            WHERE 
                bt.ts_second >= NOW() - INTERVAL '%s minutes'
                AND bt.symbol_id = ANY($1)
                AND s.is_active = true
            ORDER BY bt.symbol_id, bt.ts_second DESC
            """ % lookback_minutes
            
            rows = await conn.fetch(query, symbol_ids)
            
        return pd.DataFrame(rows)
    
    async def get_symbol_metadata(self) -> pd.DataFrame:
        """Получение метаданных символов"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    id as symbol_id,
                    symbol,
                    exchange,
                    base_asset,
                    quote_asset,
                    is_active,
                    created_at,
                    updated_at
                FROM marketdata.symbols
                ORDER BY symbol
            """)
            
        return pd.DataFrame(rows)
    
    async def check_data_freshness(self, symbols: List[str] = None) -> Dict[str, Any]:
        """Проверка свежести данных"""
        symbol_ids = None
        if symbols:
            symbol_ids = [self.symbols_cache[s].symbol_id for s in symbols if s in self.symbols_cache]
            
        async with self.pool.acquire() as conn:
            query = """
            SELECT 
                s.symbol,
                MAX(bt.ts_exchange) as last_book_ticker,
                MAX(tr.ts_exchange) as last_trade,
                COUNT(bt.*) as bt_count_1h,
                COUNT(tr.*) as trade_count_1h,
                EXTRACT(EPOCH FROM (NOW() - MAX(bt.ts_exchange))) as seconds_since_last_bt
            FROM marketdata.symbols s
            LEFT JOIN marketdata.book_ticker bt ON (
                s.id = bt.symbol_id AND 
                bt.ts_exchange >= NOW() - INTERVAL '1 hour'
            )
            LEFT JOIN marketdata.trades tr ON (
                s.id = tr.symbol_id AND
                tr.ts_exchange >= NOW() - INTERVAL '1 hour'
            )
            WHERE 
                s.is_active = true
                AND ($1::BIGINT[] IS NULL OR s.id = ANY($1))
            GROUP BY s.symbol
            ORDER BY seconds_since_last_bt
            """
            
            rows = await conn.fetch(query, symbol_ids)
            
        return {
            'timestamp': datetime.now(timezone.utc),
            'symbols_checked': len(rows),
            'data': [dict(row) for row in rows]
        }
    
    async def close(self):
        """Закрытие соединений"""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL ML адаптер закрыт")

# Utility функции для совместимости с существующим кодом

async def load_yesterday_data(symbols: List[str], 
                            connection_string: str) -> pd.DataFrame:
    """
    Функция-обертка для замены загрузки Parquet файлов
    """
    adapter = PostgresMLAdapter(connection_string)
    await adapter.initialize()
    
    try:
        df = await adapter.get_yesterday_training_data(symbols)
        return df
    finally:
        await adapter.close()

async def load_features_period(symbols: List[str],
                             days_back: int,
                             connection_string: str) -> pd.DataFrame:
    """
    Загрузка фичей за период (для batch обучения)
    """
    adapter = PostgresMLAdapter(connection_string)
    await adapter.initialize()
    
    try:
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=days_back)
        
        df = await adapter.get_features_for_ml(symbols, start_date, end_date)
        return df
    finally:
        await adapter.close()

# Пример интеграции с существующим ML кодом
class MLDataLoader:
    """
    Обертка для интеграции с существующими ML компонентами
    Заменяет Parquet ридеры на PostgreSQL запросы
    """
    
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.adapter = None
    
    async def __aenter__(self):
        self.adapter = PostgresMLAdapter(self.connection_string)
        await self.adapter.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.adapter:
            await self.adapter.close()
    
    async def get_training_data(self, symbols: List[str], 
                              target_date: date = None) -> pd.DataFrame:
        """Замена для load_parquet_data()"""
        return await self.adapter.get_yesterday_training_data(symbols, target_date)
    
    async def get_ml_features(self, symbols: List[str], 
                            days_back: int = 30) -> pd.DataFrame:
        """Замена для feature engineering pipeline"""
        end_date = date.today() - timedelta(days=1) 
        start_date = end_date - timedelta(days=days_back)
        return await self.adapter.get_features_for_ml(symbols, start_date, end_date)

# Пример использования
if __name__ == "__main__":
    async def main():
        CONNECTION_STRING = "postgresql://ingestor:password@localhost/marketdata"
        SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
        
        # Замена Parquet загрузки на PostgreSQL
        async with MLDataLoader(CONNECTION_STRING) as loader:
            # Вчерашние данные для обучения
            yesterday_data = await loader.get_training_data(SYMBOLS)
            print(f"Загружено {len(yesterday_data)} записей за вчера")
            
            # Фичи за 30 дней для batch обучения
            ml_features = await loader.get_ml_features(SYMBOLS, days_back=30)
            print(f"Сформировано {len(ml_features)} записей фичей")
    
    asyncio.run(main())