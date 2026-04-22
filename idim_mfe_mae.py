"""
IDIM IKANG — MFE/MAE Excursion Analyzer
🜂 Read what the market actually offered, not what the exit policy booked.

For every closed trade in the signals table:
  • Fetch 15-min Binance futures candles from entry forward (up to 24h)
  • Compute MFE (max favorable excursion) and MAE (max adverse) in R units
  • Replay the trade under 6 exit policies to find the real R:R ceiling

Exit policies simulated:
  P1_tp1_0.60   — current policy (TP at +0.60R, SL at -1.00R)
  P2_tp_1.20    — TP at +1.20R (2× current)
  P3_tp_2.00    — TP at +2.00R (full swing)
  P4_trail_0.50 — trailing stop: activate at +0.50R, trail 0.50R behind
  P5_time_8h    — time stop: exit at close of bar 32 (8h) or SL
  P6_time_24h   — time stop: exit at close of bar 96 (24h) or SL

SL remains -1.00R for all policies (same downside). The output reveals
whether the signal quality supports a better ceiling than TP1 currently
captures. If P2/P3/P4 show higher total_R than P1, widening the target
flips the system profitable without any score-model retraining.

Outputs:
  • mfe_mae_results.csv — per-trade excursion + policy P&L
  • Summary table to stdout — total_R and WR under each policy
  • Regime × family MFE distribution — where the ceiling is highest
"""
import os
import sys
import time
import argparse
import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

DB = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang",
)
TABLE = "signals"
BINANCE = "https://fapi.binance.com/fapi/v1/klines"
MAX_BARS = 96          # 24 hours of 15-min candles
INTERVAL = "15m"
SPOT_FALLBACK = "https://api.binance.com/api/v3/klines"


# ─────────────────────────────────────────────────────────────────────────
# LOAD
# ─────────────────────────────────────────────────────────────────────────

def load_signals(since=None, limit=None):
    conn = psycopg2.connect(DB)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    where = [
        "outcome IN ('WIN','LOSS')",
        "entry IS NOT NULL",
        "stop_loss IS NOT NULL",
    ]
    if since:
        where.append(f"ts >= '{since}'")
    lim = f"LIMIT {limit}" if limit else ""
    sql = f"""
        SELECT
            id, ts, pair, side, score,
            entry, stop_loss, take_profit,
            r_multiple AS r_mult, outcome,
            COALESCE(reason_trace->>'family_tag', signal_family, 'NONE') AS family,
            COALESCE(market_regime, regime) AS regime
        FROM {TABLE}
        WHERE {' AND '.join(where)}
        ORDER BY ts DESC
        {lim}
    """
    cur.execute(sql)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["side"] = df["side"].str.upper()
    for col in ("entry", "stop_loss", "take_profit", "r_mult"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["entry", "stop_loss"])
    return df


# ─────────────────────────────────────────────────────────────────────────
# BINANCE FETCH
# ─────────────────────────────────────────────────────────────────────────

