import psycopg2

DB_URL = "postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang"

conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

print("--- Query 1: Are new short signals being emitted at all? ---")
cur.execute("""
SELECT side, COUNT(*)
FROM signals
WHERE ts > NOW() - INTERVAL '24 hours'
GROUP BY side;
""")
print(cur.fetchall())

print("\n--- Query 2: Are new short family tags being written? ---")
cur.execute("""
SELECT COALESCE(signal_family, 'NULL') AS family_tag, COUNT(*)
FROM signals
WHERE side = 'SHORT'
  AND ts > NOW() - INTERVAL '24 hours'
GROUP BY 1
ORDER BY 2 DESC;
""")
print(cur.fetchall())

print("\n--- Query 3: Are resolved short outcomes still only legacy? ---")
cur.execute("""
SELECT COALESCE(signal_family, 'none') AS family_tag,
       COUNT(*) AS trades
FROM signals
WHERE side = 'SHORT'
  AND outcome IS NOT NULL
GROUP BY 1
ORDER BY 2 DESC;
""")
print(cur.fetchall())

print("\n--- Query 4: Check the latest actual short rows ---")
cur.execute("""
SELECT ts, pair, side, signal_family, score, outcome
FROM signals
WHERE side = 'SHORT'
ORDER BY ts DESC
LIMIT 5;
""")
for r in cur.fetchall():
    print(r)

cur.close()
conn.close()
