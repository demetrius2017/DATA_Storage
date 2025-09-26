# Рецепты gapfill/LOCF для 1s рядов

Этот документ описывает два подхода к формированию «ровной» сетки 1s:

1) PostgreSQL + MV на 24h окно
2) TimescaleDB continuous aggregates (`time_bucket_gapfill` + `locf`)

## 1) PostgreSQL: Materialized View на 24 часа

Идея: генерировать секундную сетку на окно `[now()-24h .. now())`, джоинить к `bt_1s` и `trade_1s`, применять LOCF только к state-полям.

Ключевые пункты:
- Генерация сетки: `generate_series(t_from, t_to, interval '1 second')`.
- LEFT JOIN к `bt_1s` и `trade_1s` по `(symbol_id, ts_second)`.
- LOCF: `mid_ffill`, `spread_ffill` — через оконные функции по последнему не NULL значению.
- Счётчики/объёмы: нули/NULL на пустых секундах.
- Индекс на `(symbol_id, ts_second)` и `REFRESH CONCURRENTLY` по расписанию.

См. готовый SQL: `collector/sql/features_core_1s.sql`.

## 2) TimescaleDB: Continuous Aggregate + gapfill/locf

Если доступен TimescaleDB, используйте `time_bucket_gapfill` и `locf` для state-полей и объедините с трейдами.

Пример (концептуально):

```
CREATE MATERIALIZED VIEW feature.core_1s_ts
WITH (timescaledb.continuous) AS
SELECT
  s.id AS symbol_id,
  time_bucket_gapfill('1 second', b.ts_second) AS ts_second,
  locf(MAX(b.mid_close)) AS mid_ffill,
  locf(AVG(b.spread_mean)) AS spread_ffill,
  COALESCE(SUM(t.trade_count), 0) AS trade_count,
  SUM(t.volume_sum) AS volume_sum,
  CASE WHEN COALESCE(SUM(t.trade_count), 0) = 0 THEN NULL
       ELSE SUM(t.vwap * t.trade_count) / NULLIF(SUM(t.trade_count), 0)
  END AS vwap
FROM marketdata.symbols s
LEFT JOIN marketdata.bt_1s b ON b.symbol_id = s.id
LEFT JOIN marketdata.trade_1s t ON t.symbol_id = s.id
GROUP BY s.id, time_bucket_gapfill('1 second', b.ts_second);
```

Далее настроить policy для refresh и ретеншна. Конкретный синтаксис зависит от версии TimescaleDB.

## Производительность и эксплуатация

- Для MV на 24h: выбирайте окно и расписание так, чтобы refresh занимал < 1 минуты и не мешал ingest.
- Индексы критичны для `REFRESH CONCURRENTLY` и выборок по символу и времени.
- При больших объёмах и горизонтах > 24h лучше переходить на TimescaleDB continuous aggregates.
