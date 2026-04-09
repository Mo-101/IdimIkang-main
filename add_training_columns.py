import psycopg2

conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5432/idim_ikang")
cur = conn.cursor()

# Add missing columns to training_candidates table
try:
    cur.execute("""
        ALTER TABLE training_candidates 
        ADD COLUMN IF NOT EXISTS family_indicators JSONB,
        ADD COLUMN IF NOT EXISTS trace_data JSONB
    """)
    conn.commit()
    print("Added family_indicators and trace_data columns to training_candidates table")
except Exception as e:
    print(f"Error adding columns: {e}")
    conn.rollback()

conn.close()
