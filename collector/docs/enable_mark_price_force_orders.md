# Runbook: Включение каналов mark_price и force_orders

Цель: включить реальный сбор потоков Binance Futures `markPrice@1s` и `forceOrder`, применить DDL, убедиться в корректном наполнении таблиц.

Связанные ветки: `feature/ds-spec-streams-depth`
Компонент: `collector/ingestion/multi_stream_collector.py`
Схема БД: `marketdata`

## 1) Настроить окружение

В производственных переменных окружения:

- ENABLE_MARK_PRICE=true
- ENABLE_FORCE_ORDER=true

В `.env.production` (или секреты окружения в оркестраторе) добавить/раскомментировать:

```
ENABLE_MARK_PRICE=true
ENABLE_FORCE_ORDER=true
```

## 2) Применить DDL (если ещё не применён)

DDL находится в `collector/sql/create_marketdata_schema.sql`. Убедитесь, что созданы таблицы:

- `marketdata.mark_price` (PK, индексы, hypertable при наличии Timescale)
- `marketdata.force_orders` (PK, индексы, hypertable при наличии Timescale)

Если автомиграции не настроены, выполните DDL вручную под ролью DBA.

## 3) Деплой/рестарт коллектора

- Пересоберите контейнер и перезапустите сервис коллектора.
- Убедитесь по логам, что подписка на `markPrice@1s` и `forceOrder` активна.

## 4) Верификация (10–60 минут)

Проверьте наполнение и свежесть.

Примеры запросов:

- Наличие данных по символу за 10 минут:
```
SELECT symbol, COUNT(*)
FROM marketdata.mark_price mp
JOIN marketdata.symbols s ON s.id = mp.symbol_id
WHERE mp.ts_exchange > NOW() - INTERVAL '10 minutes'
GROUP BY symbol;
```

- Свежесть по каждому символу:
```
SELECT s.symbol, NOW() - MAX(mp.ts_exchange) AS lag
FROM marketdata.mark_price mp
JOIN marketdata.symbols s ON s.id = mp.symbol_id
GROUP BY s.symbol;
```

Аналогично для `marketdata.force_orders`.

## 5) Критерии приёмки (DoD)

- За последние 10 минут: `COUNT(*) > 0` по каждому целевому символу в обеих таблицах.
- Лаг `NOW() - MAX(ts_exchange)` ≤ 60–120 секунд.
- В логах ingestion отсутствуют ошибки по новым потокам.

## 6) Доступы

- Выдать ML-ролям только `SELECT` на новые таблицы (при необходимости), без прав записи/DDL.

## 7) Troubleshooting

- Нет данных: проверьте `ENABLE_MARK_PRICE/ENABLE_FORCE_ORDER` в runtime окружении контейнера, перезапустите сервис.
- Ошибки подписки: проверьте Binance WS endpoint и сетевые ACL.
- Несоответствие `symbol_id`: убедитесь, что таблица `marketdata.symbols` содержит нужные тикеры и корректно резолвится при инсёрте.
