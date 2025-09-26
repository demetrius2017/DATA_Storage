-- ===============================================
-- 🗄️ MARKET DATA SCHEMA DDL for PostgreSQL/TimescaleDB
-- ===============================================
-- 
-- Создание схемы для сбора реальных market data
-- по 200 торговым парам с Binance
--
-- Требования:
-- - PostgreSQL 13+
-- - TimescaleDB extension (рекомендуется)
-- - Достаточно места для 30+ дней данных
-- ===============================================

-- Включение TimescaleDB (если доступно)
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Создание схемы
CREATE SCHEMA IF NOT EXISTS marketdata;

-- ===============================================
-- 1. СПРАВОЧНИК СИМВОЛОВ
-- ===============================================

CREATE TABLE marketdata.symbols (
    id bigserial PRIMARY KEY,
    exchange text NOT NULL,              -- 'binance-futures', 'binance-spot'
    symbol text NOT NULL,                -- 'BTCUSDT', 'ETHUSDT', 'SOLUSDT'
    instrument_type text,                -- 'perp', 'spot', 'option'
    base_asset text,                     -- 'BTC', 'ETH', 'SOL'
    quote_asset text,                    -- 'USDT', 'BUSD', 'BTC'
    is_active boolean DEFAULT true,
    tick_size double precision,          -- Минимальный шаг цены
    lot_size double precision,           -- Минимальный размер ордера
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    UNIQUE (exchange, symbol)
);

COMMENT ON TABLE marketdata.symbols IS 'Справочник торговых символов и инструментов';
COMMENT ON COLUMN marketdata.symbols.exchange IS 'Биржа: binance-futures, binance-spot';
COMMENT ON COLUMN marketdata.symbols.symbol IS 'Торговая пара: BTCUSDT, ETHUSDT';
COMMENT ON COLUMN marketdata.symbols.instrument_type IS 'Тип инструмента: perp, spot';

-- Индексы для symbols
CREATE INDEX idx_symbols_exchange ON marketdata.symbols (exchange);
CREATE INDEX idx_symbols_active ON marketdata.symbols (is_active) WHERE is_active = true;

-- ===============================================
-- 2. BOOK TICKER (TOP-OF-BOOK DATA)
-- ===============================================

CREATE TABLE marketdata.book_ticker (
    ts_exchange timestamptz NOT NULL,    -- Время события на бирже (UTC)
    ts_ingest timestamptz NOT NULL DEFAULT now(),  -- Время получения данных
    symbol_id bigint NOT NULL REFERENCES marketdata.symbols(id),
    update_id bigint,                    -- Update ID от биржи (если есть)
    best_bid double precision NOT NULL,  -- Лучшая цена покупки
    best_ask double precision NOT NULL,  -- Лучшая цена продажи
    bid_qty double precision NOT NULL,   -- Объём на лучшей покупке
    ask_qty double precision NOT NULL,   -- Объём на лучшей продаже
    spread double precision NOT NULL,    -- Спред: ask - bid
    mid double precision NOT NULL,       -- Средняя цена: (ask + bid) / 2
    spread_bps double precision GENERATED ALWAYS AS (
        CASE WHEN mid > 0 THEN (spread / mid) * 10000 ELSE NULL END
    ) STORED,                           -- Спред в базисных пунктах
    
    -- Составной первичный ключ для уникальности
    PRIMARY KEY (symbol_id, ts_exchange, COALESCE(update_id, 0))
);

COMMENT ON TABLE marketdata.book_ticker IS 'Поток top-of-book данных (лучшие bid/ask)';
COMMENT ON COLUMN marketdata.book_ticker.ts_exchange IS 'Время события на бирже (UTC из E/1000)';
COMMENT ON COLUMN marketdata.book_ticker.spread_bps IS 'Спред в базисных пунктах (автоматический расчёт)';

-- Индексы для book_ticker
CREATE INDEX idx_book_ticker_time ON marketdata.book_ticker (symbol_id, ts_exchange);
CREATE INDEX idx_book_ticker_ingest ON marketdata.book_ticker (ts_ingest);

-- ===============================================
-- 3. АГРЕГИРОВАННЫЕ СДЕЛКИ
-- ===============================================

CREATE TABLE marketdata.trades (
    ts_exchange timestamptz NOT NULL,    -- Время сделки на бирже
    ts_ingest timestamptz NOT NULL DEFAULT now(),
    symbol_id bigint NOT NULL REFERENCES marketdata.symbols(id),
    agg_trade_id bigint NOT NULL,        -- ID агрегированной сделки
    price double precision NOT NULL,     -- Цена сделки
    qty double precision NOT NULL,       -- Объём сделки
    is_buyer_maker boolean NOT NULL,     -- true = покупатель был maker
    trade_value double precision GENERATED ALWAYS AS (price * qty) STORED,
    
    PRIMARY KEY (symbol_id, agg_trade_id)
);

