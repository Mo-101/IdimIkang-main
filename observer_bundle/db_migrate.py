import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang")

def run_migration():
    print("Applying execution_snapshots DB schema migration...")
    ALTER_SQL = """
    ALTER TABLE signals ADD COLUMN IF NOT EXISTS spread_bps NUMERIC;
    ALTER TABLE signals ADD COLUMN IF NOT EXISTS est_slippage_bps NUMERIC;
    ALTER TABLE signals ADD COLUMN IF NOT EXISTS execution_snapshot_ts TIMESTAMPTZ;
    """
    
    CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS execution_snapshots (
        id BIGSERIAL PRIMARY KEY,
        signal_id UUID NOT NULL UNIQUE,
        ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        best_bid NUMERIC,
        best_ask NUMERIC,
        mid_price NUMERIC,
        spread_bps NUMERIC,
        bid_depth_usd_1pct NUMERIC,
        ask_depth_usd_1pct NUMERIC,
        depth_imbalance NUMERIC,
        est_slippage_bps NUMERIC,
        last_1m_range_bps NUMERIC,
        last_1m_trade_imbalance NUMERIC NULL,
        latency_ms NUMERIC,
        exec_score NUMERIC
    );

    CREATE INDEX IF NOT EXISTS idx_execution_snapshots_signal_id
        ON execution_snapshots (signal_id);
    """
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    try:
        cur.execute(ALTER_SQL)
        cur.execute(CREATE_SQL)
        conn.commit()
        print("Migration applied successfully! ✔️")
    except Exception as e:
        conn.rollback()
        print(f"Error applying migration: {e} ❌")
    finally:
        conn.close()

if __name__ == "__main__":
    run_migration()
