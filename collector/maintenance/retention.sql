-- Simple retention/maintenance script for PostgreSQL (no Timescale policies)
-- Run via cron or external scheduler
--
-- Parameters (suggested):
--   RETAIN_HOURS_BOOK_TICKER = 168   -- 7 days
--   RETAIN_HOURS_TRADES      = 168   -- 7 days
--   RETAIN_HOURS_DEPTH       = 72    -- 3 days (depth heavier)
--   RETAIN_HOURS_OB_TOP5     = 168   -- 7 days
--
-- NOTE:
-- - Use cautious values in production and adjust based on disk usage.
-- - Wrap in transaction per table to avoid long locks. Use smaller batches if needed.

BEGIN;
  -- Book Ticker
  DELETE FROM marketdata.book_ticker
  WHERE ts_exchange < NOW() - INTERVAL '168 hours';
COMMIT;

BEGIN;
  -- Trades
  DELETE FROM marketdata.trades
  WHERE ts_exchange < NOW() - INTERVAL '168 hours';
COMMIT;

BEGIN;
  -- Depth events (heavier)
  DELETE FROM marketdata.depth_events
  WHERE ts_exchange < NOW() - INTERVAL '72 hours';
COMMIT;

BEGIN;
  -- Derived top5 snapshot table
  -- Canonical table
  DELETE FROM marketdata.orderbook_topN
  WHERE ts_exchange < NOW() - INTERVAL '168 hours';
COMMIT;

-- Optional: reclaim space (be careful on large DBs)
-- VACUUM (ANALYZE) marketdata.book_ticker;
-- VACUUM (ANALYZE) marketdata.trades;
-- VACUUM (ANALYZE) marketdata.depth_events;
-- VACUUM (ANALYZE) marketdata.orderbook_topN;
