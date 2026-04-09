import psycopg2

DATABASE_URL = "postgresql://postgres:IdimIkangLocal2026!@localhost:5432/idim_ikang"

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM training_candidates")
count = cur.fetchone()[0]
print(f"training records: {count}")
