#!/usr/bin/env python3
import psycopg2

DB_URL = "postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang"

def run_truth_audit():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    
    print("=" * 65)
    print("  TRUTH & INTEGRITY AUDIT")
    print("=" * 65)

    print("\n1. CANONICAL SOURCE OF TRUTH (Split by Execution Source & Outcome)")
    cur.execute("""
        SELECT
            execution_source,
            outcome,
            COUNT(*) AS n
        FROM signals
        GROUP BY execution_source, outcome
        ORDER BY execution_source, outcome;
    """)
    for src, out, n in cur.fetchall():
        print(f"  {src:<12} | {str(out):<15} : {n}")


    print("\n2. MACRO ROW COUNTS")
    cur.execute("""
        SELECT
            COUNT(*) AS total_rows,
            COUNT(*) FILTER (WHERE outcome IS NULL) AS unresolved,
            COUNT(*) FILTER (WHERE outcome IN ('WIN','LOSS','PARTIAL_WIN','EXPIRED','ARCHIVED_V1','LIVE_WIN','LIVE_LOSS','LIVE_PARTIAL')) AS classified
        FROM signals;
    """)
    total, unres, classif = cur.fetchone()
    print(f"  Total signals: {total}")
    print(f"  Unresolved   : {unres}")
    print(f"  Classified   : {classif}")


    print("\n3. IDENTIFY CORRUPTED LOSSES")
    cur.execute("""
        SELECT
            id, pair, side, ts, outcome, r_multiple, adverse_excursion, execution_source
        FROM signals
        WHERE outcome = 'LOSS'
          AND adverse_excursion IS NOT NULL
          AND adverse_excursion < 0.999
        ORDER BY ts DESC;
    """)
    bad_rows = cur.fetchall()
    print(f"  Found {len(bad_rows)} mathematically inconsistent LOSS rows.")
    if len(bad_rows) > 0:
        print("\n  Sample of corrupted rows (up to 10):")
        print(f"  {'ID':<5} | {'PAIR':<12} | {'SIDE':<5} | {'R-MULT':<8} | {'ADV_EXC':<8} | {'SOURCE'}")
        print("  " + "-" * 70)
        for r in bad_rows[:10]:
            r_mult = f"{r[5]:.2f}" if r[5] else "None"
            adv = f"{r[6]:.2f}" if r[6] else "None"
            print(f"  {r[0]:<5} | {r[1]:<12} | {r[2]:<5} | {r_mult:<8} | {adv:<8} | {r[7]}")

    conn.close()

if __name__ == "__main__":
    run_truth_audit()
