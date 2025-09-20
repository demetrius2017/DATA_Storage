# 🎯 ТЗ: Система сбора реальных market data для 200 пар в PostgreSQL

## 📌 Общая концепция

**Цель:** Централизованный сбор live-данных с Binance по 200 торговым парам в PostgreSQL/TimescaleDB для ежедневного обучения ML моделей на "вчерашних" данных и быстрой валидации.

**Архитектура:** Реальный поток → PostgreSQL → "вчерашний" датасет → ML обучение

---

## 📊 ЧТО СОБИРАТЬ

### Приоритет 1 (лёгкий, полезный всем моделям):

#### bookTicker (top-of-book)
- **Данные:** best_bid, best_ask, bid_qty, ask_qty, event_time
- **Частота:** 30-150 updates/sec для топ-пар, <1/sec для остальных
- **Применение:** Основные сигналы, spread, mid-price

#### aggTrade (агрегированные сделки)
- **Данные:** цена/объём сделки, сторона агрессора, event_time
- **Частота:** Умеренная по 200 парам
- **Применение:** OFI, валидация ликвидности, momentum

### Приоритет 2 (для микро‑структуры):

#### depth5@100ms или depth10@100ms
- **Данные:** массивы [price, qty] на первых 5–10 уровнях + диффы
- **Частота:** Высокая для топ-пар (сначала 20-50 ликвидных пар)
- **Применение:** I1/I10, microprice, wall detection

#### mark price/funding (для фьючерсов)
- **Данные:** события изменения mark price и funding
- **Частота:** Каждые 8 часов
- **Применение:** Funding rate signals

### Рекомендация на старт:
- **Все 200 пар:** bookTicker + aggTrade (низкая/средняя нагрузка)
- **Топ-N ликвидных:** depth5@100ms (постепенное расширение)

---

## 🗄️ СХЕМА БАЗЫ ДАННЫХ

### Нормализация и структура

```sql
-- Схема для market data
CREATE SCHEMA marketdata;
```

### 1. Справочник символов
```sql
CREATE TABLE marketdata.symbols (
    id bigserial PRIMARY KEY,
    exchange text not null, -- 'binance-futures', 'binance-spot'
    symbol text not null,   -- 'SOLUSDT', 'BTCUSDT'
    instrument_type text,   -- 'perp', 'spot'
    base_asset text,
    quote_asset text,
    is_active boolean default true,
    created_at timestamptz default now(),
    UNIQUE (exchange, symbol)
);
```

### 2. Поток top-of-book (bookTicker)
```sql
CREATE TABLE marketdata.book_ticker (
    ts_exchange timestamptz not null,    -- из E/1000 (UTC)
    ts_ingest timestamptz not null default now(),
    symbol_id bigint not null references marketdata.symbols(id),
    update_id bigint,                    -- поле u (если есть)
    best_bid double precision not null,
    best_ask double precision not null,
    bid_qty double precision not null,
    ask_qty double precision not null,
    spread double precision not null,    -- best_ask - best_bid
    mid double precision not null,       -- (best_ask + best_bid)/2
    PRIMARY KEY (symbol_id, ts_exchange, coalesce(update_id, 0))
);
CREATE INDEX idx_book_ticker_time ON marketdata.book_ticker (symbol_id, ts_exchange);
```

### 3. Сделки (aggTrade)
```sql
CREATE TABLE marketdata.trades (
    ts_exchange timestamptz not null,    -- из E/1000
    ts_ingest timestamptz not null default now(),
    symbol_id bigint not null references marketdata.symbols(id),
    agg_trade_id bigint not null,        -- поле a
    price double precision not null,     -- поле p
    qty double precision not null,       -- поле q
    is_buyer_maker boolean not null,     -- поле m
    PRIMARY KEY (symbol_id, agg_trade_id)
);
CREATE INDEX idx_trades_time ON marketdata.trades (symbol_id, ts_exchange);
```

### 4. События глубины (depth updates)

#### Вариант A: Raw JSONB (быстрый ingestion)
```sql
CREATE TABLE marketdata.depth_events (
    ts_exchange timestamptz not null,
    ts_ingest timestamptz not null default now(),
    symbol_id bigint not null,
    first_update_id bigint not null,     -- U
    final_update_id bigint not null,     -- u
    prev_final_update_id bigint,         -- pu
    bids jsonb not null,                 -- массив [["price","qty"], ...]
    asks jsonb not null,
    PRIMARY KEY (symbol_id, final_update_id)
);
CREATE INDEX idx_depth_events_time ON marketdata.depth_events (symbol_id, ts_exchange);
```

