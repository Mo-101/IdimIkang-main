"""
IDIM IKANG — Gate Patch v1
🜂 Three surgical cuts to stop the bleed before we tune exits.

Gates (applied in order):
  G1: NONE family block       — no structural thesis, no emission
  G2: BTC regime alignment    — SHORTs only when btc_regime == market_regime
  G3: RANGING-LONG block      — 17.6% WR death zone, hard kill

Two modes:
  1. Library     — `from idim_gate_patch import apply_gates`
                   `ok, reason = apply_gates(signal_dict)` inside the scanner
  2. Replay      — `python idim_gate_patch.py` → historical WR with gates on

Replay reads the same `signals` table as the diagnostic and replays every
resolved trade through the gates, showing before/after WR, E[R], total_R
and surviving-pocket breakdown.
"""
import os
import sys
import argparse
import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor

DB = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang",
)
TABLE = "signals"


# ─────────────────────────────────────────────────────────────────────────
# GATE LOGIC — import these into the scanner
# ─────────────────────────────────────────────────────────────────────────

def gate_none_family(signal):
    """G1: block signals with no structural family classification."""
    family = (signal.get("family") or signal.get("family_tag") or "").strip().lower()
    if family in ("", "none", "null"):
        return False, "G1_NONE_FAMILY"
    return True, None


def gate_btc_alignment(signal):
    """G2: SHORTs require btc_regime == market_regime agreement."""
    side = (signal.get("side") or "").upper()
    if side != "SHORT":
        return True, None
    market = signal.get("regime") or signal.get("market_regime")
    btc = signal.get("btc_regime") or signal.get("btc_reg")
    if not market or not btc or market == "UNKNOWN" or btc == "UNKNOWN":
        return False, "G2_BTC_REGIME_MISSING"
    if market != btc:
        return False, "G2_BTC_MISALIGNED"
    return True, None


def gate_ranging_long(signal):
    """G3: block LONGs in RANGING regime (17.6% WR death zone)."""
    side = (signal.get("side") or "").upper()
    regime = (signal.get("regime") or signal.get("market_regime") or "").upper()
    if side == "LONG" and regime == "RANGING":
        return False, "G3_RANGING_LONG"
    return True, None


GATES = [gate_none_family, gate_btc_alignment, gate_ranging_long]


def apply_gates(signal):
    """Apply all gates in order. Returns (allowed: bool, rejection_reason: str|None)."""
    for gate in GATES:
        ok, reason = gate(signal)
        if not ok:
            return False, reason
    return True, None


# ─────────────────────────────────────────────────────────────────────────
# REPLAY MODE — show historical WR before/after each gate
# ─────────────────────────────────────────────────────────────────────────

def load_signals(since=None):
    conn = psycopg2.connect(DB)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    where = ["outcome IN ('WIN','LOSS')"]
    if since:
        where.append(f"ts >= '{since}'")
    sql = f"""
        SELECT
            ts, pair, side, score,
            r_multiple AS r_mult, outcome,
            COALESCE(reason_trace->>'family_tag', signal_family, 'NONE') AS family,
            COALESCE(market_regime, regime) AS regime,
            COALESCE(btc_regime, 'UNKNOWN') AS btc_regime
        FROM {TABLE}
        WHERE {' AND '.join(where)}
        ORDER BY ts
    """
    cur.execute(sql)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["family"] = df["family"].fillna("NONE").replace({"": "NONE", "none": "NONE"})
    df["regime"] = df["regime"].fillna("UNKNOWN")
    df["btc_regime"] = df["btc_regime"].fillna("UNKNOWN")
    df["side"] = df["side"].str.upper()
    df["r_mult"] = df["r_mult"].fillna(0.0).astype(float)
    return df


def wr_stats(df):
    n = len(df)
    if n == 0:
        return (0, 0.0, 0.0, 0.0)
    wins = (df["outcome"] == "WIN").sum()
    wr = wins / n * 100
    avg_r = df["r_mult"].mean()
    total_r = n * avg_r
    return (n, wr, avg_r, total_r)


def section(title):
    print("\n" + "═" * 72)
    print(f" {title}")
    print("═" * 72)


