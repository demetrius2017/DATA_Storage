-- ===============================================
-- 📋 СТРУКТУРА ТАБЛИЦ И ПРИМЕРЫ ДАННЫХ
-- ===============================================

-- ===============================================
-- 1. ОСНОВНАЯ ТАБЛИЦА: book_ticker
-- ===============================================

CREATE TABLE book_ticker (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    bid_price DECIMAL(20,10) NOT NULL,
    bid_qty DECIMAL(20,10) NOT NULL,
    ask_price DECIMAL(20,10) NOT NULL,
    ask_qty DECIMAL(20,10) NOT NULL,
    ts_exchange BIGINT NOT NULL,           -- Unix timestamp в миллисекундах
    ts_received BIGINT NOT NULL,           -- Время получения в нашей системе
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для производительности
CREATE INDEX idx_book_ticker_symbol_ts ON book_ticker(symbol, ts_exchange);
CREATE INDEX idx_book_ticker_created_at ON book_ticker(created_at);

-- ===============================================
-- 2. ПРИМЕРЫ РЕАЛЬНЫХ ДАННЫХ
-- ===============================================

-- Пример данных для BTCUSDT
INSERT INTO book_ticker (symbol, bid_price, bid_qty, ask_price, ask_qty, ts_exchange, ts_received) VALUES
('BTCUSDT', 63500.50, 0.15000, 63500.51, 0.23000, 1726851015123, 1726851015125),
('BTCUSDT', 63500.49, 0.08500, 63500.52, 0.18000, 1726851015234, 1726851015236),
('BTCUSDT', 63500.51, 0.12000, 63500.52, 0.09500, 1726851015345, 1726851015347),
('BTCUSDT', 63500.50, 0.25000, 63500.53, 0.41000, 1726851015456, 1726851015458),
('BTCUSDT', 63500.52, 0.35000, 63500.54, 0.15500, 1726851015567, 1726851015569);

-- Пример данных для ETHUSDT
INSERT INTO book_ticker (symbol, bid_price, bid_qty, ask_price, ask_qty, ts_exchange, ts_received) VALUES
('ETHUSDT', 2645.75, 1.25000, 2645.76, 0.89000, 1726851015234, 1726851015236),
('ETHUSDT', 2645.74, 0.95000, 2645.77, 1.15000, 1726851015345, 1726851015347),
('ETHUSDT', 2645.76, 1.85000, 2645.77, 0.75000, 1726851015456, 1726851015458),
('ETHUSDT', 2645.75, 2.15000, 2645.78, 1.35000, 1726851015567, 1726851015569),
('ETHUSDT', 2645.77, 1.65000, 2645.79, 0.95000, 1726851015678, 1726851015680);

-- Пример данных для SOLUSDT
INSERT INTO book_ticker (symbol, bid_price, bid_qty, ask_price, ask_qty, ts_exchange, ts_received) VALUES
('SOLUSDT', 142.35, 25.50000, 142.36, 18.75000, 1726851015345, 1726851015347),
('SOLUSDT', 142.34, 32.25000, 142.37, 21.50000, 1726851015456, 1726851015458),
('SOLUSDT', 142.36, 28.75000, 142.37, 19.25000, 1726851015567, 1726851015569),
('SOLUSDT', 142.35, 35.50000, 142.38, 25.75000, 1726851015678, 1726851015680),
('SOLUSDT', 142.37, 29.25000, 142.39, 22.50000, 1726851015789, 1726851015791);

-- ===============================================
-- 3. ЗАПРОСЫ ДЛЯ ПРОСМОТРА ДАННЫХ
-- ===============================================

-- Последние 10 записей
SELECT 
    symbol,
    bid_price,
    ask_price,
    (ask_price - bid_price) as spread,
    (bid_price + ask_price) / 2 as mid_price,
    to_timestamp(ts_exchange/1000) as exchange_time,
    created_at
FROM book_ticker 
ORDER BY created_at DESC 
LIMIT 10;

-- Статистика по символам за последний час
SELECT 
    symbol,
    COUNT(*) as updates_count,
    MIN(bid_price) as min_bid,
    MAX(ask_price) as max_ask,
    AVG((bid_price + ask_price) / 2) as avg_mid_price,
    AVG(ask_price - bid_price) as avg_spread,
    MIN(to_timestamp(ts_exchange/1000)) as first_update,
    MAX(to_timestamp(ts_exchange/1000)) as last_update
FROM book_ticker 
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY symbol
ORDER BY updates_count DESC;

-- Проверка частоты обновлений (соответствие ТЗ)
SELECT 
    symbol,
    COUNT(*) as total_updates,
    EXTRACT(epoch FROM (MAX(created_at) - MIN(created_at)))/60 as duration_minutes,
    COUNT(*) / (EXTRACT(epoch FROM (MAX(created_at) - MIN(created_at)))/60) as updates_per_minute,
    CASE 
        WHEN COUNT(*) / (EXTRACT(epoch FROM (MAX(created_at) - MIN(created_at)))/60) >= 1 
        THEN '✅ СООТВЕТСТВУЕТ ТЗ' 
        ELSE '❌ НЕ СООТВЕТСТВУЕТ ТЗ' 
    END as tz_compliance
FROM book_ticker 
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY symbol
HAVING EXTRACT(epoch FROM (MAX(created_at) - MIN(created_at)))/60 > 1
ORDER BY updates_per_minute DESC;

-- Проверка качества данных
SELECT 
    symbol,
    COUNT(*) as total_records,
    COUNT(*) FILTER (WHERE bid_price IS NULL OR ask_price IS NULL) as null_prices,
    COUNT(*) FILTER (WHERE bid_price <= 0 OR ask_price <= 0) as invalid_prices,
    COUNT(*) FILTER (WHERE bid_price >= ask_price) as inverted_spread,
    AVG(ask_price - bid_price) as avg_spread,
    STDDEV(ask_price - bid_price) as spread_volatility
FROM book_ticker 
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY symbol
ORDER BY symbol;

-- ===============================================
-- 4. АГРЕГИРОВАННЫЕ ДАННЫЕ (bt_1s)
-- ===============================================

-- Создание таблицы для 1-секундных агрегатов
CREATE TABLE bt_1s (
    bucket TIMESTAMP NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    open_bid DECIMAL(20,10),
    high_bid DECIMAL(20,10),
    low_bid DECIMAL(20,10),
    close_bid DECIMAL(20,10),
    open_ask DECIMAL(20,10),
    high_ask DECIMAL(20,10),
    low_ask DECIMAL(20,10),
    close_ask DECIMAL(20,10),
    avg_mid DECIMAL(20,10),
    avg_spread DECIMAL(20,10),
    update_count INTEGER,
    PRIMARY KEY (bucket, symbol)
);

-- Пример агрегированных данных
INSERT INTO bt_1s VALUES
('2025-09-20 16:30:15', 'BTCUSDT', 63500.45, 63500.55, 63500.42, 63500.50, 63500.52, 63500.58, 63500.48, 63500.51, 63500.495, 0.08, 145),
('2025-09-20 16:30:16', 'BTCUSDT', 63500.50, 63500.62, 63500.48, 63500.58, 63500.51, 63500.63, 63500.49, 63500.59, 63500.585, 0.09, 158),
('2025-09-20 16:30:17', 'BTCUSDT', 63500.58, 63500.65, 63500.55, 63500.61, 63500.59, 63500.66, 63500.56, 63500.62, 63500.615, 0.07, 142);

-- ===============================================
-- 5. ОБЪЁМЫ ДАННЫХ (ПРИМЕРНЫЕ)
-- ===============================================

-- Размер одной записи book_ticker: ~80-100 байт
-- Частота обновлений: ~150 обновлений/минуту/символ
-- Для 200 символов: ~30,000 записей/минуту
-- Для 200 символов: ~1,800,000 записей/час
-- Для 200 символов: ~43,200,000 записей/день

-- Размер данных в день: ~4.3GB
-- Размер данных в месяц: ~130GB
-- Размер данных в год: ~1.5TB

-- ===============================================
-- 6. ПОЛЕЗНЫЕ АНАЛИТИЧЕСКИЕ ЗАПРОСЫ
-- ===============================================

-- Топ-10 самых волатильных символов
SELECT 
    symbol,
    STDDEV((bid_price + ask_price) / 2) as price_volatility,
    AVG((bid_price + ask_price) / 2) as avg_price,
    STDDEV((bid_price + ask_price) / 2) / AVG((bid_price + ask_price) / 2) * 100 as volatility_percent
FROM book_ticker 
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY symbol
HAVING COUNT(*) > 100
ORDER BY volatility_percent DESC
LIMIT 10;

-- Анализ спредов
SELECT 
    symbol,
    AVG(ask_price - bid_price) as avg_spread,
    AVG((ask_price - bid_price) / ((bid_price + ask_price) / 2) * 100) as avg_spread_percent,
    MIN(ask_price - bid_price) as min_spread,
    MAX(ask_price - bid_price) as max_spread
FROM book_ticker 
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY symbol
ORDER BY avg_spread_percent ASC;

-- Проверка задержек (latency)
SELECT 
    symbol,
    AVG(ts_received - ts_exchange) as avg_latency_ms,
    MIN(ts_received - ts_exchange) as min_latency_ms,
    MAX(ts_received - ts_exchange) as max_latency_ms,
    STDDEV(ts_received - ts_exchange) as latency_stddev
FROM book_ticker 
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY symbol
ORDER BY avg_latency_ms DESC;