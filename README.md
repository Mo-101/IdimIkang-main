<div align="center">
  <img width="1200" height="475" alt="Idim Ikang banner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# Idim Ikang

**Idim Ikang** is a WSL2-based crypto signal dashboard and observer stack that combines:

- a **React + Vite frontend** for live signal visibility,
- a **FastAPI backend** for SSE/API delivery,
- a **Python scanner / collector pipeline** for market observation,
- and optional **simulation / execution plumbing** for signal handling and trade lifecycle tracking.

---

## ✨ What this app does

This project continuously scans a liquid futures universe, scores opportunities, logs full training coverage, emits qualified signals, tracks outcomes, and surfaces everything in a dashboard with Telegram visibility.

### Feature grid

| Area | What it does | Main files |
|---|---|---|
| **Frontend dashboard** | Displays market state, signals, chart panels, exchange panels, stats, and active positions | `src/`, `index.html` |
| **Signal API / SSE** | Serves signal feed, stats, streaming updates, trade endpoints | `observer_bundle/api.py`, `server.ts` |
| **Collectors** | Pulls funding, open interest, and long/short ratio data | `funding_collector.py`, `oi_collector.py`, `ls_ratio_collector.py` |
| **Scanner** | Runs market scan, worker-phase filtering, Phase 2 real-data gating, ranking, and signal insertion | `observer_bundle/scanner.py` |
| **Execution** | Processes inserted signals, dedup checks, risk checks, execution/sim dispatch | `observer_bundle/auto_executor.py` |
| **Outcome tracking** | Resolves `WIN` / `LOSS` / `EXPIRED`, tracks MAE/MFE, emits outcome alerts | `observer_bundle/outcome_tracker.py` |
| **Notifications** | Sends Telegram alerts for signal, operational, execution, and outcome events | `observer_bundle/telegram_alerts.py` |
| **Process control** | Runs the local stack under PM2 | `pm2.local.config.cjs`, `observer_bundle/ecosystem*.cjs` |

---

## 🧠 Core workflow

1. **Collectors** update derivative context (`funding`, `OI`, `LS ratio`).
2. **Scanner worker phase** scans broadly and logs training coverage.
3. **Phase 2** applies real DB alpha, sovereign ranking, and execution gating.
4. **Signals** are inserted into Postgres and broadcast via API/SSE/Telegram.
5. **Auto executor** either simulates or dispatches the order path.
6. **Outcome tracker** resolves open signals and updates performance telemetry.

> The training tunnel is intentionally broad: **every symbol, both sides, every cycle** can still be recorded in `training_candidates` even when execution gating is stricter.

---

## 🏗️ Architecture at a glance

| Layer | Tech |
|---|---|
| UI | `React 19`, `Vite`, `TypeScript`, `lucide-react` |
| Local API | `FastAPI`, `Express` |
| Market / strategy engine | `Python`, `pandas`, `psycopg2` |
| Process management | `PM2` |
| Database | PostgreSQL |
| Realtime transport | PostgreSQL `LISTEN/NOTIFY` + SSE |
| Alerting | Telegram Bot API |

### Common local ports

| Port | Service |
|---|---|
| `3000` | Vite dev frontend |
| `3001` | Local mock / utility Node server |
| `8787` | FastAPI backend (`idim-api`) |

---

## 📁 Repository layout

```text
IdimIkang-main-1/
├── src/                         # React dashboard UI
├── public/                      # Static frontend assets
├── observer_bundle/             # Sovereign scanner + backend services
│   ├── api.py
│   ├── scanner.py
│   ├── auto_executor.py
│   ├── outcome_tracker.py
│   ├── funding_collector.py
│   ├── oi_collector.py
│   ├── ls_ratio_collector.py
│   ├── telegram_alerts.py
│   └── README_DEPLOY.md
├── quant_core/                  # Shared quant / exchange helpers
├── strategies/                  # Strategy logic and supporting modules
├── pm2.local.config.cjs         # Local PM2 stack definition
├── server.ts                    # Node utility/mock API server
└── README.md
```

---

## 🚀 Quick start

### Prerequisites

Make sure you have:

- **Node.js 18+**
- **Python 3.12+** inside WSL/Ubuntu
- **PostgreSQL** reachable via `DATABASE_URL`
- **PM2** (`npm install -g pm2`) for process management
- a populated `observer_bundle/.env`

### 1) Install frontend dependencies

```bash
npm install
```

### 2) Prepare the observer environment