def replay(df):
    baseline = df.to_dict("records")

    section("HISTORICAL REPLAY — WR before/after each gate")

    n, wr, avg_r, tot = wr_stats(pd.DataFrame(baseline))
    print(f"\n [0] BASELINE                   n={n:>4}  WR={wr:5.1f}%  E[R]={avg_r:+.3f}  total_R={tot:+7.1f}")

    after_g1 = [r for r in baseline if gate_none_family(r)[0]]
    n, wr, avg_r, tot = wr_stats(pd.DataFrame(after_g1))
    print(f" [1] + G1 NONE-family block     n={n:>4}  WR={wr:5.1f}%  E[R]={avg_r:+.3f}  total_R={tot:+7.1f}")

    after_g2 = [r for r in after_g1 if gate_btc_alignment(r)[0]]
    n, wr, avg_r, tot = wr_stats(pd.DataFrame(after_g2))
    print(f" [2] + G2 BTC-alignment SHORT   n={n:>4}  WR={wr:5.1f}%  E[R]={avg_r:+.3f}  total_R={tot:+7.1f}")

    after_g3 = [r for r in after_g2 if gate_ranging_long(r)[0]]
    n_final, wr_final, avg_r_final, tot_final = wr_stats(pd.DataFrame(after_g3))
    print(f" [3] + G3 RANGING-LONG block    n={n_final:>4}  WR={wr_final:5.1f}%  E[R]={avg_r_final:+.3f}  total_R={tot_final:+7.1f}")

    # Delta summary
    n0, wr0, _, tot0 = wr_stats(df)
    section("GATE IMPACT SUMMARY")
    print(f"  Trades cut:        {n0 - n_final}  ({(n0 - n_final) / n0 * 100:.1f}%)")
    print(f"  WR improvement:    {wr0:.1f}% → {wr_final:.1f}%  ({wr_final - wr0:+.1f}pp)")
    print(f"  E[R] improvement:  {tot0/n0:+.3f} → {avg_r_final:+.3f}  ({avg_r_final - tot0/n0:+.3f})")
    print(f"  Bleed prevented:   {tot0 - tot_final:+.1f}R of drag removed")

    after_df = pd.DataFrame(after_g3)

    # Side breakdown
    section("SIDE BREAKDOWN AFTER ALL GATES")
    if after_df.empty:
        print("  (no trades survive)")
    else:
        for side in ["LONG", "SHORT"]:
            sub = after_df[after_df["side"] == side]
            n, wr, avg_r, tot = wr_stats(sub)
            print(f"  {side:<6}  n={n:>4}  WR={wr:5.1f}%  E[R]={avg_r:+.3f}  total_R={tot:+7.1f}")

    # Surviving pockets
    section("SURVIVING POCKETS (min n=3, sorted by total_R)")
    if after_df.empty:
        print("  (no trades survive)")
    else:
        pockets = []
        for key, sub in after_df.groupby(["regime", "family", "side"]):
            n, wr, avg_r, tot = wr_stats(sub)
            if n >= 3:
                pockets.append((*key, n, wr, avg_r, tot))
        pockets.sort(key=lambda x: x[6], reverse=True)
        print(f"  {'Regime':<18} {'Family':<16} {'Side':<6} {'N':>4} {'WR%':>7} {'E[R]':>7} {'tot_R':>7}")
        print(f"  {'─'*18} {'─'*16} {'─'*6} {'─'*4} {'─'*7} {'─'*7} {'─'*7}")
        for regime, family, side, n, wr, avg_r, tot in pockets:
            print(f"  {str(regime)[:18]:<18} {str(family)[:16]:<16} {side:<6} {n:>4} {wr:>6.1f}% {avg_r:>+7.3f} {tot:>+7.1f}")

    # Rejection breakdown
    section("REJECTION BREAKDOWN (why trades were blocked)")
    rejected_by = {}
    for r in baseline:
        ok, reason = apply_gates(r)
        if not ok:
            rejected_by[reason] = rejected_by.get(reason, 0) + 1
    for reason, cnt in sorted(rejected_by.items(), key=lambda x: -x[1]):
        pct = cnt / len(baseline) * 100
        print(f"  {reason:<28} {cnt:>4} blocked  ({pct:>5.1f}% of baseline)")

    # Verdict on whether gates alone flip the system
    section("VERDICT")
    if tot_final > 0:
        print("  🔥 Gates alone make the system profitable. Ship them.")
    elif avg_r_final > -0.1:
        positive_pockets = sum(1 for p in pockets if p[6] > 0) if not after_df.empty else 0
        print(f"  Gates recover most of the bleed but system still breakeven/negative.")
        print(f"  Profitable pockets (n≥3): {positive_pockets}")
        print(f"  Next lever: run idim_mfe_mae.py to find if exit-policy tuning closes the gap.")
    else:
        print(f"  Gates reduce bleed significantly but system still structurally unprofitable.")
        print(f"  The R:R ceiling (+0.60/-1.00) is the binding constraint.")
        print(f"  Run idim_mfe_mae.py to measure true excursion before choosing TP/SL policy.")


# ─────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="ISO date lower bound, e.g. 2026-04-10")
    args = ap.parse_args()

    df = load_signals(since=args.since)
    if df.empty:
        print("No closed trades found. Check DATABASE_URL and date filter.")
        sys.exit(1)
    print(f"🜂 Loaded {len(df)} closed trades from `{TABLE}`.")
    replay(df)
