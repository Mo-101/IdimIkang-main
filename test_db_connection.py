import psycopg2
import os

# Test database connection with different methods
print("Testing PostgreSQL connections...")

# Method 1: Direct connection string
try:
    conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5432/idim_ikang")
    print("Method 1: Direct connection string - SUCCESS")
    conn.close()
except Exception as e:
    print(f"Method 1: Direct connection string - FAILED: {e}")

# Method 2: Environment variable
os.environ['DATABASE_URL'] = "postgresql://postgres:IdimIkangLocal2026!@localhost:5432/idim_ikang"
try:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    print("Method 2: Environment variable - SUCCESS")
    conn.close()
except Exception as e:
    print(f"Method 2: Environment variable - FAILED: {e}")

# Method 3: Parameters
try:
    conn = psycopg2.connect(
        host="localhost",
        database="idim_ikang", 
        user="postgres",
        password="IdimIkangLocal2026!",
        port=5432
    )
    print("Method 3: Parameters - SUCCESS")
    conn.close()
except Exception as e:
    print(f"Method 3: Parameters - FAILED: {e}")
