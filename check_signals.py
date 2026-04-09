import psycopg2

conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5432/idim_ikang")
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM signals WHERE outcome IS NULL")
unresolved = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM signals WHERE outcome IS NOT NULL")
resolved = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM signals WHERE execution_id IS NOT NULL")
executed = cur.fetchone()[0]

print(f"Unresolved signals: {unresolved}")
print(f"Resolved signals: {resolved}")
print(f"Executed signals: {executed}")

conn.close()