def fetch_candles(pair, start_ms, n_bars=MAX_BARS):
    """Fetch n_bars of 15m candles starting at start_ms from Binance futures.
    Falls back to spot if futures endpoint doesn't know the symbol."""
    params = {
        "symbol": pair,
        "interval": INTERVAL,
        "startTime": int(start_ms),
        "limit": n_bars,
    }
    for url in (BINANCE, SPOT_FALLBACK):
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code != 200:
                continue
            data = r.json()
            if not isinstance(data, list) or len(data) == 0:
                continue
            return [
                {
                    "open_time": int(row[0]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                }
                for row in data
            ]
        except Exception:
            continue
    return None


# ─────────────────────────────────────────────────────────────────────────
# EXCURSION + POLICY SIMULATION
# ─────────────────────────────────────────────────────────────────────────

POLICIES = {
    "P1_tp1_0.60":   ("tp",    0.60),
    "P2_tp_1.20":    ("tp",    1.20),
    "P3_tp_2.00":    ("tp",    2.00),
    "P4_trail_0.50": ("trail", 0.50),
    "P5_time_8h":    ("time",  32),
    "P6_time_24h":   ("time",  96),
}


def compute_excursion(trade, bars):
    entry = trade["entry"]
    sl = trade["stop_loss"]
    side = trade["side"]
    risk = abs(entry - sl)
    if risk == 0 or not bars:
        return None

    def to_r(price):
        return (price - entry) / risk if side == "LONG" else (entry - price) / risk

    mfe = 0.0
    mae = 0.0
    time_to_mfe = 0

    state = {name: {"resolved": False, "r": 0.0, "bar": None} for name in POLICIES}
    trail = {
        name: {"activated": False, "high_r": 0.0}
        for name, (kind, _) in POLICIES.items()
        if kind == "trail"
    }

    for i, bar in enumerate(bars):
        if side == "LONG":
            fav_r = to_r(bar["high"])    # price up = favorable
            adv_r = to_r(bar["low"])     # price down = adverse
        else:
            fav_r = to_r(bar["low"])     # price down = favorable
            adv_r = to_r(bar["high"])    # price up = adverse

        if fav_r > mfe:
            mfe = fav_r
            time_to_mfe = i + 1
        if adv_r < mae:
            mae = adv_r

        for name, (kind, param) in POLICIES.items():
            st = state[name]
            if st["resolved"]:
                continue

            # Conservative: assume SL is checked first within the bar
            if adv_r <= -1.0:
                st.update(resolved=True, r=-1.0, bar=i + 1)
                continue

            if kind == "tp":
                if fav_r >= param:
                    st.update(resolved=True, r=param, bar=i + 1)

            elif kind == "trail":
                ts = trail[name]
                activation_r = param
                trail_dist = param
                if not ts["activated"]:
                    if fav_r >= activation_r:
                        ts["activated"] = True
                        ts["high_r"] = fav_r
                else:
                    if fav_r > ts["high_r"]:
                        ts["high_r"] = fav_r
                    stop_level = ts["high_r"] - trail_dist
                    if adv_r <= stop_level:
                        st.update(resolved=True, r=max(stop_level, -1.0), bar=i + 1)

            elif kind == "time":
                n_limit = param
                if i + 1 >= n_limit:
                    close_r = to_r(bar["close"])
                    st.update(resolved=True, r=close_r, bar=i + 1)

    # Anything still open at end of window: settle at last close
    if bars:
        last_close_r = to_r(bars[-1]["close"])
        for st in state.values():
            if not st["resolved"]:
                st.update(resolved=True, r=last_close_r, bar=len(bars))

    return {
        "id": trade.get("id"),
        "pair": trade["pair"],
        "side": side,
        "family": trade["family"],
        "regime": trade["regime"],
        "score": trade.get("score"),
        "actual_r": trade.get("r_mult"),
        "mfe": round(mfe, 3),
        "mae": round(mae, 3),
        "time_to_mfe_bars": time_to_mfe,
        "n_bars_fetched": len(bars),
        **{name: round(st["r"], 3) for name, st in state.items()},
    }


# ─────────────────────────────────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────────────────────────────────

def process_trade(trade):
    ts = trade["ts"]
    entry_ms = int(pd.Timestamp(ts).timestamp() * 1000)
    bars = fetch_candles(trade["pair"], entry_ms, MAX_BARS)
    if not bars:
        return None
    return compute_excursion(trade, bars)


def run_analysis(df, max_workers=6):
    results = []
    n = len(df)
    print(f"🜂 Fetching candles and computing excursion for {n} trades ...")
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(process_trade, row): i for i, row in enumerate(df.to_dict("records"))}
        done = 0
        failed = 0
        for fut in as_completed(futures):
            done += 1
            try:
                res = fut.result()
            except Exception:
                res = None
            if res:
                results.append(res)
            else:
                failed += 1
            if done % 25 == 0 or done == n:
                print(f"  progress: {done}/{n}  (failed: {failed})")
            time.sleep(0.01)
    return pd.DataFrame(results)


# ─────────────────────────────────────────────────────────────────────────
# REPORT
# ─────────────────────────────────────────────────────────────────────────

def section(title):
    print("\n" + "═" * 72)
    print(f" {title}")
    print("═" * 72)


