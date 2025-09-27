-- Compatibility VIEW for legacy consumers: orderbook_top5 maps to canonical orderbook_topN
-- Variant A: keep orderbook_topN as source of truth

CREATE OR REPLACE VIEW marketdata.orderbook_top5 AS
SELECT 
    ts_exchange,
    symbol_id,
    b1_price, b1_qty,
    b2_price, b2_qty,
    b3_price, b3_qty,
    b4_price, b4_qty,
    b5_price, b5_qty,
    a1_price, a1_qty,
    a2_price, a2_qty,
    a3_price, a3_qty,
    a4_price, a4_qty,
    a5_price, a5_qty,
    microprice,
    i1,
    i5,
    -- Legacy had wall_size_bps; approximate using larger wall size distance in bps if available, else NULL
    COALESCE(GREATEST(COALESCE(wall_dist_bid_bps, 0), COALESCE(wall_dist_ask_bps, 0)), NULL) as wall_size_bps
FROM marketdata.orderbook_topN;
