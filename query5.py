import psycopg2

conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang")
cur = conn.cursor()

# Query 5: Density by pair
cur.execute("""
    SELECT pair, COUNT(*) 
    FROM signals 
    GROUP BY pair 
    ORDER BY COUNT(*) DESC, pair;
""")

results = cur.fetchall()
print("pair | count")
print("-----|------")
for pair, count in results:
    print(f"{pair:5} | {count}")

conn.close()
