import psycopg2, psycopg2.extras
conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5432/idim_ikang")
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

cur.execute("""
  SELECT COALESCE(policy_version, 'legacy') as cohort,
         COUNT(*) as total,
         COUNT(*) FILTER (WHERE outcome='WIN') as wins,
         COUNT(*) FILTER (WHERE outcome='LOSS') as losses,
         COUNT(*) FILTER (WHERE outcome IS NULL) as open,
         ROUND(100.0 * COUNT(*) FILTER (WHERE outcome='WIN') / NULLIF(COUNT(*) FILTER (WHERE outcome IS NOT NULL), 0), 1) as wr,
         ROUND(AVG(r_multiple) FILTER (WHERE outcome IS NOT NULL), 3) as avg_r
  FROM signals GROUP BY COALESCE(policy_version, 'legacy') ORDER BY cohort
""")
print("=== COHORT BREAKDOWN ===")
for r in cur.fetchall():
    print(f"  {str(r['cohort']):40s} total={r['total']:3d}  W={r['wins']:2d}  L={r['losses']:2d}  open={r['open']:2d}  WR={r['wr'] or 0}%  avgR={r['avg_r'] or 'n/a'}")

cur.execute("""
  SELECT COALESCE(signal_family, 'none') as fam,
         COUNT(*) as total,
         COUNT(*) FILTER (WHERE outcome='WIN') as wins,
         COUNT(*) FILTER (WHERE outcome='LOSS') as losses,
         COUNT(*) FILTER (WHERE outcome IS NULL) as open,
         ROUND(100.0 * COUNT(*) FILTER (WHERE outcome='WIN') / NULLIF(COUNT(*) FILTER (WHERE outcome IS NOT NULL), 0), 1) as wr
  FROM signals WHERE policy_version LIKE '%familyfix%'
  GROUP BY COALESCE(signal_family, 'none') ORDER BY total DESC
""")
print("\n=== FAMILY (familyfix cohort) ===")
for r in cur.fetchall():
    print(f"  {r['fam']:20s} total={r['total']:3d}  W={r['wins']:2d}  L={r['losses']:2d}  open={r['open']:2d}  WR={r['wr'] or 0}%")

cur.execute("""
  SELECT ts, pair, side, score, COALESCE(signal_family,'none') as fam, outcome,
         ROUND(r_multiple::numeric, 2) as r_mult, policy_version
  FROM signals ORDER BY ts DESC LIMIT 10
""")
print("\n=== LATEST 10 SIGNALS ===")
for r in cur.fetchall():
    ts = r['ts'].strftime('%m/%d %H:%M')
    rm = f"{r['r_mult']:+.2f}R" if r['r_mult'] is not None else "  open"
    print(f"  {ts}  {r['pair']:12s} {r['side']:5s} sc={float(r['score']):4.0f}  fam={r['fam']:15s} {(r['outcome'] or 'OPEN'):8s} {rm}")

cur.close(); conn.close()
