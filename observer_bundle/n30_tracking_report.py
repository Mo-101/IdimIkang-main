#!/usr/bin/env python3
import os
import math
from datetime import datetime
from typing import Optional

import pandas as pd

# DB adapter:
# - PostgreSQL: pip install psycopg[binary] pandas
# - SQLite: built-in sqlite3 works automatically if DATABASE_URL starts with sqlite:///
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# ---- EDIT THIS QUERY TO MATCH YOUR SCHEMA ----
# Required output columns from the query:
#   trade_id, pair, side, regime, entry_ts, exit_ts
# And either:
#   pnl_r
# Or:
#   entry_price, stop_price, exit_price
#
# Default for this project (`signals` table updated by outcome_tracker):
SQL_QUERY = """
SELECT
    id AS trade_id,
    pair,
    side,
    COALESCE(regime, 'UNKNOWN') AS regime,
    ts AS entry_ts,
    COALESCE(updated_at, ts) AS exit_ts,
    r_multiple AS pnl_r,
    NULL::numeric AS pnl_usd
FROM signals
WHERE outcome IS NOT NULL
ORDER BY COALESCE(updated_at, ts) ASC
"""
# ----------------------------------------------

OUT_DIR = os.getenv("N30_REPORT_DIR", "/tmp")
N_TARGET = int(os.getenv("N30_TARGET", "30"))


def _connect():
    if DATABASE_URL.startswith("sqlite:///"):
        import sqlite3
        path = DATABASE_URL.replace("sqlite:///", "", 1)
        return sqlite3.connect(path)

    # postgres / postgresql
    try:
        import psycopg
        return psycopg.connect(DATABASE_URL)
    except Exception:
        try:
            import psycopg2
            return psycopg2.connect(DATABASE_URL)
        except Exception as e:
            raise RuntimeError(
                "Could not connect to DB. Set DATABASE_URL. "
                "For PostgreSQL install psycopg[binary] or psycopg2-binary."
            ) from e


