#!/usr/bin/env python3
import psycopg2
import sys
import os

DB_URL = "postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang"

def run_logic_audit():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        
        # 1. Current Rolling Share
        cur.execute("SELECT side FROM signals ORDER BY ts DESC LIMIT 200")
        rows = cur.fetchall()
        sides = [r[0] for r in rows]
        n = len(sides)
        longs = sides.count('LONG')
        long_share = longs / n if n > 0 else 0.5
        
        # 2. Logic Simulation (Matches scanner.py)
        LAMBDA = 25.0
        MAX_OFFSET = 15.0
        FLOOR = 40.0
        
        imbalance = long_share - 0.5
        raw_skew = LAMBDA * imbalance
        skew = max(-MAX_OFFSET, min(MAX_OFFSET, raw_skew))
        
        print("\n" + "="*65)
        print("  IDIM IKANG - PUSH-PULL DOCTRINE AUDIT")
        print("="*65)
        print(f"Rolling Window (N={n}):")
        print(f"  Long Share   : {long_share:.1%}")
        print(f"  Short Share  : {1-long_share:.1%}")
        print(f"  Current Skew : {skew:+.2f} pts")
        
        print("-" * 65)
        print("SCORING SIMULATION (v2.0 Symmetric Gravity):")
        print(f"{'Side':<6} {'Raw':>6} {'Skew':>8} {'Floor':>8} {'Final':>8} {'Status'}")
        print(f"{'-'*6} {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*15}")
        
        test_cases = [
            ("LONG", 60.0),
            ("LONG", 45.0),
            ("SHORT", 60.0),
            ("SHORT", 45.0),
            ("SHORT", 35.0),
        ]
        
        for side, raw in test_cases:
            if side == "LONG":
                coh_score = raw - skew
                if skew < 0 and raw < FLOOR:
                    final = raw
                    status = "Boost Denied"
                else:
                    final = coh_score
                    status = "Normal" if skew == 0 else ("Penalized" if skew > 0 else "Boosted")
            else: # SHORT
                coh_score = raw + skew
                if skew > 0 and raw < FLOOR:
                    final = raw
                    status = "Boost Denied"
                else:
                    final = coh_score
                    status = "Normal" if skew == 0 else ("Boosted" if skew > 0 else "Penalized")
            
            p_final = f"{final:+.1f}" if final != raw else f"{final:>6.1f}"
            print(f"{side:<6} {raw:>6.1f} {skew:*>8.2f} {FLOOR:>8.1f} {p_final:>8} {status}")

        print("="*65 + "\n")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Audit Error: {e}")

if __name__ == "__main__":
    run_logic_audit()
