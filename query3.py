import psycopg2

conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang")
cur = conn.cursor()

# Query 3: Outcome distribution
cur.execute("""
    SELECT COALESCE(outcome, 'UNRESOLVED') as outcome, COUNT(*) 
    FROM signals 
    GROUP BY COALESCE(outcome, 'UNRESOLVED') 
    ORDER BY outcome;
""")

results = cur.fetchall()
print("outcome | count")
print("--------|------")
for outcome, count in results:
    print(f"{outcome:8} | {count}")

conn.close()
