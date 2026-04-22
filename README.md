<div align="center">
  <img width="1200" height="475" alt="Idim Ikang banner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# Idim Ikang: Sovereign Market Observer

**Idim Ikang** is a two-sided, highly instrumented crypto signal execution engine and observer stack. It is built around the **Sovereign Coherence v2.0 Doctrine**, dynamically seeking true 60-40 operational parity across long and short spectrums. 

It executes deep-funnel market generation, strictly evaluates candidate lifespan, tracks execution outcomes, and visualizes system health via a React dashboard and Telegram API.

---

## 🦅 The Sovereign Doctrine (v2.0)

Idim Ikang does not merely search for "good setups." It functions as an environmentally-aware machine that utilizes a **Dynamic Push-Pull Coherence Controller** to manage throughput symmetry.

Instead of deploying static threshold checks, the engine dynamically adjusts its logic to prevent one-sided structural starvation based on the broader market regime.

### The Pipeline Attrition Funnel
Every pairing on the exchange goes through a strict survival gauntlet. `A signal is not born unless it survives runtime.`

1. **Alpha Template Generation (Phase 1):** Scans evaluate local indicators against specific strategy templates (Alpha Families) to establish a raw baseline score.
2. **Coherence Balancing:** The `SideBalanceController` calculates the rolling 200-trade Long/Short share. If the system is leaning >60% to one side, a maximum Coherence Boost/Penalty (±15) is dynamically applied to candidate scores to incentivize the underrepresented side. Floor denial blocks garbage setups from being artificially rescued.
3. **Regime & Soft Gating:** Exhaustion blockers, BTC Macro trends, and 1H regime-penalties apply violent soft-score decimation to overextended or structurally unsafe trades.
4. **Wolfram 5-Cell Post-Selection:** Surviving candidates that maintain an adjusted score `>= 50` are cleared for emission and post-selection logic.

---

## 🧬 Sovereign Alpha Families

Raw scoring is dictated by highly specialized, un-mirrored side doctrines. 

### Long Faction
*   `trend`: Standard 2-of-3 indicator alignment (EMA Cross, ADX, MACD).
*   `volatility`: Squeeze firings combined with significant volume expansion/ATR expansion.
*   `momentum`: RSI trajectory acceleration supported by volume.
*   `mean_reversion`: Deep oversold distances from the structural EMA20 baseline.

### Short Faction (Sprint B)
*   `failed_bounce`: Specific exhaustion templates targeting 50-65 RSI bands breaking down under upper EMAs against negative CVD.
*   `breakdown`: Uninhibited structural breakdown targets enforcing ADX expansion constraints.
*   `mean_reversion_short`: Wide-net captures targeting 2%+ VWAP over-extensions simultaneously losing MACD histogram velocity.

*(Only the maximum scoring template within a faction dictates the final baseline candidate score).*

---

## 🕵️ Deep Telemetry & Observability

Idim Ikang is heavily instrumented natively against `PM2`. Attrition logs cleanly dictate whether issues are caused by failure to generate, failures to survive gates, or system crashes.

### Diagnostics via PM2
The observer `idim-scanner` prints high-fidelity operational throughput on every execution cycle.

```bash
# General scanner operations
pm2 logs idim-scanner --lines 100 --nostream

# Pinpoint Short-Side Pipeline Attrition
pm2 logs idim-scanner --lines 200 --nostream | grep "SHORT_"
```
*Outputs distinct funnel drop-offs (e.g. `SHORT_ATTR: Emitted=0 | Miss<5=2 | Miss<10=4 | GateKilled=12 | FloorDenied=1 | TemplateZero=3`).*

### SQL Deep Dives
Idim Ikang records everything into PostgreSQL (`idim_ikang`). 

```sql
-- Check overall dataset health
SELECT MAX(ts), COUNT(*) FROM training_candidates;

-- Expected Return (E[R]) by Engine Side Over the Last 30 Days
SELECT side, COUNT(*) as trades, 
       SUM(CASE WHEN outcome ILIKE '%win%' THEN 1 ELSE 0 END) as wins, 
       AVG(r_multiple) as expectation
FROM signals 
WHERE ts >= NOW() - INTERVAL '30 days' AND outcome IS NOT NULL 
GROUP BY side;
```

---

## 🏗️ Technical Architecture

| Component | Responsibility (Tech) |
|---|---|
| **Engine Core** | `Python`, `pandas`. Manages the PM2 worker loops processing Alpha logic against live market streams. Located at `observer_bundle/`. |
| **Data Layer** | `PostgreSQL`. Stores `training_candidates` (every row processed) and `signals` (the emissions). Communicates via `LISTEN/NOTIFY`. |
| **Live UI** | `React 19`, `Vite`, `TypeScript`. Real-time GUI dashboard hooked into Postgres SSE payloads for visualization. |
| **Alerting** | `Telegram Bot API`. Operational loop. Alert tracking on emission and automated execution tracking. |

### Repository map
```text
IdimIkang-main-1/
├── src/                         # React dashboard UI
├── observer_bundle/             # Sovereign scanner + backend services
│   ├── config.py                # Coherence, ± limits, tuning offsets
│   ├── scanner.py               # The Core Funnel & Telemetry loop
│   ├── auto_executor.py         # Sim/Live execution pipeline
│   ├── outcome_tracker.py       # Resolving Wins/Losses telemetry
│   ├── telegram_alerts.py
│   └── README_DEPLOY.md  
├── pm2.local.config.cjs         # Local PM2 stack definition
└── README.md
```

---

## 🚀 Quick Start (WSL2 Deployment)

### 1. Requirements
*   **Node.js 18+**
*   **Python 3.12+** inside WSL/Ubuntu
*   **PostgreSQL** active and populated via `DATABASE_URL`
*   **PM2** (`npm install -g pm2`) 

*(Configure your environments using `.env` for the database and Telegram tokens)*.

### 2. Prepare the Python Engine
```bash
cd observer_bundle
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Initiate the Daemon Stack
Run the `Idim Ikang` stack entirely via PM2.

```bash
# Starts the API, the Scanner, the Exec engine, and UI utilities
pm2 startOrRestart pm2.local.config.cjs --update-env
pm2 list
```

### 4. Initiate the Frontend Map
Run the local Vite dashboard (Accessible locally via `3000`).
```bash
npm install
npm run dev
```

---

## ⚠️ Disclaimer

This project is for research, monitoring, and operational use in your own environment. It is **not financial advice**. Ensure strict testing of the Coherence Thresholds (`MAX_COHERENCE_OFFSET`) before initiating automated execution pathways.
