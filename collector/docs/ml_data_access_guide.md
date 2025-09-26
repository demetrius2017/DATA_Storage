# ML Data Access Guide (Binance Futures OrderBook Collector)

Документ описывает, что изменилось в базе данных, какие потоки сейчас собираются и как корректно выбирать данные для задач ML.

## Что изменили в базе

- Схема хранения: `marketdata` (TimescaleDB, если доступен)
- Базовые таблицы:
  - `marketdata.symbols` — справочник символов
  - `marketdata.book_ticker` — Top-of-Book (лучшие bid/ask) в реальном времени
  - `marketdata.trades` — агрегированные сделки (aggTrade)
  - `marketdata.depth_events` — события глубины (@depth@100ms), сырой delta-поток
- Подготовлено к включению (DDL добавлен, сбор включается флагами окружения):
  - `marketdata.mark_price` — @markPrice@1s (маркировочная и индексная цена, фандинг)
  - `marketdata.force_orders` — @forceOrder (ликвидации)
- Агрегации 1 секунда (для фичей):
  - `marketdata.bt_1s` — агрегаты book_ticker по секундам
  - `marketdata.trade_1s` — агрегаты сделок по секундам
  - (подготовлено) `feature.core_1s` — сводный слой признаков на 1s (из `bt_1s` + `trade_1s`), агрегатор есть, наполнение включается отдельно

Примечание: В текущем деплое подтверждена свежая доставка для `book_ticker`, `trades`, `depth_events` по активным символам (например: SOLUSDT, FIOUSDT, GHSTUSDT, MLNUSDT).

## Активные потоки и частоты

- bookTicker — тиковые обновления лучших цен/объёмов (миллисекундная частота)
- aggTrade — агрегированные сделки (тик)
- depth@100ms — обновления стакана каждые ~100ms (delta, содержит bids/asks изменения и цепочку update_id)
- (готово к включению) markPrice@1s — раз в секунду
- (готово к включению) forceOrder — по событию ликвидации

## Быстрый справочник по схемам таблиц

- `marketdata.book_ticker(symbol_id, ts_exchange, best_bid, best_ask, bid_qty, ask_qty, spread, mid, …)`
- `marketdata.trades(symbol_id, ts_exchange, agg_trade_id, price, qty, is_buyer_maker, trade_value)`
- `marketdata.depth_events(symbol_id, ts_exchange, first_update_id, final_update_id, prev_final_update_id, bids jsonb, asks jsonb)`
- `marketdata.bt_1s(symbol_id, ts_second, mid_open, mid_high, mid_low, mid_close, spread_mean, updates_count, …)`
- `marketdata.trade_1s(symbol_id, ts_second, trade_count, volume_sum, value_sum, vwap, buy_volume, sell_volume, …)`
- `marketdata.mark_price(symbol_id, ts_exchange, event_type, mark_price, index_price, funding_rate, next_funding_time, …)`
- `marketdata.force_orders(symbol_id, ts_exchange, side, price, qty, raw)`

## Как выбрать данные для ML

Ниже — канонические SQL-запросы. Предполагаем, что работаем в UTC и используем `marketdata` схему.

### 1) Маппинг символов

Получаем `symbol_id` для нужных тикеров:

```sql
SELECT id AS symbol_id, symbol
FROM marketdata.symbols
WHERE symbol = ANY('{"SOLUSDT","FIOUSDT","GHSTUSDT","MLNUSDT"}');
```

### 2) Top-of-Book и сделки — срез за интервал

```sql
-- book_ticker: последние N минут
SELECT s.symbol, bt.*
FROM marketdata.book_ticker bt
JOIN marketdata.symbols s ON s.id = bt.symbol_id
WHERE s.symbol IN ('SOLUSDT','FIOUSDT','GHSTUSDT','MLNUSDT')
  AND bt.ts_exchange >= NOW() - INTERVAL '10 minutes'
ORDER BY s.symbol, bt.ts_exchange;

-- trades (aggTrade): последние N минут
SELECT s.symbol, t.*
FROM marketdata.trades t
JOIN marketdata.symbols s ON s.id = t.symbol_id
WHERE s.symbol IN ('SOLUSDT','FIOUSDT','GHSTUSDT','MLNUSDT')
  AND t.ts_exchange >= NOW() - INTERVAL '10 minutes'
ORDER BY s.symbol, t.ts_exchange;
```

### 3) Сырой поток глубины — delta события

