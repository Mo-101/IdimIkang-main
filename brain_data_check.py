#!/usr/bin/env python3
"""
Selection Brain — Data Sufficiency Check
Run BEFORE building the brain to see which context cells have enough data.
  observer_bundle/.venv/bin/python brain_data_check.py

Three-tier trust model (per Code Conduit discipline):
  n >= 10  → VISIBLE    (observe only — do not act alone)
  n >= 20  → WEAK       (weak ranking influence — shrink toward parent)
  n >= 30  → TRUSTED    (full decision weight — no shrinkage needed)

Shrinkage rule:
  L2 (regime×side×family) falls back toward L1 (regime×side)
  unless L2 cell n >= 30 (TRUSTED).
"""
import psycopg2
from datetime import datetime, timezone

DB_URL = "postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang"

N_VISIBLE = 10
N_WEAK    = 20
N_TRUSTED = 30

def trust_label(n):
    if n >= N_TRUSTED: return "✅ TRUSTED"
    if n >= N_WEAK:    return "🔶 WEAK   "
    if n >= N_VISIBLE: return "👁  VISIBLE"
    return f"❌ thin({n})"

def expectancy(wr_frac, avg_win, avg_loss_abs):
    """E[R] = P(win)*avg_win_R - P(loss)*avg_loss_R"""
    if avg_win is None or avg_loss_abs is None:
        return None
    return wr_frac * float(avg_win) - (1 - wr_frac) * abs(float(avg_loss_abs))


