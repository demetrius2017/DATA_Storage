# 🚀 КОМАНДЫ ДЛЯ РАЗВЕРТЫВАНИЯ POSTGRESQL ВЕРСИИ

## 📋 Чек-лист подготовки

### 1. Создание PostgreSQL на Digital Ocean
```bash
# 1. Зайти в Digital Ocean панель
# 2. Database → Create Database → PostgreSQL 14
# 3. Выбрать регион (ближайший к вашему серверу)
# 4. Конфигурация: Basic, 1GB RAM, 25GB storage
# 5. Скопировать connection string
```

### 2. Обновление зависимостей
```bash
pip install asyncpg psycopg2-binary
```

### 3. Конфигурация окружения (.env)
```env
# Binance API
BINANCE_API_KEY=your_api_key_here
BINANCE_SECRET_KEY=your_secret_key_here

# PostgreSQL Digital Ocean
DB_HOST=your-cluster-12345.db.ondigitalocean.com
DB_PORT=25060
DB_NAME=defaultdb
DB_USER=doadmin
DB_PASSWORD=your_password_here
DB_SSLMODE=require
DB_POOL_SIZE=10
DB_BATCH_SIZE=50
```

### 4. Создание схемы базы данных
```sql
-- Подключиться к PostgreSQL и выполнить:
CREATE TABLE orderbook_data (
    id BIGSERIAL PRIMARY KEY,
    exchange VARCHAR(50) NOT NULL DEFAULT 'binance-futures',
    symbol VARCHAR(20) NOT NULL,
    timestamp BIGINT NOT NULL,
    local_timestamp BIGINT NOT NULL,
    ask_amount DECIMAL(20,8),
    ask_price DECIMAL(20,8),
    bid_price DECIMAL(20,8),
    bid_amount DECIMAL(20,8),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание индексов для производительности
CREATE INDEX idx_orderbook_symbol_timestamp ON orderbook_data(symbol, timestamp);
CREATE INDEX idx_orderbook_created_at ON orderbook_data(created_at);
CREATE INDEX idx_orderbook_symbol ON orderbook_data(symbol);
```

---

## 🏃‍♂️ БЫСТРЫЙ ЗАПУСК (После миграции на PostgreSQL)

### Один символ
```bash
python -m collector.main --symbol BTCUSDT --production
```

### Несколько символов
```bash
python -m collector.main --symbols BTCUSDT ETHUSDT SOLUSDT --production
```

### С мониторингом
```bash
python -m collector.main --symbols BTCUSDT ETHUSDT --production --monitor
```

---

## 📊 ПРОВЕРКА ДАННЫХ В POSTGRESQL

### Подключение к базе
```bash
psql "sslmode=require host=your-cluster.db.ondigitalocean.com port=25060 dbname=defaultdb user=doadmin password=your_password"
```

### Полезные SQL запросы
```sql
-- Количество записей по символам
SELECT symbol, COUNT(*) as records_count 
FROM orderbook_data 
GROUP BY symbol 
ORDER BY records_count DESC;

-- Последние 10 записей BTCUSDT
SELECT * FROM orderbook_data 
WHERE symbol = 'BTCUSDT' 
ORDER BY timestamp DESC 
LIMIT 10;

-- Записи за последний час
SELECT symbol, COUNT(*) as recent_records
FROM orderbook_data 
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY symbol;

-- Средняя частота записей в минуту
SELECT 
    symbol,
    COUNT(*) as total_records,
    EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at)))/60 as duration_minutes,
    ROUND(COUNT(*) / (EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at)))/60), 2) as records_per_minute
FROM orderbook_data 
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY symbol;
```

### Экспорт данных для ML
```sql
-- Экспорт последних 1000 записей BTCUSDT
COPY (
    SELECT exchange, symbol, timestamp, local_timestamp, 
           ask_amount, ask_price, bid_price, bid_amount
    FROM orderbook_data 
    WHERE symbol = 'BTCUSDT' 
    ORDER BY timestamp DESC 
    LIMIT 1000
) TO STDOUT WITH CSV HEADER;
```

---

## 🔧 МОНИТОРИНГ И ОБСЛУЖИВАНИЕ

### Размер базы данных
```sql
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables 
WHERE tablename = 'orderbook_data';
```

### Статистика индексов
```sql
SELECT 
    indexname,
    pg_size_pretty(pg_relation_size(indexname::regclass)) as size
FROM pg_indexes 
WHERE tablename = 'orderbook_data';
```

### Очистка старых данных (если нужно)
```sql
-- Удалить данные старше 30 дней
DELETE FROM orderbook_data 
WHERE created_at < NOW() - INTERVAL '30 days';

-- Vacuum для освобождения места
VACUUM ANALYZE orderbook_data;
```

---

## 🚨 TROUBLESHOOTING

### Проблемы с подключением
```bash
# Проверка доступности хоста
ping your-cluster.db.ondigitalocean.com

# Проверка порта
telnet your-cluster.db.ondigitalocean.com 25060

# Проверка SSL сертификата
openssl s_client -connect your-cluster.db.ondigitalocean.com:25060 -servername your-cluster.db.ondigitalocean.com
```

### Логи ошибок
```bash
# Логи коллектора
tail -f collector/logs/collector.log

# Поиск ошибок PostgreSQL
grep -i "postgresql\|database\|connection" collector/logs/collector.log
```

### Восстановление после сбоя
```python
# В коде предусмотрен fallback на файловое хранение
# При недоступности PostgreSQL данные сохраняются в CSV
# После восстановления соединения можно импортировать:

# COPY orderbook_data (exchange, symbol, timestamp, local_timestamp, 
#                      ask_amount, ask_price, bid_price, bid_amount) 
# FROM '/path/to/fallback.csv' 
# WITH CSV HEADER;
```

---

## 📈 ОЖИДАЕМАЯ ПРОИЗВОДИТЕЛЬНОСТЬ

### Throughput
- **Single symbol:** ~45 записей/мин → ~2700 записей/час
- **Multi-symbol (3):** ~100 записей/мин → ~6000 записей/час
- **Batch size 50:** оптимальный баланс задержки и производительности

### Размер данных
- **100 байт на запись** в PostgreSQL
- **BTCUSDT:** ~270KB/час, ~6.5MB/сутки
- **3 символа:** ~15-20MB/сутки

### Digital Ocean ресурсы
- **1GB RAM:** достаточно для ~10-20 символов
- **25GB storage:** хватит на ~3-6 месяцев данных
- **Connection pool:** 10 соединений для множественных коллекторов

---

**Следующий шаг:** Реализовать PostgreSQLManager и протестировать интеграцию!