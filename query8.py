import psycopg2

conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang")
cur = conn.cursor()

# Query 8: Freshness check
cur.execute("""
    SELECT (SELECT MAX(ts) FROM signals) AS last_signal_ts, 
           (SELECT MAX(ts) FROM funding_rates) AS last_funding_ts, 
           (SELECT MAX(ts) FROM open_interest) AS last_oi_ts, 
           (SELECT MAX(ts) FROM ls_ratios) AS last_ls_ts, 
           (SELECT MAX(ts) FROM system_logs) AS last_log_ts;
""")

result = cur.fetchone()
print("last_signal_ts | last_funding_ts | last_oi_ts | last_ls_ts | last_log_ts")
print(f"{result[0]} | {result[1]} | {result[2]} | {result[3]} | {result[4]}")

conn.close()
