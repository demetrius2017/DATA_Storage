# Система автоматических агрегатов TimescaleDB

Решение проблемы: **"⚠️ Отсутствие aggregates: Нет автоматического создания bt_1s/trade_1s таблиц"**

## 🎯 Обзор

Система автоматических агрегатов создает и поддерживает continuous aggregates в TimescaleDB для автоматического вычисления метрик по секундам из raw данных book_ticker, trades и depth_events.

## 📊 Созданные агрегаты

### 1. `bt_1s_continuous` - Book Ticker Aggregates
- **Источник**: `book_ticker` таблица
- **Группировка**: 1 секунда
- **Метрики**:
  - OHLC для bid/ask цен
  - Статистика количества (bid_qty, ask_qty)
  - Среднее, минимальное, максимальное значение spread
  - Microprice (среднее bid+ask цен)
  - Количество тиков

### 2. `trade_1s_continuous` - Trade Aggregates  
- **Источник**: `trades` таблица
- **Группировка**: 1 секунда
- **Метрики**:
  - OHLC цен сделок
  - Объемы и количество сделок
  - Buy/Sell разделение по is_buyer_maker
  - VWAP (Volume Weighted Average Price)
  - Buy ratio (агрессивность покупателей)

### 3. `depth_1s_continuous` - Depth Events Aggregates
- **Источник**: `depth_events` таблица  
- **Группировка**: 1 секунда
- **Метрики**:
  - Количество обновлений orderbook
  - Первое и последнее состояние bid/ask
  - Подготовка данных для расчета OFI

### 4. `market_data_1s` - Объединенное представление
- **Объединяет**: все три агрегата
- **Удобный доступ**: ко всем метрикам одним запросом

## 🚀 Развертывание

### Автоматическое развертывание

```bash
# Полное развертывание системы агрегатов
python collector/scripts/deploy_aggregates.py

# Валидация существующих агрегатов
python collector/scripts/deploy_aggregates.py validate
```

### Ручное развертывание

```bash
# Выполнить SQL команды
psql -h host -U user -d database -f collector/sql/create_continuous_aggregates.sql

# Или через Python
python -m collector.aggregates.aggregate_manager
```

## 📋 Мониторинг

### Проверка статуса агрегатов

```sql
-- Список всех continuous aggregates
SELECT view_name, materialized_only, finalized 
FROM timescaledb_information.continuous_aggregates;

-- Статус политик обновления
SELECT application_name, hypertable_name, config 
FROM timescaledb_information.jobs 
WHERE application_name LIKE '%continuous_aggregate%';
```

### Статистика данных

```sql
-- Количество записей в каждом агрегате
SELECT 
    'bt_1s_continuous' as aggregate, count(*) as records FROM bt_1s_continuous
UNION ALL
SELECT 
    'trade_1s_continuous' as aggregate, count(*) as records FROM trade_1s_continuous  
UNION ALL
SELECT 
    'depth_1s_continuous' as aggregate, count(*) as records FROM depth_1s_continuous;
```

### Последние данные

```sql
-- Последние 10 записей объединенных данных для BTCUSDT
SELECT * FROM market_data_1s 
WHERE symbol = 'BTCUSDT' 
ORDER BY ts_bucket DESC 
LIMIT 10;
```

## 🔄 Автоматическое обновление

Агрегаты настроены для автоматического обновления каждые **30 секунд** с помощью TimescaleDB политик:

```sql
-- Политика обновления (автоматически создается)
SELECT add_continuous_aggregate_policy('bt_1s_continuous',
    start_offset => INTERVAL '2 hours',
    end_offset => INTERVAL '30 seconds',
    schedule_interval => INTERVAL '30 seconds');
```

## 🛠 Управление через Python API

### Базовое использование

```python
from collector.aggregates import AggregateManager

# Инициализация
manager = AggregateManager(connection_string)

# Создание агрегатов
await manager.setup_continuous_aggregates()

# Получение статуса
status = await manager.get_aggregate_status()

# Принудительное обновление
await manager.refresh_aggregates()

# Получение данных
data = await manager.get_market_data_sample('BTCUSDT', limit=100)
```

### Расчет OFI (Order Flow Imbalance)

```python
from datetime import datetime, timedelta

# Расчет OFI за последний час
end_time = datetime.utcnow()
start_time = end_time - timedelta(hours=1)

ofi_data = await manager.calculate_ofi('BTCUSDT', start_time, end_time)
```

## 📈 Примеры использования

### 1. Анализ spread по времени

```sql
SELECT 
    ts_bucket,
    symbol,
    spread_avg,
    spread_min,
    spread_max,
    bt_ticks
FROM bt_1s_continuous 
WHERE symbol = 'BTCUSDT' 
AND ts_bucket > now() - interval '1 hour'
ORDER BY ts_bucket;
```

### 2. Анализ объемов торговли

```sql
SELECT 
    ts_bucket,
    symbol,
    volume,
    trade_count,
    buy_ratio,
    vwap
FROM trade_1s_continuous 
WHERE symbol = 'ETHUSDT'
AND ts_bucket > now() - interval '30 minutes'
ORDER BY ts_bucket;
```

### 3. Статистика по всем символам

```sql
SELECT 
    symbol,
    count(*) as data_points,
    avg(volume) as avg_volume,
    avg(trade_count) as avg_trades_per_sec,
    avg(buy_ratio) as avg_buy_ratio
FROM trade_1s_continuous 
WHERE ts_bucket > now() - interval '1 hour'
GROUP BY symbol
ORDER BY avg_volume DESC;
```

## ⚡ Производительность

### Оптимизации

1. **Индексы**: Созданы составные индексы `(ts_bucket, symbol)` и `(symbol, ts_bucket DESC)`
2. **Материализация**: Данные предвычислены и сохранены физически
3. **Партиционирование**: Используется TimescaleDB hypertables с chunk_time_interval = 1 день
4. **Сжатие**: Автоматическое сжатие старых chunk'ов (если доступно)

### Рекомендации

- **Retention**: Настроить политику удаления старых данных для экономии места
- **Monitoring**: Отслеживать размер агрегатов и производительность обновлений
- **Backup**: Включить агрегаты в резервное копирование

## 🐛 Troubleshooting

### Агрегаты не обновляются

```sql
-- Проверить статус background jobs
SELECT * FROM timescaledb_information.jobs WHERE application_name LIKE '%continuous%';

-- Принудительное обновление
CALL refresh_continuous_aggregate('bt_1s_continuous', now() - interval '1 hour', now());
```

### Нет данных в агрегатах

1. Проверить наличие raw данных в исходных таблицах
2. Убедиться, что collector работает и записывает данные
3. Проверить логи TimescaleDB jobs

### Ошибки создания

1. Убедиться, что расширение TimescaleDB установлено
2. Проверить права пользователя на создание materialized views
3. Убедиться, что исходные таблицы существуют и являются hypertables

## 📝 Логирование

Все операции логируются в стандартный Python logger:

```python
import logging
logging.basicConfig(level=logging.INFO)

# Логи будут показывать:
# - Создание агрегатов
# - Обновление данных  
# - Ошибки подключения
# - Статистику производительности
```

## 🎯 Заключение

Система автоматических агрегатов решает проблему отсутствия предвычисленных метрик и обеспечивает:

- ✅ Автоматическое создание bt_1s и trade_1s агрегатов
- ✅ Непрерывное обновление каждые 30 секунд
- ✅ Оптимизированный доступ к метрикам 
- ✅ Подготовку данных для ML pipeline
- ✅ OFI расчеты для анализа order flow

Система готова к production использованию и масштабированию на 200+ торговых пар.