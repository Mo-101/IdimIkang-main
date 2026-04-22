#!/usr/bin/env python3
import psycopg2
import os
from dotenv import load_dotenv

# Use absolute path to .env if needed, or assume it's in the same dir or root
load_dotenv("/home/idona/MoStar/IdimIkang-main-1/observer_bundle/.env")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang")

print(f"Connecting to {DATABASE_URL}...")

try:
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("""
            ALTER TABLE training_candidates 
            ADD COLUMN IF NOT EXISTS directional_long_score NUMERIC,
            ADD COLUMN IF NOT EXISTS directional_short_score NUMERIC,
            ADD COLUMN IF NOT EXISTS directional_net NUMERIC,
            ADD COLUMN IF NOT EXISTS directional_margin NUMERIC,
            ADD COLUMN IF NOT EXISTS directional_primary_side TEXT
        """)
        conn.commit()
    print("✅ Directional columns added to training_candidates")
    conn.close()
except Exception as e:
    print(f"❌ Migration failed: {e}")
