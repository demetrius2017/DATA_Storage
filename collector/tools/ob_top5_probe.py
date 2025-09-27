#!/usr/bin/env python3
"""
Лёгкий probe для marketdata.orderbook_top5 без тяжёлых сканов.

Что делает быстро:
- Проверяет существование таблицы через to_regclass.
- Даёт приблизительный размер и число строк по каталогу (pg_class.reltuples, pg_total_relation_size).
- Находит максимальный ts_exchange индекс-дружелюбно:
  DISTINCT ON (symbol_id) ORDER BY symbol_id, ts_exchange DESC — использует индекс (symbol_id, ts_exchange),
  затем берёт глобальный максимум по возвращённым строкам (число символов обычно <= 200).
- Выводит 3 последние строки для символа с max ts (индексное ORDER BY ts DESC LIMIT 3).

Подхватывает DATABASE_URL из окружения или .env/.env.production.
"""
import os
import asyncio
import asyncpg
from typing import Optional, Tuple

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None  # optional


async def table_exists(conn: asyncpg.Connection, fqname: str) -> bool:
    row = await conn.fetchrow("SELECT to_regclass($1) IS NOT NULL AS exists;", fqname)
    return bool(row[0]) if row else False


async def get_table_estimates(conn: asyncpg.Connection, schema: str, table: str) -> Tuple[Optional[int], Optional[int]]:
    """Возвращает (estimated_rows, total_size_bytes)."""
    est_rows = await conn.fetchval(
        """
        SELECT reltuples::bigint
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = $1 AND c.relname = $2;
        """,
        schema, table,
    )
    # Для идентификаторов нельзя использовать параметры, соберём строку через format() безопасно
    ident = await conn.fetchval("SELECT format('%I.%I', $1::text, $2::text);", schema, table)
    size_bytes = await conn.fetchval(f"SELECT pg_total_relation_size('{ident}');")
    return (int(est_rows) if est_rows is not None else None, int(size_bytes) if size_bytes is not None else None)


async def get_max_ts_and_symbol(conn: asyncpg.Connection) -> Optional[Tuple[int, str, str]]:
    """Возвращает (symbol_id, symbol, max_ts_iso) через индекс-дружелюбный запрос.

    Сначала берём по одному последнему ts на символ (DISTINCT ON ... ORDER BY symbol_id, ts_exchange DESC),
    затем выбираем максимальный ts среди них.
    """
    rows = await conn.fetch(
        """
        WITH last_per_symbol AS (
            SELECT DISTINCT ON (ob.symbol_id)
                ob.symbol_id,
                ob.ts_exchange
            FROM marketdata.orderbook_top5 ob
            ORDER BY ob.symbol_id, ob.ts_exchange DESC
        )
        SELECT l.symbol_id, s.symbol, l.ts_exchange
        FROM last_per_symbol l
        JOIN marketdata.symbols s ON s.id = l.symbol_id
        ORDER BY l.ts_exchange DESC
        LIMIT 1;
        """
    )
    if not rows:
        return None
    r = rows[0]
    return int(r["symbol_id"]), str(r["symbol"]), r["ts_exchange"].isoformat()


async def get_last_rows_for_symbol(conn: asyncpg.Connection, symbol_id: int, limit: int = 3):
    """Возвращает последние limit строк для заданного symbol_id (быстро по индексу)."""
    rows = await conn.fetch(
        """
        SELECT ts_exchange, b1_price, b1_qty, a1_price, a1_qty
        FROM marketdata.orderbook_top5
        WHERE symbol_id = $1
        ORDER BY ts_exchange DESC
        LIMIT $2;
        """,
        symbol_id, limit,
    )
    return [
        {
            "ts_exchange": r["ts_exchange"].isoformat() if r["ts_exchange"] else None,
            "b1": [r["b1_price"], r["b1_qty"]],
            "a1": [r["a1_price"], r["a1_qty"]],
        }
        for r in rows
    ]


async def main(db_url: str):
    conn = await asyncpg.connect(db_url)
    try:
        exists = await table_exists(conn, "marketdata.orderbook_top5")
        print(f"exists: {exists}")
        if not exists:
            return

        est_rows, size_bytes = await get_table_estimates(conn, "marketdata", "orderbook_top5")
        size_mb = round(size_bytes / (1024 * 1024), 2) if size_bytes else None
        print(f"estimated_rows: {est_rows}")
        print(f"total_size_mb: {size_mb}")

        max_info = await get_max_ts_and_symbol(conn)
        if not max_info:
            print("max_ts: None")
            return
        symbol_id, symbol, max_ts_iso = max_info
        print(f"max_ts_exchange: {max_ts_iso}")
        print(f"max_ts_symbol: {symbol} (id={symbol_id})")

        last_rows = await get_last_rows_for_symbol(conn, symbol_id, limit=3)
        print("last_rows_for_symbol:")
        for item in last_rows:
            print(item)
    finally:
        await conn.close()


if __name__ == "__main__":
    # Подхватим переменные окружения из .env и .env.production, если доступны
    if load_dotenv is not None:
        try:
            load_dotenv()  # .env по умолчанию
            if not os.getenv('DATABASE_URL') and os.path.exists('.env.production'):
                load_dotenv('.env.production')
        except Exception:
            pass

    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("DATABASE_URL env var is required")
        raise SystemExit(2)
    asyncio.run(main(db_url))
