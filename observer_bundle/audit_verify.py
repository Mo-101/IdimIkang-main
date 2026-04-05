import subprocess
import requests
import json
import time

def verify():
    results = {}
    
    # 1. PM2 Status
    try:
        res = subprocess.run(["pm2", "jlist"], capture_output=True, text=True)
        results["pm2_status"] = json.loads(res.stdout)
    except Exception as e:
        results["pm2_error"] = str(e)

    # 2. API Health Check (FastAPI)
    # We try localhost:8787/api/health first
    try:
        resp = requests.get("http://localhost:8787/api/health", timeout=5)
        results["api_health"] = resp.json()
        results["api_status_code"] = resp.status_code
    except Exception as e:
        results["api_health_error"] = str(e)

    # 3. Specific Pair Check
    try:
        resp = requests.get("http://localhost:8787/api/signals", timeout=5)
        signals = resp.json().get("signals", [])
        aiot = next((s for s in signals if s["pair"] == "AIOTUSDT"), None)
        if aiot:
            results["aiot_data"] = {
                "entry": aiot["entry"],
                "stop": aiot["stop_loss"],
                "side": aiot["side"]
            }
    except Exception as e:
        results["signals_error"] = str(e)

    with open("verification_results.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    verify()
