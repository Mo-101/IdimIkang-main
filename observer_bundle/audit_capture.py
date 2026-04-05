import subprocess
import json
import os

def capture():
    data = {}
    try:
        # PM2 jlist is reliable
        res = subprocess.run(["pm2", "jlist"], capture_output=True, text=True)
        data["pm2"] = json.loads(res.stdout)
        
        # Simple health check via curl (internal)
        res = subprocess.run(["curl", "-s", "http://localhost:8787/api/health"], capture_output=True, text=True)
        data["health"] = json.loads(res.stdout)
    except Exception as e:
        data["error"] = str(e)
        
    with open("audit_capture.json", "w") as f:
        json.dump(data, f, indent=2)

if __name__ == "__main__":
    capture()
