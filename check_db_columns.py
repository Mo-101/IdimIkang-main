import psycopg2

conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5432/idim_ikang")
cur = conn.cursor()

cur.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'training_candidates' 
    AND column_name IN ('family_indicators', 'trace_data')
""")

columns = [row[0] for row in cur.fetchall()]
print("Columns:", columns)

conn.close()
