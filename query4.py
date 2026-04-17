import psycopg2

conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang")
cur = conn.cursor()

# Query 4: Current WR / PF
cur.execute("""
    SELECT COUNT(*) AS resolved_signals, 
           SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) AS wins, 
           SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) AS losses, 
           ROUND(100.0 * SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END)::numeric / NULLIF(SUM(CASE WHEN outcome IN ('WIN','LOSS') THEN 1 ELSE 0 END),0), 4) AS win_rate_pct, 
           ROUND(3.0 * SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END)::numeric / NULLIF(SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END),0), 4) AS profit_factor 
    FROM signals 
    WHERE outcome IN ('WIN','LOSS');
""")

result = cur.fetchone()
print("resolved_signals | wins | losses | win_rate_pct | profit_factor")
print(f"{result[0]} | {result[1]} | {result[2]} | {result[3]} | {result[4]}")

conn.close()
