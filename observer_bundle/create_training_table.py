#!/usr/bin/env python3
"""Create training_candidates table for data collection."""
import os
import sys
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import psycopg2
from config import DATABASE_URL

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS training_candidates (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ DEFAULT NOW(),
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    scan_profile TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    signal_family TEXT,
    gate_profile JSONB,
    rejection_gate TEXT,
    would_have_passed_live BOOLEAN,
    regime TEXT,
    btc_regime TEXT,
    close_price NUMERIC,
    adx14 NUMERIC,
    rsi14 NUMERIC,
    atr_stretch NUMERIC,
    squeeze_on BOOLEAN,
    squeeze_fired BOOLEAN,
    vol_ratio NUMERIC,
    funding_rate NUMERIC,
    ls_ratio NUMERIC,
    score NUMERIC,
    outcome_label TEXT,
    outcome_pct NUMERIC,
    mae_pct NUMERIC,
    mfe_pct NUMERIC,
    horizon_bars INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_training_candidates_symbol_ts
    ON training_candidates (symbol, ts DESC);

CREATE INDEX IF NOT EXISTS idx_training_candidates_scan_profile
    ON training_candidates (scan_profile, ts DESC);

CREATE INDEX IF NOT EXISTS idx_training_candidates_signal_family
    ON training_candidates (signal_family, ts DESC);

CREATE INDEX IF NOT EXISTS idx_training_candidates_rejection_gate
    ON training_candidates (rejection_gate, ts DESC)
    WHERE rejection_gate IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_training_candidates_outcome_label
    ON training_candidates (outcome_label, ts DESC)
    WHERE outcome_label IS NOT NULL;
"""

def main():
    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    print("Creating training_candidates table...")
    cur.execute(CREATE_TABLE_SQL)
    conn.commit()
    print("✅ training_candidates table created successfully")
    
    # Verify
    cur.execute("SELECT COUNT(*) FROM training_candidates;")
    count = cur.fetchone()[0]
    print(f"Current row count: {count}")
    
    cur.close()
    conn.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
