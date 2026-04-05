module.exports = {
  apps: [
    {
      name: "idim-scanner",
      cwd: "/home/idona/MoStar/IdimIkang-main/observer_bundle",
      script: "/home/idona/MoStar/IdimIkang-main/observer_bundle/.venv/bin/python",
      args: "scanner.py",
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_restarts: 30,
      restart_delay: 10000,
      min_uptime: "30s",
      time: true,
      env: {
        PYTHONUNBUFFERED: "1"
      }
    },
    {
      name: "idim-api",
      cwd: "/home/idona/MoStar/IdimIkang-main/observer_bundle",
      script: "/home/idona/MoStar/IdimIkang-main/observer_bundle/.venv/bin/python",
      args: "-m uvicorn api:app --host 0.0.0.0 --port 8787",
      interpreter: "none",
      autorestart: true,
      watch: false,
      ignore_watch: ["logs", "*.log", "node_modules", "__pycache__"],
      max_restarts: 30,
      restart_delay: 10000,
      min_uptime: "30s",
      time: true,
      env: {
        PYTHONUNBUFFERED: "1"
      }
    },
    {
      name: "idim-outcome-tracker",
      cwd: "/home/idona/MoStar/IdimIkang-main/observer_bundle",
      script: "/home/idona/MoStar/IdimIkang-main/observer_bundle/.venv/bin/python",
      args: "outcome_tracker.py --loop",
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_restarts: 30,
      restart_delay: 10000,
      min_uptime: "30s",
      time: true,
      env: {
        PYTHONUNBUFFERED: "1"
      }
    },
    {
      name: "idim-dashboard",
      cwd: "/home/idona/MoStar/IdimIkang-main",
      script: "npm",
      args: "run dev",
      autorestart: true,
      watch: false,
      env: {
        NODE_ENV: "development"
      }
    }
  ]
};
