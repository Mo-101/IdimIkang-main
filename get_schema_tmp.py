import psycopg2
import sys

try:
    conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang")
    cur = conn.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'signals'")
    cols = [r[0] for r in cur.fetchall()]
    print("SCHEMA COLUMNS:", cols)
except Exception as e:
    print(e)
