"""
IDIM IKANG - Segmented Edge Diagnostic
River of Fire, where does the current actually flow?
"""
import os, sys, argparse
import pandas as pd
import numpy as np
from sqlalchemy import create_engine

pd.set_option("display.max_rows", 200)
pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 40)

DB = os.getenv("DATABASE_URL", "postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang")
TABLE = "signals"

def load(since=None):
    eng = create_engine(DB)
    where = ["outcome IN ('WIN','LOSS')"]
    if since:
        where.append(f"ts >= '{since}'")
    sql = f"""
        SELECT
            ts,
            pair,
            side,
            score,
            r_multiple AS r_mult,
            outcome,
            COALESCE(
                reason_trace->>'family_tag',
                signal_family,
                'NONE'
            ) AS family,
            COALESCE(market_regime, regime) AS regime,
            COALESCE(btc_regime, 'UNKNOWN') AS btc_reg,
            COALESCE(signal_hour_utc, EXTRACT(HOUR FROM ts)::int) AS hour,
            policy_version AS policy,
            COALESCE(risk_scale, 0.0) AS risk,
            'unknown' AS exec
        FROM {TABLE}
        WHERE {' AND '.join(where)}
        ORDER BY ts
    """
    df = pd.read_sql(sql, eng)

    df["family"] = df["family"].fillna("NONE").replace({"": "NONE", "none": "NONE"})
    df["regime"] = df["regime"].fillna("UNKNOWN")
    df["btc_reg"] = df["btc_reg"].fillna("UNKNOWN")
    df["side"] = df["side"].str.upper()
    df["r_mult"] = df["r_mult"].fillna(0.0).astype(float)
    df["risk"] = df["risk"].fillna(0.0).astype(float)
    df["score"] = df["score"].fillna(0.0).astype(float)
    df["hour"] = df["hour"].fillna(0).astype(int)
    return df

def edge(grp):
    n = len(grp)
    if n == 0:
        return pd.Series({"n": 0, "wr%": np.nan, "avg_r": np.nan, "total_r": 0.0})
    wins = (grp["outcome"] == "WIN").sum()
    wr = wins / n * 100
    avg_r = grp["r_mult"].mean()
    return pd.Series({
        "n":       n,
        "wr%":     round(wr, 1),
        "avg_r":   round(avg_r, 3),
        "total_r": round(n * avg_r, 2),
    })

def verdict(row):
    if row["n"] < 5:
        return "insufficient"
    if row["total_r"] > 2.0 and row["wr%"] >= 50:
        return "edge - protect"
    if row["total_r"] > 0:
        return "marginal"
    if row["avg_r"] > -0.3:
        return "slow bleed"
    return "KILL - block at source"

def section(title):
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")

def run(df):
    section("0. GLOBAL BASELINE")
    g = edge(df)
    print(g.to_string())

    section("1. SIDE SPLIT")
    print(df.groupby("side").apply(edge, include_groups=False).to_string())

    section("2. REGIME x FAMILY x SIDE — the pocket map (min n=5)")
    pockets = (df.groupby(["regime", "family", "side"], dropna=False)
                 .apply(edge, include_groups=False)
                 .reset_index())
    pockets = pockets[pockets["n"] >= 5].copy()
    pockets["verdict"] = pockets.apply(verdict, axis=1)
    pockets = pockets.sort_values("total_r", ascending=False)
    print(pockets.to_string(index=False))

    section("3. SCORE BUCKETS — does raising the floor save us?")
    df["score_bucket"] = pd.cut(df["score"],
        bins=[0, 40, 50, 55, 60, 100],
        labels=["<40", "40-49", "50-54", "55-59", "60+"])
    by_score = (df.groupby(["score_bucket", "side"], observed=True)
                  .apply(edge, include_groups=False)
                  .reset_index())
    print(by_score.to_string(index=False))

    section("4. NONE FAMILY ISOLATION — is it noise or signal?")
    none_fam = df[df["family"] == "NONE"]
    if len(none_fam) == 0:
        print("No NONE family trades. Skip.")
    else:
        print(f"Total NONE trades: {len(none_fam)}  ({len(none_fam)/len(df)*100:.1f}% of volume)")
        print((none_fam.groupby(["regime", "side"], dropna=False)
                       .apply(edge, include_groups=False)
                       .to_string()))

    section("5. BTC-MARKET REGIME ALIGNMENT — does agreement matter?")
    df["aligned"] = (df["regime"] == df["btc_reg"])
    print(df.groupby(["aligned", "side"]).apply(edge, include_groups=False).to_string())

    section("6. UTC HOUR BANDS — validate the graveyard zone")
    df["hour_band"] = pd.cut(df["hour"],
        bins=[-1, 5, 11, 17, 23],
        labels=["00-05 asia", "06-11 euro", "12-17 us-overlap", "18-23 evening"])
    print((df.groupby(["hour_band", "side"], observed=True)
             .apply(edge, include_groups=False)
             .to_string()))

    section("7. HOUR-BY-HOUR WIN RATE (side-agnostic)")
    hourly = df.groupby("hour").apply(edge, include_groups=False).reset_index()
    hourly["sparkline"] = hourly["wr%"].apply(
        lambda x: "|" * int(x / 5) if pd.notna(x) else ""
    )
    print(hourly.to_string(index=False))

    section("8. TOP 10 EDGE POCKETS")
    print(pockets.head(10).to_string(index=False))

    section("9. BOTTOM 10 BLEED POCKETS")
    print(pockets.tail(10).to_string(index=False))

    section("10. VERDICT SUMMARY")
    summary = pockets.groupby("verdict").agg(
        buckets=("n", "count"),
        trades=("n", "sum"),
        total_r=("total_r", "sum"),
    ).sort_values("total_r", ascending=False)
    print(summary.to_string())

    print("\nDiagnostic complete. The gates should match the map, not the theory.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="ISO date lower bound, e.g. 2026-04-10")
    args = ap.parse_args()
    df = load(since=args.since)
    print(f"Loaded {len(df)} closed trades from {TABLE}.")
    run(df)
