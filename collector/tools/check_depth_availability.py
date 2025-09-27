#!/usr/bin/env python3
import os
import asyncio
import asyncpg
import json
from typing import Optional

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None


def load_db_url() -> Optional[str]:
    db = os.getenv('DATABASE_URL')
    if db:
        return db
    if load_dotenv is not None:
        try:
            load_dotenv()
            if not os.getenv('DATABASE_URL') and os.path.exists('.env.production'):
                load_dotenv('.env.production')
        except Exception:
            pass
    return os.getenv('DATABASE_URL')


async def main():
    db = load_db_url()
    if not db:
        print(json.dumps({'error': 'no DATABASE_URL'})); return
    conn = await asyncpg.connect(dsn=db)
    try:
        # Tight timeout to avoid any long-running queries
        await conn.execute("SET LOCAL statement_timeout = '5s';")

        has_topn = await conn.fetchval("SELECT to_regclass('marketdata.orderbook_topn') IS NOT NULL;")
        depth_5m = await conn.fetchrow(
            """
            SELECT COUNT(*) AS cnt,
                   MIN(ts_exchange) AS min_ts,
                   MAX(ts_exchange) AS max_ts
            FROM marketdata.depth_events
            WHERE ts_exchange >= NOW() - INTERVAL '5 minutes'
            """
        )
        latest_depth = await conn.fetchrow(
            """
            SELECT symbol_id, MAX(ts_exchange) AS ts
            FROM marketdata.depth_events
            GROUP BY symbol_id
            ORDER BY ts DESC
            LIMIT 1
            """
        )
        out = {
            'orderbook_topN_exists': bool(has_topn),
            'depth_events_last5m': int(depth_5m['cnt']) if depth_5m else 0,
            'depth_events_min_ts_5m': depth_5m['min_ts'].isoformat() if depth_5m and depth_5m['min_ts'] else None,
            'depth_events_max_ts_5m': depth_5m['max_ts'].isoformat() if depth_5m and depth_5m['max_ts'] else None,
            'depth_latest_symbol_id': int(latest_depth['symbol_id']) if latest_depth else None,
            'depth_latest_ts': latest_depth['ts'].isoformat() if latest_depth and latest_depth['ts'] else None,
        }
        print(json.dumps(out))
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
