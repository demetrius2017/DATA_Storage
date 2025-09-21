-- ===============================================
-- 🗄️ SIMPLIFIED MARKET DATA SCHEMA 
-- ===============================================

-- Создание схемы
CREATE SCHEMA IF NOT EXISTS marketdata;

-- ===============================================
-- 1. СПРАВОЧНИК СИМВОЛОВ
-- ===============================================

CREATE TABLE marketdata.symbols (
    id bigserial PRIMARY KEY,
    exchange text NOT NULL,              
    symbol text NOT NULL,                
    instrument_type text,                
    base_asset text,                     
    quote_asset text,                    
    is_active boolean DEFAULT true,
    tick_size double precision,          
    lot_size double precision,           
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    UNIQUE (exchange, symbol)
);

-- ===============================================
-- 2. BOOK TICKER DATA
-- ===============================================

CREATE TABLE marketdata.book_ticker (
    ts_exchange timestamptz NOT NULL,    
    ts_ingest timestamptz NOT NULL DEFAULT now(),  
    symbol_id bigint NOT NULL REFERENCES marketdata.symbols(id),
    update_id bigint,                    
    best_bid double precision NOT NULL,  
    best_ask double precision NOT NULL,  
    bid_qty double precision NOT NULL,   
    ask_qty double precision NOT NULL,   
    spread double precision NOT NULL,    
    mid double precision NOT NULL       
);

-- ===============================================
-- 3. АГРЕГИРОВАННЫЕ СДЕЛКИ
-- ===============================================

CREATE TABLE marketdata.trades (
    ts_exchange timestamptz NOT NULL,    
    ts_ingest timestamptz NOT NULL DEFAULT now(),
    symbol_id bigint NOT NULL REFERENCES marketdata.symbols(id),
    agg_trade_id bigint NOT NULL,        
    price double precision NOT NULL,     
    qty double precision NOT NULL,       
    is_buyer_maker boolean NOT NULL     
);

-- ===============================================
-- 4. СОБЫТИЯ ГЛУБИНЫ РЫНКА
-- ===============================================

CREATE TABLE marketdata.depth_events (
    ts_exchange timestamptz NOT NULL,
    ts_ingest timestamptz NOT NULL DEFAULT now(),
    symbol_id bigint NOT NULL REFERENCES marketdata.symbols(id),
    first_update_id bigint NOT NULL,     
    final_update_id bigint NOT NULL,          
    prev_final_update_id bigint,         
    bids jsonb NOT NULL,                 
    asks jsonb NOT NULL
);

-- ===============================================
-- 5. АГРЕГАТЫ BOOK_TICKER (1 СЕКУНДА)
-- ===============================================

CREATE TABLE marketdata.bt_1s (
    ts_second timestamptz NOT NULL,      
    symbol_id bigint NOT NULL REFERENCES marketdata.symbols(id),
    mid_open double precision,
    mid_high double precision,
    mid_low double precision,
    mid_close double precision,
    spread_mean double precision,
    spread_std double precision,
    updates_count int,
    PRIMARY KEY (symbol_id, ts_second)
);

-- ===============================================
-- 6. АГРЕГАТЫ СДЕЛОК (1 СЕКУНДА)  
-- ===============================================

CREATE TABLE marketdata.trade_1s (
    ts_second timestamptz NOT NULL,
    symbol_id bigint NOT NULL REFERENCES marketdata.symbols(id),
    trade_count int NOT NULL DEFAULT 0,
    volume_sum double precision NOT NULL DEFAULT 0,
    vwap double precision,
    buy_volume double precision NOT NULL DEFAULT 0,   
    sell_volume double precision NOT NULL DEFAULT 0,  
    buy_count int NOT NULL DEFAULT 0,
    sell_count int NOT NULL DEFAULT 0,
    price_min double precision,
    price_max double precision,
    PRIMARY KEY (symbol_id, ts_second)
);

-- ===============================================
-- ИНДЕКСЫ
-- ===============================================

CREATE INDEX idx_book_ticker_time ON marketdata.book_ticker (symbol_id, ts_exchange);
CREATE INDEX idx_trades_time ON marketdata.trades (symbol_id, ts_exchange);
CREATE INDEX idx_depth_events_time ON marketdata.depth_events (symbol_id, ts_exchange);

-- ===============================================
-- ПЕРВИЧНЫЕ КЛЮЧИ ДЛЯ ОСНОВНЫХ ТАБЛИЦ
-- ===============================================

ALTER TABLE marketdata.book_ticker 
ADD CONSTRAINT pk_book_ticker PRIMARY KEY (symbol_id, ts_exchange, COALESCE(update_id, 0));

ALTER TABLE marketdata.trades 
ADD CONSTRAINT pk_trades PRIMARY KEY (symbol_id, agg_trade_id);

-- Для совместимости с Timescale: уникальные ключи на гипертаблицах должны включать колонку партиционирования
ALTER TABLE marketdata.depth_events 
ADD CONSTRAINT pk_depth_events PRIMARY KEY (symbol_id, ts_exchange, final_update_id);

-- ===============================================
-- НАЧАЛЬНЫЕ ДАННЫЕ
-- ===============================================

INSERT INTO marketdata.symbols (exchange, symbol, instrument_type, base_asset, quote_asset) VALUES
('binance-futures', 'BTCUSDT', 'perp', 'BTC', 'USDT'),
('binance-futures', 'ETHUSDT', 'perp', 'ETH', 'USDT'),
('binance-futures', 'SOLUSDT', 'perp', 'SOL', 'USDT'),
('binance-futures', 'ADAUSDT', 'perp', 'ADA', 'USDT'),
('binance-futures', 'DOTUSDT', 'perp', 'DOT', 'USDT'),
('binance-futures', 'BNBUSDT', 'perp', 'BNB', 'USDT'),
('binance-futures', 'XRPUSDT', 'perp', 'XRP', 'USDT'),
('binance-futures', 'AVAXUSDT', 'perp', 'AVAX', 'USDT'),
('binance-futures', 'MATICUSDT', 'perp', 'MATIC', 'USDT'),
('binance-futures', 'LINKUSDT', 'perp', 'LINK', 'USDT')
ON CONFLICT (exchange, symbol) DO NOTHING;