```bash
cd observer_bundle
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3) Run the frontend only

```bash
npm run dev
```

### 4) Run the full observer stack

From VS Code, you can run the workspace task:

- **`Start Idim Ikang Stack`**

Or from the terminal:

```bash
pm2 startOrRestart pm2.local.config.cjs --update-env
pm2 list
```

---

## ▶️ Useful commands

| Command | Purpose |
|---|---|
| `npm run dev` | Start Vite dashboard on `3000` |
| `npm run build` | Production frontend build |
| `npm run preview` | Preview built frontend |
| `npm run lint` | Type-check frontend code |
| `pm2 startOrRestart pm2.local.config.cjs --update-env` | Start/restart backend services |
| `pm2 logs idim-scanner --nostream --lines 100` | Inspect scanner logs |
| `pm2 logs idim-auto-executor --nostream --lines 100` | Inspect execution logs |
| `pm2 logs idim-outcome-tracker --nostream --lines 100` | Inspect outcome logs |

---

## ⚙️ Key runtime components

### Scanner: `observer_bundle/scanner.py`

Responsible for:

- worker-phase market scanning,
- training coverage logging,
- Phase 2 real-data rescoring,
- regime/time execution gating,
- final candidate ranking and signal insertion.

### API: `observer_bundle/api.py`

Provides:

- REST endpoints,
- realtime SSE stream (`/api/stream`),
- PostgreSQL `LISTEN/NOTIFY` bridge,
- health and signal surfaces for the dashboard.

### Auto Executor: `observer_bundle/auto_executor.py`

Responsible for:

- listening for `new_signal`,
- deduplication and circuit-breaker checks,
- simulated/live execution dispatch,
- position-opened Telegram alerts.

### Outcome Tracker: `observer_bundle/outcome_tracker.py`

Responsible for:

- resolving open signals,
- recording trade outcome metadata,
- scale-out and final result alerts,
- performance attribution over time.

---

## 🧪 Telemetry and observability

The app is instrumented around three levels:

| Telemetry type | Where it lands |
|---|---|
| Operational events | PM2 logs + Telegram |
| Signal flow | `signals` table + SSE + Telegram |
| Training coverage | `training_candidates` table |
| System events | `system_logs` table |

### Important live checks

```sql
-- Emitted signals by regime and side
SELECT regime, side, COUNT(*) AS emitted
FROM signals
WHERE ts >= NOW() - INTERVAL '24 hours'
GROUP BY regime, side
ORDER BY regime, side;
```

```sql
-- Phase 2 rejection reasons stored in training metadata
SELECT trace_data->>'phase2_rejection_gate' AS gate, COUNT(*) AS c
FROM training_candidates
WHERE ts >= NOW() - INTERVAL '24 hours'
  AND trace_data ? 'phase2_rejection_gate'
GROUP BY gate
ORDER BY c DESC;
```

```sql
-- Tunnel integrity / training rows over time
SELECT date_trunc('hour', ts) AS hr, COUNT(*) AS rows_logged
FROM training_candidates
WHERE ts >= NOW() - INTERVAL '24 hours'
GROUP BY hr
ORDER BY hr;
```

---

## 🔐 Important environment variables

The observer stack relies primarily on `observer_bundle/.env`.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection for signals, logs, and training rows |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token for alerts |
| `TELEGRAM_CHAT_ID` | Telegram target chat/channel |
| `ENABLE_LIVE_TRADING` | Switch between live and sim behavior |
| `SCAN_INTERVAL_SECONDS` | Scan cadence |
| `SSE_AUTH_TOKEN` | Optional SSE/API auth token |

You may also tune values in `observer_bundle/config.py`, including:

- score thresholds,
- regime/time execution gating,
- squeeze and volume gates,
- Phase 2 weighting multipliers.

---

## 🩺 Troubleshooting

### Backend services are not all online

```bash
pm2 list
pm2 logs idim-scanner --nostream --lines 100
```

### API port `8787` is already in use

Check what is bound:

```bash
ss -ltnp | grep 8787
```

### Telegram alerts are missing

Check:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- PM2 logs for `scanner`, `auto_executor`, and `outcome_tracker`

### Dashboard loads but no fresh signals appear

Verify:

- `idim-api` is online
- PostgreSQL `LISTEN/NOTIFY` is working
- `/api/stream` is reachable
- `signals` table is receiving inserts

### Scanner is running but signals are scarce

This can be normal when:

- Phase 2 execution gating is active,
- dead hours are blocked,
- strict live thresholds are enabled,
- BTC or regime filters suppress low-quality setups.

---

## 📦 Deployment note

For the WSL2 observer deployment bundle, see:

- `observer_bundle/README_DEPLOY.md`

That doc covers the local sovereign deployment model and PM2 operation in more detail.

---

## ⚠️ Disclaimer

This project is for research, monitoring, and operational use in your own environment. It is **not financial advice**. Review all execution settings, API keys, and risk controls before enabling live trading.
