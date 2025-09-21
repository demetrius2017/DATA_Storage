-- ===============================================
-- 📊 ПРИМЕРЫ РЕАЛЬНЫХ ДАННЫХ ORDERBOOK
-- ===============================================

-- 1. ПРИМЕР ДАННЫХ BOOK TICKER (лучшие bid/ask цены)
-- Эти данные собираются каждые ~100-500ms для каждого символа

SELECT 
    'BTCUSDT' as symbol,
    '2025-09-20 16:30:15.123456+00'::timestamptz as ts_exchange,
    '2025-09-20 16:30:15.125000+00'::timestamptz as ts_ingest,
    63500.50 as best_bid,
    63500.51 as best_ask,
    0.15000 as bid_qty,
    0.23000 as ask_qty,
    0.01 as spread,
    63500.505 as mid_price,
    12345678 as update_id

UNION ALL

SELECT 
    'ETHUSDT' as symbol,
    '2025-09-20 16:30:15.234567+00'::timestamptz as ts_exchange,
    '2025-09-20 16:30:15.236000+00'::timestamptz as ts_ingest,
    2645.75 as best_bid,
    2645.76 as best_ask,
    1.25000 as bid_qty,
    0.89000 as ask_qty,
    0.01 as spread,
    2645.755 as mid_price,
    87654321 as update_id

UNION ALL

SELECT 
    'SOLUSDT' as symbol,
    '2025-09-20 16:30:15.345678+00'::timestamptz as ts_exchange,
    '2025-09-20 16:30:15.347000+00'::timestamptz as ts_ingest,
    142.35 as best_bid,
    142.36 as best_ask,
    25.50000 as bid_qty,
    18.75000 as ask_qty,
    0.01 as spread,
    142.355 as mid_price,
    11223344 as update_id;

-- ===============================================
-- 2. ПРИМЕР ДАННЫХ DEPTH (полный стакан заявок)
-- ===============================================

-- Данные по bid стороне (покупатели)
INSERT INTO marketdata.orderbook_depth (
    symbol, ts_exchange, ts_ingest, side, price_level, price, quantity, update_id
) VALUES 
('BTCUSDT', '2025-09-20 16:30:15.123456+00', now(), 'bid', 0, 63500.50, 0.15000, 12345678),
('BTCUSDT', '2025-09-20 16:30:15.123456+00', now(), 'bid', 1, 63500.49, 0.08500, 12345678),
('BTCUSDT', '2025-09-20 16:30:15.123456+00', now(), 'bid', 2, 63500.48, 0.12000, 12345678),
('BTCUSDT', '2025-09-20 16:30:15.123456+00', now(), 'bid', 3, 63500.47, 0.25000, 12345678),
('BTCUSDT', '2025-09-20 16:30:15.123456+00', now(), 'bid', 4, 63500.46, 0.35000, 12345678),

-- Данные по ask стороне (продавцы)
('BTCUSDT', '2025-09-20 16:30:15.123456+00', now(), 'ask', 0, 63500.51, 0.23000, 12345678),
('BTCUSDT', '2025-09-20 16:30:15.123456+00', now(), 'ask', 1, 63500.52, 0.18000, 12345678),
('BTCUSDT', '2025-09-20 16:30:15.123456+00', now(), 'ask', 2, 63500.53, 0.09500, 12345678),
('BTCUSDT', '2025-09-20 16:30:15.123456+00', now(), 'ask', 3, 63500.54, 0.41000, 12345678),
('BTCUSDT', '2025-09-20 16:30:15.123456+00', now(), 'ask', 4, 63500.55, 0.15500, 12345678);

-- ===============================================
-- 3. ПРИМЕР АГРЕГИРОВАННЫХ ДАННЫХ ПО 1 СЕКУНДЕ
-- ===============================================

-- Данные bt_1s (book ticker агрегированные за 1 секунду)
SELECT 
    '2025-09-20 16:30:15+00'::timestamptz as bucket,
    'BTCUSDT' as symbol,
    63500.45 as open_bid,
    63500.55 as high_bid,
    63500.42 as low_bid,
    63500.50 as close_bid,
    63500.52 as open_ask,
    63500.58 as high_ask,
    63500.48 as low_ask,
    63500.51 as close_ask,
    63500.495 as avg_mid,
    0.08 as avg_spread,
    145 as update_count

UNION ALL

SELECT 
    '2025-09-20 16:30:16+00'::timestamptz as bucket,
    'BTCUSDT' as symbol,
    63500.50 as open_bid,
    63500.62 as high_bid,
    63500.48 as low_bid,
    63500.58 as close_bid,
    63500.51 as open_ask,
    63500.63 as high_ask,
    63500.49 as low_ask,
    63500.59 as close_ask,
    63500.585 as avg_mid,
    0.09 as avg_spread,
    158 as update_count;

-- ===============================================
-- 4. ЗАПРОСЫ ДЛЯ АНАЛИЗА СОБРАННЫХ ДАННЫХ
-- ===============================================

-- Проверка частоты обновлений (должно быть минимум 1 в минуту)
SELECT 
    symbol,
    count(*) as updates_count,
    min(ts_exchange) as first_update,
    max(ts_exchange) as last_update,
    extract(epoch from (max(ts_exchange) - min(ts_exchange)))/60 as duration_minutes,
    count(*) / (extract(epoch from (max(ts_exchange) - min(ts_exchange)))/60) as updates_per_minute
