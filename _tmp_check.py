import psycopg2
def check():
    conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM signals WHERE side = 'LONG' AND regime = 'RANGING' AND ts > NOW() - INTERVAL '3 days'")
    print("RANGING LONGS LAST 3 DAYS:", cur.fetchone()[0])
    
    cur.execute("SELECT COUNT(*) FROM signals WHERE side = 'LONG' AND regime = 'RANGING' AND ts <= NOW() - INTERVAL '3 days'")
    print("RANGING LONGS OLDER THAN 3 DAYS:", cur.fetchone()[0])
check()
