import psycopg2

conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang")
cur = conn.cursor()

# Query 8: Freshness check - check actual column names
print("Checking table schemas...")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name IN ('signals', 'funding_rates', 'open_interest', 'ls_ratios', 'system_logs')
    ORDER BY table_name, ordinal_position;
""")

columns = cur.fetchall()
for table, col in [(t, c) for t, c in [(row[0], row[1]) for row in columns]]:
    print(f"{table}: {col}")

# Now run the freshness check with correct column names
cur.execute("""
    SELECT (SELECT MAX(created_at) FROM signals) AS last_signal_ts, 
           (SELECT MAX(created_at) FROM funding_rates) AS last_funding_ts, 
           (SELECT MAX(created_at) FROM open_interest) AS last_oi_ts, 
           (SELECT MAX(created_at) FROM ls_ratios) AS last_ls_ts, 
           (SELECT MAX(ts) FROM system_logs) AS last_log_ts;
""")

result = cur.fetchone()
print("\nlast_signal_ts | last_funding_ts | last_oi_ts | last_ls_ts | last_log_ts")
print(f"{result[0]} | {result[1]} | {result[2]} | {result[3]} | {result[4]}")

conn.close()
