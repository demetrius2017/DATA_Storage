# PostgreSQL Market Data для ML: схема, рецепты и примеры

Этот документ даёт ML‑инженеру всё необходимое, чтобы понять структуру данных, быстро собрать фичи и таргеты для MLP/GRU моделей и выгрузить выборки в CSV/Parquet.

## Подключение к базе

- DSN (prod): переменная `DATABASE_URL` из `.env.production`
- Важно: все timestamps в UTC. Ключевые столбцы времени:
  - raw потоки: `ts_exchange` (время биржи), `ts_ingest` (время приёма)
  - агрегаты 1s: `ts_second`

Пример подключения в Python (psycopg):
```python
import os
import psycopg
import pandas as pd

conn = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
```

## Схема данных (marketdata.*)

- symbols
  - id (PK), exchange, symbol, instrument_type, base_asset, quote_asset, is_active
- book_ticker (raw top-of-book)
  - ts_exchange, ts_ingest, symbol_id, update_id, best_bid/ask, bid_qty/ask_qty, spread, mid, spread_bps (stored), PK(symbol_id, ts_exchange, coalesce(update_id,0))
- trades (aggTrade)
  - ts_exchange, ts_ingest, symbol_id, agg_trade_id, price, qty, is_buyer_maker, trade_value (stored), PK(symbol_id, agg_trade_id)
- depth_events (raw L2/L3 диффы)
  - ts_exchange, ts_ingest, symbol_id, first_update_id, final_update_id, prev_final_update_id, bids jsonb, asks jsonb, bids_count/asks_count (stored), PK(symbol_id, ts_exchange, final_update_id)
- orderbook_topN (процессинг top-5 уровней + микроструктура)
  - b1..b5_price/qty, a1..a5_price/qty, microprice, i1, i5, wall_*, ofi_1s, total_bid_qty/total_ask_qty (stored), PK(symbol_id, ts_exchange)
- bt_1s (агрегаты book_ticker по 1 сек)
  - ts_second, symbol_id, mid_ohlc, spread_mean/std/min/max, bid_qty_mean, ask_qty_mean, updates_count, volume_weighted_mid, PK(symbol_id, ts_second)
- trade_1s (агрегаты сделок по 1 сек)
  - ts_second, symbol_id, trade_count, volume_sum, value_sum, vwap, buy/sell_volume/count, imbalance_ratio (stored), price_min/max, PK(symbol_id, ts_second)
- views
  - yesterday_dataset: джойн `bt_1s` + `trade_1s` за «вчера», уже с lag‑фичами
  - ingestion_health: мониторинг ingestion

TimescaleDB (если включён): все большие таблицы — hypertable по времени + `symbol_id`; retention и compression настроены.

## Базовые соответствия для ML

- Идентификатор инструмента: `symbol_id` (джойнится на `symbols.id`). Для удобства можно джойнить `symbols` и работать по строковому `symbol`.
- Глубина (depth_events) — сырой jsonb; для фич лучше использовать `orderbook_topN` (готовые уровни) или агрегаты `bt_1s`/`trade_1s`.
- Рекомендованные источники для MLP/GRU:
  - MLP: табличные агрегаты `bt_1s` + `trade_1s` (+ при желании `orderbook_topN` на ближайший тик в секунде)
  - GRU: последовательности из `bt_1s` + `trade_1s` (L секунд истории) или повышенная частота из `book_ticker` при необходимости <1s

## Рецепт: базовый табличный датасет (MLP)

Задача: собрать признаки на 1s сетке и таргет — будущий доход за горизонтом H секунд (например, 5s) по mid‑price.

