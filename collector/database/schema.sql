-- =====================================================
-- POSTGRES/TIMESCALE SCHEMA FOR ORDERBOOK COLLECTION
-- Реализация полной схемы согласно ТЗ для 200 торговых пар
-- =====================================================

-- 1. СОЗДАНИЕ СХЕМЫ И РАСШИРЕНИЙ
-- =============================

CREATE SCHEMA IF NOT EXISTS marketdata;
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 2. СПРАВОЧНИК СИМВОЛОВ
-- =====================

CREATE TABLE IF NOT EXISTS marketdata.symbols (
    id BIGSERIAL PRIMARY KEY,
    exchange TEXT NOT NULL DEFAULT 'binance-futures',
    symbol TEXT NOT NULL,
    instrument_type TEXT DEFAULT 'perp',
    base_asset TEXT,
    quote_asset TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT unique_exchange_symbol UNIQUE (exchange, symbol)
);

-- Индексы для symbols
CREATE INDEX IF NOT EXISTS idx_symbols_active ON marketdata.symbols (is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_symbols_exchange ON marketdata.symbols (exchange);

-- Заполнение базовых символов для старта
INSERT INTO marketdata.symbols (exchange, symbol, base_asset, quote_asset) VALUES
('binance-futures', 'BTCUSDT', 'BTC', 'USDT'),
('binance-futures', 'ETHUSDT', 'ETH', 'USDT'),
('binance-futures', 'SOLUSDT', 'SOL', 'USDT'),
('binance-futures', 'ADAUSDT', 'ADA', 'USDT'),
('binance-futures', 'DOTUSDT', 'DOT', 'USDT')
ON CONFLICT (exchange, symbol) DO NOTHING;

-- 3. ОСНОВНАЯ ТАБЛИЦА: BOOK TICKER (TOP-OF-BOOK)
-- ==============================================

CREATE TABLE IF NOT EXISTS marketdata.book_ticker (
    ts_exchange TIMESTAMPTZ NOT NULL,          -- E/1000 от биржи (UTC)
    ts_ingest TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol_id BIGINT NOT NULL REFERENCES marketdata.symbols(id),
    update_id BIGINT,                          -- u поле (может отсутствовать)
    best_bid DOUBLE PRECISION NOT NULL,        -- b поле
    best_ask DOUBLE PRECISION NOT NULL,        -- a поле  
    bid_qty DOUBLE PRECISION NOT NULL,         -- B поле
    ask_qty DOUBLE PRECISION NOT NULL,         -- A поле
    spread DOUBLE PRECISION GENERATED ALWAYS AS (best_ask - best_bid) STORED,
    mid DOUBLE PRECISION GENERATED ALWAYS AS ((best_ask + best_bid) / 2.0) STORED,
    
    -- Составной первичный ключ для уникальности
    PRIMARY KEY (symbol_id, ts_exchange, ts_ingest)
);

-- Создание TimescaleDB hypertable
SELECT create_hypertable('marketdata.book_ticker', 'ts_exchange', 
    chunk_time_interval => INTERVAL '1 hour',
    partitioning_column => 'symbol_id',
    number_partitions => 4,
    if_not_exists => TRUE
);

-- Индексы для book_ticker
CREATE INDEX IF NOT EXISTS idx_book_ticker_symbol_ts ON marketdata.book_ticker (symbol_id, ts_exchange);
CREATE INDEX IF NOT EXISTS idx_book_ticker_ingest ON marketdata.book_ticker (ts_ingest);

-- 4. ТАБЛИЦА СДЕЛОК (AGG_TRADE)
-- =============================

CREATE TABLE IF NOT EXISTS marketdata.trades (
    ts_exchange TIMESTAMPTZ NOT NULL,          -- E/1000
    ts_ingest TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol_id BIGINT NOT NULL REFERENCES marketdata.symbols(id),
    agg_trade_id BIGINT NOT NULL,              -- a поле
    price DOUBLE PRECISION NOT NULL,           -- p поле
    qty DOUBLE PRECISION NOT NULL,             -- q поле
    is_buyer_maker BOOLEAN NOT NULL,           -- m поле
    
    PRIMARY KEY (symbol_id, agg_trade_id)
);

-- Создание hypertable для trades
SELECT create_hypertable('marketdata.trades', 'ts_exchange',
    chunk_time_interval => INTERVAL '1 hour',
    partitioning_column => 'symbol_id', 
    number_partitions => 4,
    if_not_exists => TRUE
);

-- Индексы для trades
CREATE INDEX IF NOT EXISTS idx_trades_symbol_ts ON marketdata.trades (symbol_id, ts_exchange);
CREATE INDEX IF NOT EXISTS idx_trades_price ON marketdata.trades (symbol_id, price, ts_exchange);

-- 5. СОБЫТИЯ ГЛУБИНЫ (DEPTH UPDATES) - JSONB ВАРИАНТ
-- ==================================================

CREATE TABLE IF NOT EXISTS marketdata.depth_events (
    ts_exchange TIMESTAMPTZ NOT NULL,          -- E/1000
    ts_ingest TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol_id BIGINT NOT NULL REFERENCES marketdata.symbols(id),
    first_update_id BIGINT NOT NULL,           -- U поле
    final_update_id BIGINT NOT NULL,           -- u поле  
    prev_final_update_id BIGINT,               -- pu поле (может быть NULL)
    bids JSONB NOT NULL,                       -- массив [["price","qty"], ...]
    asks JSONB NOT NULL,                       -- массив [["price","qty"], ...]
    
    PRIMARY KEY (symbol_id, final_update_id)
);

-- Создание hypertable для depth_events
SELECT create_hypertable('marketdata.depth_events', 'ts_exchange',
    chunk_time_interval => INTERVAL '30 minutes',
    partitioning_column => 'symbol_id',
    number_partitions => 8,
    if_not_exists => TRUE
);

-- Индексы для depth_events
CREATE INDEX IF NOT EXISTS idx_depth_symbol_ts ON marketdata.depth_events (symbol_id, ts_exchange);
CREATE INDEX IF NOT EXISTS idx_depth_update_id ON marketdata.depth_events (symbol_id, final_update_id);

-- GIN индекс для быстрого поиска по JSONB
CREATE INDEX IF NOT EXISTS idx_depth_bids_gin ON marketdata.depth_events USING GIN (bids);
CREATE INDEX IF NOT EXISTS idx_depth_asks_gin ON marketdata.depth_events USING GIN (asks);

-- 6. ПРОИЗВОДНАЯ ТАБЛИЦА: TOP-N ORDERBOOK (ПЛОСКИЙ ФОРМАТ)
-- ========================================================

CREATE TABLE IF NOT EXISTS marketdata.orderbook_top5 (
    ts_exchange TIMESTAMPTZ NOT NULL,
    symbol_id BIGINT NOT NULL REFERENCES marketdata.symbols(id),
    
    -- Топ-5 bid уровней
    b1_price DOUBLE PRECISION, b1_qty DOUBLE PRECISION,
    b2_price DOUBLE PRECISION, b2_qty DOUBLE PRECISION,
    b3_price DOUBLE PRECISION, b3_qty DOUBLE PRECISION,
    b4_price DOUBLE PRECISION, b4_qty DOUBLE PRECISION,
    b5_price DOUBLE PRECISION, b5_qty DOUBLE PRECISION,
    
    -- Топ-5 ask уровней  
    a1_price DOUBLE PRECISION, a1_qty DOUBLE PRECISION,
    a2_price DOUBLE PRECISION, a2_qty DOUBLE PRECISION,
    a3_price DOUBLE PRECISION, a3_qty DOUBLE PRECISION,
    a4_price DOUBLE PRECISION, a4_qty DOUBLE PRECISION,
    a5_price DOUBLE PRECISION, a5_qty DOUBLE PRECISION,
    
    -- Производные фичи для ML
    microprice DOUBLE PRECISION,               -- (b1*a1_qty + a1*b1_qty)/(b1_qty + a1_qty)
    i1 DOUBLE PRECISION,                       -- bid/ask imbalance level 1
    i5 DOUBLE PRECISION,                       -- bid/ask imbalance level 1-5
    wall_size_bps DOUBLE PRECISION,            -- размер стены в базисных пунктах
    
    PRIMARY KEY (symbol_id, ts_exchange)
);

-- Создание hypertable для orderbook_top5
SELECT create_hypertable('marketdata.orderbook_top5', 'ts_exchange',
    chunk_time_interval => INTERVAL '30 minutes',
    partitioning_column => 'symbol_id',
    number_partitions => 8,
    if_not_exists => TRUE
);

-- Индексы для orderbook_top5
CREATE INDEX IF NOT EXISTS idx_ob_top5_symbol_ts ON marketdata.orderbook_top5 (symbol_id, ts_exchange);

-- 7. CONTINUOUS AGGREGATES (МАТЕРИАЛИЗОВАННЫЕ ПРЕДСТАВЛЕНИЯ)
-- ==========================================================

-- 7.1 Агрегаты book_ticker по 1 секунде
CREATE MATERIALIZED VIEW IF NOT EXISTS marketdata.bt_1s
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 second', ts_exchange) AS ts_second,
    symbol_id,
    
    -- OHLC для mid price
    FIRST(mid, ts_exchange) AS mid_open,
    MAX(mid) AS mid_high,
    MIN(mid) AS mid_low,
    LAST(mid, ts_exchange) AS mid_close,
    
    -- Spread статистика
    AVG(spread) AS spread_mean,
    MIN(spread) AS spread_min,
    MAX(spread) AS spread_max,
    STDDEV(spread) AS spread_std,
    
    -- Volume
    AVG(bid_qty + ask_qty) AS total_qty_mean,
    
    -- Количество обновлений
    COUNT(*) AS update_count,
    
    -- Latency метрики
    AVG(EXTRACT(EPOCH FROM (ts_ingest - ts_exchange)) * 1000) AS avg_latency_ms

FROM marketdata.book_ticker
GROUP BY ts_second, symbol_id
WITH NO DATA;

-- Настройка refresh policy для bt_1s
SELECT add_continuous_aggregate_policy('marketdata.bt_1s',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists => TRUE
);

-- 7.2 Агрегаты trades по 1 секунде  
CREATE MATERIALIZED VIEW IF NOT EXISTS marketdata.trade_1s
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 second', ts_exchange) AS ts_second,
    symbol_id,
    
    -- Trade статистика
    COUNT(*) AS trade_count,
    SUM(qty) AS vol_sum,
    SUM(price * qty) / SUM(qty) AS vwap,
    
    -- Buy/Sell imbalance
    SUM(CASE WHEN is_buyer_maker = false THEN qty ELSE 0 END) AS buy_vol,
    SUM(CASE WHEN is_buyer_maker = true THEN qty ELSE 0 END) AS sell_vol,
    
    -- Price движение
    FIRST(price, ts_exchange) AS price_open,
    MAX(price) AS price_high,
    MIN(price) AS price_low,
    LAST(price, ts_exchange) AS price_close

FROM marketdata.trades
GROUP BY ts_second, symbol_id
WITH NO DATA;

-- Настройка refresh policy для trade_1s
SELECT add_continuous_aggregate_policy('marketdata.trade_1s',
    start_offset => INTERVAL '1 hour', 
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists => TRUE
);

-- 8. ПОЛИТИКИ RETENTION И КОМПРЕССИЯ
-- =================================

-- Компрессия book_ticker старше 7 дней
SELECT add_compression_policy('marketdata.book_ticker', INTERVAL '7 days', if_not_exists => TRUE);

-- Компрессия trades старше 7 дней
SELECT add_compression_policy('marketdata.trades', INTERVAL '7 days', if_not_exists => TRUE);

-- Компрессия depth_events старше 3 дней (большой объём)
SELECT add_compression_policy('marketdata.depth_events', INTERVAL '3 days', if_not_exists => TRUE);

-- Retention policy: удаление сырых данных старше 30 дней
SELECT add_retention_policy('marketdata.book_ticker', INTERVAL '30 days', if_not_exists => TRUE);
SELECT add_retention_policy('marketdata.trades', INTERVAL '30 days', if_not_exists => TRUE);  
SELECT add_retention_policy('marketdata.depth_events', INTERVAL '7 days', if_not_exists => TRUE);

-- Агрегаты храним дольше - 90 дней
SELECT add_retention_policy('marketdata.bt_1s', INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_retention_policy('marketdata.trade_1s', INTERVAL '90 days', if_not_exists => TRUE);

-- 9. ФУНКЦИИ ДЛЯ "ВЧЕРАШНЕГО" ОБУЧЕНИЯ
-- ====================================

-- Функция для получения данных за вчерашний день
CREATE OR REPLACE FUNCTION marketdata.get_yesterday_training_data(
    p_symbol_id BIGINT DEFAULT NULL,
    p_date DATE DEFAULT (CURRENT_DATE - INTERVAL '1 day')::DATE
)
RETURNS TABLE (
    ts_second TIMESTAMPTZ,
    symbol_id BIGINT,
    mid_close DOUBLE PRECISION,
    spread_mean DOUBLE PRECISION,
    trade_count BIGINT,
    vwap DOUBLE PRECISION,
    buy_sell_imbalance DOUBLE PRECISION
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        bt.ts_second,
        bt.symbol_id,
        bt.mid_close,
        bt.spread_mean,
        COALESCE(tr.trade_count, 0) AS trade_count,
        tr.vwap,
        CASE 
            WHEN tr.buy_vol + tr.sell_vol > 0 
            THEN (tr.buy_vol - tr.sell_vol) / (tr.buy_vol + tr.sell_vol)
            ELSE 0 
        END AS buy_sell_imbalance
    FROM marketdata.bt_1s bt
    LEFT JOIN marketdata.trade_1s tr ON (
        bt.ts_second = tr.ts_second AND 
        bt.symbol_id = tr.symbol_id
    )
    WHERE 
        bt.ts_second >= p_date::TIMESTAMPTZ 
        AND bt.ts_second < (p_date + INTERVAL '1 day')::TIMESTAMPTZ
        AND (p_symbol_id IS NULL OR bt.symbol_id = p_symbol_id)
    ORDER BY bt.symbol_id, bt.ts_second;
END;
$$ LANGUAGE plpgsql;

-- 10. МОНИТОРИНГ И СТАТИСТИКА
-- ===========================

-- Представление для мониторинга ingestion rate
CREATE OR REPLACE VIEW marketdata.ingestion_stats AS
SELECT 
    s.symbol,
    COUNT(bt.*) AS book_ticker_count_1h,
    COUNT(tr.*) AS trades_count_1h,
    MAX(bt.ts_ingest) AS last_book_ticker,
    MAX(tr.ts_ingest) AS last_trade,
    AVG(EXTRACT(EPOCH FROM (bt.ts_ingest - bt.ts_exchange)) * 1000) AS avg_latency_ms
FROM marketdata.symbols s
LEFT JOIN marketdata.book_ticker bt ON (
    s.id = bt.symbol_id AND 
    bt.ts_exchange >= NOW() - INTERVAL '1 hour'
)
LEFT JOIN marketdata.trades tr ON (
    s.id = tr.symbol_id AND 
    tr.ts_exchange >= NOW() - INTERVAL '1 hour'  
)
WHERE s.is_active = true
GROUP BY s.id, s.symbol
ORDER BY book_ticker_count_1h DESC;

-- Представление для data quality check
CREATE OR REPLACE VIEW marketdata.data_quality_check AS
SELECT 
    s.symbol,
    COUNT(bt.*) AS total_records,
    COUNT(CASE WHEN bt.best_bid <= 0 THEN 1 END) AS invalid_bid_price,
    COUNT(CASE WHEN bt.best_ask <= 0 THEN 1 END) AS invalid_ask_price,
    COUNT(CASE WHEN bt.bid_qty <= 0 THEN 1 END) AS invalid_bid_qty,
    COUNT(CASE WHEN bt.ask_qty <= 0 THEN 1 END) AS invalid_ask_qty,
    COUNT(CASE WHEN bt.spread <= 0 THEN 1 END) AS invalid_spread,
    COUNT(CASE WHEN bt.ts_ingest < bt.ts_exchange THEN 1 END) AS invalid_latency
FROM marketdata.symbols s
LEFT JOIN marketdata.book_ticker bt ON (
    s.id = bt.symbol_id AND 
    bt.ts_exchange >= NOW() - INTERVAL '1 hour'
)
WHERE s.is_active = true
GROUP BY s.id, s.symbol;

-- КОНЕЦ SCHEMA
-- Схема готова для разворачивания на PostgreSQL + TimescaleDB
-- Поддерживает до 200 торговых пар с оптимизацией для "вчерашнего" обучения