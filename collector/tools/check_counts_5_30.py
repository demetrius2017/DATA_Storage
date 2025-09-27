#!/usr/bin/env python3
"""
Quick counts for last 5m and 30m in key tables: book_ticker, trades, depth_events, orderbook_topN/orderbook_top5.
Outputs JSON with counts to help triage ingestion.
"""
import os
import asyncio
import asyncpg
import json

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None


def load_db_url():
    db = os.getenv("DATABASE_URL")
    if db:
        return db
    if load_dotenv is not None:
        try:
            load_dotenv()
            if not os.getenv("DATABASE_URL") and os.path.exists('.env.production'):
                load_dotenv('.env.production')
        except Exception:
            pass
    return os.getenv("DATABASE_URL")


async def main():
    db = load_db_url()
    if not db:
        print(json.dumps({"error": "no DATABASE_URL"})); return
    conn = await asyncpg.connect(dsn=db)
    try:
        tables = {
            "book_ticker": "marketdata.book_ticker",
            "trades": "marketdata.trades",
            "depth_events": "marketdata.depth_events",
        }
        # decide processed table
        top_tbl = await conn.fetchval("SELECT CASE WHEN to_regclass('marketdata.orderbook_topn') IS NOT NULL THEN 'marketdata.orderbook_topN' WHEN to_regclass('marketdata.orderbook_top5') IS NOT NULL THEN 'marketdata.orderbook_top5' ELSE NULL END")
        tables["orderbook_top"] = top_tbl
        out = {}
        for k, v in tables.items():
            if not v:
                out[k] = {"5m": 0, "30m": 0}
                continue
            q = f"SELECT COUNT(*) FILTER (WHERE ts_exchange >= NOW() - INTERVAL '5 minutes') AS c5, COUNT(*) FILTER (WHERE ts_exchange >= NOW() - INTERVAL '30 minutes') AS c30 FROM {v}"
            r = await conn.fetchrow(q)
            out[k] = {"5m": int(r["c5"]) if r else 0, "30m": int(r["c30"]) if r else 0}
        print(json.dumps(out))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
