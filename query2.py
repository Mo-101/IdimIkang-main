import psycopg2

conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang")
cur = conn.cursor()

# Query 2: Core row counts
cur.execute("""
    SELECT (SELECT COUNT(*) FROM signals) as signals, 
           (SELECT COUNT(*) FROM funding_rates) as funding, 
           (SELECT COUNT(*) FROM open_interest) as oi, 
           (SELECT COUNT(*) FROM ls_ratios) as ls;
""")

result = cur.fetchone()
print("signals | funding | oi | ls")
print(f"{result[0]} | {result[1]} | {result[2]} | {result[3]}")

conn.close()