```sql
-- depth delta за интервал (100ms обновления)
SELECT s.symbol,
       de.ts_exchange,
       de.first_update_id,
       de.final_update_id,
       de.prev_final_update_id,
       de.bids,
       de.asks
FROM marketdata.depth_events de
JOIN marketdata.symbols s ON s.id = de.symbol_id
WHERE s.symbol IN ('SOLUSDT','FIOUSDT','GHSTUSDT','MLNUSDT')
  AND de.ts_exchange >= NOW() - INTERVAL '10 minutes'
ORDER BY s.symbol, de.ts_exchange;
```

- Восстановление стакана выполняется как: начальный REST-снимок + последовательное применение delta событий, соблюдая цепочку `prev_final_update_id -> first_update_id..final_update_id` без пропусков.

### 4) 1-секундные агрегаты для базовых признаков

```sql
-- Book Ticker aggregates per second
SELECT s.symbol, bt1.*
FROM marketdata.bt_1s bt1
JOIN marketdata.symbols s ON s.id = bt1.symbol_id
WHERE s.symbol IN ('SOLUSDT','FIOUSDT','GHSTUSDT','MLNUSDT')
  AND bt1.ts_second BETWEEN TIMESTAMP '2025-09-26 16:00:00+00' AND TIMESTAMP '2025-09-26 17:00:00+00'
ORDER BY s.symbol, bt1.ts_second;

-- Trades aggregates per second
SELECT s.symbol, tr1.*
FROM marketdata.trade_1s tr1
JOIN marketdata.symbols s ON s.id = tr1.symbol_id
WHERE s.symbol IN ('SOLUSDT','FIOUSDT','GHSTUSDT','MLNUSDT')
  AND tr1.ts_second BETWEEN TIMESTAMP '2025-09-26 16:00:00+00' AND TIMESTAMP '2025-09-26 17:00:00+00'
ORDER BY s.symbol, tr1.ts_second;
```

### 5) Связка с markPrice/forceOrder (когда включим)

```sql
-- Привязка mark_price к символам
SELECT s.symbol, mp.*
FROM marketdata.mark_price mp
JOIN marketdata.symbols s ON s.id = mp.symbol_id
WHERE s.symbol = 'SOLUSDT'
  AND mp.ts_exchange >= NOW() - INTERVAL '1 hour'
ORDER BY mp.ts_exchange;

-- Ликвидации
SELECT s.symbol, fo.*
FROM marketdata.force_orders fo
JOIN marketdata.symbols s ON s.id = fo.symbol_id
WHERE s.symbol IN ('SOLUSDT','FIOUSDT')
  AND fo.ts_exchange >= NOW() - INTERVAL '1 day'
ORDER BY fo.ts_exchange;
```

## Рекомендованные практики

- Временные поля: используйте `ts_exchange` (UTC) как опорное «время события».
- Идемпотентность при инкрементальном чтении:
  - `book_ticker`: PK включает `(symbol_id, ts_exchange, COALESCE(update_id,0))` — допускает несколько тиков в одну миллисекунду.
  - `trades`: PK `(symbol_id, agg_trade_id)`
  - `depth_events`: PK `(symbol_id, ts_exchange, final_update_id)`
- Ограничения по объёму:
  - `depth_events` генерирует большой поток. Для ML лучше заранее агрегировать в Top-N (`orderbook_topN`) или использовать 1s фичи.
- TimescaleDB:
  - Хранение — Hypertable; Retention/Compression включены по расписанию.
- Качество данных (QA):
  - L1 coverage (book_ticker): >= 99.9% за 6ч
  - Цепочка depth: без разрывов по update_id
  - Дубликаты — не допускаются по PK
  - Спред/микроцена — без артефактов (NaN/Inf)

## Частые выборки для ML пайплайна

- Ежедневный выгруз: объединить `bt_1s` и `trade_1s` по `(symbol_id, ts_second)` в окно дат. Для CSV/Parquet экспорта используйте серверный экспорт или клиентский скрипт (pandas/pyarrow).
- Для тиковой модели — выбирайте `book_ticker` и `trades` в интервале, синхронизируйте по ближайшему времени или ресемплингу на стороне клиента.
- Для реконструкции стакана — используйте `depth_events` + REST snapshot; хранить промежуточный state лучше на своей стороне, применяя delta последовательно.

---

Контакты и дополнения: см. также `collector/docs/ds_spec_binance_streams_trades_depth.md` и `collector/docs/continuous_aggregates.md`.
