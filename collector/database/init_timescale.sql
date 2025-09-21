-- Инициализация TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Проверка успешной установки
SELECT extname FROM pg_extension WHERE extname = 'timescaledb';