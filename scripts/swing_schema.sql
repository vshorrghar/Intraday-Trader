-- Swing trades table
CREATE TABLE IF NOT EXISTS swing_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    tradingsymbol TEXT NOT NULL,
    nse_symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    product_type TEXT DEFAULT 'CNC',
    quantity INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    target_price REAL NOT NULL,
    stop_loss_price REAL NOT NULL,
    current_price REAL,
    days_held INTEGER DEFAULT 0,
    entry_date DATE NOT NULL,
    exit_date DATE,
    exit_price REAL,
    exit_reason TEXT,
    gross_pnl REAL,
    charges REAL,
    pnl REAL,
    status TEXT NOT NULL,
    confidence_score INTEGER,
    strategy_type TEXT DEFAULT 'PULLBACK',
    rationale TEXT,
    thesis_invalidation TEXT,
    buy_order_id TEXT,
    sell_order_id TEXT,
    sector TEXT,
    holding_days_estimate INTEGER,
    entry_regime_score INTEGER,
    mode TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Swing audit log
CREATE TABLE IF NOT EXISTS swing_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER,
    event_type TEXT NOT NULL,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (trade_id) REFERENCES swing_trades(id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_swing_status ON swing_trades(status);
CREATE INDEX IF NOT EXISTS idx_swing_entry_date ON swing_trades(entry_date);
CREATE INDEX IF NOT EXISTS idx_swing_symbol ON swing_trades(symbol);