#### Вариант B: Плоская структура (удобно для фич)
```sql
CREATE TABLE marketdata.orderbook_topN (
    ts_exchange timestamptz not null,
    symbol_id bigint not null,
    -- Top 5 bids/asks
    b1_price double precision, b1_qty double precision,
    b2_price double precision, b2_qty double precision,
    b3_price double precision, b3_qty double precision,
    b4_price double precision, b4_qty double precision,
    b5_price double precision, b5_qty double precision,
    a1_price double precision, a1_qty double precision,
    a2_price double precision, a2_qty double precision,
    a3_price double precision, a3_qty double precision,
    a4_price double precision, a4_qty double precision,
    a5_price double precision, a5_qty double precision,
    -- Derived features
    i1 double precision,                 -- Immediate impact 1
    i5 double precision,                 -- Immediate impact 5
    microprice double precision,         -- Микроцена
    wall_size double precision,          -- Размер стены
    wall_dist_bps double precision,      -- Расстояние до стены в bps
    PRIMARY KEY (symbol_id, ts_exchange)
);
CREATE INDEX idx_orderbook_topN_time ON marketdata.orderbook_topN (symbol_id, ts_exchange);
```

### 5. Материализованные агрегаты

#### book_ticker агрегаты (1s)
```sql
CREATE TABLE marketdata.bt_1s (
    ts_second timestamptz not null,
    symbol_id bigint not null,
    mid_open double precision,
    mid_high double precision,
    mid_low double precision,
    mid_close double precision,
    spread_mean double precision,
    spread_std double precision,
    volume_weighted_mid double precision,
    PRIMARY KEY (symbol_id, ts_second)
);
CREATE INDEX idx_bt_1s_time ON marketdata.bt_1s (symbol_id, ts_second);
```

#### trade агрегаты (1s)
```sql
CREATE TABLE marketdata.trade_1s (
    ts_second timestamptz not null,
    symbol_id bigint not null,
    trade_count int,
    volume_sum double precision,
    vwap double precision,
    buy_volume double precision,
    sell_volume double precision,
    imbalance_ratio double precision,    -- (buy_vol - sell_vol) / total_vol
    PRIMARY KEY (symbol_id, ts_second)
);
CREATE INDEX idx_trade_1s_time ON marketdata.trade_1s (symbol_id, ts_second);
```

---

## ⚡ INGESTION АРХИТЕКТУРА

### WebSocket Соединения
- **Binance Combined Streams:** `wss://fstream.binance.com/stream?streams=...`
- **Шардирование:** 3-5 соединений на 200 пар:
  - 1-2 для bookTicker
  - 1-2 для aggTrade  
  - 1 для depth топовых пар
- **Batch размер:** 50-100 пар на соединение

### Батчинг в БД
- **Пакетная вставка:** 50-500 записей
- **Драйвер:** asyncpg `copy_records_to_table` или `execute_many`
- **Транзакции:** Короткие, autocommit off
- **Дедупликация:** UPSERT ON CONFLICT DO NOTHING

### Отказоустойчивость
- **At least once delivery:** уникальные ключи защищают от дублей
- **Offsets tracking:** последний обработанный update_id per symbol
- **Reconnection logic:** автоматическое переподключение с backoff

---

## 🔄 РОТАЦИЯ И КОМПРЕССИЯ

### TimescaleDB настройки
```sql
-- Включение TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Hypertables
SELECT create_hypertable('marketdata.book_ticker', 'ts_exchange', 
    partitioning_column => 'symbol_id', number_partitions => 16);
SELECT create_hypertable('marketdata.trades', 'ts_exchange',
    partitioning_column => 'symbol_id', number_partitions => 16);
SELECT create_hypertable('marketdata.depth_events', 'ts_exchange',
    partitioning_column => 'symbol_id', number_partitions => 16);

-- Retention policies
SELECT add_retention_policy('marketdata.book_ticker', INTERVAL '30 days');
SELECT add_retention_policy('marketdata.trades', INTERVAL '30 days');
SELECT add_retention_policy('marketdata.depth_events', INTERVAL '7 days');

-- Compression policies
SELECT add_compression_policy('marketdata.book_ticker', INTERVAL '7 days');
SELECT add_compression_policy('marketdata.trades', INTERVAL '7 days');
```

