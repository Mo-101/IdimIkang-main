import psycopg2

DB_URL = "postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang"

def run_reset_expired():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    
    print("Resetting EXPIRED simulated outcomes to properly backtest them through Binance klines...")
    cur.execute("""
        UPDATE signals 
        SET outcome = NULL, 
            r_multiple = NULL, 
            adverse_excursion = 0, 
            is_partial = FALSE, 
            trailing_sl = NULL, 
            updated_at = NOW() 
        WHERE execution_source = 'simulated'
          AND outcome = 'EXPIRED';
    """)
    conn.commit()
    print(f"Reset {cur.rowcount} prematurely expired rows back to unresolved state.")
    conn.close()

if __name__ == "__main__":
    run_reset_expired()
