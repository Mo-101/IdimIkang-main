import psycopg2
import os
from dotenv import load_dotenv

def main():
    load_dotenv()
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not found in .env")
        return

    commands = [
        """
        CREATE TABLE IF NOT EXISTS funding_rates (
          exchange text,
          pair text,
          ts timestamptz,
          funding_rate numeric,
          PRIMARY KEY (exchange, pair, ts)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS open_interest_snapshots (
          exchange text,
          pair text,
          ts timestamptz,
          open_interest numeric,
          PRIMARY KEY (exchange, pair, ts)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS long_short_ratios (
          exchange text,
          pair text,
          ts timestamptz,
          ls_ratio numeric,
          PRIMARY KEY (exchange, pair, ts)
        );
        """,
        "ALTER TABLE signals ADD COLUMN IF NOT EXISTS exchange TEXT NOT NULL DEFAULT 'BINANCE';",
        "CREATE INDEX IF NOT EXISTS idx_signals_exchange_pair_ts ON signals(exchange, pair, ts DESC);",
        "CREATE INDEX IF NOT EXISTS idx_funding_pair_ts ON funding_rates(exchange, pair, ts DESC);",
        "CREATE INDEX IF NOT EXISTS idx_oi_pair_ts ON open_interest_snapshots(exchange, pair, ts DESC);",
        "CREATE INDEX IF NOT EXISTS idx_ls_pair_ts ON long_short_ratios(exchange, pair, ts DESC);",
        """
        CREATE OR REPLACE VIEW signal_feature_snapshot AS
        SELECT
            s.signal_id,
            s.exchange,
            s.pair,
            s.ts,
            s.side,
            s.score,
            s.regime,
            s.outcome,
            s.r_multiple,
            fr.ts AS funding_ts,
            fr.funding_rate,
            oi.ts AS oi_ts,
            oi.open_interest,
            ls.ts AS ls_ts,
            ls.ls_ratio
        FROM signals s
        LEFT JOIN LATERAL (
            SELECT f.ts, f.funding_rate
            FROM funding_rates f
            WHERE f.exchange = s.exchange
              AND f.pair = s.pair
              AND f.ts <= s.ts
            ORDER BY f.ts DESC
            LIMIT 1
        ) fr ON TRUE
        LEFT JOIN LATERAL (
            SELECT o.ts, o.open_interest
            FROM open_interest_snapshots o
            WHERE o.exchange = s.exchange
              AND o.pair = s.pair
              AND o.ts <= s.ts
            ORDER BY o.ts DESC
            LIMIT 1
        ) oi ON TRUE
        LEFT JOIN LATERAL (
            SELECT l.ts, l.ls_ratio
            FROM long_short_ratios l
            WHERE l.exchange = s.exchange
              AND l.pair = s.pair
              AND l.ts <= s.ts
            ORDER BY l.ts DESC
            LIMIT 1
        ) ls ON TRUE
        WHERE s.outcome IN ('WIN','LOSS');
        """,
        """
        CREATE OR REPLACE VIEW signal_feature_snapshot_fresh AS
        SELECT *
        FROM signal_feature_snapshot
        WHERE (funding_ts IS NULL OR ts - funding_ts <= interval '12 hours')
          AND (oi_ts      IS NULL OR ts - oi_ts      <= interval '2 hours')
          AND (ls_ts      IS NULL OR ts - ls_ts      <= interval '2 hours');
        """
    ]

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        for cmd in commands:
            print(f"Executing: {cmd[:50]}...")
            cur.execute(cmd)
        conn.commit()
        print("Framework setup successfully.")
    except Exception as e:
        print(f"Error during setup: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
