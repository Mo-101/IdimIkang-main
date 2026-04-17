import psycopg2, os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

# Check distinct outcomes
cur.execute("SELECT DISTINCT outcome FROM signals WHERE outcome IS NOT NULL")
print('Distinct outcomes:', [r[0] for r in cur.fetchall()])
print()

# Overall WR
cur.execute("""
SELECT count(*) FILTER (WHERE outcome IS NOT NULL) resolved,
       count(*) FILTER (WHERE outcome='WIN') wins,
       count(*) FILTER (WHERE outcome='LOSS') losses,
       count(*) FILTER (WHERE outcome='PARTIAL') partials,
       round(100.0 * count(*) FILTER (WHERE outcome='WIN') / NULLIF(count(*) FILTER (WHERE outcome IN ('WIN','LOSS')),0), 2) wr,
       round(avg(r_multiple) FILTER (WHERE outcome IS NOT NULL)::numeric, 4) avg_r,
       round(sum(r_multiple) FILTER (WHERE outcome IS NOT NULL)::numeric, 4) sum_r,
       count(*) total
FROM signals
""")
r = cur.fetchone()
print(f'OVERALL: {r[7]} total | {r[0]} resolved | {r[1]}W/{r[2]}L/{r[3]}P | WR={r[4]}% | avg_R={r[5]} | sum_R={r[6]}')
print()

# By signal_family
print('--- BY SIGNAL_FAMILY ---')
cur.execute("""
SELECT COALESCE(signal_family,'?') fam,
       count(*) FILTER (WHERE outcome IN ('WIN','LOSS')) resolved,
       count(*) FILTER (WHERE outcome='WIN') w,
       count(*) FILTER (WHERE outcome='LOSS') l,
       round(100.0 * count(*) FILTER (WHERE outcome='WIN') / NULLIF(count(*) FILTER (WHERE outcome IN ('WIN','LOSS')),0), 2) wr,
       round(avg(r_multiple) FILTER (WHERE outcome IS NOT NULL)::numeric, 4) avg_r,
       round(sum(r_multiple) FILTER (WHERE outcome IS NOT NULL)::numeric, 4) sum_r
FROM signals GROUP BY 1 ORDER BY resolved DESC
""")
for r in cur.fetchall():
    print(f'  {str(r[0]):12s} | {r[1]:3d} resolved | {r[2]}W/{r[3]}L | WR={r[4]}% | avg_R={r[5]} | sum_R={r[6]}')
print()

# By regime
print('--- BY REGIME ---')
cur.execute("""
SELECT COALESCE(regime,'?') rg,
       count(*) FILTER (WHERE outcome IN ('WIN','LOSS')) resolved,
       count(*) FILTER (WHERE outcome='WIN') w,
       count(*) FILTER (WHERE outcome='LOSS') l,
       round(100.0 * count(*) FILTER (WHERE outcome='WIN') / NULLIF(count(*) FILTER (WHERE outcome IN ('WIN','LOSS')),0), 2) wr,
       round(avg(r_multiple) FILTER (WHERE outcome IS NOT NULL)::numeric, 4) avg_r,
       round(sum(r_multiple) FILTER (WHERE outcome IS NOT NULL)::numeric, 4) sum_r
FROM signals GROUP BY 1 ORDER BY resolved DESC
""")
for r in cur.fetchall():
    print(f'  {str(r[0]):20s} | {r[1]:3d} resolved | {r[2]}W/{r[3]}L | WR={r[4]}% | avg_R={r[5]} | sum_R={r[6]}')
print()

# By market_regime
print('--- BY MARKET_REGIME ---')
cur.execute("""
SELECT COALESCE(market_regime,'?') mr,
       count(*) FILTER (WHERE outcome IN ('WIN','LOSS')) resolved,
       count(*) FILTER (WHERE outcome='WIN') w,
       count(*) FILTER (WHERE outcome='LOSS') l,
       round(100.0 * count(*) FILTER (WHERE outcome='WIN') / NULLIF(count(*) FILTER (WHERE outcome IN ('WIN','LOSS')),0), 2) wr,
       round(avg(r_multiple) FILTER (WHERE outcome IS NOT NULL)::numeric, 4) avg_r
FROM signals GROUP BY 1 ORDER BY resolved DESC
""")
for r in cur.fetchall():
    print(f'  {str(r[0]):20s} | {r[1]:3d} resolved | {r[2]}W/{r[3]}L | WR={r[4]}% | avg_R={r[5]}')
print()

# FAMILY x REGIME cross
print('--- FAMILY x REGIME CROSS ---')
cur.execute("""
SELECT COALESCE(signal_family,'?') fam, COALESCE(regime,'?') rg,
       count(*) FILTER (WHERE outcome IN ('WIN','LOSS')) resolved,
       count(*) FILTER (WHERE outcome='WIN') w,
       count(*) FILTER (WHERE outcome='LOSS') l,
       round(100.0 * count(*) FILTER (WHERE outcome='WIN') / NULLIF(count(*) FILTER (WHERE outcome IN ('WIN','LOSS')),0), 2) wr,
       round(avg(r_multiple) FILTER (WHERE outcome IS NOT NULL)::numeric, 4) avg_r,
       round(sum(r_multiple) FILTER (WHERE outcome IS NOT NULL)::numeric, 4) sum_r
FROM signals GROUP BY 1,2 HAVING count(*) FILTER (WHERE outcome IN ('WIN','LOSS')) > 0 ORDER BY resolved DESC
""")
for r in cur.fetchall():
    print(f'  {str(r[0]):10s} x {str(r[1]):20s} | {r[2]:3d} resolved | {r[3]}W/{r[4]}L | WR={r[5]}% | avg_R={r[6]} | sum_R={r[7]}')