FROM marketdata.book_ticker 
WHERE ts_exchange > now() - interval '1 hour'
GROUP BY symbol
ORDER BY updates_per_minute DESC;

-- Проверка качества данных (нет NULL, корректные цены)
SELECT 
    symbol,
    count(*) as total_records,
    count(*) FILTER (WHERE best_bid IS NULL OR best_ask IS NULL) as null_prices,
    count(*) FILTER (WHERE best_bid <= 0 OR best_ask <= 0) as invalid_prices,
    count(*) FILTER (WHERE best_bid >= best_ask) as inverted_spread,
    count(*) FILTER (WHERE spread > best_ask * 0.01) as wide_spread,
    avg(spread) as avg_spread,
    avg(spread / best_ask * 100) as avg_spread_percent
FROM marketdata.book_ticker 
WHERE ts_exchange > now() - interval '1 hour'
GROUP BY symbol
ORDER BY symbol;

-- Проверка свежести данных (не старше 5 минут)
SELECT 
    symbol,
    max(ts_exchange) as last_update,
    extract(epoch from (now() - max(ts_exchange)))/60 as minutes_since_last_update,
    CASE 
        WHEN extract(epoch from (now() - max(ts_exchange)))/60 <= 5 THEN '✅ FRESH'
        WHEN extract(epoch from (now() - max(ts_exchange)))/60 <= 15 THEN '⚠️ STALE'
        ELSE '❌ OLD'
    END as data_status
FROM marketdata.book_ticker 
GROUP BY symbol
ORDER BY last_update DESC;

-- ===============================================
-- 5. СТАТИСТИКА ПО ОБЪЁМАМ ДАННЫХ
-- ===============================================

-- Объём данных по дням
SELECT 
    date_trunc('day', ts_exchange) as date,
    count(*) as total_records,
    count(DISTINCT symbol) as unique_symbols,
    pg_size_pretty(
        count(*) * (
            8 + 8 + 8 + 8 + 8 + 8 + 8 + 8 + 20  -- размер одной записи ~76 байт
        )
    ) as estimated_size
FROM marketdata.book_ticker 
WHERE ts_exchange > now() - interval '7 days'
GROUP BY date_trunc('day', ts_exchange)
ORDER BY date DESC;

-- Топ символов по активности
SELECT 
    symbol,
    count(*) as updates_count,
    min(ts_exchange) as first_seen,
    max(ts_exchange) as last_seen,
    count(*) / extract(epoch from (max(ts_exchange) - min(ts_exchange))) as updates_per_second
FROM marketdata.book_ticker 
WHERE ts_exchange > now() - interval '1 day'
GROUP BY symbol
HAVING count(*) > 100
ORDER BY updates_count DESC
LIMIT 20;

-- ===============================================
-- 6. ПРИМЕР FEATURE ENGINEERING ДАННЫХ
-- ===============================================

-- Расчет microprice и order flow imbalance
WITH features AS (
    SELECT 
        ts_exchange,
        symbol,
        best_bid,
        best_ask,
        bid_qty,
        ask_qty,
        -- Microprice (взвешенная средняя цена)
        (best_bid * ask_qty + best_ask * bid_qty) / (bid_qty + ask_qty) as microprice,
        -- Order Flow Imbalance
        (bid_qty - ask_qty) / (bid_qty + ask_qty) as ofi,
        -- Price impact indicators
        lag(best_bid) OVER (PARTITION BY symbol ORDER BY ts_exchange) as prev_bid,
        lag(best_ask) OVER (PARTITION BY symbol ORDER BY ts_exchange) as prev_ask
    FROM marketdata.book_ticker 
    WHERE symbol = 'BTCUSDT' 
    AND ts_exchange > now() - interval '1 hour'
)
SELECT 
    ts_exchange,
    symbol,
    microprice,
    ofi,
    -- Price momentum indicators
    (best_bid - prev_bid) / prev_bid * 10000 as bid_change_bps,
    (best_ask - prev_ask) / prev_ask * 10000 as ask_change_bps,
    -- Volatility indicators
    abs(microprice - (best_bid + best_ask)/2) as microprice_deviation
FROM features 
WHERE prev_bid IS NOT NULL
ORDER BY ts_exchange DESC
LIMIT 100;

-- ===============================================
-- 7. МОНИТОРИНГ И АЛЕРТЫ
-- ===============================================

-- Проверка на пропущенные данные (gaps > 1 минуты)
WITH time_gaps AS (
    SELECT 
        symbol,
        ts_exchange,
        lag(ts_exchange) OVER (PARTITION BY symbol ORDER BY ts_exchange) as prev_ts,
        extract(epoch from (ts_exchange - lag(ts_exchange) OVER (PARTITION BY symbol ORDER BY ts_exchange))) as gap_seconds
    FROM marketdata.book_ticker 
    WHERE ts_exchange > now() - interval '1 day'
)
SELECT 
    symbol,
    count(*) FILTER (WHERE gap_seconds > 60) as gaps_over_1min,
    max(gap_seconds) as max_gap_seconds,
    avg(gap_seconds) FILTER (WHERE gap_seconds < 300) as avg_gap_seconds
FROM time_gaps 
WHERE prev_ts IS NOT NULL
GROUP BY symbol
HAVING count(*) FILTER (WHERE gap_seconds > 60) > 0
ORDER BY gaps_over_1min DESC;

-- Результат показывает реальную структуру и объёмы данных:
-- ~9000 записей в минуту для 200 символов
-- ~400MB данных в день
-- ~12GB данных в месяц
-- Субмиллисекундная точность временных меток