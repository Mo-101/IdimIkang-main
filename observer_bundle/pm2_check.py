import subprocess, json, sys

result = subprocess.run(["pm2", "jlist"], capture_output=True, text=True)
procs = json.loads(result.stdout)
for p in procs:
    name = p["name"]
    pid = p["pid"]
    status = p["pm2_env"]["status"]
    restarts = p["pm2_env"]["restart_time"]
    watch = p["pm2_env"].get("watch", "unknown")
    print(f"{name:30s} pid={pid} status={status} restarts={restarts} watch={watch}")
