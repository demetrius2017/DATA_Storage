-- =====================================================
-- ПРИМЕР РЕАЛЬНЫХ ДАННЫХ ORDERBOOK COLLECTION SYSTEM
-- =====================================================

-- 1. ОСНОВНАЯ ТАБЛИЦА ДЛЯ ХРАНЕНИЯ ДАННЫХ ORDERBOOK
CREATE TABLE book_ticker (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    bid_price DECIMAL(20,10) NOT NULL,     -- Лучшая цена покупки
    bid_qty DECIMAL(20,10) NOT NULL,       -- Объем на покупку
    ask_price DECIMAL(20,10) NOT NULL,     -- Лучшая цена продажи
    ask_qty DECIMAL(20,10) NOT NULL,       -- Объем на продажу
    ts_exchange BIGINT NOT NULL,           -- Timestamp от биржи (milliseconds)
    ts_received BIGINT NOT NULL,           -- Timestamp получения (milliseconds)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Индексы для быстрого поиска
    INDEX idx_symbol_ts (symbol, ts_exchange),
    INDEX idx_received_ts (ts_received),
    INDEX idx_symbol_created (symbol, created_at)
);

-- 2. ПРИМЕРЫ РЕАЛЬНЫХ ДАННЫХ (формат как от Binance WebSocket)
INSERT INTO book_ticker (symbol, bid_price, bid_qty, ask_price, ask_qty, ts_exchange, ts_received) VALUES
-- BTCUSDT - Bitcoin к Tether
('BTCUSDT', 63500.50, 0.15000, 63500.51, 0.23000, 1726851015123, 1726851015125),
('BTCUSDT', 63500.49, 0.08500, 63500.52, 0.18000, 1726851015234, 1726851015236),
('BTCUSDT', 63501.00, 0.25000, 63501.01, 0.12000, 1726851015445, 1726851015447),

-- ETHUSDT - Ethereum к Tether  
('ETHUSDT', 2645.75, 1.25000, 2645.76, 0.89000, 1726851015234, 1726851015236),
('ETHUSDT', 2645.80, 0.75000, 2645.81, 1.15000, 1726851015445, 1726851015447),
('ETHUSDT', 2645.73, 2.50000, 2645.74, 0.65000, 1726851015556, 1726851015558),

-- SOLUSDT - Solana к Tether
('SOLUSDT', 142.35, 25.50, 142.36, 18.75, 1726851015345, 1726851015347),
('SOLUSDT', 142.40, 15.20, 142.41, 22.30, 1726851015456, 1726851015458),
('SOLUSDT', 142.33, 35.80, 142.34, 28.90, 1726851015567, 1726851015569);

-- 3. ЗАПРОСЫ ДЛЯ АНАЛИЗА СОБРАННЫХ ДАННЫХ
-- ===================================================

-- 3.1 Последние данные по каждому символу
SELECT 
    symbol,
    bid_price,
    ask_price,
    (ask_price - bid_price) as spread,
    (ask_price - bid_price) / bid_price * 100 as spread_percent,
    ts_exchange,
    ts_received,
    (ts_received - ts_exchange) as latency_ms
FROM book_ticker 
WHERE created_at >= NOW() - INTERVAL '1 hour'
ORDER BY symbol, ts_exchange DESC;

-- 3.2 Статистика частоты обновлений по символам
SELECT 
    symbol,
    COUNT(*) as updates_count,
    MIN(ts_exchange) as first_update,
    MAX(ts_exchange) as last_update,
    (MAX(ts_exchange) - MIN(ts_exchange)) / 1000 as duration_seconds,
    COUNT(*) / ((MAX(ts_exchange) - MIN(ts_exchange)) / 1000.0) as updates_per_second
FROM book_ticker 
WHERE created_at >= NOW() - INTERVAL '1 hour'
GROUP BY symbol
ORDER BY updates_per_second DESC;

-- 3.3 Анализ спредов (разность между bid и ask)
SELECT 
    symbol,
    AVG(ask_price - bid_price) as avg_spread,
    MIN(ask_price - bid_price) as min_spread,
    MAX(ask_price - bid_price) as max_spread,
    STDDEV(ask_price - bid_price) as spread_volatility,
    AVG((ask_price - bid_price) / bid_price * 100) as avg_spread_percent
