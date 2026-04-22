#!/usr/bin/env python3
"""
Idim Ikang — Full Historical Data Review
From inception to today. Run with:
  observer_bundle/.venv/bin/python full_data_review.py
"""

import psycopg2
from datetime import datetime, timezone

DB_URL = "postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang"

SEP  = "=" * 65
SEP2 = "-" * 40

# ── Sprint D: Activation Cutoff ──────────────────────────────
# Only evaluate probability model performance on signals 
# emitted after the cutover to ensure clean calibration.
SPRINT_D_ACTIVATED_AT = "2026-04-18 20:20:00Z"

def pct(part, total):
    return f"{part/total*100:.1f}%" if total > 0 else "n/a"

def run():
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()
    now  = datetime.now(timezone.utc)

    print(SEP)
    print("  IDIM IKANG — ALL-TIME DATA REVIEW")
    print(f"  Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(SEP)

    # ── 1. INCEPTION DATE & TOTAL VOLUME ────────────────────────
    print("\n1. INCEPTION & TOTAL VOLUME")
    print(SEP2)
    cur.execute("""
        SELECT
            MIN(created_at)   AS inception,
            MAX(created_at)   AS latest,
            COUNT(*)          AS total_rows,
            COUNT(DISTINCT symbol) AS unique_symbols,
            COUNT(DISTINCT DATE(created_at)) AS active_days
        FROM training_candidates
    """)
    r = cur.fetchone()
    inception, latest, total_rows, unique_syms, active_days = r
    if inception:
        span_hours = (latest - inception).total_seconds() / 3600
        rate = total_rows / span_hours if span_hours > 0 else 0
        print(f"  Inception       : {inception.strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"  Latest record   : {latest.strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"  Active days     : {active_days}")
        print(f"  Span            : {span_hours:.1f} hours")
        print(f"  Total rows      : {total_rows:,}")
        print(f"  Unique symbols  : {unique_syms}")
        print(f"  Avg rate        : {rate:.0f} rows/hour  (~{rate/12:.0f} rows/cycle)")
    else:
        print("  ⚠  No training_candidates rows found yet.")

    # ── 2. DATASET MILESTONES ───────────────────────────────────
    print("\n2. DATASET MILESTONES")
    print(SEP2)
    cur.execute("SELECT COUNT(*) FROM training_candidates")
    total = cur.fetchone()[0]
    for milestone in [200, 500, 1000, 2000, 5000, 10000]:
        status = "✅ REACHED" if total >= milestone else f"⏳ {milestone - total:,} to go"
        print(f"  {milestone:>6,} rows  →  {status}")

    # ── 3. DAILY BREAKDOWN ──────────────────────────────────────
    print("\n3. DAILY BREAKDOWN")
    print(SEP2)
    cur.execute("""
        SELECT
            DATE(created_at)  AS day,
            COUNT(*)          AS rows,
            COUNT(DISTINCT symbol) AS symbols,
            SUM(CASE WHEN would_have_passed_live THEN 1 ELSE 0 END) AS passed,
            SUM(CASE WHEN rejection_gate IS NULL AND NOT would_have_passed_live THEN 1 ELSE 0 END) AS no_gate
        FROM training_candidates
        GROUP BY day
        ORDER BY day
    """)
    rows = cur.fetchall()
    if rows:
        print(f"  {'Date':<12} {'Rows':>7} {'Syms':>5} {'Passed':>7} {'Cycles~':>8}")
        print(f"  {'-'*12} {'-'*7} {'-'*5} {'-'*7} {'-'*8}")
        for day, cnt, syms, passed, _ in rows:
            cycles = cnt // 60
            print(f"  {str(day):<12} {cnt:>7,} {syms:>5} {passed:>7} {cycles:>8}")
    else:
        print("  No data.")

    # ── 4. REJECTION GATE ANALYSIS (ALL TIME) ──────────────────
    print("\n4. REJECTION GATE ANALYSIS — ALL TIME")
    print(SEP2)
    cur.execute("""
        SELECT
            COALESCE(rejection_gate, 'PASSED') AS gate,
            COUNT(*) AS cnt,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) AS pct
        FROM training_candidates
        GROUP BY gate
        ORDER BY cnt DESC
    """)
    rows = cur.fetchall()
    for gate, cnt, p in rows:
        bar = "█" * int(p / 2)
        print(f"  {gate:<30} {cnt:>7,} ({p:>5.1f}%)  {bar}")

    # ── 5. SIGNAL FAMILY DISTRIBUTION ──────────────────────────
    print("\n5. SIGNAL FAMILY DISTRIBUTION — ALL TIME")
    print(SEP2)
    cur.execute("""
        SELECT
            COALESCE(signal_family,'unknown') AS family,
            COUNT(*) AS cnt,
            SUM(CASE WHEN would_have_passed_live THEN 1 ELSE 0 END) AS passed,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) AS pct
        FROM training_candidates
        GROUP BY family
        ORDER BY cnt DESC
    """)
    rows = cur.fetchall()
    print(f"  {'Family':<16} {'Total':>7} {'Passed':>7} {'Share':>7}  {'PassRate':>9}")
    print(f"  {'-'*16} {'-'*7} {'-'*7} {'-'*7}  {'-'*9}")
    for fam, cnt, passed, p in rows:
        pr = pct(passed, cnt)
        print(f"  {fam:<16} {cnt:>7,} {passed:>7} {p:>6.1f}%  {pr:>9}")

    # ── 6. MARKET REGIME COVERAGE ──────────────────────────────
    print("\n6. MARKET REGIME COVERAGE — ALL TIME")
    print(SEP2)
    cur.execute("""
        SELECT
            COALESCE(regime,'unknown') AS regime,
            COUNT(*) AS cnt,
            SUM(CASE WHEN would_have_passed_live THEN 1 ELSE 0 END) AS passed,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) AS pct
        FROM training_candidates
        GROUP BY regime
        ORDER BY cnt DESC
    """)
    rows = cur.fetchall()
    for regime, cnt, passed, p in rows:
        pr = pct(passed, cnt)
        print(f"  {regime:<22} {cnt:>7,} ({p:>5.1f}%)  pass={pr}")

    # ── 7. TOP 15 SYMBOLS BY VOLUME ─────────────────────────────
    print("\n7. TOP 15 MOST OBSERVED SYMBOLS")
    print(SEP2)
    cur.execute("""
        SELECT symbol, COUNT(*) AS cnt,
               SUM(CASE WHEN would_have_passed_live THEN 1 ELSE 0 END) AS passed
        FROM training_candidates
        GROUP BY symbol
        ORDER BY cnt DESC
        LIMIT 15
    """)
    rows = cur.fetchall()
    print(f"  {'Symbol':<16} {'Rows':>7} {'Passed':>7} {'PassRate':>9}")
    print(f"  {'-'*16} {'-'*7} {'-'*7} {'-'*9}")
    for sym, cnt, passed in rows:
        pr = pct(passed, cnt)
        print(f"  {sym:<16} {cnt:>7,} {passed:>7} {pr:>9}")

    # ── 8. SIGNAL EMISSION RECORD ───────────────────────────────
    print("\n8. SIGNAL EMISSION RECORD (signals table)")
    print(SEP2)
    cur.execute("""
        SELECT
            COUNT(*)                                            AS total,
            COUNT(CASE WHEN outcome IS NOT NULL THEN 1 END)    AS resolved,
            COUNT(CASE WHEN outcome ILIKE '%win%' THEN 1 END)  AS wins,
            COUNT(CASE WHEN outcome ILIKE '%loss%' THEN 1 END) AS losses,
            ROUND(AVG(CASE WHEN outcome IS NOT NULL THEN r_multiple END)::numeric, 4) AS avg_r,
            MIN(ts)                                            AS first_signal,
            MAX(ts)                                            AS last_signal
        FROM signals
    """)
    r = cur.fetchone()
    total_sig, resolved, wins, losses, avg_r, first_sig, last_sig = r
    print(f"  Total signals emitted    : {total_sig:,}")
    if first_sig:
        print(f"  First signal             : {first_sig.strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"  Last signal              : {last_sig.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Resolved (outcome set)   : {resolved} ({pct(resolved, total_sig)})")
    print(f"  Wins                     : {wins}")
    print(f"  Losses                   : {losses}")
    wr = pct(wins, wins + losses) if (wins + losses) > 0 else "n/a"
    print(f"  Win rate                 : {wr}")
    print(f"  Avg R-multiple           : {avg_r if avg_r is not None else 'n/a'}")

    # ── 9. SIGNALS BY REGIME & SIDE ─────────────────────────────
    if total_sig > 0:
        print("\n9. EMITTED SIGNALS — REGIME × SIDE BREAKDOWN")
        print(SEP2)
        cur.execute("""
            SELECT
                regime_label,
                side,
                COUNT(*) AS cnt,
                COUNT(CASE WHEN outcome IS NOT NULL THEN 1 END) AS resolved,
                COUNT(CASE WHEN outcome ILIKE '%win%' THEN 1 END) AS wins,
                ROUND(AVG(CASE WHEN outcome IS NOT NULL THEN r_multiple END)::numeric, 4) AS avg_r
            FROM (
                SELECT
                    COALESCE(market_regime, regime, 'unknown') AS regime_label,
                    side, outcome, r_multiple
                FROM signals
            ) sub
            GROUP BY regime_label, side
            ORDER BY cnt DESC
        """)
        rows = cur.fetchall()
        print(f"  {'Regime':<22} {'Side':<6} {'Cnt':>5} {'Res':>5} {'Wins':>5} {'AvgR':>7}")
        print(f"  {'-'*22} {'-'*6} {'-'*5} {'-'*5} {'-'*5} {'-'*7}")
        for regime, side, cnt, res, wins_c, avg_r in rows:
            ar = f"{avg_r:.3f}" if avg_r is not None else "  n/a"
            print(f"  {regime:<22} {side:<6} {cnt:>5} {res:>5} {wins_c:>5} {ar:>7}")

    # ── 9b. HOUR OF DAY P&L ─────────────────────────────────────
    if total_sig > 0:
        print("\n9b. EMITTED SIGNALS — HOUR OF DAY P&L (UTC)")
        print(SEP2)
        cur.execute("""
            SELECT
                signal_hour_utc AS hour,
                COUNT(*) AS cnt,
                COUNT(CASE WHEN outcome ILIKE '%win%' THEN 1 END) AS wins,
                COUNT(CASE WHEN outcome ILIKE '%loss%' THEN 1 END) AS losses,
                ROUND(AVG(CASE WHEN outcome IS NOT NULL THEN r_multiple END)::numeric, 3) AS avg_r
            FROM signals
            WHERE outcome IS NOT NULL AND signal_hour_utc IS NOT NULL
            GROUP BY hour
            ORDER BY cnt DESC
        """)
        rows = cur.fetchall()
        print(f"  {'Hour(UTC)':<11} {'N':>4} {'Wins':>5} {'Loss':>5} {'WR%':>6} {'AvgR':>7}")
        print(f"  {'-'*11} {'-'*4} {'-'*5} {'-'*5} {'-'*6} {'-'*7}")
        for hour, cnt, wins_c, losses_c, avg_r in rows:
            wr_pct = f"{wins_c/cnt*100:.1f}%" if cnt > 0 else "n/a"
            ar = f"{avg_r:.3f}" if avg_r is not None else "  n/a"
            flag = " ← best" if avg_r and avg_r == max(r[4] for r in rows if r[4] is not None) else ""
            flag = " ← worst" if avg_r and avg_r == min(r[4] for r in rows if r[4] is not None) else flag
            print(f"  h={int(hour or 0):02d}:00-{int(hour or 0):02d}:59  {cnt:>4} {wins_c:>5} {losses_c:>5} {wr_pct:>6} {ar:>7}{flag}")

    # ── 9d. SOVEREIGN COHERENCE (ROLLING 200) ──────────────────
    if total_sig > 0:
        print("\n9d. SOVEREIGN COHERENCE — ROLLING 200 SIDE SHARE")
        print(SEP2)
        cur.execute("""
            SELECT
                COUNT(*) AS n,
                SUM(CASE WHEN side = 'LONG' THEN 1 ELSE 0 END) AS longs,
                SUM(CASE WHEN side = 'SHORT' THEN 1 ELSE 0 END) AS shorts
            FROM (
                SELECT side FROM signals ORDER BY ts DESC LIMIT 200
            ) sub
        """)
        n, ls, ss = cur.fetchone()
        if n > 0:
            l_pct = ls / n * 100
            s_pct = ss / n * 100
            delta_coh = abs(ls / n - 0.5)
            status = "✅ COHERENT" if 40 <= l_pct <= 60 else "⚠️ IMBALANCED"
            print(f"  Sample size       : {n}")
            print(f"  Long share        : {ls} ({l_pct:.1f}%)")
            print(f"  Short share       : {ss} ({s_pct:.1f}%)")
            print(f"  Δ_coherence       : {delta_coh:.3f}")
            print(f"  Status            : {status}")
        else:
            print("  No recent signals found.")

    # ── 9e. EXPECTANCY BY SIDE ─────────────────────────────────
    if total_sig > 0:
        print("\n9e. E[R | side] — EXPECTANCY BY SIDE")
        print(SEP2)
        cur.execute("""
            SELECT
                side,
                COUNT(*) AS trades,
                SUM(CASE WHEN outcome ILIKE '%win%' THEN 1 ELSE 0 END) AS wins,
                ROUND(AVG(CASE WHEN outcome IS NOT NULL THEN r_multiple END)::numeric, 4) AS avg_r
            FROM signals
            WHERE outcome IS NOT NULL
            GROUP BY side
            ORDER BY side
        """)
        rows = cur.fetchall()
        print(f"  {'Side':<6} {'Trades':>7} {'Wins':>6} {'WR%':>7} {'E[R]':>8}")
        print(f"  {'-'*6} {'-'*7} {'-'*6} {'-'*7} {'-'*8}")
        for side, trades, wins_c, avg_r in rows:
            wr = f"{wins_c/trades*100:.1f}%" if trades > 0 else "n/a"
            ar = f"{avg_r:.4f}" if avg_r is not None else "   n/a"
            print(f"  {side:<6} {trades:>7} {wins_c:>6} {wr:>7} {ar:>8}")

    # ── 9f. EXPECTANCY BY REGIME × SIDE ──────────────────────
    if total_sig > 0:
        print("\n9f. E[R | regime, side] — REGIME × SIDE EXPECTANCY")
        print(SEP2)
        cur.execute("""
            SELECT
                COALESCE(market_regime, regime, 'unknown') AS regime_label,
                side,
                COUNT(*) AS trades,
                SUM(CASE WHEN outcome ILIKE '%win%' THEN 1 ELSE 0 END) AS wins,
                ROUND(AVG(CASE WHEN outcome IS NOT NULL THEN r_multiple END)::numeric, 4) AS avg_r
            FROM signals
            WHERE outcome IS NOT NULL
            GROUP BY regime_label, side
            ORDER BY trades DESC
        """)
        rows = cur.fetchall()
        print(f"  {'Regime':<22} {'Side':<6} {'N':>4} {'WR%':>7} {'E[R]':>8}")
        print(f"  {'-'*22} {'-'*6} {'-'*4} {'-'*7} {'-'*8}")
        for regime_l, side, trades, wins_c, avg_r in rows:
            wr = f"{wins_c/trades*100:.1f}%" if trades > 0 else "n/a"
            ar = f"{avg_r:.4f}" if avg_r is not None else "   n/a"
            print(f"  {regime_l:<22} {side:<6} {trades:>4} {wr:>7} {ar:>8}")

    # ── 9g. P(emit short | downtrend) ────────────────────────
    if total_sig > 0:
        print("\n9g. P(emit short | downtrend)")
        print(SEP2)
        for r_label in ("DOWNTREND", "STRONG_DOWNTREND"):
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN side = 'SHORT' THEN 1 ELSE 0 END) AS shorts
                FROM signals
                WHERE COALESCE(market_regime, regime, 'unknown') = %s
            """, (r_label,))
            total_r, shorts_r = cur.fetchone()
            p_short = f"{shorts_r/total_r*100:.1f}%" if total_r > 0 else "n/a"
            print(f"  {r_label:<22} : {shorts_r}/{total_r} = {p_short}")

    # ── 9h. EXPECTANCY BY SHORT FAMILY (SPRINT B) ────────────
    if total_sig > 0:
        print("\n9h. E[R | short_family] — SPRINT B ALPHA")
        print(SEP2)
        cur.execute("""
            SELECT
                COALESCE(signal_family, 'legacy') AS family,
                COUNT(*) AS trades,
                SUM(CASE WHEN outcome ILIKE '%win%' THEN 1 ELSE 0 END) AS wins,
                ROUND(AVG(CASE WHEN outcome IS NOT NULL THEN r_multiple END)::numeric, 4) AS avg_r
            FROM signals
            WHERE side = 'SHORT'
              AND outcome IS NOT NULL
            GROUP BY family
            ORDER BY trades DESC
        """)
        rows = cur.fetchall()
        print(f"  {'Family':<20} {'Trades':>6} {'Wins':>6} {'WR%':>7} {'E[R]':>8}")
        print(f"  {'-'*20} {'-'*6} {'-'*6} {'-'*7} {'-'*8}")
        for fam, trades, wins_c, avg_r in rows:
            wr = f"{wins_c/trades*100:.1f}%" if trades > 0 else "n/a"
            ar = f"{avg_r:.4f}" if avg_r is not None else "   n/a"
            print(f"  {fam:<20} {trades:>6} {wins_c:>6} {wr:>7} {ar:>8}")


    # ── 9i. P(WIN) DECILE CALIBRATION ────────────────────────────
    print("\n9i. P(WIN) DECILE CALIBRATION (Post-Sprint D)")
    print(SEP2)
    cur.execute(f"""
        WITH base AS (
          SELECT
            pwin,
            outcome,
            r_multiple,
            NTILE(10) OVER (ORDER BY pwin) AS decile
          FROM signals
          WHERE outcome IS NOT NULL
            AND pwin IS NOT NULL
            AND ts >= '{SPRINT_D_ACTIVATED_AT}'
        )
        SELECT
          decile,
          COUNT(*) AS trades,
          ROUND(AVG(pwin)::numeric, 4) AS avg_pwin,
          ROUND(AVG(CASE WHEN UPPER(outcome) IN ('WIN','LIVE_WIN','PARTIAL_WIN','LIVE_PARTIAL') THEN 1.0 ELSE 0.0 END)::numeric, 4) AS realized_wr,
          ROUND(AVG(r_multiple)::numeric, 4) AS avg_r
        FROM base
        GROUP BY decile
        HAVING COUNT(*) >= 5 -- Sample guard
        ORDER BY decile;
    """)
    rows = cur.fetchall()
    if rows:
        print(f"  {'Decile':<6} {'Trades':>6} {'Exp P(win)':>11} {'Realized WR':>12} {'Avg R':>7}")
        print(f"  {'-'*6} {'-'*6} {'-'*11} {'-'*12} {'-'*7}")
        for d, t, ap, rw, ar in rows:
            print(f"  {d:<6} {t:>6} {ap:>11.4f} {rw:>11.2%} {ar:>7.3f}")
    else:
        print("  Insufficient post-Sprint D data for decile calibration (< 5 trades).")

    # ── 9j. PROB VS LEGACY DISCRIMINATION ──────────────────────────
    print("\n9j. PROB VS LEGACY DISCRIMINATION (Post-Sprint D)")
    print(SEP2)
    cur.execute(f"""
        WITH scored AS (
          SELECT
            prob_score,
            legacy_score,
            outcome,
            r_multiple,
            NTILE(5) OVER (ORDER BY prob_score) AS prob_quintile,
            NTILE(5) OVER (ORDER BY legacy_score) AS legacy_quintile
          FROM signals
          WHERE outcome IS NOT NULL
            AND prob_score IS NOT NULL
            AND legacy_score IS NOT NULL
            AND ts >= '{SPRINT_D_ACTIVATED_AT}'
        )
        SELECT
          'Prob Score' AS model,
          prob_quintile AS quintile,
          COUNT(*) AS trades,
          ROUND(AVG(CASE WHEN UPPER(outcome) IN ('WIN','LIVE_WIN','PARTIAL_WIN','LIVE_PARTIAL') THEN 1.0 ELSE 0.0 END)::numeric, 4) AS wr,
          ROUND(AVG(r_multiple)::numeric, 4) AS avg_r
        FROM scored
        GROUP BY prob_quintile
        HAVING COUNT(*) >= 3
        UNION ALL
        SELECT
          'Legacy Score' AS model,
          legacy_quintile AS quintile,
          COUNT(*) AS trades,
          ROUND(AVG(CASE WHEN UPPER(outcome) IN ('WIN','LIVE_WIN','PARTIAL_WIN','LIVE_PARTIAL') THEN 1.0 ELSE 0.0 END)::numeric, 4) AS wr,
          ROUND(AVG(r_multiple)::numeric, 4) AS avg_r
        FROM scored
        GROUP BY legacy_quintile
        HAVING COUNT(*) >= 3
        ORDER BY model, quintile;
    """)
    rows = cur.fetchall()
    if rows:
        print(f"  {'Model':<12} {'Quint':>5} {'Trades':>6} {'WR%':>7} {'Avg R':>7}")
        print(f"  {'-'*12} {'-'*5} {'-'*6} {'-'*7} {'-'*7}")
        for m, q, t, wr, ar in rows:
            print(f"  {m:<12} {q:>5} {t:>6} {wr*100:>6.1f}% {ar:>7.3f}")

    # ── 9k. CALIBRATION BY SIDE ──────────────────────────────────
    print("\n9k. CALIBRATION BY SIDE (Post-Sprint D)")
    print(SEP2)
    cur.execute(f"""
        WITH base AS (
          SELECT
            side,
            pwin,
            outcome,
            r_multiple,
            NTILE(3) OVER (PARTITION BY side ORDER BY pwin) AS tertile
          FROM signals
          WHERE outcome IS NOT NULL
            AND pwin IS NOT NULL
            AND ts >= '{SPRINT_D_ACTIVATED_AT}'
        )
        SELECT
          side,
          tertile,
          COUNT(*) AS trades,
          ROUND(AVG(pwin)::numeric, 4) AS avg_pwin,
          ROUND(AVG(CASE WHEN UPPER(outcome) IN ('WIN','LIVE_WIN','PARTIAL_WIN','LIVE_PARTIAL') THEN 1.0 ELSE 0.0 END)::numeric, 4) AS realized_wr
        FROM base
        GROUP BY side, tertile
        HAVING COUNT(*) >= 3
        ORDER BY side, tertile;
    """)
    rows = cur.fetchall()
    if rows:
        print(f"  {'Side':<6} {'Tert':>5} {'Trades':>7} {'Exp P(win)':>11} {'Realized WR':>11}")
        print(f"  {'-'*6} {'-'*5} {'-'*7} {'-'*11} {'-'*11}")
        for s, t, tr, ap, rw in rows:
            print(f"  {s:<6} {t:>5} {tr:>7} {ap:>11.4f} {rw:>11.2%}")

    # ── 9l. CALIBRATION BY REGIME × SIDE ──────────────────────────
    print("\n9l. CALIBRATION BY REGIME × SIDE (Post-Sprint D)")
    print(SEP2)
    cur.execute(f"""
        WITH base AS (
          SELECT
            COALESCE(market_regime, regime) AS regime,
            side,
            pwin,
            outcome,
            r_multiple,
            NTILE(3) OVER (PARTITION BY COALESCE(market_regime, regime), side ORDER BY pwin) AS tertile
          FROM signals
          WHERE outcome IS NOT NULL
            AND pwin IS NOT NULL
            AND ts >= '{SPRINT_D_ACTIVATED_AT}'
        )
        SELECT
          regime,
          side,
          tertile,
          COUNT(*) AS trades,
          ROUND(AVG(pwin)::numeric, 4) AS avg_pwin,
          ROUND(AVG(CASE WHEN UPPER(outcome) IN ('WIN','LIVE_WIN','PARTIAL_WIN','LIVE_PARTIAL') THEN 1.0 ELSE 0.0 END)::numeric, 4) AS realized_wr
        FROM base
        GROUP BY regime, side, tertile
        HAVING COUNT(*) >= 5
        ORDER BY regime, side, tertile;
    """)
    rows = cur.fetchall()
    if rows:
        print(f"  {'Regime':<18} {'Side':<5} {'Tert':>5} {'N':>3} {'ExpWR':>7} {'RealWR':>7}")
        print(f"  {'-'*18} {'-'*5} {'-'*5} {'-'*3} {'-'*7} {'-'*7}")
        for rg, sd, tr, cnt, ap, rw in rows:
            print(f"  {rg:<18} {sd:<5} {tr:>5} {cnt:>3} {ap*100:>6.1f}% {rw*100:>6.1f}%")

    # ── 9m. RISK SCALE VS EDGE ────────────────────────────────────
    print("\n9m. RISK SCALE VS EDGE (Conviction Check)")
    print(SEP2)
    cur.execute(f"""
        SELECT
          ROUND(risk_scale::numeric, 2) AS risk_scale_bucket,
          COUNT(*) AS trades,
          ROUND(AVG(pwin)::numeric, 4) AS avg_pwin,
          ROUND(AVG(CASE WHEN UPPER(outcome) IN ('WIN','LIVE_WIN','PARTIAL_WIN','LIVE_PARTIAL') THEN 1.0 ELSE 0.0 END)::numeric, 4) AS realized_wr,
          ROUND(AVG(r_multiple)::numeric, 4) AS avg_r
        FROM signals
        WHERE outcome IS NOT NULL
          AND risk_scale IS NOT NULL
          AND ts >= '{SPRINT_D_ACTIVATED_AT}'
        GROUP BY ROUND(risk_scale::numeric, 2)
        ORDER BY risk_scale_bucket;
    """)
    rows = cur.fetchall()
    if rows:
        print(f"  {'Scale':<6} {'Trades':>6} {'P(win)':>7} {'RealWR':>7} {'AvgR':>7}")
        print(f"  {'-'*6} {'-'*6} {'-'*7} {'-'*7} {'-'*7}")
        for sc, t, ap, rw, ar in rows:
            ap=float(ap or 0); rw=float(rw or 0); ar=float(ar or 0)
            print(f"  {sc:<6.2f} {t:>6} {ap:>7.2f} {rw*100:>6.1f}% {ar:>7.3f}")

    # ── 9n. FAMILY-AWARE R:R PERFORMANCE ─────────────────────────
    print("\n9n. FAMILY-AWARE R:R PERFORMANCE")
    print(SEP2)
    cur.execute(f"""
        SELECT
          signal_family,
          ROUND(AVG(rr_sl_mult)::numeric, 3) AS avg_sl_mult,
          ROUND(AVG(rr_tp_mult)::numeric, 3) AS avg_tp_mult,
          COUNT(*) AS trades,
          ROUND(AVG(CASE WHEN UPPER(outcome) IN ('WIN','LIVE_WIN','PARTIAL_WIN','LIVE_PARTIAL') THEN 1.0 ELSE 0.0 END)::numeric, 4) AS realized_wr,
          ROUND(AVG(r_multiple)::numeric, 4) AS avg_r
        FROM signals
        WHERE outcome IS NOT NULL
          AND rr_sl_mult IS NOT NULL
          AND rr_tp_mult IS NOT NULL
          AND ts >= '{SPRINT_D_ACTIVATED_AT}'
        GROUP BY signal_family
        ORDER BY trades DESC;
    """)
    rows = cur.fetchall()
    if rows:
        print(f"  {'Family':<16} {'SLx':>6} {'TPx':>6} {'N':>4} {'WR%':>6} {'AvgR':>7}")
        print(f"  {'-'*16} {'-'*6} {'-'*6} {'-'*4} {'-'*6} {'-'*7}")
        for fam, sl, tp, cnt, wr, ar in rows:
            print(f"  {str(fam):<16} {sl:>6.2f} {tp:>6.2f} {cnt:>4} {wr*100:>5.1f}% {ar:>7.3f}")

    # ── 10. SIGNAL FAMILY P&L ───────────────────────────────────
    if total_sig > 0:
        print("\n10. EMITTED SIGNALS — FAMILY P&L")
        print(SEP2)
        cur.execute("""
            SELECT
                COALESCE(signal_family,'unknown') AS family,
                COUNT(*) AS cnt,
                COUNT(CASE WHEN outcome ILIKE '%win%' THEN 1 END) AS wins,
                COUNT(CASE WHEN outcome ILIKE '%loss%' THEN 1 END) AS losses,
                ROUND(AVG(CASE WHEN outcome IS NOT NULL THEN r_multiple END)::numeric, 3) AS avg_r
            FROM signals
            GROUP BY family
            ORDER BY cnt DESC
        """)
        rows = cur.fetchall()
        print(f"  {'Family':<16} {'Cnt':>5} {'Wins':>5} {'Loss':>5} {'AvgR':>7}")
        print(f"  {'-'*16} {'-'*5} {'-'*5} {'-'*5} {'-'*7}")
        for fam, cnt, wins_c, losses_c, avg_r in rows:
            ar = f"{avg_r:.3f}" if avg_r is not None else "  n/a"
            print(f"  {fam:<16} {cnt:>5} {wins_c:>5} {losses_c:>5} {ar:>7}")

    # ── 11. CALIBRATION VIEW ────────────────────────────────────
    print("\n11. CALIBRATION VIEW (win rate & expectancy by context)")
    print(SEP2)
    cur.execute("""
        SELECT table_name FROM information_schema.views
        WHERE table_schema = 'public'
          AND table_name = 'signal_context_calibration'
    """)
    if cur.fetchone():
        cur.execute("""
            SELECT policy_version, market_regime, side, trades, wins,
                   win_rate_pct, avg_r, expectancy_r
            FROM signal_context_calibration
            WHERE trades > 0
            ORDER BY trades DESC
            LIMIT 20
        """)
        rows = cur.fetchall()
        if rows:
            print(f"  {'Policy':<22} {'Regime':<18} {'Side':<5} {'N':>4} {'WR%':>6} {'AvgR':>7} {'Exp':>7}")
            print(f"  {'-'*22} {'-'*18} {'-'*5} {'-'*4} {'-'*6} {'-'*7} {'-'*7}")
            for pv, mr, side, trades, wins_c, wr, ar, exp in rows:
                ar_s  = f"{ar:.3f}"  if ar  is not None else "  n/a"
                exp_s = f"{exp:.3f}" if exp is not None else "  n/a"
                print(f"  {str(pv):<22} {str(mr):<18} {str(side):<5} {trades:>4} {float(wr or 0):>5.1f}% {ar_s:>7} {exp_s:>7}")
        else:
            print("  No resolved signals in calibration view yet.")
    else:
        print("  Calibration view not found — run scanner once to create it.")

    # ── 12. COLLECTORS STATUS ───────────────────────────────────
    print("\n12. COLLECTOR DATA (funding / OI / LS ratios)")
    print(SEP2)

    for table, col, label, ts_col in [
        ("funding_rates",  "funding_rate", "Funding collector", "funding_time"),
        ("open_interest",  "open_interest", "OI collector      ", "timestamp"),
        ("ls_ratios",      "long_account_ratio", "LS ratio collector", "timestamp"),
    ]:
        try:
            cur.execute(f"""
                SELECT COUNT(*), MIN({ts_col}), MAX({ts_col})
                FROM {table}
            """)
            cnt, mn, mx = cur.fetchone()
            age = ""
            if mx:
                secs = (now - mx).total_seconds()
                age  = f"  last {int(secs//60)} min ago"
            print(f"  {label}: {cnt:,} rows  |  {mx.strftime('%H:%M UTC') if mx else 'no data'}{age}")
        except Exception:
            print(f"  {label}: table not found / no access")
        try:
            conn.rollback()
        except Exception:
            pass

    # ── SUMMARY ────────────────────────────────────────────────
    print("\n" + SEP)
    print("  SUMMARY")
    print(SEP2)
    print(f"  Training rows collected  : {total_rows:,}")
    print(f"  200-row milestone        : {'✅ REACHED' if total_rows >= 200 else f'⏳ {200 - total_rows} to go'}")
    print(f"  Signals emitted          : {total_sig:,}")
    if total_sig > 0 and (wins + losses) > 0:
        print(f"  Win rate (resolved)      : {pct(wins, wins+losses)}")
        print(f"  Avg R (resolved)         : {avg_r}")
    else:
        print(f"  Win/loss data            : no resolved outcomes yet")
    print(f"  Collectors               : funding / OI / LS active")
    print(SEP)

    cur.close()
    conn.close()

if __name__ == "__main__":
    run()
