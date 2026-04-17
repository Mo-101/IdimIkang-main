import os
import hashlib
import time
import ccxt
from dotenv import load_dotenv

load_dotenv()

def fp(v):
    if not v:
        return "MISSING"
    # Clean the same way the app does (strip whitespace and common quotes)
    clean_v = v.strip(" '\"")
    return hashlib.sha256(clean_v.encode()).hexdigest()[:10]

def run_diagnostic():
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")

    print("--- SOVEREIGN TRUTH DIAGNOSTIC ---")
    
    # 1. Env Presence Check
    results = {
        "key_present": api_key is not None,
        "secret_present": api_secret is not None,
        "key_fp": fp(api_key),
        "secret_fp": fp(api_secret),
        "cwd": os.getcwd(),
    }
    
    print("\n1. Environment Integrity Check:")
    for k, v in results.items():
        print(f"  {k}: {v}")

    if results["key_fp"] == results["secret_fp"] and api_key:
        print("\n⚠️  ALERT: API KEY AND SECRET ARE IDENTICAL! This is a configuration error.")
    
    # 2. System Time check
    print("\n2. System Time Sync:")
    local_ms = int(time.time() * 1000)
    print(f"  Local Time (ms): {local_ms}")

    # 3. Isolated Signer Test
    print("\n3. Standalone CCXT Test:")
    if not api_key or not api_secret:
        print("  ❌ Skipping: Keys missing.")
        return

    exchange = ccxt.binance({
        'apiKey': api_key.strip(" '\""),
        'secret': api_secret.strip(" '\""),
        'options': {
            'defaultType': 'future',
            'adjustForTimeDifference': True,
            'recvWindow': 10000
        }
    })

    try:
        print("  Fetching server time...")
        server_time = exchange.fetch_time()
        print(f"  Server Time (ms): {server_time}")
        print(f"  Drift: {server_time - local_ms} ms")
        
        print("  Attempting authenticated fetch_balance...")
        balance = exchange.fetch_balance()
        print("  ✅ SUCCESS: Authentication proved.")
    except Exception as e:
        print(f"  ❌ FAIL: {e}")
        if "-1022" in str(e):
            print("  Confirmation: -1022 Signature Error detected.")

if __name__ == "__main__":
    run_diagnostic()
