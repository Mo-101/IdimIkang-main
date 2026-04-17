import psycopg2
import json

conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang")
cur = conn.cursor()

# BTC fetch failure details
cur.execute("""
    SELECT ts, details 
    FROM system_logs 
    WHERE event='btc_fetch_failed' 
    ORDER BY ts DESC 
    LIMIT 5;
""")

results = cur.fetchall()
print("BTC FETCH FAILURES (most recent):")
print("=" * 60)
for ts, details in results:
    print(f"Time: {ts}")
    if details:
        if isinstance(details, dict):
            print(f"  Error: {details.get('error', 'N/A')}")
        else:
            print(f"  Details: {details}")
    print()

# Also check: how many btc_fetch_failed in last 24h?
cur.execute("""
    SELECT COUNT(*) 
    FROM system_logs 
    WHERE event='btc_fetch_failed' 
    AND ts > NOW() - INTERVAL '24 hours';
""")
count = cur.fetchone()[0]
print(f"BTC fetch failures in last 24h: {count}")

# Check if BTC 4h klines are actually fetchable right now
print("\n--- Testing BTC 4h kline fetch ---")
try:
    import sys
    sys.path.insert(0, '/home/idona/MoStar/IdimIkang-main-1/observer_bundle')
    from data_fetch import fetch_klines
    df = fetch_klines("BTCUSDT", "4h", 300)
    if df is not None and len(df) > 0:
        print(f"BTC 4h klines: OK ({len(df)} bars, last close: {df['close'].iloc[-1]})")
    else:
        print("BTC 4h klines: EMPTY DataFrame returned")
except Exception as e:
    print(f"BTC 4h klines: FAILED - {e}")

conn.close()
