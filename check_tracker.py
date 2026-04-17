import psycopg2

def check():
    conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM signals WHERE outcome IS NULL")
    unresolved = cur.fetchone()[0]
    
    cur.execute("SELECT outcome, COUNT(*) FROM signals WHERE outcome IS NOT NULL GROUP BY outcome")
    resolved = cur.fetchall()
    
    print(f"Signals waiting to be tracked (outcome IS NULL): {unresolved}")
    print("\nCurrently resolved states:")
    for out, cnt in resolved:
        print(f"  {out}: {cnt}")
        
    conn.close()

if __name__ == "__main__":
    check()
