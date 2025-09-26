# DS Spec: Binance Futures Streams (trade, aggTrade, bookTicker, depth@100ms, markPrice@1s, forceOrder)

Цель: формализовать источники данных и схему в PostgreSQL для стабильного лоадинга фич и датасетов под МЛ.

## Источники

- WebSocket (Futures):
  - <wss://fstream.binance.com/stream?streams=> комбинированные потоки
  - По одному символу: trade, aggTrade, bookTicker, depth@100ms, markPrice@1s, forceOrder
  - Глобальные (!bookTicker, !markPrice@arr, !forceOrder@arr) — отдельно от core
- REST:
  - Снапшоты orderbook (для реконструкции) + бэкап на случай пропусков

## DDL PostgreSQL (кратко)

- marketdata.symbols — справочник инструментов
- marketdata.book_ticker — top-of-book raw (PK: symbol_id, ts_exchange, coalesce(update_id,0))
- marketdata.trades — aggTrade raw (PK: symbol_id, agg_trade_id)
- marketdata.depth_events — raw depth диффы (PK: symbol_id, ts_exchange, final_update_id)
- marketdata.mark_price — mark/index price (PK: symbol_id, ts_exchange)
- marketdata.force_orders — ликвидации (PK: symbol_id, ts_exchange, side, price, qty)
- marketdata.bt_1s, marketdata.trade_1s — агрегаты 1s
- Hypertables (если TimescaleDB), retention/compression — настроены

Подробный SQL: `collector/sql/create_marketdata_schema.sql`.

## Правила

- Символ-изоляция: партиционирование по `symbol_id`, PK включает время
- Идемпотентность: ON CONFLICT DO NOTHING/PK ключи
- Depth: реконструкция через «snapshot + deltas»; отслеживание `U/u/pu`
- Авто‑reconnect WS, шардирование по символам, batch ingestion
- Ретеншн: depth_events 7d, raw/agg 30d, 1s агрегаты 180d

## QA и приёмка

- Заполненность L1 (book_ticker) ≥ 99.9% за 6 часов по каждому активному символу
- Связность update_id у depth: нет разрывов по `prev_final_update_id -> first_update_id`
- Отсутствие дублей (проверка PK/уникальных индексов)
- Валидные spread/microprice (spread ≥ 0, mid > 0)

## Что ещё можно собирать через fstream

- Глобальные массивы: `!bookTicker`, `!markPrice@arr`, `!forceOrder@arr` — собирать отдельно, не смешивая с core флоу
- Kline (например, kline_1m) — опционально для обогащения фич

---

Документ синхронизирован с текущим кодом коллектора (multi‑stream) и схемой в SQL; изменения согласовывать через PR.
