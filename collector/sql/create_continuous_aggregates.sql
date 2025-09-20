-- ==========================================
-- CONTINUOUS AGGREGATES FOR TIMESCALEDB
-- ==========================================
-- Решение проблемы: "⚠️ Отсутствие aggregates: Нет автоматического создания bt_1s/trade_1s таблиц"
-- Создает непрерывные агрегаты для book_ticker и trades с автоматическим обновлением

-- ==========================================
-- 1. BOOK TICKER 1-SECOND AGGREGATES
-- ==========================================

-- Создаем непрерывный агрегат для book_ticker с группировкой по секундам
CREATE MATERIALIZED VIEW bt_1s_continuous
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 second', ts_exchange) as ts_bucket,
    symbol,
    
    -- Статистика по bid
    first(bid_price, ts_exchange) as bid_open,
    last(bid_price, ts_exchange) as bid_close,
    max(bid_price) as bid_high,
    min(bid_price) as bid_low,
    avg(bid_price::numeric) as bid_avg,
    
    -- Статистика по ask
    first(ask_price, ts_exchange) as ask_open,
    last(ask_price, ts_exchange) as ask_close,
    max(ask_price) as ask_high,
    min(ask_price) as ask_low,
    avg(ask_price::numeric) as ask_avg,
    
    -- Статистика по количеству
    first(bid_qty, ts_exchange) as bid_qty_open,
    last(bid_qty, ts_exchange) as bid_qty_close,
    max(bid_qty) as bid_qty_max,
    min(bid_qty) as bid_qty_min,
    avg(bid_qty::numeric) as bid_qty_avg,
    
    first(ask_qty, ts_exchange) as ask_qty_open,
    last(ask_qty, ts_exchange) as ask_qty_close,
    max(ask_qty) as ask_qty_max,
    min(ask_qty) as ask_qty_min,
    avg(ask_qty::numeric) as ask_qty_avg,
    
    -- Spread и метрики
    avg((ask_price - bid_price)::numeric) as spread_avg,
    max(ask_price - bid_price) as spread_max,
    min(ask_price - bid_price) as spread_min,
    
    -- Количество тиков
    count(*) as tick_count,
    
    -- Микропричина (простая версия)
    avg((bid_price + ask_price)::numeric / 2) as microprice_avg
    
FROM book_ticker
GROUP BY ts_bucket, symbol;

-- Создаем индекс для быстрого доступа
CREATE INDEX ON bt_1s_continuous (ts_bucket, symbol);

-- ==========================================
-- 2. TRADES 1-SECOND AGGREGATES
-- ==========================================

-- Создаем непрерывный агрегат для trades с группировкой по секундам
CREATE MATERIALIZED VIEW trade_1s_continuous
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 second', ts_exchange) as ts_bucket,
    symbol,
    
    -- OHLC для цены
    first(price, ts_exchange) as price_open,
    last(price, ts_exchange) as price_close,
    max(price) as price_high,
    min(price) as price_low,
    
    -- Объемы
    sum(quantity::numeric) as volume,
    sum(quote_quantity::numeric) as quote_volume,
    count(*) as trade_count,
    
    -- Статистика по размерам сделок
    avg(quantity::numeric) as avg_trade_size,
    max(quantity) as max_trade_size,
    min(quantity) as min_trade_size,
    
    -- Buy/Sell анализ
    sum(CASE WHEN is_buyer_maker = false THEN quantity::numeric ELSE 0 END) as buy_volume,
    sum(CASE WHEN is_buyer_maker = true THEN quantity::numeric ELSE 0 END) as sell_volume,
    count(CASE WHEN is_buyer_maker = false THEN 1 END) as buy_count,
    count(CASE WHEN is_buyer_maker = true THEN 1 END) as sell_count,
    
    -- VWAP (Volume Weighted Average Price)
    sum(price::numeric * quantity::numeric) / sum(quantity::numeric) as vwap,
    
    -- Агрессивность торгов
    (count(CASE WHEN is_buyer_maker = false THEN 1 END)::numeric / count(*)::numeric) as buy_ratio

FROM trades
GROUP BY ts_bucket, symbol;

-- Создаем индекс для быстрого доступа
CREATE INDEX ON trade_1s_continuous (ts_bucket, symbol);

-- ==========================================
-- 3. DEPTH EVENTS 1-SECOND AGGREGATES
-- ==========================================

