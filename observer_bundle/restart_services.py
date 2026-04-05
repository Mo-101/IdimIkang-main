import subprocess
import sys

def restart():
    print("Attempting PM2 Restart via Python Subprocess...")
    try:
        # Restart all services
        res = subprocess.run(["pm2", "restart", "all"], capture_output=True, text=True)
        print("STDOUT:", res.stdout)
        print("STDERR:", res.stderr)
        
        # Capture status
        res = subprocess.run(["pm2", "status"], capture_output=True, text=True)
        print("Final Status:\n", res.stdout)
    except Exception as e:
        print(f"Failed to restart PM2: {e}")

if __name__ == "__main__":
    restart()
