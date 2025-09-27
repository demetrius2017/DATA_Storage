#!/usr/bin/env python3
"""
Создаёт таблицу marketdata.orderbook_topN (если отсутствует), переводит в hypertable и добавляет индексы.
Идempotent и безопасно к многократному запуску. Не трогает legacy marketdata.orderbook_top5 (если это TABLE).
"""
import os
import asyncio
import asyncpg

DDL = r'''
CREATE SCHEMA IF NOT EXISTS marketdata;
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS marketdata.orderbook_topN (
    ts_exchange timestamptz NOT NULL,
    symbol_id bigint NOT NULL REFERENCES marketdata.symbols(id),
    b1_price double precision, b1_qty double precision,
    b2_price double precision, b2_qty double precision,
    b3_price double precision, b3_qty double precision,
    b4_price double precision, b4_qty double precision,
    b5_price double precision, b5_qty double precision,
    a1_price double precision, a1_qty double precision,
    a2_price double precision, a2_qty double precision,
    a3_price double precision, a3_qty double precision,
    a4_price double precision, a4_qty double precision,
    a5_price double precision, a5_qty double precision,
    microprice double precision,
    i1 double precision,
    i5 double precision,
    wall_size_bid double precision,
    wall_size_ask double precision,
    wall_dist_bid_bps double precision,
    wall_dist_ask_bps double precision,
    ofi_1s double precision,
    total_bid_qty double precision GENERATED ALWAYS AS (
        COALESCE(b1_qty,0) + COALESCE(b2_qty,0) + COALESCE(b3_qty,0) + COALESCE(b4_qty,0) + COALESCE(b5_qty,0)
    ) STORED,
    total_ask_qty double precision GENERATED ALWAYS AS (
        COALESCE(a1_qty,0) + COALESCE(a2_qty,0) + COALESCE(a3_qty,0) + COALESCE(a4_qty,0) + COALESCE(a5_qty,0)
    ) STORED,
    PRIMARY KEY (symbol_id, ts_exchange)
);

-- Hypertable (idempotent)
SELECT create_hypertable(
    'marketdata.orderbook_topN', 'ts_exchange',
    chunk_time_interval => INTERVAL '6 hours', if_not_exists => TRUE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_orderbook_topN_time ON marketdata.orderbook_topN (symbol_id, ts_exchange);
'''


async def main():
    dsn = os.getenv('DATABASE_URL')
    if not dsn:
        print('ERROR: DATABASE_URL not set', flush=True)
        return 1
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("SET lock_timeout = '5s'; SET statement_timeout = '15s';")
        await conn.execute(DDL)
        exists = await conn.fetchval("SELECT to_regclass('marketdata.orderbook_topn') IS NOT NULL;")
        print({'orderbook_topN_exists': bool(exists)})
    finally:
        await conn.close()
    return 0


if __name__ == '__main__':
    asyncio.run(main())
