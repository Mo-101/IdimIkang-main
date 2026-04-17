import psycopg2

DB_URL = "postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang"

def run_reset():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    
    print("Wiping existing simulated outcomes to re-resolve with new MAE/R-multiple math...")
    cur.execute("""
        UPDATE signals 
        SET outcome = NULL, 
            r_multiple = NULL, 
            adverse_excursion = 0, 
            is_partial = FALSE, 
            trailing_sl = NULL, 
            updated_at = NOW() 
        WHERE execution_source = 'simulated'
          AND outcome IS NOT NULL;
    """)
    conn.commit()
    print(f"Reset {cur.rowcount} corrupted/legacy rows back to unresolved state.")
    
    print("Restarting outcome tracker to re-evaluate history...")
    conn.close()

if __name__ == "__main__":
    run_reset()
