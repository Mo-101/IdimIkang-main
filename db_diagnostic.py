import psycopg2

DB_URL = "postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang"

def run_diagnostic():
    print("=" * 65)
    print("  DASHBOARD & TRACKER STATE AUDIT")
    print("=" * 65)
    
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    
    # 1. Overall State
    print("\n1. OVERALL STATE")
    cur.execute("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE outcome IS NULL) AS unresolved,
               COUNT(*) FILTER (WHERE outcome IS NOT NULL) AS resolved
        FROM signals;
    """)
    total, unres, res = cur.fetchone()
    print(f"  Total ROWS: {total}")
    print(f"  Unresolved (NULL): {unres}  <-- If this is high, dashboard is just waiting")
    print(f"  Resolved (NOT NULL): {res} <-- Dashboard display pool")
    
    # 2. What the tracker has labeled
    print("\n2. CURRENT LABELS (DB TRUTH)")
    cur.execute("""
        SELECT execution_source, COALESCE(outcome, 'UNRESOLVED'), COUNT(*) 
        FROM signals 
        GROUP BY 1, 2 ORDER BY 1, 2;
    """)
    for src, out, cnt in cur.fetchall():
        print(f"  {src:<12} | {str(out):<15} : {cnt}")
        
    # 3. Check Expiry Trap
    print("\n3. EXPIRY TRAP CHECK")
    cur.execute("""
        SELECT COUNT(*) FROM signals 
        WHERE execution_source = 'simulated' AND outcome = 'EXPIRED';
    """)
    expired_cnt = cur.fetchone()[0]
    print(f"  Simulated Rows currently EXPIRED: {expired_cnt}")
    
    conn.close()

if __name__ == "__main__":
    run_diagnostic()
