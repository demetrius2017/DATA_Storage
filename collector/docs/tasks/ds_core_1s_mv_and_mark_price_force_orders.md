# DS-задача: Ровная 1s сетка (MV) и включение mark_price/force_orders

Статус: план к исполнению (Phase 1 → 2)
Ответственные: DS/DBA
Связанные ветки: `feature/ds-spec-streams-depth`

## Причина (почему это нужно)

- Текущие агрегаты `marketdata.bt_1s` и `marketdata.trade_1s` «рваные» по секундам на неликвидных интервалах (coverage < 1.0), т.к. пишутся только секунды с событиями.
- Для стабильного ML-пайплайна требуется ровная сетка 1s с корректным gap‑fill/LOCF: переносить состояния (mid, spread), но не переносить счётчики.
- Каналы `mark_price` и `force_orders` пока не включены, но нужны для контроля справедливой цены, ликвидаций и как потенциальные признаки.

## Задача 1 — Материализованный вид «ровной» сетки 1s (24h окно)

Сделать в БД материализованный вид `feature.core_1s_24h` с ровной сеткой на 1 секунду по всем символам за последние 24 часа и корректной политикой gap‑fill/LOCF.

### Что сделать

1) Применить SQL из `collector/sql/features_core_1s.sql`:
   - Создать схему `feature` (если нет).
   - Создать MV `feature.core_1s_24h` (ровная сетка 1s на окно `[now()-24h .. now())`).
   - Создать индекс `(symbol_id, ts_second)` для быстрых чтений и `REFRESH CONCURRENTLY`.

2) LOCF-политика (важно):
   - Переносим только состояния: `ffmid = ffill(mid_close)`, `ffspread = ffill(spread_mean)` из `bt_1s`.
   - Не переносим счётчики: `update_count`, `trade_count` — равны 0, если в секунду нет событий.
   - `volume_sum` = 0 при отсутствии сделок; `vwap` = NULL, если `trade_count = 0`.

3) Настроить расписание обновления (cron/job):
   - Выполнять `REFRESH MATERIALIZED VIEW CONCURRENTLY feature.core_1s_24h` не реже 1 раза в минуту.
   - Окно скользящее за 24 часа: текущий `REFRESH` должен сдвигать окно.

4) Доступы:
   - `GRANT SELECT` на `feature.core_1s_24h` ML-ролям/сервис-аккаунтам.
   - Права на `REFRESH` держать на DS/DBA (рекомендуется). Если обновление с ML-стороны — выдать `REFRESH` только на этот объект.

5) Альтернатива (если TimescaleDB доступен):
   - Создать continuous aggregate с `time_bucket_gapfill` + `locf` для mid/spread и объединить с `trade_1s`.
   - Детальный рецепт — в `collector/docs/sql_gapfill_locf_recipes.md` (раздел TimescaleDB).

### Критерии приёмки (DoD)

- Coverage = 1.00: в любом окне в пределах 24 часов по каждому целевому символу `feature.core_1s_24h` содержит ровно 1 строку на секунду.
- Лаг обновления: `now() - max(ts_second)` ≤ 2 минуты при регулярном refresh каждую минуту.
- Корректность LOCF:
  - `mid_ffill` и `spread_ffill` удерживают последнее известное значение из `bt_1s`.
  - `update_count`/`trade_count` не переносятся (0 на пустых секундах).
  - `vwap = NULL` при отсутствии сделок; `volume_sum = 0`.
- Нагрузочные эффекты: `REFRESH` не деградирует ingest (окно и тайминг согласовать).

### Быстрый QA-чеклист

- MV создан, индексы на месте, первый `REFRESH CONCURRENTLY` выполнен.
- Запрос coverage для 5–15 минут по 3–4 символам показывает 1.00 (ровная сетка).
- Лаг обновления в норме, `REFRESH` стабилен.

## Задача 2 — Включить сбор `mark_price` и `force_orders`

### Что сделать

1) Установить ENV/Secrets для коллектора:
   - `ENABLE_MARK_PRICE=true`
   - `ENABLE_FORCE_ORDER=true`

2) Применить DDL (если необходимо) для таблиц:
   - `marketdata.mark_price`, `marketdata.force_orders` (см. `collector/sql/create_marketdata_schema.sql`).

3) Перезапустить деплой коллектора, убедиться в подписке на соответствующие потоки.

4) Провести верификацию за 10–60 минут:
   - Таблицы наполняются; есть строки по целевым символам; `symbol_id` корректно маппится на `marketdata.symbols`.

### Критерии приёмки (DoD)

- За последние 10 минут: `SELECT COUNT(*) > 0` для `marketdata.mark_price` и `marketdata.force_orders` по каждому целевому символу.
- Свежесть: лаг `now() - max(ts_exchange)` ≤ 60–120 секунд.
- Нет конфликтов/ошибок в логах ingestion для новых потоков.

## Общие политики/ограничения

- Live only: никаких synthetic/random данных.
- Строгая изоляция по символу: не смешивать метрики разных тикеров.
- Доступы: ML-ролям — только `SELECT` на `feature.core_1s_24h` и чтение новых таблиц.

## Ссылки на артефакты

- SQL: `collector/sql/features_core_1s.sql`
- Рецепты: `collector/docs/sql_gapfill_locf_recipes.md`
- Runbook: `collector/docs/enable_mark_price_force_orders.md`
- ML-гайд (канонические запросы): `collector/docs/ml_data_access_guide.md`
- Логика проекта: `ORDERBOOK_COLLECTION_LOGIC.md`

## Примечания по эксплуатации

- Для `REFRESH CONCURRENTLY` требуется уникальный индекс, покрывающий все строки MV: `(symbol_id, ts_second)`.
- Рекомендуется выделить отдельное окно maintenance по минутам, чтобы минимизировать совпадения с пиками ingest.
- При наличии TimescaleDB continuous aggregates предпочтительнее для больших горизонтов (но для 24h MV — достаточно).
