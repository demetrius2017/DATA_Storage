#!/usr/bin/env python3
"""
Точечный probe для каналов mark_price и force_orders:
- total COUNT
- MAX(ts_exchange)
- COUNT за 60m и 24h
- топ-символы за 24h
- по одному последнему ряду (sample)
"""
import os
import asyncio
import asyncpg
from dotenv import load_dotenv

SQL = {
    "totals": {
        "mark_price_total": "SELECT COUNT(*) FROM marketdata.mark_price;",
        "force_orders_total": "SELECT COUNT(*) FROM marketdata.force_orders;",
    },
    "last_ts": {
        "mark_price_last": "SELECT MAX(ts_exchange) AS max_ts FROM marketdata.mark_price;",
        "force_orders_last": "SELECT MAX(ts_exchange) AS max_ts FROM marketdata.force_orders;",
    },
    "window_counts": {
        "mark_price_60m": "SELECT COUNT(*) FROM marketdata.mark_price WHERE ts_exchange >= NOW() - INTERVAL '60 minutes';",
        "force_orders_60m": "SELECT COUNT(*) FROM marketdata.force_orders WHERE ts_exchange >= NOW() - INTERVAL '60 minutes';",
        "mark_price_24h": "SELECT COUNT(*) FROM marketdata.mark_price WHERE ts_exchange >= NOW() - INTERVAL '24 hours';",
        "force_orders_24h": "SELECT COUNT(*) FROM marketdata.force_orders WHERE ts_exchange >= NOW() - INTERVAL '24 hours';",
    },
    "top_symbols_24h": (
        "SELECT s.symbol, COUNT(*) AS cnt "
        "FROM marketdata.mark_price mp JOIN marketdata.symbols s ON s.id = mp.symbol_id "
        "WHERE mp.ts_exchange >= NOW() - INTERVAL '24 hours' "
        "GROUP BY s.symbol ORDER BY cnt DESC LIMIT 10;"
    ),
    "latest_rows": {
        "mark_price": "SELECT * FROM marketdata.mark_price ORDER BY ts_exchange DESC LIMIT 1;",
        "force_orders": "SELECT * FROM marketdata.force_orders ORDER BY ts_exchange DESC LIMIT 1;",
    }
}


async def main():
    # Подгружаем .env/.env.production
    load_dotenv()
    if not os.getenv('DATABASE_URL') and os.path.exists('.env.production'):
        load_dotenv('.env.production')
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("DATABASE_URL не задан")
        return 2

    conn = await asyncpg.connect(db_url)
    try:
        print("== Totals ==")
        for name, q in SQL["totals"].items():
            r = await conn.fetchrow(q)
            print(f"{name:18s}: {r['count']}")

        print("\n== Last timestamps ==")
        for name, q in SQL["last_ts"].items():
            r = await conn.fetchrow(q)
            print(f"{name:18s}: {r['max_ts']}")

        print("\n== Window counts (60m / 24h) ==")
        for name, q in SQL["window_counts"].items():
            r = await conn.fetchrow(q)
            print(f"{name:18s}: {r['count']}")

        print("\n== Top symbols by mark_price (24h) ==")
        rows = await conn.fetch(SQL["top_symbols_24h"])
        if rows:
            for r in rows:
                print(f"{r['symbol']:12s} {r['cnt']}")
        else:
            print("<none>")

        print("\n== Latest rows (samples) ==")
        for name, q in SQL["latest_rows"].items():
            try:
                r = await conn.fetchrow(q)
                print(f"{name:12s}: {dict(r) if r else None}")
            except Exception as e:
                print(f"{name:12s}: error {e}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
