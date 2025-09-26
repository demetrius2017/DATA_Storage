"""
Core 1s Aggregator
-------------------
Материализация сводной таблицы feature.core_1s из marketdata.bt_1s и marketdata.trade_1s.

Контракт:
- Вход: интервал времени [start_ts, end_ts), опционально фильтр по symbol.
- Выход: записи в feature.core_1s с PK(symbol_id, ts_second), idempotent (ON CONFLICT DO UPDATE).

Использование: импортировать функцию build_core_1s(...) из задач/оркестрации.
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional
import asyncpg

UPSERT_SQL = """
INSERT INTO feature.core_1s (
    ts_second, symbol_id,
    mid_open, mid_high, mid_low, mid_close,
    spread_mean, spread_std, bid_qty_mean, ask_qty_mean, updates_count,
    trade_count, volume_sum, value_sum, vwap,
    buy_volume, sell_volume, buy_count, sell_count,
    imbalance_ratio, price_min, price_max
)
SELECT 
    bt.ts_second, bt.symbol_id,
    bt.mid_open, bt.mid_high, bt.mid_low, bt.mid_close,
    bt.spread_mean, bt.spread_std, bt.bid_qty_mean, bt.ask_qty_mean, bt.updates_count,
    tr.trade_count, tr.volume_sum, tr.value_sum, tr.vwap,
    tr.buy_volume, tr.sell_volume, tr.buy_count, tr.sell_count,
    tr.imbalance_ratio, tr.price_min, tr.price_max
FROM marketdata.bt_1s bt
LEFT JOIN marketdata.trade_1s tr
  ON tr.symbol_id = bt.symbol_id AND tr.ts_second = bt.ts_second
WHERE bt.ts_second >= $1 AND bt.ts_second < $2
  AND ($3::bigint IS NULL OR bt.symbol_id = $3)
ON CONFLICT (symbol_id, ts_second) DO UPDATE SET
    mid_open = EXCLUDED.mid_open,
    mid_high = EXCLUDED.mid_high,
    mid_low = EXCLUDED.mid_low,
    mid_close = EXCLUDED.mid_close,
    spread_mean = EXCLUDED.spread_mean,
    spread_std = EXCLUDED.spread_std,
    bid_qty_mean = EXCLUDED.bid_qty_mean,
    ask_qty_mean = EXCLUDED.ask_qty_mean,
    updates_count = EXCLUDED.updates_count,
    trade_count = EXCLUDED.trade_count,
    volume_sum = EXCLUDED.volume_sum,
    value_sum = EXCLUDED.value_sum,
    vwap = EXCLUDED.vwap,
    buy_volume = EXCLUDED.buy_volume,
    sell_volume = EXCLUDED.sell_volume,
    buy_count = EXCLUDED.buy_count,
    sell_count = EXCLUDED.sell_count,
    imbalance_ratio = EXCLUDED.imbalance_ratio,
    price_min = EXCLUDED.price_min,
    price_max = EXCLUDED.price_max
"""

async def build_core_1s(conn_str: str, start_ts: str, end_ts: str, symbol_id: Optional[int] = None) -> int:
    """
    Заполнить feature.core_1s за интервал времени.

    Args:
        conn_str: DSN PostgreSQL
        start_ts: Начало интервала (ISO8601)
        end_ts: Конец интервала (ISO8601)
        symbol_id: Фильтр по символу (id), если None — все символы
    Returns:
        Количество вставленных/обновлённых строк (оценочно)
    """
    pool = await asyncpg.create_pool(conn_str, min_size=1, max_size=4)
    try:
        async with pool.acquire() as conn:
            res = await conn.execute(UPSERT_SQL, start_ts, end_ts, symbol_id)
            # res формат: 'INSERT 0 <n>' или 'UPDATE ...'; вернём best-effort n
            try:
                n = int(res.split()[-1])
            except Exception:
                n = 0
            return n
    finally:
        await pool.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--symbol-id', type=int)
    args = parser.parse_args()

    dsn = os.environ.get('DATABASE_URL')
    if not dsn:
        raise SystemExit("DATABASE_URL not set")

    n = asyncio.run(build_core_1s(dsn, args.start, args.end, args.symbol_id))
    print({"rows": n})