### Хранение стратегия
- **Сырые данные:** 7-30 дней (с компрессией)
- **Depth events:** 3-7 дней (объёмные)
- **Агрегаты 1s:** 90-180 дней (эффективные для ML)
- **Features таблицы:** 30-90 дней

---

## 🎯 "ВЧЕРАШНИЙ" ДАТАСЕТ ДЛЯ ML

### Быстрый доступ
- **Окно:** [00:00:00Z; 23:59:59Z] вчера
- **Источники:** Агрегированные таблицы bt_1s, trade_1s, orderbook_topN
- **Запросы:** Один скан партиции по дню

### ML Pipeline интеграция
```sql
-- Пример запроса "вчерашних" данных
SELECT 
    bt.ts_second,
    bt.symbol_id,
    bt.mid_close,
    bt.spread_mean,
    tr.vwap,
    tr.imbalance_ratio,
    ob.i1,
    ob.i5,
    ob.microprice
FROM marketdata.bt_1s bt
LEFT JOIN marketdata.trade_1s tr USING (symbol_id, ts_second)
LEFT JOIN marketdata.orderbook_topN ob ON (
    bt.symbol_id = ob.symbol_id 
    AND ob.ts_exchange >= bt.ts_second 
    AND ob.ts_exchange < bt.ts_second + INTERVAL '1 second'
)
WHERE bt.ts_second >= date_trunc('day', now() - INTERVAL '1 day')
  AND bt.ts_second < date_trunc('day', now())
  AND bt.symbol_id = ANY($1);  -- массив symbol_id
```

---

## 📈 НАГРУЗКА И ПРОИЗВОДИТЕЛЬНОСТЬ

### Объёмы данных
- **bookTicker:** ~2-10M записей/день (200 пар)
- **trades:** ~1-5M записей/день  
- **depth_events:** ~5-50M записей/день (зависит от пар)

### Оптимизация
- **Индексы:** (symbol_id, ts_exchange) везде
- **Партиционирование:** по времени + symbol_id
- **Vacuum:** автоматический + мониторинг блоатинга
- **Connection pooling:** 10-20 соединений

---

## 🔌 ИНТЕГРАЦИЯ С ТЕКУЩИМ ПРОЕКТОМ

### Новые компоненты
1. **Multi-stream инжестор** (`collector/ingestion/multi_stream_collector.py`)
2. **PostgreSQL адаптер** (`collector/storage/marketdata_manager.py`) 
3. **Feature pipeline** (`collector/features/feature_calculator.py`)
4. **Yesterday dataset provider** (`collector/ml/yesterday_provider.py`)

### MCP расширения
- `getOrderBookSnapshotFromDB(symbol, timestamp)`
- `getTradesSlice(symbol, from_ts, to_ts)`
- `getYesterdayFeatures(symbols, feature_set)`

---

## 🚀 ПЛАН РАЗВЕРТЫВАНИЯ

### Этап 1: Базовая схема (1-2 дня)
- [ ] Создание schema marketdata
- [ ] Таблицы symbols, book_ticker, trades
- [ ] TimescaleDB hypertables
- [ ] Базовые индексы

### Этап 2: Ingestion (2-3 дня)  
- [ ] Multi-stream WebSocket collector
- [ ] Batch PostgreSQL writer
- [ ] Error handling и reconnection
- [ ] Мониторинг и алерты

### Этап 3: Features (1-2 дня)
- [ ] depth_events обработка
- [ ] orderbook_topN расчёт
- [ ] I1/I5/microprice pipeline
- [ ] Агрегаты bt_1s, trade_1s

### Этап 4: ML интеграция (1 день)
- [ ] Yesterday dataset provider
- [ ] Адаптеры в copilot
- [ ] Перенастройка студентов на PostgreSQL

---

## ✅ КРИТЕРИИ УСПЕХА

1. **Стабильность:** 99%+ uptime сбора данных
2. **Латентность:** <100ms от события до БД
3. **Полнота:** <0.1% потерь данных  
4. **Производительность:** Yesterday training <5 минут
5. **Масштабируемость:** Готовность к расширению до 500+ пар

---

## 🎯 ИТОГОВАЯ ЦЕННОСТЬ

**Для проекта:**
- Непрерывный поток качественных данных
- Быстрая валидация ML моделей
- Репликация результатов
- Масштабируемая архитектура

**Для ML pipeline:**
- Свежие данные каждый день
- Консистентные фичи
- Быстрые эксперименты
- Automated backtesting на real data