COMMENT ON TABLE marketdata.trades IS 'Агрегированные сделки с биржи';
COMMENT ON COLUMN marketdata.trades.is_buyer_maker IS 'true = покупатель был maker (пассивная сторона)';
COMMENT ON COLUMN marketdata.trades.trade_value IS 'Объём сделки в quote валюте (price * qty)';

-- Индексы для trades
CREATE INDEX idx_trades_time ON marketdata.trades (symbol_id, ts_exchange);
CREATE INDEX idx_trades_side ON marketdata.trades (symbol_id, is_buyer_maker, ts_exchange);

-- ===============================================
-- 3.1. MARK PRICE (1s updates)
-- ===============================================

CREATE TABLE IF NOT EXISTS marketdata.mark_price (
    ts_exchange timestamptz NOT NULL,
    ts_ingest timestamptz NOT NULL DEFAULT now(),
    symbol_id bigint NOT NULL REFERENCES marketdata.symbols(id),
    event_type text,                      -- 'markPriceUpdate'
    mark_price double precision,          -- p
    index_price double precision,         -- i
    est_settlement_price double precision,-- P (если присутствует)
    funding_rate double precision,        -- r (если присутствует)
    next_funding_time timestamptz,        -- T (мс → timestamptz)

    PRIMARY KEY (symbol_id, ts_exchange)
);

COMMENT ON TABLE marketdata.mark_price IS 'Mark price / index price updates (@markPrice@1s)';

CREATE INDEX IF NOT EXISTS idx_mark_price_time ON marketdata.mark_price (symbol_id, ts_exchange);

-- ===============================================
-- 3.2. FORCE ORDERS (Liquidations)
-- ===============================================

CREATE TABLE IF NOT EXISTS marketdata.force_orders (
    ts_exchange timestamptz NOT NULL,
    ts_ingest timestamptz NOT NULL DEFAULT now(),
    symbol_id bigint NOT NULL REFERENCES marketdata.symbols(id),
    side text,                            -- 'BUY' / 'SELL' (S)
    price double precision,               -- p
    qty double precision,                 -- q
    raw jsonb NOT NULL,                   -- исходный объект события ('o')

    -- В силу отсутствия строгого ID используем составной ключ для идемпотентности
    PRIMARY KEY (symbol_id, ts_exchange, side, price, qty)
);

COMMENT ON TABLE marketdata.force_orders IS 'Liquidation orders stream (@forceOrder)';

CREATE INDEX IF NOT EXISTS idx_force_orders_time ON marketdata.force_orders (symbol_id, ts_exchange);

-- ===============================================
-- 4. СОБЫТИЯ ГЛУБИНЫ РЫНКА (RAW)
-- ===============================================

CREATE TABLE marketdata.depth_events (
    ts_exchange timestamptz NOT NULL,
    ts_ingest timestamptz NOT NULL DEFAULT now(),
    symbol_id bigint NOT NULL REFERENCES marketdata.symbols(id),
    first_update_id bigint NOT NULL,     -- Первый update ID в событии
    final_update_id bigint NOT NULL,     -- Последний update ID в событии  
    prev_final_update_id bigint,         -- Предыдущий final update ID
    bids jsonb NOT NULL,                 -- Массив [[price, qty], ...] для bid
    asks jsonb NOT NULL,                 -- Массив [[price, qty], ...] для ask
    bids_count int GENERATED ALWAYS AS (jsonb_array_length(bids)) STORED,
    asks_count int GENERATED ALWAYS AS (jsonb_array_length(asks)) STORED,
    
    -- Важно: для Timescale уникальные ключи на гипертаблицах должны включать колонку партиционирования (ts_exchange)
    PRIMARY KEY (symbol_id, ts_exchange, final_update_id)
);

COMMENT ON TABLE marketdata.depth_events IS 'Raw события изменения глубины рынка';
COMMENT ON COLUMN marketdata.depth_events.bids IS 'Массив изменений bid [[price, qty], ...]';
COMMENT ON COLUMN marketdata.depth_events.asks IS 'Массив изменений ask [[price, qty], ...]';

