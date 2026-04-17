import psycopg2, psycopg2.extras, os
conn = psycopg2.connect(os.environ.get("DATABASE_URL", "postgresql://postgres:IdimIkangLocal2026!@localhost:5432/idim_ikang"))
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# Cohort breakdown by policy_version
cur.execute("""
  SELECT policy_version, 
         COUNT(*) as total,
         COUNT(*) FILTER (WHERE outcome='WIN') as wins,
         COUNT(*) FILTER (WHERE outcome='LOSS') as losses,
         COUNT(*) FILTER (WHERE outcome IS NULL) as open,
         ROUND(100.0 * COUNT(*) FILTER (WHERE outcome='WIN') / NULLIF(COUNT(*) FILTER (WHERE outcome IS NOT NULL), 0), 1) as wr,
         ROUND(AVG(r_multiple) FILTER (WHERE outcome IS NOT NULL), 3) as avg_r
  FROM signals
  GROUP BY policy_version ORDER BY policy_version
""")
print("=== COHORT BREAKDOWN ===")
for r in cur.fetchall():
    print(f"  {r['policy_version']:40s} total={r['total']:3d}  W={r['wins']:2d}  L={r['losses']:2d}  open={r['open']:2d}  WR={r['wr'] or 0}%  avgR={r['avg_r'] or 'n/a'}")

# Signal family breakdown (post-fix only)
cur.execute("""
  SELECT signal_family,
         COUNT(*) as total,
         COUNT(*) FILTER (WHERE outcome='WIN') as wins,
         COUNT(*) FILTER (WHERE outcome='LOSS') as losses,
         COUNT(*) FILTER (WHERE outcome IS NULL) as open
  FROM signals
  WHERE policy_version LIKE '%familyfix%'
  GROUP BY signal_family ORDER BY total DESC
""")
print("\n=== FAMILY BREAKDOWN (post-fix cohort) ===")
for r in cur.fetchall():
    print(f"  {(r['signal_family'] or 'none'):20s} total={r['total']:3d}  W={r['wins']:2d}  L={r['losses']:2d}  open={r['open']:2d}")

# Recent signals
cur.execute("""
  SELECT ts, pair, side, score, signal_family, outcome, r_multiple, policy_version
  FROM signals ORDER BY ts DESC LIMIT 8
""")
print("\n=== LATEST 8 SIGNALS ===")
for r in cur.fetchall():
    ts = r['ts'].strftime('%m/%d %H:%M')
    rm = f"{r['r_multiple']:+.2f}R" if r['r_multiple'] else "open"
    print(f"  {ts}  {r['pair']:12s} {r['side']:5s} sc={r['score']:4.0f}  fam={r['signal_family'] or 'none':15s} {r['outcome'] or 'OPEN':8s} {rm}")

cur.close()
conn.close()