def report(res):
    if res.empty:
        print("No trades resolved. Check Binance connectivity or symbol names.")
        return

    policy_cols = [c for c in res.columns if c.startswith("P")]

    section("POLICY COMPARISON — total R and WR under each exit rule")
    summary = {}
    print(f"  {'Policy':<16} {'N':>4} {'WR%':>7} {'E[R]':>7} {'total_R':>9}")
    print(f"  {'─'*16} {'─'*4} {'─'*7} {'─'*7} {'─'*9}")
    for col in policy_cols:
        n = len(res)
        wins = (res[col] > 0).sum()
        wr = wins / n * 100
        avg_r = res[col].mean()
        total = res[col].sum()
        summary[col] = (n, wr, avg_r, total)
        print(f"  {col:<16} {n:>4} {wr:>6.1f}% {avg_r:>+7.3f} {total:>+9.1f}")

    section("MFE / MAE DISTRIBUTION (what the market actually offered)")
    print(f"  MFE   median={res['mfe'].median():.2f}R  p75={res['mfe'].quantile(.75):.2f}R  "
          f"p90={res['mfe'].quantile(.90):.2f}R  max={res['mfe'].max():.2f}R")
    print(f"  MAE   median={res['mae'].median():.2f}R  p25={res['mae'].quantile(.25):.2f}R  "
          f"p10={res['mae'].quantile(.10):.2f}R  min={res['mae'].min():.2f}R")
    ttm = res["time_to_mfe_bars"].median()
    print(f"  Median time to MFE: {ttm:.0f} bars × 15min = {ttm*15:.0f} min")

    section("MFE CEILING BY REGIME × FAMILY × SIDE (min n=5)")
    fam_reg = (res.groupby(["regime", "family", "side"])
                  .agg(n=("mfe", "count"),
                       mfe_med=("mfe", "median"),
                       mfe_p75=("mfe", lambda x: x.quantile(.75)),
                       mae_med=("mae", "median"))
                  .reset_index())
    fam_reg = fam_reg[fam_reg["n"] >= 5].sort_values("mfe_med", ascending=False)
    print(fam_reg.round(3).to_string(index=False))

    section("MFE vs BOOKED — how much R the current policy left on the table")
    # Signed booked: actual_r — current policy; compare to MFE for winners
    winners = res[res["actual_r"] > 0].copy()
    if not winners.empty:
        winners["mfe_leftover"] = winners["mfe"] - winners["actual_r"]
        print(f"  Winners only (n={len(winners)}):")
        print(f"    Median booked R:   {winners['actual_r'].median():.2f}")
        print(f"    Median MFE R:      {winners['mfe'].median():.2f}")
        print(f"    Median leftover:   {winners['mfe_leftover'].median():.2f}R left on the table")
        print(f"    p75 leftover:      {winners['mfe_leftover'].quantile(.75):.2f}R")
    else:
        print("  No winners in sample.")

    section("VERDICT")
    best_name, (n, wr, avg_r, best_tot) = max(summary.items(), key=lambda x: x[1][3])
    worst_name, (_, _, _, worst_tot) = min(summary.items(), key=lambda x: x[1][3])
    current = summary.get("P1_tp1_0.60", (0, 0, 0, 0))[3]
    improvement = best_tot - current
    print(f"  Current policy P1_tp1_0.60 total_R:  {current:+.1f}")
    print(f"  Best policy {best_name} total_R:    {best_tot:+.1f}")
    print(f"  Improvement from switching:          {improvement:+.1f}R  ({improvement/abs(current)*100 if current else 0:+.1f}%)")
    if best_tot > 0 >= current:
        print("  🔥 Exit policy change alone flips the system to profitable.")
    elif best_tot > current:
        print("  ⚡ Better exit policy reduces bleed but doesn't flip profitability.")
        print("     Combine with idim_gate_patch.py for the full stack.")
    else:
        print("  The R:R ceiling is real. Signal quality, not exit policy, is the next lever.")


# ─────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="ISO date lower bound")
    ap.add_argument("--limit", type=int, help="Cap N trades for a fast first run")
    ap.add_argument("--out", default="mfe_mae_results.csv")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    df = load_signals(since=args.since, limit=args.limit)
    if df.empty:
        print("No trades loaded. Check DATABASE_URL and filters.")
        sys.exit(1)
    print(f"🜂 Loaded {len(df)} closed trades with valid entry/SL.")

    res = run_analysis(df, max_workers=args.workers)
    if res.empty:
        print("No trades produced candle data. Check symbol names against Binance.")
        sys.exit(1)

    res.to_csv(args.out, index=False)
    print(f"✓ Per-trade results saved to {args.out}")
    report(res)
