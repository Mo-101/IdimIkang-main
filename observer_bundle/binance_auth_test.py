import os
import time
import hmac
import hashlib
import requests
import ccxt
from dotenv import load_dotenv

load_dotenv()

def test_binance_auth():
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")

    print("--- BINANCE AUTH DIAGNOSTIC ---")
    
    if not api_key or not api_secret:
        print("❌ ERROR: BINANCE_API_KEY or BINANCE_API_SECRET missing from environment.")
        return

    # 1. Cleanliness Check
    if api_key != api_key.strip():
        print("⚠️ WARNING: BINANCE_API_KEY has leading/trailing whitespace.")
    if api_secret != api_secret.strip():
        print("⚠️ WARNING: BINANCE_API_SECRET has leading/trailing whitespace.")

    # 2. CCXT Initialization Test
    print(f"\n1. Initializing CCXT Binance (Futures)...")
    exchange = ccxt.binance({
        'apiKey': (api_key or "").strip(" '\""),
        'secret': (api_secret or "").strip(" '\""),
        'options': {
            'defaultType': 'future',
            'adjustForTimeDifference': True,
            'recvWindow': 10000
        }
    })

    try:
        # Check time sync
        print("Fetching server time...")
        server_time = exchange.fetch_time()
        local_time = int(time.time() * 1000)
        drift = server_time - local_time
        print(f"Server Time: {server_time}")
        print(f"Local Time:  {local_time}")
        print(f"Clock Drift: {drift} ms")

        # 3. Attempt Authenticated Call
        print("\n2. Attempting fetch_balance (Authenticated Call)...")
        balance = exchange.fetch_balance()
        print("✅ SUCCESS: fetch_balance completed.")
        print(f"USDT Total: {balance.get('total', {}).get('USDT', 0)}")

    except ccxt.AuthenticationError as e:
        print(f"❌ AUTH ERROR: {e}")
        if "-1022" in str(e):
            print("Detected -1022 Signature Error.")
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}")

if __name__ == "__main__":
    test_binance_auth()
