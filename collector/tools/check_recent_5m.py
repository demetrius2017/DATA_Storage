#!/usr/bin/env python3
"""
Check last 5 minutes data presence in marketdata.orderbook_topN (or fallback to orderbook_top5 VIEW).

Outputs compact JSON:
{
  "table": "marketdata.orderbook_topN",
  "count_5m": 1234,
  "min_ts": "...",
  "max_ts": "..."
}

DATABASE_URL is taken from env, or loaded from .env/.env.production if available.
"""
import os
import asyncio
import asyncpg
import json
from typing import Optional

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None


def _load_db_url() -> Optional[str]:
    db = os.getenv("DATABASE_URL")
    if db:
        return db
    # Try load from .env and .env.production
    if load_dotenv is not None:
        try:
            load_dotenv()
            db = os.getenv("DATABASE_URL")
            if db:
                return db
            if os.path.exists('.env.production'):
                load_dotenv('.env.production')
                db = os.getenv("DATABASE_URL")
                if db:
                    return db
        except Exception:
            pass
    return None


async def main():
    db_url = _load_db_url()
    if not db_url:
        print(json.dumps({"error": "no DATABASE_URL"}))
        return
    conn = await asyncpg.connect(dsn=db_url)
    try:
        table = await conn.fetchval(
            """
            SELECT CASE 
                WHEN to_regclass('marketdata.orderbook_topn') IS NOT NULL THEN 'marketdata.orderbook_topN'
                WHEN to_regclass('marketdata.orderbook_top5') IS NOT NULL THEN 'marketdata.orderbook_top5'
                ELSE NULL END
            """
        )
        if not table:
            print(json.dumps({"table": None, "count_5m": 0, "min_ts": None, "max_ts": None}))
            return
        q = f"""
            SELECT MIN(ts_exchange) AS min_ts, MAX(ts_exchange) AS max_ts, COUNT(*) AS cnt
            FROM {table}
            WHERE ts_exchange >= NOW() - INTERVAL '5 minutes'
        """
        r = await conn.fetchrow(q)
        def iso(x):
            try:
                return x.isoformat() if x else None
            except Exception:
                return None
        out = {
            "table": table,
            "count_5m": int(r['cnt']) if r and r['cnt'] is not None else 0,
            "min_ts": iso(r['min_ts'] if r else None),
            "max_ts": iso(r['max_ts'] if r else None),
        }
        print(json.dumps(out))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
