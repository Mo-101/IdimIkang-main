const repoRoot = '/home/idona/MoStar/IdimIkang-main-1';
const observerRoot = `${repoRoot}/observer_bundle`;
const venvPython = `${observerRoot}/.venv/bin/python`;

function inlineApp(name, script, args = []) {
    return {
        name,
        script: venvPython,
        args,
        cwd: observerRoot,
        autorestart: true,
        watch: false,
        max_restarts: 20,
        restart_delay: 5000,
        time: true,
        env_file: `${observerRoot}/.env`,
    };
}

module.exports = {
    apps: [
        inlineApp('funding-collector', venvPython, ['funding_collector.py']),
        inlineApp('oi-collector', venvPython, ['oi_collector.py']),
        inlineApp('ls-ratio-collector', venvPython, ['ls_ratio_collector.py']),
        inlineApp('idim-api', venvPython, ['-m', 'uvicorn', 'api:app', '--host', '0.0.0.0', '--port', '8787']),
        inlineApp('idim-scanner', venvPython, ['scanner.py']),
        inlineApp('idim-outcome-tracker', venvPython, ['outcome_tracker.py', '--loop']),
        inlineApp('idim-auto-executor', venvPython, ['auto_executor.py']),
    ],
};