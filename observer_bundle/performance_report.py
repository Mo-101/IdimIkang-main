#!/usr/bin/env python3
"""
Idim Ikang — Automated Performance Report
==========================================
Generates a cohort-based performance report from resolved signals.
Outputs: console summary + optional Telegram dispatch.

Usage:
    python performance_report.py                   # Full report
    python performance_report.py --burst-only      # Burst-period signals only
    python performance_report.py --telegram        # Also send to Telegram
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import dotenv

dotenv.load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

WIN_OUTCOMES = ("WIN", "LIVE_WIN", "PARTIAL_WIN", "LIVE_PARTIAL")
LOSS_OUTCOMES = ("LOSS", "LIVE_LOSS")


def _conn():
    return psycopg2.connect(DATABASE_URL)


def _run_query(sql: str, params: dict | None = None) -> list[dict]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or {})
            return [dict(r) for r in cur.fetchall()]


# ──────────────────────────────────────────────────────────────────────────────
# Report queries
# ──────────────────────────────────────────────────────────────────────────────

def summary_stats(policy_filter: str | None = None) -> dict:
    where = "WHERE outcome IS NOT NULL"
    if policy_filter:
        where += " AND policy_version = %(policy)s"
    rows = _run_query(f"""
        SELECT
            COUNT(*) AS total_trades,
            SUM(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN UPPER(outcome) IN {LOSS_OUTCOMES} THEN 1 ELSE 0 END) AS losses,
            SUM(CASE WHEN outcome = 'EXPIRED' THEN 1 ELSE 0 END) AS expired,
            ROUND(AVG(r_multiple)::numeric, 4) AS avg_r,
            ROUND(AVG(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN r_multiple END)::numeric, 4) AS avg_win_r,
            ROUND(ABS(AVG(CASE WHEN UPPER(outcome) IN {LOSS_OUTCOMES} THEN r_multiple END))::numeric, 4) AS avg_loss_r_abs,
            ROUND((
                COALESCE(AVG(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN r_multiple END), 0)
                * AVG(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN 1.0 ELSE 0.0 END)
                -
                COALESCE(ABS(AVG(CASE WHEN UPPER(outcome) IN {LOSS_OUTCOMES} THEN r_multiple END)), 0)
                * (1 - AVG(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN 1.0 ELSE 0.0 END))
            )::numeric, 4) AS expectancy_r,
            ROUND((AVG(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN 1.0 ELSE 0.0 END) * 100)::numeric, 1) AS win_rate_pct,
            MIN(ts) AS first_signal,
            MAX(ts) AS last_signal
        FROM signals
        {where}
    """, {"policy": policy_filter})
    return rows[0] if rows else {}


def regime_side_breakdown(policy_filter: str | None = None) -> list[dict]:
    where = "WHERE outcome IS NOT NULL"
    if policy_filter:
        where += " AND policy_version = %(policy)s"
    return _run_query(f"""
        SELECT
            COALESCE(market_regime, regime) AS regime,
            side,
            COUNT(*) AS trades,
            ROUND((AVG(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN 1.0 ELSE 0.0 END) * 100)::numeric, 1) AS win_rate_pct,
            ROUND(AVG(r_multiple)::numeric, 4) AS avg_r,
            ROUND((
                COALESCE(AVG(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN r_multiple END), 0)
                * AVG(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN 1.0 ELSE 0.0 END)
                -
                COALESCE(ABS(AVG(CASE WHEN UPPER(outcome) IN {LOSS_OUTCOMES} THEN r_multiple END)), 0)
                * (1 - AVG(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN 1.0 ELSE 0.0 END))
            )::numeric, 4) AS expectancy_r
        FROM signals
        {where}
        GROUP BY COALESCE(market_regime, regime), side
        ORDER BY expectancy_r DESC
    """, {"policy": policy_filter})


def hour_breakdown(policy_filter: str | None = None) -> list[dict]:
    where = "WHERE outcome IS NOT NULL AND signal_hour_utc IS NOT NULL"
    if policy_filter:
        where += " AND policy_version = %(policy)s"
    return _run_query(f"""
        SELECT
            signal_hour_utc AS hour_utc,
            COUNT(*) AS trades,
            ROUND((AVG(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN 1.0 ELSE 0.0 END) * 100)::numeric, 1) AS win_rate_pct,
            ROUND(AVG(r_multiple)::numeric, 4) AS avg_r,
            ROUND((
                COALESCE(AVG(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN r_multiple END), 0)
                * AVG(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN 1.0 ELSE 0.0 END)
                -
                COALESCE(ABS(AVG(CASE WHEN UPPER(outcome) IN {LOSS_OUTCOMES} THEN r_multiple END)), 0)
                * (1 - AVG(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN 1.0 ELSE 0.0 END))
            )::numeric, 4) AS expectancy_r
        FROM signals
        {where}
        GROUP BY signal_hour_utc
        ORDER BY expectancy_r DESC
    """, {"policy": policy_filter})


def family_breakdown(policy_filter: str | None = None) -> list[dict]:
    where = "WHERE outcome IS NOT NULL"
    if policy_filter:
        where += " AND policy_version = %(policy)s"
    return _run_query(f"""
        SELECT
            COALESCE(signal_family, reason_trace->>'signal_family', 'none') AS family,
            COUNT(*) AS trades,
            ROUND((AVG(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN 1.0 ELSE 0.0 END) * 100)::numeric, 1) AS win_rate_pct,
            ROUND(AVG(r_multiple)::numeric, 4) AS avg_r,
            ROUND((
                COALESCE(AVG(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN r_multiple END), 0)
                * AVG(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN 1.0 ELSE 0.0 END)
                -
                COALESCE(ABS(AVG(CASE WHEN UPPER(outcome) IN {LOSS_OUTCOMES} THEN r_multiple END)), 0)
                * (1 - AVG(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN 1.0 ELSE 0.0 END))
            )::numeric, 4) AS expectancy_r
        FROM signals
        {where}
        GROUP BY COALESCE(signal_family, reason_trace->>'signal_family', 'none')
        ORDER BY expectancy_r DESC
    """, {"policy": policy_filter})


def btc_regime_breakdown(policy_filter: str | None = None) -> list[dict]:
    where = "WHERE outcome IS NOT NULL AND btc_regime IS NOT NULL"
    if policy_filter:
        where += " AND policy_version = %(policy)s"
    return _run_query(f"""
        SELECT
            btc_regime,
            COUNT(*) AS trades,
            ROUND((AVG(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN 1.0 ELSE 0.0 END) * 100)::numeric, 1) AS win_rate_pct,
            ROUND(AVG(r_multiple)::numeric, 4) AS avg_r,
            ROUND((
                COALESCE(AVG(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN r_multiple END), 0)
                * AVG(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN 1.0 ELSE 0.0 END)
                -
                COALESCE(ABS(AVG(CASE WHEN UPPER(outcome) IN {LOSS_OUTCOMES} THEN r_multiple END)), 0)
                * (1 - AVG(CASE WHEN UPPER(outcome) IN {WIN_OUTCOMES} THEN 1.0 ELSE 0.0 END))
            )::numeric, 4) AS expectancy_r
        FROM signals
        {where}
        GROUP BY btc_regime
        ORDER BY expectancy_r DESC
    """, {"policy": policy_filter})


def burst_vs_strict() -> list[dict]:
    return _run_query(f"""
        SELECT * FROM burst_vs_strict_comparison
        ORDER BY cohort, expectancy_r DESC
    """)


def unresolved_signals() -> list[dict]:
    return _run_query("""
        SELECT pair, side, score,
               COALESCE(market_regime, regime) AS regime,
               signal_family, ts,
               EXTRACT(EPOCH FROM (NOW() - ts)) / 3600 AS hours_open
        FROM signals
        WHERE outcome IS NULL
        ORDER BY ts DESC
    """)


# ──────────────────────────────────────────────────────────────────────────────
# Formatters
# ──────────────────────────────────────────────────────────────────────────────

def _tbl(rows: list[dict], title: str = "") -> str:
    if not rows:
        return f"  {title}: (no data)\n"
    keys = list(rows[0].keys())
    widths = {k: max(len(k), max(len(str(r.get(k, ""))) for r in rows)) for k in keys}
    header = " | ".join(k.ljust(widths[k]) for k in keys)
    sep = "-+-".join("-" * widths[k] for k in keys)
    body = "\n".join(" | ".join(str(r.get(k, "")).ljust(widths[k]) for k in keys) for r in rows)
    out = ""
    if title:
        out += f"\n{'=' * 60}\n  {title}\n{'=' * 60}\n"
    return out + header + "\n" + sep + "\n" + body + "\n"


def _telegram_html(summary: dict, regime: list, hours: list, families: list, btc: list) -> str:
    s = summary
    lines = [
        "<b>IDIM-IKANG PERFORMANCE REPORT</b>",
        f"<pre>Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</pre>",
        "",
        "<b>SUMMARY</b>",
        f"Trades: {s.get('total_trades', 0)} | Wins: {s.get('wins', 0)} | Losses: {s.get('losses', 0)}",
        f"Win Rate: {s.get('win_rate_pct', 0)}% | Avg R: {s.get('avg_r', 0)}",
        f"<b>Expectancy: {s.get('expectancy_r', 0)}R</b>",
        f"Avg Win: {s.get('avg_win_r', 0)}R | Avg Loss: {s.get('avg_loss_r_abs', 0)}R",
        "",
    ]

    if regime:
        lines.append("<b>REGIME x SIDE</b>")
        for r in regime[:8]:
            lines.append(
                f"  {r['regime']} {r['side']}: {r['trades']}t "
                f"WR={r['win_rate_pct']}% E[R]={r['expectancy_r']}"
            )
        lines.append("")

    if families:
        lines.append("<b>FAMILY</b>")
        for f in families:
            lines.append(
                f"  {f['family']}: {f['trades']}t "
                f"WR={f['win_rate_pct']}% E[R]={f['expectancy_r']}"
            )
        lines.append("")

    if hours:
        best = hours[0] if hours else None
        worst = hours[-1] if hours else None
        lines.append("<b>BEST/WORST HOURS (UTC)</b>")
        if best:
            lines.append(f"  Best:  {best['hour_utc']}h — {best['trades']}t E[R]={best['expectancy_r']}")
        if worst:
            lines.append(f"  Worst: {worst['hour_utc']}h — {worst['trades']}t E[R]={worst['expectancy_r']}")
        lines.append("")

    if btc:
        lines.append("<b>BTC REGIME</b>")
        for b in btc:
            lines.append(
                f"  {b['btc_regime']}: {b['trades']}t "
                f"WR={b['win_rate_pct']}% E[R]={b['expectancy_r']}"
            )
        lines.append("")

    lines.append("<b>MoStar Industries</b> | <i>African Flame Initiative</i>")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Idim Ikang Performance Report")
    parser.add_argument("--burst-only", action="store_true", help="Filter to burst-period signals only")
    parser.add_argument("--telegram", action="store_true", help="Also send report to Telegram")
    parser.add_argument("--policy", type=str, default=None, help="Filter by specific policy_version")
    args = parser.parse_args()

    policy = args.policy
    if args.burst_only:
        policy = "phase2_data_burst_v1"

    label = f"policy={policy}" if policy else "ALL SIGNALS"
    print(f"\nIdim Ikang Performance Report — {label}")
    print(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # Summary
    s = summary_stats(policy)
    if not s or not s.get("total_trades"):
        print("\n  No resolved signals found for this filter.\n")
        # Still show unresolved
        unresolved = unresolved_signals()
        if unresolved:
            print(_tbl(unresolved, "OPEN SIGNALS (unresolved)"))
        return

    print(f"\n{'=' * 60}")
    print(f"  SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total Trades:   {s['total_trades']}")
    print(f"  Wins:           {s['wins']}")
    print(f"  Losses:         {s['losses']}")
    print(f"  Expired:        {s['expired']}")
    print(f"  Win Rate:       {s['win_rate_pct']}%")
    print(f"  Avg R:          {s['avg_r']}")
    print(f"  Avg Win R:      {s['avg_win_r']}")
    print(f"  Avg Loss R:     {s['avg_loss_r_abs']}")
    print(f"  EXPECTANCY:     {s['expectancy_r']}R")
    print(f"  Period:         {s['first_signal']} → {s['last_signal']}")

    # Breakdowns
    regime = regime_side_breakdown(policy)
    print(_tbl(regime, "REGIME x SIDE"))

    families = family_breakdown(policy)
    print(_tbl(families, "SIGNAL FAMILY"))

    hours = hour_breakdown(policy)
    print(_tbl(hours, "HOUR (UTC)"))

    btc = btc_regime_breakdown(policy)
    print(_tbl(btc, "BTC REGIME"))

    # Burst vs strict if no filter
    if not policy:
        bvs = burst_vs_strict()
        if bvs:
            print(_tbl(bvs, "BURST vs STRICT COHORT"))

    # Open signals
    unresolved = unresolved_signals()
    if unresolved:
        print(_tbl(unresolved, f"OPEN SIGNALS ({len(unresolved)} unresolved)"))

    # Telegram
    if args.telegram:
        try:
            from telegram_alerts import send_telegram_sync
            html_report = _telegram_html(s, regime, hours, families, btc)
            ok = send_telegram_sync(html_report, context="performance_report")
            if ok:
                print("\n  [OK] Report sent to Telegram.")
            else:
                print("\n  [WARN] Telegram delivery failed or disabled.")
        except Exception as e:
            print(f"\n  [ERROR] Telegram dispatch failed: {e}")


if __name__ == "__main__":
    main()
