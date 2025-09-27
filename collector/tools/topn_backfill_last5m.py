#!/usr/bin/env python3
import os
import asyncio
import asyncpg
from typing import Dict, Any, List


async def fetch_recent_symbols(conn) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT DISTINCT d.symbol_id, s.symbol
        FROM marketdata.depth_events d
        JOIN marketdata.symbols s ON s.id = d.symbol_id
        WHERE d.ts_exchange >= NOW() - INTERVAL '5 minutes'
        ORDER BY 1
        """
    )
    return [{'symbol_id': r['symbol_id'], 'symbol': r['symbol']} for r in rows]


async def fetch_events(conn, symbol_id: int):
    rows = await conn.fetch(
        """
        SELECT EXTRACT(EPOCH FROM ts_exchange)*1000.0 AS E,
               first_update_id AS U,
               final_update_id AS u,
               bids AS b,
               asks AS a
        FROM marketdata.depth_events
        WHERE symbol_id = $1 AND ts_exchange >= NOW() - INTERVAL '5 minutes'
        ORDER BY ts_exchange ASC, final_update_id ASC
        """,
        symbol_id,
    )
    return [dict(r) for r in rows]


async def insert_topn(conn, records: List[Dict[str, Any]]):
    if not records:
        return 0
    await conn.executemany(
        """
        INSERT INTO marketdata.orderbook_topN (
            ts_exchange, symbol_id,
            b1_price, b1_qty, b2_price, b2_qty, b3_price, b3_qty, b4_price, b4_qty, b5_price, b5_qty,
            a1_price, a1_qty, a2_price, a2_qty, a3_price, a3_qty, a4_price, a4_qty, a5_price, a5_qty,
            microprice, i1, i5, wall_size_bid, wall_size_ask, wall_dist_bid_bps, wall_dist_ask_bps, ofi_1s
        ) VALUES (
            to_timestamp($1/1000.0), $2,
            $3,$4,$5,$6,$7,$8,$9,$10,$11,$12,
            $13,$14,$15,$16,$17,$18,$19,$20,$21,$22,
            $23,$24,$25,$26,$27,$28,$29,$30
        )
        ON CONFLICT (symbol_id, ts_exchange) DO NOTHING
        """,
        [
            (
                r['ts_exchange'], r['symbol_id'],
                r.get('b1_price'), r.get('b1_qty'), r.get('b2_price'), r.get('b2_qty'), r.get('b3_price'), r.get('b3_qty'),
                r.get('b4_price'), r.get('b4_qty'), r.get('b5_price'), r.get('b5_qty'),
                r.get('a1_price'), r.get('a1_qty'), r.get('a2_price'), r.get('a2_qty'), r.get('a3_price'), r.get('a3_qty'),
                r.get('a4_price'), r.get('a4_qty'), r.get('a5_price'), r.get('a5_qty'),
                r.get('microprice'), r.get('i1'), r.get('i5'), r.get('wall_size_bid'), r.get('wall_size_ask'),
                r.get('wall_dist_bid_bps'), r.get('wall_dist_ask_bps'), r.get('ofi_1s'),
            ) for r in records
        ],
    )
    return len(records)


async def main():
    dsn = os.getenv('DATABASE_URL')
    if not dsn:
        print('ERROR: DATABASE_URL not set'); return
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("SET lock_timeout = '5s'; SET statement_timeout = '30s';")
        symbols = await fetch_recent_symbols(conn)
        if not symbols:
            print('{"inserted":0, "symbols":0}'); return

        # Lazy import TopNBuilder
        from collector.processing.topn_builder import TopNBuilder
        builder = TopNBuilder()
        total = 0
        for row in symbols:
            sid = int(row['symbol_id']); sym = str(row['symbol'])
            events = await fetch_events(conn, sid)
            batch: List[Dict[str, Any]] = []
            for ev in events:
                ev['s'] = sym
                rec = await builder.process_event(sym, ev, sid)
                if rec:
                    batch.append(rec)
            total += len(batch)
            if batch:
                await insert_topn(conn, batch)
        print({"inserted": total, "symbols": len(symbols)})
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
