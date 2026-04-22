import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

def migrate():
    print(f"Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    
    try:
        with conn.cursor() as cur:
            # 1. Add Columns
            print("Adding calibration columns to 'signals' table...")
            columns = [
                ("prob_score", "NUMERIC"),
                ("legacy_score", "NUMERIC"),
                ("pwin", "NUMERIC"),
                ("z_score", "NUMERIC"),
                ("score_mode", "TEXT"),
                ("risk_scale", "NUMERIC"),
                ("rr_sl_mult", "NUMERIC"),
                ("rr_tp_mult", "NUMERIC")
            ]
            
            for col_name, col_type in columns:
                try:
                    cur.execute(f"ALTER TABLE signals ADD COLUMN {col_name} {col_type};")
                    print(f"  [OK] Added {col_name}")
                except psycopg2.errors.DuplicateColumn:
                    print(f"  [SKIP] {col_name} already exists")
                except Exception as e:
                    print(f"  [ERROR] {col_name}: {e}")

            # 2. Add Indexes
            print("Ensuring indexes on calibration fields...")
            indexes = [
                ("idx_signals_score_mode", "score_mode"),
                # Others pre-exist but ensuring basic ones are available
                ("idx_signals_ts_desc", "ts DESC"),
            ]
            
            for idx_name, idx_def in indexes:
                try:
                    cur.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON signals ({idx_def});")
                    print(f"  [OK] Index {idx_name}")
                except Exception as e:
                    print(f"  [ERROR] Index {idx_name}: {e}")
                    
            print("\nMigration complete.")
            
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