Пример SQL (один символ, интервал времени):
```sql
WITH base AS (
  SELECT 
    bt.ts_second,
    s.symbol,
    bt.mid_open, bt.mid_high, bt.mid_low, bt.mid_close,
    bt.spread_mean, bt.spread_std,
    bt.bid_qty_mean, bt.ask_qty_mean,
    bt.updates_count,
    tr.trade_count, tr.volume_sum, tr.vwap, tr.imbalance_ratio
  FROM marketdata.bt_1s bt
  JOIN marketdata.symbols s ON s.id = bt.symbol_id
  LEFT JOIN marketdata.trade_1s tr ON tr.symbol_id = bt.symbol_id AND tr.ts_second = bt.ts_second
  WHERE s.symbol = 'SOLUSDT'
    AND bt.ts_second >= '2025-09-21T00:00:00Z'
    AND bt.ts_second <  '2025-09-22T00:00:00Z'
), labeled AS (
  SELECT 
    b.*,
    LEAD(b.mid_close, 5) OVER (ORDER BY b.ts_second) AS mid_t_plus_5,
    CASE 
      WHEN LEAD(b.mid_close, 5) OVER (ORDER BY b.ts_second) IS NULL THEN NULL
      ELSE (LEAD(b.mid_close, 5) OVER (ORDER BY b.ts_second) - b.mid_close) / NULLIF(b.mid_close,0)
    END AS ret_5s
  FROM base b
)
SELECT * FROM labeled
WHERE mid_t_plus_5 IS NOT NULL
ORDER BY ts_second;
```
Идеи таргета:
- Регрессия: `ret_5s`
- Классификация: `label = sign(ret_5s)`, либо трёхкласс с порогом `±thr` (например, 0.05%): `label = 1 (up) / 0 (flat) / -1 (down)`

Экспорт в Parquet (psycopg + pandas + pyarrow):
```python
import os, psycopg, pandas as pd

sql = """<вставьте SQL выше>"""
with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    df = pd.read_sql(sql, conn)

# Пример целевой метки
thr = 0.0005
df["label3"] = df["ret_5s"].apply(lambda r: 1 if r>thr else (-1 if r<-thr else 0))

# Простейшая нормализация некоторых фич
for col in ["mid_close", "spread_mean", "spread_std", "bid_qty_mean", "ask_qty_mean", "trade_count", "volume_sum"]:
    df[f"z_{col}"] = (df[col] - df[col].mean())/ (df[col].std()+1e-9)

# Сохранение
df.to_parquet("mlp_SOLUSDT_1s_H5.parquet", index=False)
```

## Рецепт: последовательности для GRU (L шагов истории)

Идея: собрать последовательности длиной L=64 секунд (пример) по признакам из `bt_1s` и `trade_1s`, с шагом скольжения s (например, s=5).

Шаги:
1) Вытащить табличный базис (как в MLP), отсортированный по времени без пропусков секунд.
2) Преобразовать в тензор `X.shape = (N, L, F)` и таргеты `y.shape = (N, )` или `(N, C)`.

Пример Python:
```python
import numpy as np
import pandas as pd
import psycopg, os

L = 64  # длина окна
step = 5  # шаг смещения окна
features = [
    "mid_close", "spread_mean", "spread_std",
    "bid_qty_mean", "ask_qty_mean", "updates_count",
    "trade_count", "volume_sum", "vwap", "imbalance_ratio"
]

sql = """
WITH base AS (
  SELECT 
    bt.ts_second,
    bt.symbol_id,
    bt.mid_close, bt.spread_mean, bt.spread_std,
    bt.bid_qty_mean, bt.ask_qty_mean, bt.updates_count,
    tr.trade_count, tr.volume_sum, tr.vwap, tr.imbalance_ratio
  FROM marketdata.bt_1s bt
  LEFT JOIN marketdata.trade_1s tr ON tr.symbol_id = bt.symbol_id AND tr.ts_second = bt.ts_second
  JOIN marketdata.symbols s ON s.id = bt.symbol_id AND s.symbol = 'SOLUSDT'
  WHERE bt.ts_second >= '2025-09-21T00:00:00Z' AND bt.ts_second < '2025-09-22T00:00:00Z'
)
SELECT * FROM base ORDER BY ts_second;
"""

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    df = pd.read_sql(sql, conn)

# Создадим таргет: 5-секундный доход вперёд от mid_close
df["mid_fwd_5"] = df["mid_close"].shift(-5)
df["ret_5s"] = (df["mid_fwd_5"] - df["mid_close"]) / df["mid_close"].replace(0, np.nan)

# Нормализация (robust по медиане/IQR или стандартная)
Xtab = df[features].copy().fillna(method="ffill").fillna(0.0)
Xtab = (Xtab - Xtab.mean()) / (Xtab.std() + 1e-9)

# Формирование окон
Xs, ys = [], []
vals = Xtab.values
ret = df["ret_5s"].values
for i in range(0, len(df) - L - 5, step):
    window = vals[i:i+L]
    target = ret[i+L-1]  # target относительно конца окна
    if np.isnan(target):
        continue
    Xs.append(window)
    ys.append(target)

X = np.stack(Xs, axis=0)  # (N, L, F)
y = np.array(ys)

# Сохранить в Parquet (через pandas):
seq_df = pd.DataFrame({
    "X": list(X),  # массивы будут сериализованы как объекты; для обучения лучше сохранить в npz
    "y": y
})
seq_df.to_parquet("gru_SOLUSDT_L64_s5_H5.parquet", index=False)

# Альтернатива: сохранить компактно в .npz
np.savez_compressed("gru_SOLUSDT_L64_s5_H5.npz", X=X, y=y)
```
Примечания:
- Если нужна частота выше 1s — используйте `book_ticker` и агрегируйте в 100–250ms окна (в SQL через `time_bucket` при Timescale или в pandas), затем аналогично формируйте последовательности.
- Для многосимвольных наборов добавьте признак «one‑hot символа» или обучайте отдельные модели на каждый символ.