def run():
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()
    now  = datetime.now(timezone.utc)

    print("=" * 68)
    print("  SELECTION BRAIN — DATA SUFFICIENCY CHECK")
    print(f"  {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print("  Trust tiers:  ✅ TRUSTED n≥30 | 🔶 WEAK n≥20 | 👁 VISIBLE n≥10")
    print("=" * 68)

    cur.execute("SELECT COUNT(*) FROM signals WHERE outcome IS NOT NULL")
    total = cur.fetchone()[0]
    print(f"\n  Resolved signals in database: {total}")

    # ─── LEVEL 1: regime × side ──────────────────────────────────
    print("\n" + "─"*68)
    print("  L1 — P(win | regime, side)   [guaranteed base layer]")
    print("─"*68)
    cur.execute("""
        SELECT
            COALESCE(market_regime, regime, 'unknown') AS reg,
            side,
            COUNT(*) AS n,
            ROUND(AVG(CASE WHEN outcome ILIKE '%win%' THEN 1.0 ELSE 0.0 END)*100, 1) AS wr_pct,
            AVG(CASE WHEN outcome ILIKE '%win%' THEN r_multiple END)      AS avg_win_r,
            AVG(CASE WHEN outcome ILIKE '%loss%' THEN r_multiple END)     AS avg_loss_r,
            ROUND(AVG(r_multiple)::numeric, 3)                            AS avg_r
        FROM (
            SELECT COALESCE(market_regime, regime, 'unknown') AS market_regime,
                   regime, side, outcome, r_multiple
            FROM signals WHERE outcome IS NOT NULL
        ) s
        GROUP BY 1, 2
        ORDER BY n DESC
    """)
    l1_rows = cur.fetchall()
    # Build lookup dict for shrinkage fallback
    l1_lookup = {}
    print(f"  {'Regime':<22} {'Side':<6} {'N':>4} {'WR%':>6} {'AvgR':>7} {'Exp':>7}  Trust")
    print(f"  {'-'*22} {'-'*6} {'-'*4} {'-'*6} {'-'*7} {'-'*7}  {'─'*10}")
    for reg, side, n, wr, aw, al, avg_r in l1_rows:
        wr_f  = float(wr or 0) / 100
        exp   = expectancy(wr_f, aw, al)
        exp_s = f"{exp:+.3f}" if exp is not None else "   n/a"
        ar_s  = f"{float(avg_r):.3f}" if avg_r is not None else "  n/a"
        tl    = trust_label(n)
        print(f"  {str(reg):<22} {str(side):<6} {n:>4} {float(wr or 0):>5.1f}% {ar_s:>7} {exp_s:>7}  {tl}")
        if n >= N_VISIBLE:
            l1_lookup[(reg, side)] = {"n": n, "wr": wr_f, "exp": exp, "avg_r": float(avg_r or 0)}

    # ─── LEVEL 2: regime × side × family ────────────────────────
    print("\n" + "─"*68)
    print("  L2 — P(win | regime, side, family)   [family promoted only if n≥10]")
    print("  Shrinkage: cells <30 show blended expectancy ← parent L1")
    print("─"*68)
    cur.execute("""
        SELECT
            reg, side, family, n, wr_pct, avg_win_r, avg_loss_r, avg_r
        FROM (
            SELECT
                COALESCE(market_regime, regime, 'unknown') AS reg,
                side,
                COALESCE(signal_family, 'unknown') AS family,
                COUNT(*) AS n,
                ROUND(AVG(CASE WHEN outcome ILIKE '%win%' THEN 1.0 ELSE 0.0 END)*100, 1) AS wr_pct,
                AVG(CASE WHEN outcome ILIKE '%win%' THEN r_multiple END)  AS avg_win_r,
                AVG(CASE WHEN outcome ILIKE '%loss%' THEN r_multiple END) AS avg_loss_r,
                ROUND(AVG(r_multiple)::numeric, 3) AS avg_r
            FROM signals
            WHERE outcome IS NOT NULL
            GROUP BY 1, 2, 3
        ) sub
        ORDER BY n DESC
    """)
    l2_rows = cur.fetchall()

    trusted_l2 = []
    positive_l2 = []
    print(f"  {'Regime':<22} {'Side':<5} {'Family':<14} {'N':>4} {'WR%':>6} {'Exp(own)':>9} {'Exp(blend)':>11}  Trust")
    print(f"  {'-'*22} {'-'*5} {'-'*14} {'-'*4} {'-'*6} {'-'*9} {'-'*11}  {'─'*10}")

    for reg, side, fam, n, wr, aw, al, avg_r in l2_rows:
        if n < N_VISIBLE:
            continue  # too thin to even show
        wr_f    = float(wr or 0) / 100
        exp_own = expectancy(wr_f, aw, al)
        tl      = trust_label(n)

        # Shrinkage blending: thin cells pull toward L1 parent
        parent  = l1_lookup.get((reg, side))
        if parent and n < N_TRUSTED:
            # Weight: own=(n/30), parent=(1-n/30)
            w_own    = min(n / N_TRUSTED, 1.0)
            w_parent = 1.0 - w_own
            exp_blend = (
                w_own    * (exp_own or 0) +
                w_parent * (parent["exp"] or 0)
            ) if exp_own is not None else parent["exp"]
        else:
            exp_blend = exp_own

        exp_own_s   = f"{exp_own:+.3f}"   if exp_own   is not None else "    n/a"
        exp_blend_s = f"{exp_blend:+.3f}" if exp_blend is not None else "    n/a"
        ar_s = f"{float(avg_r):.3f}" if avg_r is not None else "  n/a"

        print(f"  {str(reg):<22} {str(side):<5} {str(fam):<14} {n:>4} {float(wr or 0):>5.1f}% "
              f"{exp_own_s:>9} {exp_blend_s:>11}  {tl}")

        entry = (reg, side, fam, n, float(wr or 0), exp_own, exp_blend)
        if n >= N_VISIBLE:
            trusted_l2.append(entry)
        if exp_blend is not None and exp_blend > 0:
            positive_l2.append(entry)

    # ─── LEVEL 3: hour-of-day density ───────────────────────────
    print("\n" + "─"*68)
    print("  L3 — Hour-of-day density   [not actionable yet — observation only]")
    print("─"*68)
    cur.execute("""
        SELECT signal_hour_utc, COUNT(*) AS n
        FROM signals
        WHERE outcome IS NOT NULL AND signal_hour_utc IS NOT NULL
        GROUP BY 1 ORDER BY n DESC
    """)
    hour_rows = cur.fetchall()
    trusted_hours = [(h, n) for h, n in hour_rows if n >= N_TRUSTED]
    for h, n in hour_rows:
        tl = trust_label(n)
        print(f"  UTC h={int(h or 0):02d}  n={n:>4}  {tl}")
    print(f"\n  Hours at TRUSTED level (n≥{N_TRUSTED}): {len(trusted_hours)}")

    # ─── RECOMMENDATION ─────────────────────────────────────────
    print("\n" + "="*68)
    print("  SELECTION BRAIN BUILD RECOMMENDATION")
    print("="*68)

    l1_trusted  = [r for r in l1_lookup.values() if r["n"] >= N_TRUSTED]
    l1_positive = [(k, v) for k, v in l1_lookup.items()
                   if v.get("exp") is not None and v["exp"] > 0 and v["n"] >= N_VISIBLE]
    l2_pos_trusted = [r for r in positive_l2 if r[3] >= N_TRUSTED]

    print(f"\n  L1 cells at TRUSTED level          : {len(l1_trusted)}")
    print(f"  L1 cells with positive expectancy  : {len(l1_positive)}")
    print(f"  L2 cells with positive exp (blended): {len(positive_l2)}")
    print(f"  L2 cells TRUSTED + positive exp    : {len(l2_pos_trusted)}")

    print("\n  ── POSITIVE EXPECTANCY (L1) ──")
    if l1_positive:
        for (reg, side), v in sorted(l1_positive, key=lambda x: -x[1]["exp"]):
            print(f"    {trust_label(v['n'])}  {reg:<22} {side:<6}  "
                  f"WR={v['wr']*100:.1f}%  Exp={v['exp']:+.3f}R  n={v['n']}")
    else:
        print("    ⚠️  None. System is currently net-negative across all regime×side cells.")

    print("\n  ── POSITIVE EXPECTANCY (L2, blended) ──")
    if positive_l2:
        for reg, side, fam, n, wr, exp_own, exp_blend in sorted(positive_l2, key=lambda x: -(x[6] or 0)):
            print(f"    {trust_label(n)}  {reg:<22} {side:<5} {fam:<14}  "
                  f"Exp(blend)={exp_blend:+.3f}R  n={n}")
    else:
        print("    ⚠️  None with positive blended expectancy.")

    print("\n  ── BRAIN BUILD DECISION ──")
    if len(l2_pos_trusted) >= 2:
        print("  ✅ BUILD L2 BRAIN now.")
        print("     Multiple TRUSTED cells with positive expectancy.")
        print("     Use: regime × side, promote family where n≥30.")
        print("     Shrink family cells n<30 toward parent L1.")
    elif len(l1_positive) >= 2:
        print("  🔶 BUILD L1 BRAIN (regime × side only).")
        print("     Some positive-expectancy L1 cells exist.")
        print("     Collect 2-4 more weeks before promoting family dimension.")
    else:
        print("  ❌ NOT READY. No reliable positive-expectancy cells found.")
        print("     Continue collection. The doctrine is working — the data isn't mature.")
        print("     Target: 500+ resolved signals before re-evaluating.")

    print()
    conn.close()


if __name__ == "__main__":
    run()