FROM book_ticker 
WHERE created_at >= NOW() - INTERVAL '1 hour'
GROUP BY symbol
ORDER BY avg_spread_percent;

-- 3.4 Контроль качества данных (валидация ТЗ)
SELECT 
    'Data Quality Check' as check_type,
    symbol,
    COUNT(*) as total_records,
    COUNT(CASE WHEN bid_price <= 0 THEN 1 END) as invalid_bid_price,
    COUNT(CASE WHEN ask_price <= 0 THEN 1 END) as invalid_ask_price,
    COUNT(CASE WHEN bid_qty <= 0 THEN 1 END) as invalid_bid_qty,
    COUNT(CASE WHEN ask_qty <= 0 THEN 1 END) as invalid_ask_qty,
    COUNT(CASE WHEN ask_price <= bid_price THEN 1 END) as invalid_spread,
    COUNT(CASE WHEN ts_received < ts_exchange THEN 1 END) as invalid_latency
FROM book_ticker 
WHERE created_at >= NOW() - INTERVAL '1 hour'
GROUP BY symbol;

-- 3.5 Мониторинг задержек (latency analysis)
SELECT 
    symbol,
    AVG(ts_received - ts_exchange) as avg_latency_ms,
    MIN(ts_received - ts_exchange) as min_latency_ms,
    MAX(ts_received - ts_exchange) as max_latency_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY ts_received - ts_exchange) as p95_latency_ms
FROM book_ticker 
WHERE created_at >= NOW() - INTERVAL '1 hour'
GROUP BY symbol
ORDER BY avg_latency_ms;

-- 4. АГРЕГИРОВАННЫЕ ТАБЛИЦЫ (TimescaleDB continuous aggregates)
-- ============================================================

-- 4.1 Создание continuous aggregate для 1-секундных интервалов
CREATE MATERIALIZED VIEW bt_1s
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 second', to_timestamp(ts_exchange / 1000)) AS bucket,
    symbol,
    FIRST(bid_price, ts_exchange) as first_bid,
    LAST(bid_price, ts_exchange) as last_bid,
    MAX(bid_price) as max_bid,
    MIN(bid_price) as min_bid,
    FIRST(ask_price, ts_exchange) as first_ask,
    LAST(ask_price, ts_exchange) as last_ask,
    MAX(ask_price) as max_ask,
    MIN(ask_price) as min_ask,
    AVG(ask_price - bid_price) as avg_spread,
    COUNT(*) as update_count
FROM book_ticker
GROUP BY bucket, symbol;

-- 4.2 Запрос агрегированных данных за последний час по секундам
SELECT 
    bucket,
    symbol,
    last_bid,
    last_ask,
    avg_spread,
    update_count
FROM bt_1s 
WHERE bucket >= NOW() - INTERVAL '1 hour'
ORDER BY symbol, bucket DESC;

-- 5. ЭКСПОРТ ДАННЫХ ДЛЯ ML (CSV FORMAT)
-- =====================================

-- 5.1 Экспорт базовых features для ML
\copy (
    SELECT 
        symbol,
        extract(epoch from to_timestamp(ts_exchange / 1000)) as timestamp,
        bid_price,
        bid_qty,
        ask_price,
        ask_qty,
        (ask_price - bid_price) as spread,
        (ask_price - bid_price) / bid_price * 100 as spread_percent,
        ts_received - ts_exchange as latency_ms
    FROM book_ticker 
    WHERE symbol = 'BTCUSDT' 
    AND created_at >= NOW() - INTERVAL '24 hours'
    ORDER BY ts_exchange
) TO '/tmp/btcusdt_orderbook_features.csv' WITH CSV HEADER;

-- 6. PERFORMANCE MONITORING
-- =========================

-- 6.1 Размер таблицы и количество записей
SELECT 
    schemaname,
    tablename,
    attname,
    n_distinct,
    correlation
FROM pg_stats 
WHERE tablename = 'book_ticker';

-- 6.2 Статистика индексов
SELECT 
    indexname,
    indexdef,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes 
WHERE relname = 'book_ticker';

-- КОНЕЦ ФАЙЛА
-- Этот файл показывает полную структуру данных, которые собирает система
-- orderbook collection в соответствии с ТЗ проекта.