## Пример: добавление top‑N уровней (обогащение фич)

Если требуется микроструктура глубины, подмешайте ближайший `orderbook_topN` для соответствующей секунды.

```sql
SELECT 
  bt.ts_second, s.symbol,
  bt.mid_close, bt.spread_mean, bt.updates_count,
  tr.trade_count, tr.volume_sum, tr.imbalance_ratio,
  onb.b1_price, onb.b1_qty, onb.a1_price, onb.a1_qty,
  onb.microprice, onb.i1, onb.i5, onb.total_bid_qty, onb.total_ask_qty
FROM marketdata.bt_1s bt
JOIN marketdata.symbols s ON s.id = bt.symbol_id
LEFT JOIN marketdata.trade_1s tr ON tr.symbol_id=bt.symbol_id AND tr.ts_second=bt.ts_second
LEFT JOIN LATERAL (
  SELECT * FROM marketdata.orderbook_topN onb
  WHERE onb.symbol_id = bt.symbol_id
    AND onb.ts_exchange >= bt.ts_second
    AND onb.ts_exchange <  bt.ts_second + interval '1 second'
  ORDER BY onb.ts_exchange DESC
  LIMIT 1
) onb ON TRUE
WHERE s.symbol='SOLUSDT' AND bt.ts_second BETWEEN '2025-09-21' AND '2025-09-22'
ORDER BY bt.ts_second;
```

## Экспорт в CSV/Parquet для обучения

- CSV (server‑side):
```sql
\copy (
  SELECT * FROM marketdata.yesterday_dataset WHERE symbol='SOLUSDT' ORDER BY ts_second
) TO '/tmp/ds_SOLUSDT_yesterday.csv' CSV HEADER
```
- Parquet (Python): используйте `pandas.to_parquet()` (pyarrow/fastparquet).

## Производительность и надёжность

- Всегда фильтруйте по `symbol_id`/`symbol` и по диапазону времени.
- Используйте агрегаты `bt_1s`/`trade_1s` вместо сырых `book_ticker`/`trades` для уроков на длинных периодах — это значительно быстрее.
- Индексы уже есть: `(symbol_id, ts_second)` для 1s таблиц; `(symbol_id, ts_exchange)` для raw; Timescale hypertables оптимизируют скан.
- Пропуски секунд закрывайте ffill или удаляйте строки — это важно для корректной формы последовательностей.

## Мини‑контракт данных

- Вход (для MLP): табличные фичи на равномерной сетке времени (1s), по одному символу или по нескольким.
- Вход (для GRU): тензор (N, L, F) из тех же фич, окна без пропусков.
- Таргет: доход/направление за горизонт H секунд вперёд.
- Успех: стабильная генерация датасетов, repeatable прогон, валидационные метрики растут при добавлении информативных фич.

## Диагностика и свежесть данных

- Быстрая сводка: `GET http://<host>:8000/health` → status, counts_1m, last timestamps
- Системные метрики: `GET /api/system` на том же порту (если включено)

---

Итоговые примеры покрывают два типовых пайплайна: табличный (MLP) и последовательностный (GRU). При необходимости можно расширять состав фич за счёт `orderbook_topN` или более частых агрегатов из `book_ticker`. 