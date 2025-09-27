#!/usr/bin/env python3
"""
Быстрый probe для проверки, что данные реально пишутся в PostgreSQL.
Читает DATABASE_URL из env или принимает через --db.
Выводит:
- последние ts_exchange по основным таблицам,
- количество записей за последние 5/60 минут,
- топ-символы по book_ticker за 60 минут,
- строку из marketdata.ingestion_stats (если view доступен).
"""
import os
import asyncio
import argparse
import asyncpg
from datetime import timedelta
from dotenv import load_dotenv

DEFAULT_LAST_MIN = 5
DEFAULT_LAST_MIN_LONG = 60

SQL_QUERIES = {
    "last_ts": {
        "book_ticker": "SELECT MAX(ts_exchange) AS max_ts FROM marketdata.book_ticker;",
        "trades": "SELECT MAX(ts_exchange) AS max_ts FROM marketdata.trades;",
        "depth_events": "SELECT MAX(ts_exchange) AS max_ts FROM marketdata.depth_events;",
        "mark_price": "SELECT MAX(ts_exchange) AS max_ts FROM marketdata.mark_price;",
        "force_orders": "SELECT MAX(ts_exchange) AS max_ts FROM marketdata.force_orders;",
        "orderbook_top5": "SELECT MAX(ts_exchange) AS max_ts FROM marketdata.orderbook_top5;"
    },
    "counts_recent": {
        "book_ticker_5m": "SELECT COUNT(*) FROM marketdata.book_ticker WHERE ts_exchange >= NOW() - INTERVAL '5 minutes';",
        "trades_5m": "SELECT COUNT(*) FROM marketdata.trades WHERE ts_exchange >= NOW() - INTERVAL '5 minutes';",
        "depth_events_5m": "SELECT COUNT(*) FROM marketdata.depth_events WHERE ts_exchange >= NOW() - INTERVAL '5 minutes';",
        "mark_price_5m": "SELECT COUNT(*) FROM marketdata.mark_price WHERE ts_exchange >= NOW() - INTERVAL '5 minutes';",
        "force_orders_5m": "SELECT COUNT(*) FROM marketdata.force_orders WHERE ts_exchange >= NOW() - INTERVAL '5 minutes';",
        "book_ticker_60m": "SELECT COUNT(*) FROM marketdata.book_ticker WHERE ts_exchange >= NOW() - INTERVAL '60 minutes';",
        "trades_60m": "SELECT COUNT(*) FROM marketdata.trades WHERE ts_exchange >= NOW() - INTERVAL '60 minutes';",
        "depth_events_60m": "SELECT COUNT(*) FROM marketdata.depth_events WHERE ts_exchange >= NOW() - INTERVAL '60 minutes';"
    },
    "top_symbols": {
        "book_ticker_top": (
            "SELECT s.symbol, COUNT(*) AS cnt "
            "FROM marketdata.book_ticker bt JOIN marketdata.symbols s ON s.id = bt.symbol_id "
            "WHERE bt.ts_exchange >= NOW() - INTERVAL '60 minutes' "
            "GROUP BY s.symbol ORDER BY cnt DESC LIMIT 10;"
        )
    },
    "ingestion_stats": "SELECT * FROM marketdata.ingestion_stats ORDER BY book_ticker_count_1h DESC LIMIT 10;"
}

async def run_probe(db_url: str):
    conn = await asyncpg.connect(db_url)
    try:
        print("== Last timestamps ==")
        for name, sql in SQL_QUERIES["last_ts"].items():
            row = await conn.fetchrow(sql)
            print(f"{name:16s}: {row['max_ts']}")
        
        print("\n== Counts recent (5m / 60m) ==")
        for name, sql in SQL_QUERIES["counts_recent"].items():
            row = await conn.fetchrow(sql)
            print(f"{name:16s}: {row['count']}")
        
        print("\n== Top symbols by book_ticker (60m) ==")
        rows = await conn.fetch(SQL_QUERIES["top_symbols"]["book_ticker_top"])
        for r in rows:
            print(f"{r['symbol']:12s} {r['cnt']}")
        
        print("\n== Ingestion stats (view) ==")
        try:
            rows = await conn.fetch(SQL_QUERIES["ingestion_stats"]) 
            for r in rows:
                print(dict(r))
        except Exception as e:
            print(f"ingestion_stats not available: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    # Подхватим переменные окружения из .env и .env.production, если доступны
    try:
        load_dotenv()  # .env по умолчанию
        if not os.getenv('DATABASE_URL') and os.path.exists('.env.production'):
            load_dotenv('.env.production')
    except Exception:
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument('--db', dest='db', default=os.getenv('DATABASE_URL'), help='Database URL (postgres:// or postgresql://)')
    args = parser.parse_args()
    if not args.db:
        print("DATABASE_URL not provided. Use --db=... or set env var.")
        raise SystemExit(2)
    asyncio.run(run_probe(args.db))
