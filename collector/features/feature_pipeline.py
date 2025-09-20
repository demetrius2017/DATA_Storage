"""
Feature Pipeline для расчета финансовых индикаторов
Решает задачу подготовки данных для ML pipeline

Вычисляемые фичи:
- I1, I10: Imbalance indicators
- Microprice: Средневзвешенная цена bid/ask
- OFI: Order Flow Imbalance  
- VPIN: Volume-synchronized Probability of Informed Trading
- Spread metrics: Относительный и абсолютный spread
- Volume flow: Анализ направления объемов
"""

import asyncio
import numpy as np
import pandas as pd
import logging
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime, timedelta
from dataclasses import dataclass
import json

@dataclass
class MarketFeatures:
    """Структура для хранения вычисленных фичей"""
    timestamp: datetime
    symbol: str
    
    # Price features
    microprice: float
    mid_price: float
    spread_abs: float
    spread_rel: float
    
    # Imbalance features  
    i1: float  # Level 1 imbalance
    i10: float  # Level 10 imbalance (если доступно)
    ofi: float  # Order Flow Imbalance
    
    # Volume features
    volume_imbalance: float
    buy_volume_ratio: float
    vpin: Optional[float] = None
    
    # Volatility features
    price_volatility: Optional[float] = None
    return_1s: Optional[float] = None
    
    def to_dict(self) -> Dict:
        """Конвертация в словарь для JSON сериализации"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'symbol': self.symbol,
            'microprice': self.microprice,
            'mid_price': self.mid_price,
            'spread_abs': self.spread_abs,
            'spread_rel': self.spread_rel,
            'i1': self.i1,
            'i10': self.i10,
            'ofi': self.ofi,
            'volume_imbalance': self.volume_imbalance,
            'buy_volume_ratio': self.buy_volume_ratio,
            'vpin': self.vpin,
            'price_volatility': self.price_volatility,
            'return_1s': self.return_1s
        }

class FeaturePipeline:
    """Pipeline для расчета финансовых фичей из market data"""
    
    def __init__(self, lookback_window: int = 10):
        """
        Инициализация pipeline
        
        Args:
            lookback_window: Размер окна для скользящих расчетов
        """
        self.lookback_window = lookback_window
        self.logger = logging.getLogger(__name__)
        
        # Буферы для скользящих расчетов
        self.price_buffer = {}  # symbol -> list of prices
        self.volume_buffer = {}  # symbol -> list of volumes
        
    def calculate_microprice(self, bid_price: float, ask_price: float, 
                           bid_qty: float, ask_qty: float) -> float:
        """
        Рассчитывает microprice (средневзвешенную цену)
        
        Formula: microprice = (bid_price * ask_qty + ask_price * bid_qty) / (bid_qty + ask_qty)
        """
        if bid_qty + ask_qty == 0:
            return (bid_price + ask_price) / 2
            
        return (bid_price * ask_qty + ask_price * bid_qty) / (bid_qty + ask_qty)
    
    def calculate_imbalance_i1(self, bid_qty: float, ask_qty: float) -> float:
        """
        Рассчитывает I1 (Level 1 imbalance)
        
        Formula: I1 = (bid_qty - ask_qty) / (bid_qty + ask_qty)
        """
        if bid_qty + ask_qty == 0:
            return 0.0
            
        return (bid_qty - ask_qty) / (bid_qty + ask_qty)
    
    def calculate_imbalance_i10(self, bids: List[Tuple[float, float]], 
                               asks: List[Tuple[float, float]]) -> float:
        """
        Рассчитывает I10 (Level 10 imbalance) из depth data
        
        Args:
            bids: List of (price, quantity) для top 10 bids
            asks: List of (price, quantity) для top 10 asks
        """
        if not bids or not asks:
            return 0.0
            
        total_bid_qty = sum(qty for _, qty in bids[:10])
        total_ask_qty = sum(qty for _, qty in asks[:10])
        
        if total_bid_qty + total_ask_qty == 0:
            return 0.0
            
        return (total_bid_qty - total_ask_qty) / (total_bid_qty + total_ask_qty)
    
    def calculate_ofi(self, current_data: Dict, previous_data: Optional[Dict]) -> float:
        """
        Рассчитывает Order Flow Imbalance (OFI)
        
        OFI измеряет изменения в orderbook, которые могут указывать на
        направление будущего движения цены
        """
        if not previous_data:
            return 0.0
            
        # Текущие значения
        bid_price = float(current_data.get('bid_price', 0))
        ask_price = float(current_data.get('ask_price', 0))
        bid_qty = float(current_data.get('bid_qty', 0))
        ask_qty = float(current_data.get('ask_qty', 0))
        
        # Предыдущие значения
        prev_bid_price = float(previous_data.get('bid_price', 0))
        prev_ask_price = float(previous_data.get('ask_price', 0))
        prev_bid_qty = float(previous_data.get('bid_qty', 0))
        prev_ask_qty = float(previous_data.get('ask_qty', 0))
        
        # Расчет OFI
        bid_flow = 0.0
        ask_flow = 0.0
        
        # Если цена bid не изменилась, берем разность количества
        if abs(bid_price - prev_bid_price) < 1e-8:
            bid_flow = bid_qty - prev_bid_qty
        else:
            # Если цена изменилась, используем текущее количество
            bid_flow = bid_qty if bid_price > prev_bid_price else -prev_bid_qty
            
        # Аналогично для ask
        if abs(ask_price - prev_ask_price) < 1e-8:
            ask_flow = ask_qty - prev_ask_qty
        else:
            ask_flow = -ask_qty if ask_price < prev_ask_price else prev_ask_qty
            
        return bid_flow + ask_flow
    
    def calculate_vpin(self, buy_volume: float, sell_volume: float, 
                      window_volumes: List[float]) -> float:
        """
        Рассчитывает VPIN (Volume-synchronized Probability of Informed Trading)
        
        VPIN измеряет вероятность информированной торговли
        """
        if not window_volumes or len(window_volumes) < 2:
            return 0.0
            
        total_volume = buy_volume + sell_volume
        if total_volume == 0:
            return 0.0
            
        volume_imbalance = abs(buy_volume - sell_volume)
        avg_volume = np.mean(window_volumes)
        
        if avg_volume == 0:
            return 0.0
            
        return volume_imbalance / avg_volume
    
    def calculate_return(self, current_price: float, previous_price: float) -> float:
        """
        Рассчитывает логарифмический return
        """
        if previous_price <= 0:
            return 0.0
            
        return np.log(current_price / previous_price)
    
    def calculate_volatility(self, symbol: str, current_price: float) -> float:
        """
        Рассчитывает скользящую волатильность
        """
        if symbol not in self.price_buffer:
            self.price_buffer[symbol] = []
            
        self.price_buffer[symbol].append(current_price)
        
        # Ограничиваем размер буфера
        if len(self.price_buffer[symbol]) > self.lookback_window:
            self.price_buffer[symbol] = self.price_buffer[symbol][-self.lookback_window:]
            
        prices = self.price_buffer[symbol]
        if len(prices) < 2:
            return 0.0
            
        # Рассчитываем returns
        returns = []
        for i in range(1, len(prices)):
            ret = self.calculate_return(prices[i], prices[i-1])
            returns.append(ret)
            
        if not returns:
            return 0.0
            
        return float(np.std(returns))
    
    def extract_features_from_aggregates(self, bt_data: Dict, trade_data: Optional[Dict] = None,
                                       depth_data: Optional[Dict] = None,
                                       previous_bt_data: Optional[Dict] = None) -> MarketFeatures:
        """
        Извлекает фичи из данных агрегатов
        
        Args:
            bt_data: Данные из bt_1s_continuous
            trade_data: Данные из trade_1s_continuous (опционально)
            depth_data: Данные из depth_1s_continuous (опционально)
            previous_bt_data: Предыдущая запись для расчета OFI
        """
        symbol = bt_data['symbol']
        timestamp = bt_data['ts_bucket']
        
        # Основные цены
        bid_price = float(bt_data['bid_close'])
        ask_price = float(bt_data['ask_close'])
        bid_qty = float(bt_data['bid_qty_close'])
        ask_qty = float(bt_data['ask_qty_close'])
        
        # Расчет базовых метрик
        microprice = self.calculate_microprice(bid_price, ask_price, bid_qty, ask_qty)
        mid_price = (bid_price + ask_price) / 2
        spread_abs = ask_price - bid_price
        spread_rel = spread_abs / mid_price if mid_price > 0 else 0.0
        
        # Imbalance метрики
        i1 = self.calculate_imbalance_i1(bid_qty, ask_qty)
        i10 = i1  # Упрощенная версия, используем I1 как I10
        
        # OFI
        ofi = self.calculate_ofi(
            {'bid_price': bid_price, 'ask_price': ask_price, 'bid_qty': bid_qty, 'ask_qty': ask_qty},
            previous_bt_data
        )
        
        # Volume метрики из trades
        volume_imbalance = 0.0
        buy_volume_ratio = 0.5
        vpin = None
        
        if trade_data:
            buy_volume = float(trade_data.get('buy_volume', 0))
            sell_volume = float(trade_data.get('sell_volume', 0))
            total_volume = buy_volume + sell_volume
            
            if total_volume > 0:
                volume_imbalance = (buy_volume - sell_volume) / total_volume
                buy_volume_ratio = buy_volume / total_volume
                
                # Обновляем буфер объемов для VPIN
                if symbol not in self.volume_buffer:
                    self.volume_buffer[symbol] = []
                self.volume_buffer[symbol].append(total_volume)
                
                if len(self.volume_buffer[symbol]) > self.lookback_window:
                    self.volume_buffer[symbol] = self.volume_buffer[symbol][-self.lookback_window:]
                
                vpin = self.calculate_vpin(buy_volume, sell_volume, self.volume_buffer[symbol])
        
        # Volatility и returns
        price_volatility = self.calculate_volatility(symbol, mid_price)
        
        return_1s = None
        if previous_bt_data:
            prev_mid = (float(previous_bt_data.get('bid_close', 0)) + 
                       float(previous_bt_data.get('ask_close', 0))) / 2
            if prev_mid > 0:
                return_1s = self.calculate_return(mid_price, prev_mid)
        
        return MarketFeatures(
            timestamp=timestamp,
            symbol=symbol,
            microprice=microprice,
            mid_price=mid_price,
            spread_abs=spread_abs,
            spread_rel=spread_rel,
            i1=i1,
            i10=i10,
            ofi=ofi,
            volume_imbalance=volume_imbalance,
            buy_volume_ratio=buy_volume_ratio,
            vpin=vpin,
            price_volatility=price_volatility,
            return_1s=return_1s
        )
    
    def process_market_data_batch(self, market_data: List[Dict]) -> List[MarketFeatures]:
        """
        Обрабатывает batch market data и извлекает фичи
        
        Args:
            market_data: Список записей из market_data_1s представления
            
        Returns:
            Список MarketFeatures
        """
        features_list = []
        previous_data = None
        
        for data in market_data:
            # Разделяем данные на компоненты
            bt_data = {
                'symbol': data['symbol'],
                'ts_bucket': data['ts_bucket'],
                'bid_close': data['bid_close'],
                'ask_close': data['ask_close'],
                'bid_qty_close': data.get('bid_qty_close', 0),
                'ask_qty_close': data.get('ask_qty_close', 0)
            }
            
            trade_data = None
            if data.get('volume') is not None:
                trade_data = {
                    'buy_volume': data.get('buy_volume', 0),
                    'sell_volume': data.get('sell_volume', 0),
                    'volume': data['volume'],
                    'buy_ratio': data.get('buy_ratio', 0.5)
                }
                
                # Если нет разделения buy/sell, используем buy_ratio
                if trade_data['buy_volume'] == 0 and trade_data['sell_volume'] == 0:
                    total_vol = float(trade_data['volume'])
                    buy_ratio = float(trade_data['buy_ratio'])
                    trade_data['buy_volume'] = total_vol * buy_ratio
                    trade_data['sell_volume'] = total_vol * (1 - buy_ratio)
            
            # Извлекаем фичи
            features = self.extract_features_from_aggregates(
                bt_data, trade_data, None, previous_data
            )
            
            features_list.append(features)
            previous_data = bt_data
            
        return features_list


class FeatureStorage:
    """Система хранения вычисленных фичей"""
    
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.logger = logging.getLogger(__name__)
    
    async def create_features_table(self):
        """Создает таблицу для хранения фичей"""
        
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS market_features (
            ts_exchange TIMESTAMPTZ NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            
            -- Price features
            microprice DECIMAL(20,8),
            mid_price DECIMAL(20,8),
            spread_abs DECIMAL(20,8),
            spread_rel DECIMAL(10,6),
            
            -- Imbalance features
            i1 DECIMAL(10,6),
            i10 DECIMAL(10,6),
            ofi DECIMAL(20,4),
            
            -- Volume features
            volume_imbalance DECIMAL(10,6),
            buy_volume_ratio DECIMAL(10,6),
            vpin DECIMAL(10,6),
            
            -- Volatility features
            price_volatility DECIMAL(10,6),
            return_1s DECIMAL(12,8),
            
            created_at TIMESTAMPTZ DEFAULT now(),
            
            PRIMARY KEY (ts_exchange, symbol)
        );
        
        -- Создаем hypertable
        SELECT create_hypertable('market_features', 'ts_exchange', 
            chunk_time_interval => INTERVAL '1 day',
            if_not_exists => TRUE);
        
        -- Индексы
        CREATE INDEX IF NOT EXISTS idx_market_features_symbol_ts 
        ON market_features (symbol, ts_exchange DESC);
        
        CREATE INDEX IF NOT EXISTS idx_market_features_created 
        ON market_features (created_at DESC);
        """
        
        try:
            import asyncpg
            pool = await asyncpg.create_pool(self.connection_string)
            async with pool.acquire() as conn:
                await conn.execute(create_table_sql)
                self.logger.info("✅ Таблица market_features создана")
            await pool.close()
            return True
        except Exception as e:
            self.logger.error(f"Ошибка создания таблицы: {e}")
            return False
    
    async def store_features(self, features_list: List[MarketFeatures]) -> bool:
        """Сохраняет вычисленные фичи в базу данных"""
        
        if not features_list:
            return True
            
        insert_sql = """
        INSERT INTO market_features (
            ts_exchange, symbol, microprice, mid_price, spread_abs, spread_rel,
            i1, i10, ofi, volume_imbalance, buy_volume_ratio, vpin,
            price_volatility, return_1s
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
        ON CONFLICT (ts_exchange, symbol) DO UPDATE SET
            microprice = EXCLUDED.microprice,
            mid_price = EXCLUDED.mid_price,
            spread_abs = EXCLUDED.spread_abs,
            spread_rel = EXCLUDED.spread_rel,
            i1 = EXCLUDED.i1,
            i10 = EXCLUDED.i10,
            ofi = EXCLUDED.ofi,
            volume_imbalance = EXCLUDED.volume_imbalance,
            buy_volume_ratio = EXCLUDED.buy_volume_ratio,
            vpin = EXCLUDED.vpin,
            price_volatility = EXCLUDED.price_volatility,
            return_1s = EXCLUDED.return_1s
        """
        
        try:
            import asyncpg
            pool = await asyncpg.create_pool(self.connection_string)
            
            async with pool.acquire() as conn:
                for features in features_list:
                    await conn.execute(
                        insert_sql,
                        features.timestamp, features.symbol,
                        features.microprice, features.mid_price,
                        features.spread_abs, features.spread_rel,
                        features.i1, features.i10, features.ofi,
                        features.volume_imbalance, features.buy_volume_ratio,
                        features.vpin, features.price_volatility, features.return_1s
                    )
                    
            await pool.close()
            self.logger.info(f"✅ Сохранено {len(features_list)} features")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка сохранения features: {e}")
            return False