-- Создаем непрерывный агрегат для depth events (для расчета OFI)
CREATE MATERIALIZED VIEW depth_1s_continuous
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 second', ts_exchange) as ts_bucket,
    symbol,
    
    -- Статистика по изменениям orderbook
    count(*) as update_count,
    
    -- Последнее состояние orderbook в секунду
    last(data->'bids'->0->0, ts_exchange) as last_bid_price,
    last(data->'asks'->0->0, ts_exchange) as last_ask_price,
    last(data->'bids'->0->1, ts_exchange) as last_bid_qty,
    last(data->'asks'->0->1, ts_exchange) as last_ask_qty,
    
    -- Первое состояние для расчета изменений
    first(data->'bids'->0->0, ts_exchange) as first_bid_price,
    first(data->'asks'->0->0, ts_exchange) as first_ask_price,
    first(data->'bids'->0->1, ts_exchange) as first_bid_qty,
    first(data->'asks'->0->1, ts_exchange) as first_ask_qty
    
FROM depth_events
GROUP BY ts_bucket, symbol;

-- Создаем индекс для быстрого доступа
CREATE INDEX ON depth_1s_continuous (ts_bucket, symbol);

-- ==========================================
-- 4. АВТОМАТИЧЕСКОЕ ОБНОВЛЕНИЕ ПОЛИТИК
-- ==========================================

-- Настраиваем автоматическое обновление агрегатов каждые 30 секунд
SELECT add_continuous_aggregate_policy('bt_1s_continuous',
    start_offset => INTERVAL '2 hours',
    end_offset => INTERVAL '30 seconds',
    schedule_interval => INTERVAL '30 seconds');

SELECT add_continuous_aggregate_policy('trade_1s_continuous',
    start_offset => INTERVAL '2 hours',
    end_offset => INTERVAL '30 seconds',
    schedule_interval => INTERVAL '30 seconds');

SELECT add_continuous_aggregate_policy('depth_1s_continuous',
    start_offset => INTERVAL '2 hours',
    end_offset => INTERVAL '30 seconds',
    schedule_interval => INTERVAL '30 seconds');

-- ==========================================
-- 5. ПРОВЕРОЧНЫЕ ЗАПРОСЫ
-- ==========================================

-- Показать информацию о созданных агрегатах
SELECT view_name, materialized_only, finalized 
FROM timescaledb_information.continuous_aggregates;

-- Показать статус политик обновления
SELECT application_name, hypertable_name, config 
FROM timescaledb_information.jobs 
WHERE application_name LIKE '%continuous_aggregate%';

-- ==========================================
-- 6. ВСПОМОГАТЕЛЬНЫЕ ПРЕДСТАВЛЕНИЯ
-- ==========================================

-- Создаем удобное представление для объединения всех метрик
CREATE VIEW market_data_1s AS
SELECT 
    bt.ts_bucket,
    bt.symbol,
    
    -- Book ticker метрики
    bt.bid_close,
    bt.ask_close,
    bt.spread_avg,
    bt.microprice_avg,
    bt.tick_count as bt_ticks,
    
    -- Trade метрики
    tr.price_close,
    tr.volume,
    tr.trade_count,
    tr.vwap,
    tr.buy_ratio,
    
    -- Depth метрики
    dp.update_count as depth_updates
    
FROM bt_1s_continuous bt
LEFT JOIN trade_1s_continuous tr ON bt.ts_bucket = tr.ts_bucket AND bt.symbol = tr.symbol
LEFT JOIN depth_1s_continuous dp ON bt.ts_bucket = dp.ts_bucket AND bt.symbol = dp.symbol
ORDER BY bt.ts_bucket DESC, bt.symbol;

-- Индекс для общего представления
CREATE INDEX ON bt_1s_continuous (symbol, ts_bucket DESC);
CREATE INDEX ON trade_1s_continuous (symbol, ts_bucket DESC);
CREATE INDEX ON depth_1s_continuous (symbol, ts_bucket DESC);

-- ==========================================
-- ГОТОВО! СИСТЕМА АВТОМАТИЧЕСКИХ АГРЕГАТОВ СОЗДАНА
-- ==========================================
-- ✅ Continuous aggregates обновляются автоматически каждые 30 секунд
-- ✅ Данные группируются по секундам для всех основных метрик  
-- ✅ Созданы индексы для быстрого доступа
-- ✅ Объединенное представление market_data_1s для удобного анализа