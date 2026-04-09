import os
import psycopg2

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM training_candidates")
count = cur.fetchone()[0]
print(f"training records: {count}")
