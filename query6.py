import psycopg2

conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang")
cur = conn.cursor()

# Query 6: Density by Wolfram cell
cur.execute("""
    SELECT regime, ROUND(score)::int AS score_bucket, COUNT(*) 
    FROM signals 
    GROUP BY regime, ROUND(score)::int 
    ORDER BY COUNT(*) DESC, regime, score_bucket;
""")

results = cur.fetchall()
print("regime | score_bucket | count")
print("-------|-------------|------")
for regime, score_bucket, count in results:
    print(f"{regime:7} | {score_bucket:11} | {count}")

conn.close()