def load_trades() -> pd.DataFrame:
    conn = _connect()
    try:
        df = pd.read_sql(SQL_QUERY, conn)
    finally:
        conn.close()

    if df.empty:
        return df

    for col in ["entry_ts", "exit_ts"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

    if "pnl_r" not in df.columns:
        needed = {"entry_price", "stop_price", "exit_price", "side"}
        missing = needed - set(df.columns)
        if missing:
            raise RuntimeError(
                f"Query must return pnl_r or enough fields to compute it. Missing: {sorted(missing)}"
            )
        df["pnl_r"] = df.apply(compute_r_multiple, axis=1)

    if "pnl_usd" not in df.columns:
        df["pnl_usd"] = pd.NA

    df["regime"] = df["regime"].fillna("UNKNOWN").astype(str)
    df["side"] = df["side"].fillna("UNKNOWN").astype(str).str.upper()
    df = df.sort_values("exit_ts").reset_index(drop=True)
    return df


def compute_r_multiple(row: pd.Series) -> Optional[float]:
    try:
        entry = float(row["entry_price"])
        stop = float(row["stop_price"])
        exit_ = float(row["exit_price"])
        side = str(row["side"]).upper()

        risk = abs(entry - stop)
        if risk <= 0:
            return None

        if side == "LONG":
            return (exit_ - entry) / risk
        if side == "SHORT":
            return (entry - exit_) / risk
        return None
    except Exception:
        return None


def safe_div(a: float, b: float) -> float:
    return 0.0 if b == 0 else a / b


def profit_factor(r: pd.Series) -> float:
    gross_win = r[r > 0].sum()
    gross_loss = -r[r < 0].sum()
    if gross_loss == 0:
        return float("inf") if gross_win > 0 else 0.0
    return gross_win / gross_loss


def max_drawdown_r(r: pd.Series) -> float:
    equity = r.fillna(0).cumsum()
    peak = equity.cummax()
    dd = equity - peak
    return float(dd.min()) if len(dd) else 0.0


def streaks(outcomes: pd.Series) -> tuple[int, int, int, int]:
    # returns: current_win_streak, current_loss_streak, max_win_streak, max_loss_streak
    cur_w = cur_l = max_w = max_l = 0
    for x in outcomes:
        if x > 0:
            cur_w += 1
            cur_l = 0
        elif x < 0:
            cur_l += 1
            cur_w = 0
        else:
            cur_w = 0
            cur_l = 0
        max_w = max(max_w, cur_w)
        max_l = max(max_l, cur_l)

    # recompute current streak from end
    tail_w = tail_l = 0
    for x in reversed(list(outcomes)):
        if x > 0 and tail_l == 0:
            tail_w += 1
        elif x < 0 and tail_w == 0:
            tail_l += 1
        else:
            break
    return tail_w, tail_l, max_w, max_l


def summarize(df: pd.DataFrame, label: str) -> dict:
    r = df["pnl_r"].dropna().astype(float)
    wins = (r > 0).sum()
    losses = (r < 0).sum()
    breakeven = (r == 0).sum()
    total = len(r)

    wr = safe_div(wins, total)
    avg_r = r.mean() if total else 0.0
    med_r = r.median() if total else 0.0
    pf = profit_factor(r) if total else 0.0
    exp_r = avg_r
    dd_r = max_drawdown_r(r) if total else 0.0
    cur_w, cur_l, max_w, max_l = streaks(r)

    return {
        "label": label,
        "closed_trades": int(total),
        "wins": int(wins),
        "losses": int(losses),
        "breakeven": int(breakeven),
        "wr": float(wr),
        "pf": float(pf),
        "avg_r": float(avg_r),
        "median_r": float(med_r),
        "expectancy_r": float(exp_r),
        "max_drawdown_r": float(dd_r),
        "current_win_streak": int(cur_w),
        "current_loss_streak": int(cur_l),
        "max_win_streak": int(max_w),
        "max_loss_streak": int(max_l),
    }


def print_summary(summary: dict):
    pf = "inf" if math.isinf(summary["pf"]) else f"{summary['pf']:.2f}"
    print(
        f"[{summary['label']}] "
        f"closed={summary['closed_trades']} "
        f"W={summary['wins']} L={summary['losses']} BE={summary['breakeven']} "
        f"WR={summary['wr']*100:.1f}% PF={pf} "
        f"avgR={summary['avg_r']:.3f} medR={summary['median_r']:.3f} "
        f"expR={summary['expectancy_r']:.3f} "
        f"DD={summary['max_drawdown_r']:.3f}R "
        f"curW={summary['current_win_streak']} curL={summary['current_loss_streak']} "
        f"maxW={summary['max_win_streak']} maxL={summary['max_loss_streak']}"
    )


def main():
    df = load_trades()
    if df.empty:
        print("No closed trades found.")
        return

    latest_n = df.tail(N_TARGET).copy()

    # Main summaries
    all_summary = summarize(df, "ALL_CLOSED")
    n_summary = summarize(latest_n, f"LATEST_{N_TARGET}")

    print_summary(all_summary)
    print_summary(n_summary)

    # Per-regime split for latest N
    print("\n[PER-REGIME SPLIT]")
    regime_rows = []
    for regime, grp in latest_n.groupby("regime", dropna=False):
        s = summarize(grp, str(regime))
        regime_rows.append(s)
        print_summary(s)

    # Export CSVs
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    trades_csv = os.path.join(OUT_DIR, f"n30_closed_trades_{ts}.csv")
    regime_csv = os.path.join(OUT_DIR, f"n30_regime_report_{ts}.csv")
    summary_csv = os.path.join(OUT_DIR, f"n30_summary_{ts}.csv")

    latest_n.to_csv(trades_csv, index=False)
    pd.DataFrame(regime_rows).to_csv(regime_csv, index=False)
    pd.DataFrame([all_summary, n_summary]).to_csv(summary_csv, index=False)

    print("\n[EXPORTS]")
    print(trades_csv)
    print(regime_csv)
    print(summary_csv)


if __name__ == "__main__":
    main()
