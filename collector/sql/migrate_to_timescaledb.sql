-- ===============================================
-- 🚀 МИГРАЦИЯ НА ПОЛНУЮ TIMESCALEDB СХЕМУ
-- ===============================================
-- 
-- Этот скрипт обновляет простую схему до полной TimescaleDB
-- с hypertables, compression, retention policies
-- 
-- Выполнять ОСТОРОЖНО на production данных!
-- ===============================================

-- Шаг 1: Включаем TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Шаг 2: Создаем новые таблицы из полной схемы (если нужно)

-- ===============================================
-- СОЗДАНИЕ HYPERTABLES
-- ===============================================

-- Конвертируем book_ticker в hypertable
SELECT create_hypertable(
    'marketdata.book_ticker', 
    'ts_exchange',
    chunk_time_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Конвертируем trades в hypertable  
SELECT create_hypertable(
    'marketdata.trades',
    'ts_exchange', 
    chunk_time_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Конвертируем depth_events в hypertable
SELECT create_hypertable(
    'marketdata.depth_events',
    'ts_exchange',
    chunk_time_interval => INTERVAL '1 hour', 
    if_not_exists => TRUE
);

-- ===============================================
-- СОЗДАНИЕ НОВЫХ ТАБЛИЦ ИЗ ПОЛНОЙ СХЕМЫ
-- ===============================================

-- Создаем orderbook_topN таблицу
CREATE TABLE IF NOT EXISTS marketdata.orderbook_topN (
    ts_exchange timestamptz NOT NULL,
    symbol_id bigint NOT NULL REFERENCES marketdata.symbols(id),
    
    -- Top 5 levels bid side
    b1_price double precision, b1_qty double precision,
    b2_price double precision, b2_qty double precision,
    b3_price double precision, b3_qty double precision,
    b4_price double precision, b4_qty double precision,
    b5_price double precision, b5_qty double precision,
    
    -- Top 5 levels ask side  
    a1_price double precision, a1_qty double precision,
    a2_price double precision, a2_qty double precision,
    a3_price double precision, a3_qty double precision,
    a4_price double precision, a4_qty double precision,
    a5_price double precision, a5_qty double precision,
    
    -- Derived microstructure features
    microprice double precision,         -- Микроцена Lee-Ready
    i1 double precision,                 -- Immediate impact level 1
    i5 double precision,                 -- Immediate impact level 5  
    wall_size_bid double precision,      -- Размер стены на bid стороне
    wall_size_ask double precision,      -- Размер стены на ask стороне
    wall_dist_bid_bps double precision,  -- Расстояние до стены bid (bps)
    wall_dist_ask_bps double precision,  -- Расстояние до стены ask (bps)
    ofi_1s double precision,             -- Order Flow Imbalance 1s
    total_bid_qty double precision GENERATED ALWAYS AS (
        COALESCE(b1_qty,0) + COALESCE(b2_qty,0) + COALESCE(b3_qty,0) + 
        COALESCE(b4_qty,0) + COALESCE(b5_qty,0)
    ) STORED,
    total_ask_qty double precision GENERATED ALWAYS AS (
        COALESCE(a1_qty,0) + COALESCE(a2_qty,0) + COALESCE(a3_qty,0) + 
        COALESCE(a4_qty,0) + COALESCE(a5_qty,0)
    ) STORED,
    
    PRIMARY KEY (symbol_id, ts_exchange)
);

-- Создаем bt_1s агрегаты
CREATE TABLE IF NOT EXISTS marketdata.bt_1s (
    ts_second timestamptz NOT NULL,      -- Округлённое время до секунды
    symbol_id bigint NOT NULL REFERENCES marketdata.symbols(id),
    
    -- OHLC для mid price
    mid_open double precision,
    mid_high double precision,
    mid_low double precision,
    mid_close double precision,
    
    -- Статистика спреда
    spread_mean double precision,
    spread_std double precision,
    spread_min double precision,
    spread_max double precision,
    
    -- Объёмы
    total_updates bigint,                -- Количество обновлений
    
    PRIMARY KEY (symbol_id, ts_second)
);

-- Создаем trade_1s агрегаты
CREATE TABLE IF NOT EXISTS marketdata.trade_1s (
    ts_second timestamptz NOT NULL,
    symbol_id bigint NOT NULL REFERENCES marketdata.symbols(id),
    
    -- OHLCV для trade price
    price_open double precision,
    price_high double precision,
    price_low double precision,
    price_close double precision,
    volume_base double precision,        -- Объём в базовой валюте
    volume_quote double precision,       -- Объём в котируемой валюте
    
    -- Микроструктура
    trades_count bigint,                 -- Количество сделок
    buy_trades_count bigint,             -- Количество покупок
    sell_trades_count bigint,            -- Количество продаж
    buy_volume double precision,         -- Объём покупок
    sell_volume double precision,        -- Объём продаж
    
    PRIMARY KEY (symbol_id, ts_second)
);

-- Конвертируем агрегаты в hypertables
SELECT create_hypertable(
    'marketdata.orderbook_topN',
    'ts_exchange',
    chunk_time_interval => INTERVAL '6 hours',
    if_not_exists => TRUE
);

SELECT create_hypertable(
    'marketdata.bt_1s',
    'ts_second',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

SELECT create_hypertable(
    'marketdata.trade_1s',
    'ts_second', 
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- ===============================================
-- COMPRESSION POLICIES
-- ===============================================

-- Включаем сжатие для raw данных (старше 1 дня)
SELECT add_compression_policy(
    'marketdata.book_ticker',
    INTERVAL '1 day'
);

SELECT add_compression_policy(
    'marketdata.trades', 
    INTERVAL '1 day'
);

SELECT add_compression_policy(
    'marketdata.depth_events',
    INTERVAL '1 day'
);

-- Сжатие для агрегатов (старше 7 дней)
SELECT add_compression_policy(
    'marketdata.bt_1s',
    INTERVAL '7 days'
);

SELECT add_compression_policy(
    'marketdata.trade_1s',
    INTERVAL '7 days'
);

-- ===============================================
-- RETENTION POLICIES
-- ===============================================

-- Raw данные: хранить 30 дней
SELECT add_retention_policy(
    'marketdata.book_ticker',
    INTERVAL '30 days'
);

SELECT add_retention_policy(
    'marketdata.trades',
    INTERVAL '30 days'
);

SELECT add_retention_policy(
    'marketdata.depth_events',
    INTERVAL '30 days'
);

-- Агрегаты: хранить 180 дней
SELECT add_retention_policy(
    'marketdata.bt_1s',
    INTERVAL '180 days'
);

SELECT add_retention_policy(
    'marketdata.trade_1s', 
    INTERVAL '180 days'
);

-- Features: хранить 90 дней
SELECT add_retention_policy(
    'marketdata.orderbook_topN',
    INTERVAL '90 days'
);

-- ===============================================
-- ДОПОЛНИТЕЛЬНЫЕ ИНДЕКСЫ
-- ===============================================

CREATE INDEX IF NOT EXISTS idx_orderbook_topN_time 
ON marketdata.orderbook_topN (symbol_id, ts_exchange);

CREATE INDEX IF NOT EXISTS idx_bt_1s_time 
ON marketdata.bt_1s (symbol_id, ts_second);

CREATE INDEX IF NOT EXISTS idx_trade_1s_time 
ON marketdata.trade_1s (symbol_id, ts_second);

-- ===============================================
-- CONTINUOUS AGGREGATES (Materialized Views)
-- ===============================================

-- Создаем непрерывный агрегат для bt_1s из book_ticker
CREATE MATERIALIZED VIEW IF NOT EXISTS marketdata.bt_1s_continuous
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 second', ts_exchange) AS ts_second,
    symbol_id,
    
    -- OHLC для mid price
    first(mid, ts_exchange) AS mid_open,
    max(mid) AS mid_high,
    min(mid) AS mid_low,
    last(mid, ts_exchange) AS mid_close,
    
    -- Статистика спреда
    avg(spread) AS spread_mean,
    stddev(spread) AS spread_std,
    min(spread) AS spread_min,
    max(spread) AS spread_max,
    
    count(*) AS total_updates
FROM marketdata.book_ticker
GROUP BY ts_second, symbol_id;

-- Refresh policy для continuous aggregate (каждые 30 секунд)
SELECT add_continuous_aggregate_policy(
    'marketdata.bt_1s_continuous',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '30 seconds',
    schedule_interval => INTERVAL '30 seconds'
);

COMMENT ON MATERIALIZED VIEW marketdata.bt_1s_continuous IS 
'Автоматический агрегат book_ticker данных по секундам';

-- ===============================================
-- СТАТИСТИКА И ИНФОРМАЦИЯ
-- ===============================================

-- Показать информацию о hypertables
SELECT 
    hypertable_schema,
    hypertable_name,
    compression_enabled,
    compressed_chunks,
    uncompressed_chunks
FROM timescaledb_information.hypertables 
WHERE hypertable_schema = 'marketdata';

-- Показать политики retention
SELECT 
    hypertable_schema,
    hypertable_name, 
    drop_after
FROM timescaledb_information.drop_chunks_policies
WHERE hypertable_schema = 'marketdata';

-- Показать политики compression
SELECT 
    hypertable_schema,
    hypertable_name,
    compress_after
FROM timescaledb_information.compression_settings
WHERE hypertable_schema = 'marketdata';

NOTICE 'TimescaleDB миграция завершена успешно!';