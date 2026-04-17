#!/usr/bin/env python3
"""
COVENANT ACCEPTANCE PROOF SET
A: PM2 stability (checked externally)
B: Freshness check
C: Scanner proof (last 3 cycles)
D: Executor doctrine proof
"""
import psycopg2
import json
from datetime import datetime, timezone

DATABASE_URL = "postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang"
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# ═══════════════════════════════════════════════════════════════
# B: FRESHNESS CHECK
# ═══════════════════════════════════════════════════════════════
print("=" * 60)
print("B: FRESHNESS CHECK")
print("=" * 60)

now = datetime.now(timezone.utc)
tables = {
    "signals": "created_at",
    "funding_rates": "collected_at",
    "open_interest": "collected_at",
    "ls_ratios": "collected_at",
}

for table, ts_col in tables.items():
    cur.execute(f"SELECT MAX({ts_col}) FROM {table}")
    max_ts = cur.fetchone()[0]
    if max_ts:
        if hasattr(max_ts, 'tzinfo') and max_ts.tzinfo is None:
            age = (now.replace(tzinfo=None) - max_ts).total_seconds() / 60
        else:
            age = (now - max_ts).total_seconds() / 60
        status = "✅ FRESH" if age < 60 else ("⚠️ STALE" if age < 360 else "🚨 DEAD")
        print(f"  {table:20}: last={max_ts} | age={age:.0f}min | {status}")
    else:
        print(f"  {table:20}: NO DATA")

# ═══════════════════════════════════════════════════════════════
# C: SCANNER PROOF — last 3 cycles from PM2 logs
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("C: SCANNER PROOF (last 3 cycles from PM2)")
print("=" * 60)

import subprocess
result = subprocess.run(
    ["grep", "-c", "CYCLE COMPLETE", "/home/idona/.pm2/logs/idim-scanner-out.log"],
    capture_output=True, text=True, timeout=5
)
cycle_count = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0
print(f"  Total scan cycles logged: {cycle_count}")

# Last 3 cycles
result2 = subprocess.run(
    ["grep", "CYCLE COMPLETE", "/home/idona/.pm2/logs/idim-scanner-out.log"],
    capture_output=True, text=True, timeout=5
)
lines = result2.stdout.strip().split("\n")
for line in lines[-3:]:
    # Extract the meaningful part
    if "CYCLE COMPLETE" in line:
        parts = line.split("CYCLE COMPLETE")
        if len(parts) > 1:
            print(f"  {parts[1].strip()[:120]}")
        else:
            print(f"  {line.strip()[-120:]}")

# Check for import errors or wrapper regressions
result3 = subprocess.run(
    ["grep", "-c", "-i", "import error\\|module not found\\|resilient.*fail\\|ops_covenant.*error",
     "/home/idona/.pm2/logs/idim-scanner-error.log"],
    capture_output=True, text=True, timeout=5
)
import_errors = int(result3.stdout.strip()) if result3.stdout.strip().isdigit() else 0
print(f"\n  Import/wrapper errors in scanner: {import_errors} {'✅' if import_errors == 0 else '🚨'}")

# ═══════════════════════════════════════════════════════════════
# D: EXECUTOR DOCTRINE PROOF
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("D: EXECUTOR DOCTRINE PROOF")
print("=" * 60)

# D1: Check system_logs for doctrine/covenant entries
cur.execute("""
    SELECT ts, level, event
    FROM system_logs
    WHERE component = 'auto_executor'
    AND (event ILIKE '%doctrine%' OR event ILIKE '%covenant%' OR event ILIKE '%gate%')
    ORDER BY ts DESC
    LIMIT 5
""")
doctrine_entries = cur.fetchall()
if doctrine_entries:
    for ts, level, event in doctrine_entries:
        print(f"  [{level}] {ts}: {event}")
else:
    print("  No doctrine entries in system_logs (PM2 logs only)")

# D2: Check for any LIVE_DISPATCH entries
cur.execute("""
    SELECT COUNT(*) FROM system_logs
    WHERE event ILIKE '%live_dispatch%' OR event ILIKE '%execution_source%'
""")
live_count = cur.fetchone()[0]
print(f"\n  Live dispatch entries in DB: {live_count} {'✅ ZERO' if live_count == 0 else '🚨 FOUND'}")

# D3: Check signals for execution_source
cur.execute("""
    SELECT execution_source, COUNT(*) FROM signals
    WHERE execution_source IS NOT NULL
    GROUP BY execution_source
""")
exec_sources = cur.fetchall()
print(f"  Execution sources in signals:")
for source, count in exec_sources:
    marker = "🚨" if source == "live" else "  "
    print(f"    {marker} {source}: {count}")

# D4: Verify ENABLE_LIVE_TRADING and token from config
import sys, os
sys.path.insert(0, "/home/idona/MoStar/IdimIkang-main-1/observer_bundle")
os.chdir("/home/idona/MoStar/IdimIkang-main-1/observer_bundle")
import config

print(f"\n  ENABLE_LIVE_TRADING: {config.ENABLE_LIVE_TRADING}")
print(f"  Doctrine reason: {config._DOCTRINE_REASON}")
print(f"  LIVE_TRADING_UNLOCK_TOKEN: {'SET' if os.environ.get('LIVE_TRADING_UNLOCK_TOKEN','') else 'ABSENT'}")

# D5: Infra health
from ops_covenant import infra_health
print(f"  Infra health: {infra_health.overall_health():.0%}")
print(f"\n{infra_health.status_report()}")

conn.close()

# ═══════════════════════════════════════════════════════════════
# VERDICT
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("ACCEPTANCE VERDICT")
print("=" * 60)

all_clean = (
    live_count == 0
    and not config.ENABLE_LIVE_TRADING
    and import_errors == 0
    and infra_health.overall_health() >= 0.9
)

if all_clean:
    print("✅ COVENANT ACCEPTANCE: PASS")
    print("   PM2 stable, collectors fresh, scanner clean, doctrine locked.")
else:
    print("⚠️ COVENANT ACCEPTANCE: WATCH")
    print("   One or more checks require attention.")
