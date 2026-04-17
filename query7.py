import psycopg2

conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang")
cur = conn.cursor()

# Query 7: Recent anomalies
cur.execute("""
    SELECT ts, level, component, event 
    FROM system_logs 
    WHERE level IN ('WARN','ERROR') 
    ORDER BY ts DESC 
    LIMIT 50;
""")

results = cur.fetchall()
print("ts | level | component | event")
print("---|-------|-----------|------")
for ts, level, component, event in results:
    print(f"{ts} | {level:5} | {component:9} | {event}")

conn.close()
