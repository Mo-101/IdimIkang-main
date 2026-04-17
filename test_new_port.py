import psycopg2

# Test database connection with new port 5433
print("Testing PostgreSQL connection on port 5433...")

try:
    conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang")
    print("Connection to port 5433 - SUCCESS")
    
    # Test a simple query
    cur = conn.cursor()
    cur.execute("SELECT version();")
    version = cur.fetchone()[0]
    print(f"PostgreSQL version: {version[:50]}...")
    
    conn.close()
    print("Connection test completed successfully!")
    
except Exception as e:
    print(f"Connection to port 5433 - FAILED: {e}")
