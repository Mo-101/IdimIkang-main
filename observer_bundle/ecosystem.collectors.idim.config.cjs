module.exports = {
  apps: [
    {
      name: 'funding-collector',
      cwd: '/home/idona/MoStar/IdimIkang-main/observer_bundle',
      script: '/home/idona/MoStar/IdimIkang-main/observer_bundle/.venv/bin/python',
      args: 'funding_collector.py',
      interpreter: 'none',
      autorestart: true,
      watch: false,
      max_restarts: 20,
      restart_delay: 5000,
      time: true,
      error_file: 'logs/funding-collector-error.log',
      out_file: 'logs/funding-collector-out.log',
      merge_logs: true,
      env: {
        PYTHONUNBUFFERED: '1'
      }
    },
    {
      name: 'oi-collector',
      cwd: '/home/idona/MoStar/IdimIkang-main/observer_bundle',
      script: '/home/idona/MoStar/IdimIkang-main/observer_bundle/.venv/bin/python',
      args: 'oi_collector.py',
      interpreter: 'none',
      autorestart: true,
      watch: false,
      max_restarts: 20,
      restart_delay: 5000,
      time: true,
      error_file: 'logs/oi-collector-error.log',
      out_file: 'logs/oi-collector-out.log',
      merge_logs: true,
      env: {
        PYTHONUNBUFFERED: '1'
      }
    },
    {
      name: 'ls-ratio-collector',
      cwd: '/home/idona/MoStar/IdimIkang-main/observer_bundle',
      script: '/home/idona/MoStar/IdimIkang-main/observer_bundle/.venv/bin/python',
      args: 'ls_ratio_collector.py',
      interpreter: 'none',
      autorestart: true,
      watch: false,
      max_restarts: 20,
      restart_delay: 5000,
      time: true,
      error_file: 'logs/ls-ratio-collector-error.log',
      out_file: 'logs/ls-ratio-collector-out.log',
      merge_logs: true,
      env: {
        PYTHONUNBUFFERED: '1'
      }
    }
  ]
};
