#!/usr/bin/env python3
"""
Проверка пер-символьного сбора через прямой запрос в БД.

Использование:
  python -m collector.tools.symbol_probe --symbols SOLUSDT,FIOUSDT,MLNUSDT,GHSTUSDT [--minutes 5]

Требования:
  - DATABASE_URL в окружении (postgresql://...)

Результат:
  - Печатает JSON-словарь по каждому символу: last_bt, bt_5m, bt_60m, tr_5m, tr_60m
  - Возвращает код 0, если все символы существуют и bt_5m > 0; иначе 1
"""
import os
import sys
import json
import argparse
import asyncio
from typing import List, Dict, Any
import asyncpg


async def probe_symbols(db_url: str, symbols: List[str], minutes: int) -> Dict[str, Any]:
    conn = await asyncpg.connect(db_url)
    try:
        out: Dict[str, Any] = {}
        for s in symbols:
            row = await conn.fetchrow(
                f"""
                SELECT 
                  s.symbol,
                  MAX(bt.ts_exchange) AS last_bt,
                  COUNT(*) FILTER (WHERE bt.ts_exchange >= NOW() - INTERVAL '{minutes} minutes') AS bt_5m,
                  COUNT(*) FILTER (WHERE bt.ts_exchange >= NOW() - INTERVAL '60 minutes') AS bt_60m,
                  COUNT(tr.*) FILTER (WHERE tr.ts_exchange >= NOW() - INTERVAL '{minutes} minutes') AS tr_5m,
                  COUNT(tr.*) FILTER (WHERE tr.ts_exchange >= NOW() - INTERVAL '60 minutes') AS tr_60m
                FROM marketdata.symbols s
                LEFT JOIN marketdata.book_ticker bt ON bt.symbol_id = s.id
                LEFT JOIN marketdata.trades tr ON tr.symbol_id = s.id
                WHERE s.symbol = $1
                GROUP BY s.symbol
                """,
                s,
            )
            if row:
                out[s] = {
                    'last_bt': row['last_bt'].isoformat() if row['last_bt'] else None,
                    'bt_5m': int(row['bt_5m'] or 0),
                    'bt_60m': int(row['bt_60m'] or 0),
                    'tr_5m': int(row['tr_5m'] or 0),
                    'tr_60m': int(row['tr_60m'] or 0),
                }
            else:
                out[s] = None
        return out
    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbols', required=True, help='CSV: e.g. SOLUSDT,FIOUSDT,MLNUSDT,GHSTUSDT')
    parser.add_argument('--minutes', type=int, default=5, help='Window for recent checks (default: 5)')
    args = parser.parse_args()

    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print(json.dumps({'error': 'DATABASE_URL is not set'}))
        sys.exit(2)

    symbols = [s.strip().upper() for s in args.symbols.split(',') if s.strip()]
    result = asyncio.run(probe_symbols(db_url, symbols, args.minutes))
    print(json.dumps(result))

    # Exit non-zero if any missing or no recent updates
    for s in symbols:
        info = result.get(s)
        if not info or int(info.get('bt_5m', 0)) <= 0:
            sys.exit(1)

    sys.exit(0)


if __name__ == '__main__':
    main()
