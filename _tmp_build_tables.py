import psycopg2

def create_derivative_tables():
    conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang")
    conn.autocommit = True
    cur = conn.cursor()

    print("Building derivative tables...")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS funding_rates (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(20) NOT NULL,
        funding_rate DECIMAL(20, 10) NOT NULL,
        timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
        exchange VARCHAR(20) DEFAULT 'binance'
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS open_interest (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(20) NOT NULL,
        open_interest DECIMAL(30, 8) NOT NULL,
        timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
        exchange VARCHAR(20) DEFAULT 'binance'
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS ls_ratio (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(20) NOT NULL,
        long_ratio DECIMAL(10, 4) NOT NULL,
        short_ratio DECIMAL(10, 4) NOT NULL,
        timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
        exchange VARCHAR(20) DEFAULT 'binance'
    );
    """)

    print("Building indices...")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_funding_symbol_time ON funding_rates(symbol, timestamp);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_oi_symbol_time ON open_interest(symbol, timestamp);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ls_symbol_time ON ls_ratio(symbol, timestamp);")

    print("Done!")
    
if __name__ == "__main__":
    create_derivative_tables()
