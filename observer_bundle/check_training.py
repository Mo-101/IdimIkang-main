import psycopg2
import config

conn = psycopg2.connect(config.DB_URL)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM training_candidates")
count = cur.fetchone()[0]
print(f"training records: {count}")
