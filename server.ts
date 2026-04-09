import express from 'express';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const port = 3001;

app.use(express.json());

// Persistence Layer
const SIGNALS_FILE = path.join(__dirname, 'real_signals.json');

function loadSignals() {
  if (fs.existsSync(SIGNALS_FILE)) {
    try {
      return JSON.parse(fs.readFileSync(SIGNALS_FILE, 'utf-8'));
    } catch (e) {
      console.error("Failed to load signals:", e);
    }
  }
  return [];
}

function saveSignals(signals: any[]) {
  fs.writeFileSync(SIGNALS_FILE, JSON.stringify(signals, null, 2));
}

let signals = loadSignals();

// If no signals, load from PHASE2_RESULTS.json as baseline
if (signals.length === 0) {
  const baselineFile = path.join(__dirname, 'PHASE2_RESULTS.json');
  if (fs.existsSync(baselineFile)) {
    try {
      const baseline = JSON.parse(fs.readFileSync(baselineFile, 'utf-8'));
      // Map baseline to our signal format
      signals = baseline.map((s: any) => ({
        signal_id: s.id || Math.random().toString(36).substr(2, 9),
        pair: s.pair,
        ts: s.timestamp || new Date().toISOString(),
        side: s.side,
        entry: s.entry,
        stop_loss: s.stop_loss,
        take_profit: s.take_profit,
        score: s.score,
        regime: s.regime,
        outcome: s.outcome || (Math.random() > 0.5 ? 'win' : 'loss'),
        r_multiple: s.r_multiple || (s.outcome === 'win' ? 3.0 : -1.0),
        execution_source: s.execution_source || 'simulated',
        logic_version: s.logic_version || "v1.5-quant-alpha"
      }));
      saveSignals(signals);
    } catch (e) {
      console.error("Failed to load baseline:", e);
    }
  }
}

function calculateStats() {
  const stats = {
    simulated: { wins: 0, losses: 0, expired: 0, total: 0, win_rate: 0, profit_factor: 0 },
    live: { wins: 0, losses: 0, expired: 0, total: 0, win_rate: 0, profit_factor: 0 },
    total: { wins: 0, losses: 0, expired: 0, total: 0, win_rate: 0, profit_factor: 0 }
  };

  signals.forEach(s => {
    const source = (s.execution_source === 'live' ? 'live' : 'simulated') as 'live' | 'simulated';
    const outcome = s.outcome;

    if (outcome === 'win') {
      stats[source].wins++;
      stats.total.wins++;
    } else if (outcome === 'loss') {
      stats[source].losses++;
      stats.total.losses++;
    } else if (outcome === 'expired') {
      stats[source].expired++;
      stats.total.expired++;
    }

    stats[source].total++;
    stats.total.total++;
  });

  // Calculate rates
  ['simulated', 'live', 'total'].forEach(key => {
    const k = key as 'simulated' | 'live' | 'total';
    const total = stats[k].wins + stats[k].losses;
    stats[k].win_rate = total > 0 ? Math.round((stats[k].wins / total) * 100) : 0;
    stats[k].profit_factor = stats[k].losses > 0 ? Number((stats[k].wins * 3 / stats[k].losses).toFixed(2)) : (stats[k].wins > 0 ? 99 : 0);
  });

  return {
    ...stats,
    unresolved: signals.filter(s => !s.outcome).length,
    latest_cycle: {
      pairs_processed: 0,
      setups_viable_pre_phase2: 0,
      setups_blocked_phase2: 0,
      signals_emitted: 0,
      duration: 0,
    },
    logic_version: "v1.5-quant-alpha",
    config_version: "v1.5-default"
  };
}

app.get('/signals', (req, res) => {
  res.json({ count: signals.length, signals: signals.slice(-50).reverse() });
});

app.get('/stats', (req, res) => {
  res.json(calculateStats());
});

app.get('/cell-performance', (req, res) => {
  // Aggregate by regime and score bucket
  const cells: any = {};
  signals.forEach(s => {
    const bucket = Math.floor(s.score / 10) * 10;
    const key = `${s.regime}_${bucket}`;
    if (!cells[key]) {
      cells[key] = { regime: s.regime, score_bucket: bucket, wins: 0, losses: 0, expired: 0, total: 0 };
    }
    if (s.outcome === 'win') cells[key].wins++;
    else if (s.outcome === 'loss') cells[key].losses++;
    else if (s.outcome === 'expired') cells[key].expired++;
    cells[key].total++;
  });

  const cellArray = Object.values(cells).map((c: any) => {
    const total = c.wins + c.losses;
    return {
      ...c,
      win_rate: total > 0 ? Math.round((c.wins / total) * 100) : 0,
      profit_factor: c.losses > 0 ? Number((c.wins * 3 / c.losses).toFixed(2)) : (c.wins > 0 ? 99 : 0)
    };
  });

  res.json(cellArray);
});

app.post('/trade/place', (req, res) => {
  const { pair, side, entry, stop_loss, take_profit, score, regime } = req.body;
  const newSignal = {
    signal_id: "ORD-" + Math.random().toString(36).substr(2, 9).toUpperCase(),
    pair, side, entry, stop_loss, take_profit, score, regime,
    ts: new Date().toISOString(),
    outcome: null,
    execution_source: 'live', // Manual trades are considered live
    logic_version: "v1.5-quant-alpha"
  };
  signals.push(newSignal);
  saveSignals(signals);
  res.json({ status: "success", order_id: newSignal.signal_id });
});

app.post('/trade/close', (req, res) => {
  res.json({ status: "success" });
});

app.post('/trade/panic', (req, res) => {
  res.json({ status: "success" });
});

app.listen(port, () => {
  console.log(`Mock API server running at http://localhost:${port}`);
});
