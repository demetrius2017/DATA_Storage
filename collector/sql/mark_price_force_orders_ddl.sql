-- DDL для marketdata.mark_price и marketdata.force_orders под текущую схему

CREATE SCHEMA IF NOT EXISTS marketdata;

-- MARK PRICE (@markPrice@1s)
CREATE TABLE IF NOT EXISTS marketdata.mark_price (
    ts_exchange timestamptz NOT NULL,
    ts_ingest timestamptz NOT NULL DEFAULT now(),
    symbol_id bigint NOT NULL REFERENCES marketdata.symbols(id),
    event_type text,
    mark_price double precision,
    index_price double precision,
    est_settlement_price double precision,
    funding_rate double precision,
    next_funding_time timestamptz,
    PRIMARY KEY (symbol_id, ts_exchange)
);
CREATE INDEX IF NOT EXISTS idx_mark_price_time ON marketdata.mark_price (symbol_id, ts_exchange);

-- FORCE ORDERS (@forceOrder)
CREATE TABLE IF NOT EXISTS marketdata.force_orders (
    ts_exchange timestamptz NOT NULL,
    ts_ingest timestamptz NOT NULL DEFAULT now(),
    symbol_id bigint NOT NULL REFERENCES marketdata.symbols(id),
    side text,
    price double precision,
    qty double precision,
    raw jsonb NOT NULL,
    PRIMARY KEY (symbol_id, ts_exchange, side, price, qty)
);
CREATE INDEX IF NOT EXISTS idx_force_orders_time ON marketdata.force_orders (symbol_id, ts_exchange);
