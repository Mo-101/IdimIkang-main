import json, subprocess
result = subprocess.run(["pm2", "jlist"], capture_output=True, text=True, timeout=15)
data = json.loads(result.stdout)
for p in data:
    name = p.get("name", "unknown")
    env = p.get("pm2_env", {})
    monit = p.get("monit", {})
    print(f"{name:25} status={env.get('status','?'):8} restarts={env.get('restart_time',0):4} mem={round(monit.get('memory',0)/1024/1024,1):6.1f}mb")
