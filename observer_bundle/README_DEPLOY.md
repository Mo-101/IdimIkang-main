# Idim Ikang Local WSL2 Observer Bundle

This bundle is for local sovereign deployment on an existing WSL2 Ubuntu stack.

## What it includes
- `ecosystem.idim.config.js`
- `setup_db.sql`
- `scanner.py`
- `api.py`
- `.env.example`
- `deploy.sh`
- `outcome_tracker.py`
- `requirements.txt`

## Notes
- Scanner uses a self-contained baseline-aligned scoring implementation.
- It does **not** import the unstable repo scoring modules.
- It is observer-only. No trading or order execution.
- PM2 handles restart on crash/wake.
- Laptop sleep is acceptable for observer mode. Gaps are logged.

## Deploy
```bash
chmod +x deploy.sh
./deploy.sh
```
