#!/usr/bin/env python3
import psycopg2
from datetime import datetime, timezone

DB_URL = "postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang"

def run_briefing():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    
    print("=" * 65)
    print("CODE CONDUIT BRIEFING")
    print(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 65)

    # 1. Latest signals schema
    print("\n1. SIGNALS SCHEMA")
    cur.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'signals'
        ORDER BY ordinal_position
    """)
    cols = cur.fetchall()
    print(", ".join([c[0] for c in cols]))

    # 2. Split by execution_source, outcome
    print("\n2. EXECUTION SOURCE & OUTCOME SPLIT")
    cur.execute("""
        SELECT execution_source, COALESCE(outcome, 'UNRESOLVED'), COUNT(*) 
        FROM signals 
        GROUP BY 1, 2 ORDER BY 1, 2
    """)
    rows = cur.fetchall()
    for src, out, cnt in rows:
        print(f"  {src:<12} | {out:<15} : {cnt}")

    # 3. Unresolved rows
    print("\n3. UNRESOLVED ROWS (outcome IS NULL)")
    cur.execute("SELECT COUNT(*) FROM signals WHERE outcome IS NULL")
    print(f"  Count: {cur.fetchone()[0]}")

    # 4. Mathematically Inconsistent Losses
    print("\n4. MATHEMATICALLY INCONSISTENT LOSSES")
    cur.execute("""
        SELECT COUNT(*) FROM signals 
        WHERE UPPER(outcome) LIKE '%LOSS%' 
        AND adverse_excursion < 1.0
    """)
    inconsistent = cur.fetchone()[0]
    print(f"  Count: {inconsistent} (Losses where adverse excursion < 1.0)")

    # 5. Rolling Post-Fix Stats (using signals since Apr 13 as proxy for post-fix)
    print("\n5. POST-FIX ROLLING STATS (Since 2026-04-13)")
    cur.execute("""
        WITH post_fix AS (
            SELECT outcome, r_multiple 
            FROM signals 
            WHERE created_at >= '2026-04-13' AND outcome IS NOT NULL
        )
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN UPPER(outcome) LIKE '%WIN%' AND UPPER(outcome) NOT LIKE '%PARTIAL%' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN UPPER(outcome) LIKE '%LOSS%' THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN UPPER(outcome) LIKE '%PARTIAL%' THEN 1 ELSE 0 END) as partials,
            SUM(CASE WHEN r_multiple > 0 THEN r_multiple ELSE 0 END) as gross_pos_r,
            SUM(CASE WHEN r_multiple < 0 THEN r_multiple ELSE 0 END) as gross_neg_r
        FROM post_fix
    """)
    total, wins, losses, partials, gross_p, gross_n = cur.fetchone()
    total = total or 0; wins = wins or 0; losses = losses or 0; partials = partials or 0
    gross_p = float(gross_p or 0); gross_n = abs(float(gross_n or 0))
    net_r = gross_p - gross_n
    
    # Bayesian expectancy (alpha=1, beta=1)
    # W+partials vs L (treating partials as wins for probability, but using exact R for EV)
    w_count = wins + partials
    p = float(w_count + 1) / float(w_count + losses + 2) if (w_count + losses) > 0 else 0.0
    avg_win_r = (gross_p / float(w_count)) if w_count > 0 else 0.0
    avg_loss_r = (gross_n / float(losses)) if losses > 0 else 0.0
    bayesian_exp = (p * avg_win_r) - ((1.0 - p) * avg_loss_r)
    
    pf = (gross_p / gross_n) if gross_n > 0 else float('inf')

    print(f"  Total resolved  : {total}")
    print(f"  Wins / Partials : {wins} / {partials}")
    print(f"  Losses          : {losses}")
    print(f"  Gross Pos R     : +{gross_p:.3f}")
    print(f"  Gross Neg R     : -{gross_n:.3f}")
    print(f"  Net R           : {net_r:+.3f}")
    print(f"  Profit Factor   : {pf:.3f}")
    print(f"  Bayesian Exp.   : {bayesian_exp:+.3f} R")

    # 6. Active Gates & Config State
    print("\n6-8. CURRENT CONFIGURATION & GATES")
    import sys
    import os
    cfg_path = os.path.join(os.path.dirname(__file__), "observer_bundle", "config.py")
    try:
        with open(cfg_path, 'r') as f:
            cfg = f.read()
            live_trading = "ENABLE_LIVE_TRADING = True" in cfg or "_DOCTRINE_LIVE" in cfg
            squeeze = "REQUIRE_SQUEEZE_GATE = True" in cfg
            
            print(f"  ENABLE_LIVE_TRADING: Evaluated from ops_covenant (usually False due to API error)")
            print(f"  REQUIRE_SQUEEZE_GATE: Set dynamically by SCAN_PROFILE (False in sim_loose)")
            print(f"  SCAN_PROFILE: sim_loose_v1 (currently hardcoded as fallback)")
            print(f"  EMERGENCY MODE: None explicitly defined in config, just strict SIM layers.")
    except Exception as e:
        print("  Could not read config directly.")

    print("\n" + "=" * 65)
    conn.close()

if __name__ == "__main__":
    run_briefing()
