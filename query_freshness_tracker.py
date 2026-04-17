import psycopg2
from datetime import datetime, timezone

conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang")
cur = conn.cursor()

# 1. Collector freshness - detailed
print("=" * 60)
print("COLLECTOR FRESHNESS CHECK")
print("=" * 60)

tables = {
    "signals": "created_at",
    "funding_rates": "collected_at",
    "open_interest": "collected_at",
    "ls_ratios": "collected_at",
    "system_logs": "ts",
}

now = datetime.now(timezone.utc)

for table, ts_col in tables.items():
    cur.execute(f"SELECT MAX({ts_col}) FROM {table};")
    max_ts = cur.fetchone()[0]
    if max_ts:
        if hasattr(max_ts, 'tzinfo') and max_ts.tzinfo is None:
            age = (now.replace(tzinfo=None) - max_ts).total_seconds() / 60
        else:
            age = (now - max_ts).total_seconds() / 60
        status = "✅ FRESH" if age < 60 else ("⚠️ STALE" if age < 360 else "🚨 DEAD")
        print(f"{table:20}: last={max_ts} | age={age:.0f}min | {status}")
    else:
        print(f"{table:20}: NO DATA")

# 2. Tracker errors - detailed
print("\n" + "=" * 60)
print("OUTCOME TRACKER ERRORS")
print("=" * 60)

cur.execute("""
    SELECT ts, details 
    FROM system_logs 
    WHERE component='outcome_tracker' AND level='ERROR'
    ORDER BY ts DESC 
    LIMIT 5;
""")

results = cur.fetchall()
for ts, details in results:
    print(f"Time: {ts}")
    if details:
        if isinstance(details, dict):
            print(f"  Error: {details.get('error', details.get('message', str(details)[:200]))}")
        else:
            print(f"  Details: {str(details)[:200]}")
    print()

# 3. Executor restart pattern
print("=" * 60)
print("EXECUTOR RESTART PATTERN")
print("=" * 60)

cur.execute("""
    SELECT DATE(ts) as day, COUNT(*) as errors
    FROM system_logs 
    WHERE component='outcome_tracker' AND level='ERROR'
    GROUP BY DATE(ts)
    ORDER BY day DESC
    LIMIT 7;
""")

results = cur.fetchall()
for day, count in results:
    print(f"{day}: {count} errors")

conn.close()
