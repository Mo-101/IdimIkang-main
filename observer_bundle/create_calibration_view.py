import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

VIEW_SQL = """
CREATE OR REPLACE VIEW signal_probability_calibration AS
WITH base AS (
  SELECT
    ts,
    pair,
    side,
    COALESCE(market_regime, regime) AS market_regime,
    signal_family,
    pwin,
    prob_score,
    legacy_score,
    z_score,
    score_mode,
    risk_scale,
    rr_sl_mult,
    rr_tp_mult,
    outcome,
    r_multiple,
    NTILE(10) OVER (PARTITION BY score_mode ORDER BY pwin) AS pwin_decile
  FROM signals
  WHERE pwin IS NOT NULL
)
SELECT
  score_mode,
  pwin_decile,
  side,
  market_regime,
  signal_family,
  COUNT(*) AS trades,
  ROUND(AVG(pwin)::numeric, 4) AS avg_pwin,
  ROUND(AVG(prob_score)::numeric, 4) AS avg_prob_score,
  ROUND(AVG(legacy_score)::numeric, 4) AS avg_legacy_score,
  ROUND(AVG(z_score)::numeric, 4) AS avg_z_score,
  ROUND(AVG(risk_scale)::numeric, 4) AS avg_risk_scale,
  ROUND(AVG(rr_sl_mult)::numeric, 4) AS avg_rr_sl_mult,
  ROUND(AVG(rr_tp_mult)::numeric, 4) AS avg_rr_tp_mult,
  ROUND(AVG(CASE WHEN UPPER(outcome) IN ('WIN','LIVE_WIN','PARTIAL_WIN','LIVE_PARTIAL') THEN 1.0 ELSE 0.0 END)::numeric, 4) AS realized_wr,
  ROUND(AVG(r_multiple)::numeric, 4) AS avg_r
FROM base
WHERE outcome IS NOT NULL
GROUP BY score_mode, pwin_decile, side, market_regime, signal_family;
"""

def create_view():
    print(f"Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    
    try:
        with conn.cursor() as cur:
            print("Creating 'signal_probability_calibration' view...")
            cur.execute(VIEW_SQL)
            print("  [OK] View created.")
    finally:
        conn.close()

if __name__ == "__main__":
    create_view()