print()

# TREND family pair detail
print('--- TREND FAMILY - PAIR BREAKDOWN ---')
cur.execute("""
SELECT pair, side,
       count(*) FILTER (WHERE outcome IN ('WIN','LOSS')) resolved,
       count(*) FILTER (WHERE outcome='WIN') w,
       count(*) FILTER (WHERE outcome='LOSS') l,
       round(100.0 * count(*) FILTER (WHERE outcome='WIN') / NULLIF(count(*) FILTER (WHERE outcome IN ('WIN','LOSS')),0), 2) wr,
       round(avg(r_multiple) FILTER (WHERE outcome IS NOT NULL)::numeric, 4) avg_r
FROM signals WHERE signal_family='TREND'
GROUP BY 1,2 HAVING count(*) FILTER (WHERE outcome IN ('WIN','LOSS')) > 0
ORDER BY resolved DESC, wr ASC
""")
for r in cur.fetchall():
    print(f'  {r[0]:14s} {r[1]:5s} | {r[2]:2d} resolved | {r[3]}W/{r[4]}L | WR={r[5]}% | avg_R={r[6]}')
print()

# NONE family pair detail
print('--- NONE FAMILY - PAIR BREAKDOWN ---')
cur.execute("""
SELECT pair, side,
       count(*) FILTER (WHERE outcome IN ('WIN','LOSS')) resolved,
       count(*) FILTER (WHERE outcome='WIN') w,
       count(*) FILTER (WHERE outcome='LOSS') l,
       round(100.0 * count(*) FILTER (WHERE outcome='WIN') / NULLIF(count(*) FILTER (WHERE outcome IN ('WIN','LOSS')),0), 2) wr,
       round(avg(r_multiple) FILTER (WHERE outcome IS NOT NULL)::numeric, 4) avg_r
FROM signals WHERE signal_family='NONE'
GROUP BY 1,2 HAVING count(*) FILTER (WHERE outcome IN ('WIN','LOSS')) > 0
ORDER BY resolved DESC, wr ASC
""")
for r in cur.fetchall():
    print(f'  {r[0]:14s} {r[1]:5s} | {r[2]:2d} resolved | {r[3]}W/{r[4]}L | WR={r[5]}% | avg_R={r[6]}')
print()

# MOMENTUM family pair detail
print('--- MOMENTUM FAMILY - PAIR BREAKDOWN ---')
cur.execute("""
SELECT pair, side,
       count(*) FILTER (WHERE outcome IN ('WIN','LOSS')) resolved,
       count(*) FILTER (WHERE outcome='WIN') w,
       count(*) FILTER (WHERE outcome='LOSS') l,
       round(100.0 * count(*) FILTER (WHERE outcome='WIN') / NULLIF(count(*) FILTER (WHERE outcome IN ('WIN','LOSS')),0), 2) wr,
       round(avg(r_multiple) FILTER (WHERE outcome IS NOT NULL)::numeric, 4) avg_r
FROM signals WHERE signal_family='MOMENTUM'
GROUP BY 1,2 HAVING count(*) FILTER (WHERE outcome IN ('WIN','LOSS')) > 0
ORDER BY resolved DESC, wr ASC
""")
for r in cur.fetchall():
    print(f'  {r[0]:14s} {r[1]:5s} | {r[2]:2d} resolved | {r[3]}W/{r[4]}L | WR={r[5]}% | avg_R={r[6]}')
print()

# Score breakdown on losses vs wins by family
print('--- SCORE ON LOSSES vs WINS BY FAMILY ---')
cur.execute("""
SELECT COALESCE(signal_family,'?') fam, outcome,
       round(avg(score)::numeric, 2) avg_score,
       round(min(score)::numeric, 2) min_s,
       round(max(score)::numeric, 2) max_s,
       count(*)
FROM signals WHERE outcome IN ('WIN','LOSS')
GROUP BY 1,2 ORDER BY 1, 2
""")
for r in cur.fetchall():
    print(f'  {str(r[0]):12s} {r[1]:5s} | avg_score={r[2]} | range=[{r[3]}-{r[4]}] | n={r[5]}')
print()

# Burst comparison table
print('--- BURST VS STRICT (if populated) ---')
cur.execute("SELECT * FROM burst_vs_strict_comparison ORDER BY cohort, market_regime, side, signal_family")
cols = [d[0] for d in cur.description]
print('  ' + ' | '.join(cols))
for r in cur.fetchall():
    print('  ' + ' | '.join(str(v) for v in r))

conn.close()