-- Индексы для depth_events
CREATE INDEX idx_depth_events_time ON marketdata.depth_events (symbol_id, ts_exchange);
CREATE INDEX idx_depth_events_update_id ON marketdata.depth_events (symbol_id, final_update_id);
-- Дублирующий уникальный индекс для ускорения ON CONFLICT, если PK уже определяет уникальность
-- CREATE UNIQUE INDEX IF NOT EXISTS uq_depth_events_symbol_time_final ON marketdata.depth_events (symbol_id, ts_exchange, final_update_id);

-- ===============================================
-- 5. ORDERBOOK TOP-N (PROCESSED FEATURES)
-- ===============================================

CREATE TABLE marketdata.orderbook_topN (
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

COMMENT ON TABLE marketdata.orderbook_topN IS 'Обработанные топ-N уровней orderbook с фичами';
COMMENT ON COLUMN marketdata.orderbook_topN.microprice IS 'Микроцена по алгоритму Lee-Ready';
COMMENT ON COLUMN marketdata.orderbook_topN.i1 IS 'Immediate impact для 1 уровня';
COMMENT ON COLUMN marketdata.orderbook_topN.ofi_1s IS 'Order Flow Imbalance за 1 секунду';

-- Индексы для orderbook_topN
CREATE INDEX idx_orderbook_topN_time ON marketdata.orderbook_topN (symbol_id, ts_exchange);

-- ===============================================
-- 6. АГРЕГАТЫ BOOK_TICKER (1 СЕКУНДА)
-- ===============================================

CREATE TABLE marketdata.bt_1s (
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
    bid_qty_mean double precision,
    ask_qty_mean double precision,
    
    -- Количество обновлений
    updates_count int,
    
    -- Volume weighted mid
    volume_weighted_mid double precision,
    
    PRIMARY KEY (symbol_id, ts_second)
);

COMMENT ON TABLE marketdata.bt_1s IS 'Агрегаты book_ticker данных по секундам';

-- Индексы для bt_1s
CREATE INDEX idx_bt_1s_time ON marketdata.bt_1s (symbol_id, ts_second);

-- ===============================================
-- 7. АГРЕГАТЫ СДЕЛОК (1 СЕКУНДА)  
-- ===============================================

CREATE TABLE marketdata.trade_1s (
    ts_second timestamptz NOT NULL,
    symbol_id bigint NOT NULL REFERENCES marketdata.symbols(id),
    
    -- Количество и объёмы
    trade_count int NOT NULL DEFAULT 0,
    volume_sum double precision NOT NULL DEFAULT 0,
    value_sum double precision NOT NULL DEFAULT 0,  -- В quote валюте
    
    -- VWAP
    vwap double precision,
    
    -- Разделение по сторонам
    buy_volume double precision NOT NULL DEFAULT 0,   -- Агрессивные покупки
    sell_volume double precision NOT NULL DEFAULT 0,  -- Агрессивные продажи
    buy_count int NOT NULL DEFAULT 0,
    sell_count int NOT NULL DEFAULT 0,
    
    -- Дисбаланс
    imbalance_ratio double precision GENERATED ALWAYS AS (
        CASE WHEN (buy_volume + sell_volume) > 0 
             THEN (buy_volume - sell_volume) / (buy_volume + sell_volume)
             ELSE 0 END
    ) STORED,
    
    -- Ценовые характеристики
    price_min double precision,
    price_max double precision,
    
    PRIMARY KEY (symbol_id, ts_second)
);

COMMENT ON TABLE marketdata.trade_1s IS 'Агрегаты сделок по секундам';
COMMENT ON COLUMN marketdata.trade_1s.imbalance_ratio IS 'Дисбаланс покупок/продаж: (buy-sell)/(buy+sell)';

-- Индексы для trade_1s
CREATE INDEX idx_trade_1s_time ON marketdata.trade_1s (symbol_id, ts_second);

-- ===============================================
-- 8. СЛУЖЕБНЫЕ ТАБЛИЦЫ
-- ===============================================

-- Отслеживание offsets для надёжности
CREATE TABLE marketdata.ingestion_offsets (
    symbol_id bigint NOT NULL REFERENCES marketdata.symbols(id),
    stream_type text NOT NULL,           -- 'bookTicker', 'aggTrade', 'depth'
    last_update_id bigint,
    last_event_time timestamptz,
    last_processed_at timestamptz DEFAULT now(),
    
    PRIMARY KEY (symbol_id, stream_type)
);

COMMENT ON TABLE marketdata.ingestion_offsets IS 'Отслеживание обработанных событий для recovery';

-- Статистика ingestion
CREATE TABLE marketdata.ingestion_stats (
    date_hour timestamptz NOT NULL,      -- Округлено до часа
    symbol_id bigint NOT NULL REFERENCES marketdata.symbols(id),
    stream_type text NOT NULL,
    events_processed bigint DEFAULT 0,
    events_failed bigint DEFAULT 0,
    last_latency_ms double precision,    -- Задержка обработки
    
    PRIMARY KEY (date_hour, symbol_id, stream_type)
);

COMMENT ON TABLE marketdata.ingestion_stats IS 'Статистика обработки событий по часам';

-- ===============================================
-- 9. TIMESCALEDB HYPERTABLES (если доступно)
-- ===============================================

-- Проверяем доступность TimescaleDB и создаём hypertables
DO $$
BEGIN
    -- Проверяем наличие TimescaleDB
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        
        -- Создаём hypertables с партиционированием по времени и symbol_id
        PERFORM create_hypertable('marketdata.book_ticker', 'ts_exchange',
            partitioning_column => 'symbol_id', 
            number_partitions => 16,
            if_not_exists => TRUE);
            
        PERFORM create_hypertable('marketdata.trades', 'ts_exchange',
            partitioning_column => 'symbol_id',
            number_partitions => 16, 
            if_not_exists => TRUE);

        PERFORM create_hypertable('marketdata.mark_price', 'ts_exchange',
            partitioning_column => 'symbol_id',
            number_partitions => 8,
            if_not_exists => TRUE);
            
        PERFORM create_hypertable('marketdata.depth_events', 'ts_exchange',
            partitioning_column => 'symbol_id',
            number_partitions => 8,  -- Меньше партиций для depth (более объёмная таблица)
            if_not_exists => TRUE);

        PERFORM create_hypertable('marketdata.force_orders', 'ts_exchange',
            partitioning_column => 'symbol_id',
            number_partitions => 8,
            if_not_exists => TRUE);
            
        PERFORM create_hypertable('marketdata.orderbook_topN', 'ts_exchange',
            partitioning_column => 'symbol_id',
            number_partitions => 16,
            if_not_exists => TRUE);
            
        PERFORM create_hypertable('marketdata.bt_1s', 'ts_second',
            partitioning_column => 'symbol_id',
            number_partitions => 8,
            if_not_exists => TRUE);
            
        PERFORM create_hypertable('marketdata.trade_1s', 'ts_second', 
            partitioning_column => 'symbol_id',
            number_partitions => 8,
            if_not_exists => TRUE);
            
        RAISE NOTICE 'TimescaleDB hypertables созданы успешно';
        
    ELSE
        RAISE NOTICE 'TimescaleDB не найден, используются обычные таблицы PostgreSQL';
    END IF;
END
$$;

-- ===============================================
-- 10. ПОЛИТИКИ RETENTION И COMPRESSION
-- ===============================================

-- Retention policies (если TimescaleDB доступен)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        
        -- Retention: автоматическое удаление старых данных
        PERFORM add_retention_policy('marketdata.book_ticker', INTERVAL '30 days', if_not_exists => TRUE);
        PERFORM add_retention_policy('marketdata.trades', INTERVAL '30 days', if_not_exists => TRUE);
    PERFORM add_retention_policy('marketdata.mark_price', INTERVAL '30 days', if_not_exists => TRUE);
        PERFORM add_retention_policy('marketdata.depth_events', INTERVAL '7 days', if_not_exists => TRUE);
    PERFORM add_retention_policy('marketdata.force_orders', INTERVAL '30 days', if_not_exists => TRUE);
        PERFORM add_retention_policy('marketdata.orderbook_topN', INTERVAL '30 days', if_not_exists => TRUE);
        PERFORM add_retention_policy('marketdata.bt_1s', INTERVAL '180 days', if_not_exists => TRUE);
        PERFORM add_retention_policy('marketdata.trade_1s', INTERVAL '180 days', if_not_exists => TRUE);
        
        -- Compression: автоматическое сжатие старых партиций
        PERFORM add_compression_policy('marketdata.book_ticker', INTERVAL '7 days', if_not_exists => TRUE);
        PERFORM add_compression_policy('marketdata.trades', INTERVAL '7 days', if_not_exists => TRUE);
    PERFORM add_compression_policy('marketdata.mark_price', INTERVAL '7 days', if_not_exists => TRUE);
        PERFORM add_compression_policy('marketdata.depth_events', INTERVAL '1 day', if_not_exists => TRUE);
    PERFORM add_compression_policy('marketdata.force_orders', INTERVAL '7 days', if_not_exists => TRUE);
        PERFORM add_compression_policy('marketdata.orderbook_topN', INTERVAL '7 days', if_not_exists => TRUE);
        PERFORM add_compression_policy('marketdata.bt_1s', INTERVAL '30 days', if_not_exists => TRUE);
        PERFORM add_compression_policy('marketdata.trade_1s', INTERVAL '30 days', if_not_exists => TRUE);
        
        RAISE NOTICE 'TimescaleDB retention и compression policies настроены';
        
    END IF;
END
$$;

-- ===============================================
-- 11. НАЧАЛЬНЫЕ ДАННЫЕ
-- ===============================================

-- Вставляем основные торговые пары для тестирования
INSERT INTO marketdata.symbols (exchange, symbol, instrument_type, base_asset, quote_asset) VALUES
('binance-futures', 'BTCUSDT', 'perp', 'BTC', 'USDT'),
('binance-futures', 'ETHUSDT', 'perp', 'ETH', 'USDT'),
('binance-futures', 'SOLUSDT', 'perp', 'SOL', 'USDT'),
('binance-futures', 'ADAUSDT', 'perp', 'ADA', 'USDT'),
('binance-futures', 'DOTUSDT', 'perp', 'DOT', 'USDT')
ON CONFLICT (exchange, symbol) DO NOTHING;

-- ===============================================
-- 12. ПОЛЕЗНЫЕ VIEWS
-- ===============================================

-- View для быстрого доступа к "вчерашним" данным
CREATE OR REPLACE VIEW marketdata.yesterday_dataset AS
SELECT 
    bt.ts_second,
    s.symbol,
    bt.mid_open,
    bt.mid_high, 
    bt.mid_low,
    bt.mid_close,
    bt.spread_mean,
    tr.trade_count,
    tr.volume_sum,
    tr.vwap,
    tr.imbalance_ratio,
    -- Добавляем lag features
    LAG(bt.mid_close, 1) OVER (PARTITION BY bt.symbol_id ORDER BY bt.ts_second) AS prev_mid,
    LAG(tr.imbalance_ratio, 1) OVER (PARTITION BY bt.symbol_id ORDER BY bt.ts_second) AS prev_imbalance
FROM marketdata.bt_1s bt
LEFT JOIN marketdata.trade_1s tr USING (symbol_id, ts_second)
LEFT JOIN marketdata.symbols s ON bt.symbol_id = s.id
WHERE bt.ts_second >= date_trunc('day', now() - INTERVAL '1 day')
  AND bt.ts_second < date_trunc('day', now())
  AND s.is_active = true;

COMMENT ON VIEW marketdata.yesterday_dataset IS 'View для быстрого доступа к данным за вчера для ML';

-- View для мониторинга статистики
CREATE OR REPLACE VIEW marketdata.ingestion_health AS
SELECT 
    s.symbol,
    ios.stream_type,
    ios.last_event_time,
    ios.last_processed_at,
    EXTRACT(EPOCH FROM (now() - ios.last_processed_at)) AS seconds_since_last,
    ist.events_processed,
    ist.events_failed,
    ist.last_latency_ms
FROM marketdata.ingestion_offsets ios
LEFT JOIN marketdata.symbols s ON ios.symbol_id = s.id
LEFT JOIN marketdata.ingestion_stats ist ON (
    ios.symbol_id = ist.symbol_id 
    AND ios.stream_type = ist.stream_type
    AND ist.date_hour = date_trunc('hour', now())
)
WHERE s.is_active = true
ORDER BY s.symbol, ios.stream_type;

COMMENT ON VIEW marketdata.ingestion_health IS 'Мониторинг состояния ingestion процесса';

-- ===============================================
-- ЗАВЕРШЕНИЕ
-- ===============================================

-- Включаем автовакуум и статистику
ALTER SYSTEM SET track_activities = on;
ALTER SYSTEM SET track_counts = on;
ALTER SYSTEM SET track_io_timing = on;

-- Применяем настройки
SELECT pg_reload_conf();

-- Финальное сообщение
DO $$
BEGIN
    RAISE NOTICE '✅ Market Data Schema успешно создана!';
    RAISE NOTICE 'Схема: marketdata';
    RAISE NOTICE 'Таблицы: symbols, book_ticker, trades, depth_events, orderbook_topN, bt_1s, trade_1s';
    RAISE NOTICE 'Views: yesterday_dataset, ingestion_health';
    RAISE NOTICE 'TimescaleDB: %', CASE WHEN EXISTS(SELECT 1 FROM pg_extension WHERE extname='timescaledb') THEN 'Включён' ELSE 'Не найден' END;
END
$$;