# Пример использования
async def demo_feature_pipeline():
    """Демонстрация работы feature pipeline"""
    
    # Настройка логирования
    logging.basicConfig(level=logging.INFO)
    
    # Создание pipeline
    pipeline = FeaturePipeline(lookback_window=10)
    
    print("🔬 Демонстрация Feature Pipeline")
    print("=" * 50)
    
    # Симуляция market data
    mock_data = [
        {
            'symbol': 'BTCUSDT',
            'ts_bucket': datetime.utcnow(),
            'bid_close': 50000.0,
            'ask_close': 50001.0,
            'bid_qty_close': 1.5,
            'ask_qty_close': 2.0,
            'volume': 100.5,
            'buy_ratio': 0.6
        },
        {
            'symbol': 'BTCUSDT',  
            'ts_bucket': datetime.utcnow() + timedelta(seconds=1),
            'bid_close': 50001.0,
            'ask_close': 50002.0,
            'bid_qty_close': 1.2,
            'ask_qty_close': 1.8,
            'volume': 150.3,
            'buy_ratio': 0.55
        }
    ]
    
    # Обработка данных
    features_list = pipeline.process_market_data_batch(mock_data)
    
    print(f"📊 Обработано записей: {len(features_list)}")
    
    for i, features in enumerate(features_list):
        print(f"\n📈 Запись {i+1}:")
        print(f"   Symbol: {features.symbol}")
        print(f"   Microprice: {features.microprice:.6f}")
        print(f"   Spread rel: {features.spread_rel:.6f}")
        print(f"   I1: {features.i1:.6f}")
        print(f"   OFI: {features.ofi:.4f}")
        print(f"   Volume imbalance: {features.volume_imbalance:.6f}")
        
        if features.return_1s is not None:
            print(f"   Return 1s: {features.return_1s:.8f}")
    
    print("\n✅ Demo завершен!")

if __name__ == "__main__":
    asyncio.run(demo_feature_pipeline())