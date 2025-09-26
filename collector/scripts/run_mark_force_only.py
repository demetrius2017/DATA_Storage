#!/usr/bin/env python3
"""
Helper runner: start MultiStreamCollector only for markPrice@1s and forceOrder streams
Use when base BatchIngestor already collects bookTicker/aggTrade/depth to avoid duplication.
"""
import asyncio
import os
from collector.ingestion.multi_stream_collector import MultiStreamCollector


async def main():
    os.environ.setdefault('ENABLE_BOOK_TICKER', 'false')
    os.environ.setdefault('ENABLE_AGG_TRADE', 'false')
    # keep depth top off here by default
    os.environ.setdefault('ENABLE_DEPTH_TOP', 'false')
    # Ensure mark/force are on
    os.environ.setdefault('ENABLE_MARK_PRICE', 'true')
    os.environ.setdefault('ENABLE_FORCE_ORDER', 'true')

    dsn = os.getenv('DATABASE_URL')
    if not dsn:
        raise SystemExit('DATABASE_URL is required')

    collector = MultiStreamCollector(dsn, batch_size=200)
    await collector.initialize()
    await collector.start()


if __name__ == '__main__':
    asyncio.run(main())
