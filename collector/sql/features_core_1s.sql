-- ===============================================
-- 📦 FEATURES: CORE 1s TABLE
-- ===============================================
-- Сводная таблица 1s-признаков из bt_1s и trade_1s для быстрого лоадинга ML

CREATE SCHEMA IF NOT EXISTS feature;

CREATE TABLE IF NOT EXISTS feature.core_1s (
    ts_second timestamptz NOT NULL,
    symbol_id bigint NOT NULL REFERENCES marketdata.symbols(id),

    -- book_ticker агрегаты
    mid_open double precision,
    mid_high double precision,
    mid_low double precision,
    mid_close double precision,
    spread_mean double precision,
    spread_std double precision,
    bid_qty_mean double precision,
    ask_qty_mean double precision,
    updates_count int,

    -- trade агрегаты
    trade_count int,
    volume_sum double precision,
    value_sum double precision,
    vwap double precision,
    buy_volume double precision,
    sell_volume double precision,
    buy_count int,
    sell_count int,
    imbalance_ratio double precision,
    price_min double precision,
    price_max double precision,

    PRIMARY KEY (symbol_id, ts_second)
);

CREATE INDEX IF NOT EXISTS idx_core_1s_time ON feature.core_1s (symbol_id, ts_second);

-- Материализация/заполнение этой таблицы выполняется агрегатором в collector/features/core_1s_aggregator.py
