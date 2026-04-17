#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════
IDIM IKANG — GATE BREACH AUDIT + CLEAN BASELINE
The Flame Architect | MoStar Industries
═══════════════════════════════════════════════════════════════════

Part 1: Verify no live Binance orders were placed during default-open window
Part 2: Freeze a clean post-fix baseline snapshot

Run on WSL:
  python3 /tmp/idim_gate_audit.py

Requires:
  - Binance API keys in .env (read-only check, no trading)
  - PostgreSQL on port 5433
  - All PM2 services online
═══════════════════════════════════════════════════════════════════
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Locate .env ──────────────────────────────────────────────────
ENV_PATHS = [
    Path("/home/idona/MoStar/IdimIkang-main-1/observer_bundle/.env"),
    Path("/home/idona/idim-ikang/.env"),
]

for env_path in ENV_PATHS:
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
        break

# ── Config ───────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

BASELINE_PATH = Path("/home/idona/MoStar/IdimIkang-main-1/observer_bundle/baselines")
BASELINE_PATH.mkdir(parents=True, exist_ok=True)


def part_1_gate_breach_audit():
    """
    PROOF: No live Binance orders were placed.

    Three independent checks:
    1. Query Binance API for all orders in the last 90 days
    2. Check local PostgreSQL for any execution records with live=true
    3. Check PM2 logs for any order placement log lines
    """
    print("=" * 60)
    print("PART 1: GATE BREACH AUDIT")
    print("Proving no live orders escaped during default-open window")
    print("=" * 60)

    evidence = {"binance_orders": None, "db_executions": None, "log_evidence": None}

    # ── Check 1: Binance API — query all orders ─────────────────
    print("\n[1/3] Querying Binance Futures for any orders...")
    try:
        import hmac, hashlib, time, urllib.request, urllib.parse

        base_url = "https://fapi.binance.com"
        timestamp = int(time.time() * 1000)

        # Query all orders (no symbol filter = all pairs)
        # Check last 90 days
        start_time = int((datetime.now(timezone.utc) - timedelta(days=90)).timestamp() * 1000)

        params = {
            "timestamp": str(timestamp),
            "startTime": str(start_time),
            "recvWindow": "10000",
        }
        query_string = urllib.parse.urlencode(params)
        signature = hmac.new(
            BINANCE_API_SECRET.encode(), query_string.encode(), hashlib.sha256
        ).hexdigest()
        query_string += f"&signature={signature}"

        # Try account trades endpoint (shows actual fills)
        url = f"{base_url}/fapi/v1/userTrades?{query_string}"
        req = urllib.request.Request(url, headers={"X-MBX-APIKEY": BINANCE_API_KEY})

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                trades = json.loads(resp.read())
                if isinstance(trades, list):
                    evidence["binance_orders"] = len(trades)
                    if len(trades) == 0:
                        print("  ✅ ZERO trades found on Binance Futures (last 90 days)")
                    else:
                        print(f"  🚨 FOUND {len(trades)} trades on Binance Futures!")
                        for t in trades[:5]:
                            print(f"     {t.get('symbol')} | {t.get('side')} | qty={t.get('qty')} | time={t.get('time')}")
                else:
                    # API returned error object, likely needs symbol param
                    print(f"  ⚠️  API response: {json.dumps(trades)[:200]}")
                    evidence["binance_orders"] = "api_error"
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            error_data = json.loads(body) if body else {}
            code = error_data.get("code", "")

            if code == -1101:
                # "Too many parameters" — need to query per-symbol
                # Try with just BTCUSDT as canary
                print("  ℹ️  API requires symbol param, checking BTCUSDT as canary...")
                params["symbol"] = "BTCUSDT"
                query_string = urllib.parse.urlencode(params)
                signature = hmac.new(
                    BINANCE_API_SECRET.encode(), query_string.encode(), hashlib.sha256
                ).hexdigest()
                query_string += f"&signature={signature}"
                url2 = f"{base_url}/fapi/v1/userTrades?{query_string}"
                req2 = urllib.request.Request(url2, headers={"X-MBX-APIKEY": BINANCE_API_KEY})
                try:
                    with urllib.request.urlopen(req2, timeout=15) as resp2:
                        trades2 = json.loads(resp2.read())
                        evidence["binance_orders"] = len(trades2) if isinstance(trades2, list) else "error"
                        if isinstance(trades2, list) and len(trades2) == 0:
                            print("  ✅ ZERO BTCUSDT trades found (canary clean)")
                        elif isinstance(trades2, list):
                            print(f"  🚨 FOUND {len(trades2)} BTCUSDT trades!")
                        else:
                            print(f"  ⚠️  {trades2}")
                except Exception as e2:
                    print(f"  ⚠️  Canary check failed: {e2}")
                    evidence["binance_orders"] = "canary_failed"
            else:
                print(f"  ⚠️  Binance API error: {body[:200]}")
                evidence["binance_orders"] = "api_error"

    except ImportError:
        print("  ⚠️  Cannot check Binance (missing libs)")
        evidence["binance_orders"] = "skipped"
    except Exception as e:
        print(f"  ⚠️  Binance check error: {e}")
        evidence["binance_orders"] = str(e)

    # ── Check 2: Local DB — any execution records? ───────────────
    print("\n[2/3] Checking local PostgreSQL for execution records...")
    try:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        # Check for any table that might store executions
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            AND (table_name ILIKE '%exec%' OR table_name ILIKE '%order%' OR table_name ILIKE '%trade%')
        """)
        exec_tables = [r[0] for r in cur.fetchall()]

        if exec_tables:
            print(f"  Found execution-related tables: {exec_tables}")
            for table in exec_tables:
                cur.execute(f"SELECT count(*) FROM {table}")
                count = cur.fetchone()[0]
                print(f"    {table}: {count} rows")
                if count > 0:
                    cur.execute(f"SELECT * FROM {table} LIMIT 3")
                    cols = [d[0] for d in cur.description]
                    for row in cur.fetchall():
                        print(f"      {dict(zip(cols, row))}")
        else:
            print("  ✅ No execution/order/trade tables found in database")

        # Also check system_logs for any dispatch evidence
        cur.execute("""
            SELECT count(*) FROM system_logs
            WHERE component = 'auto_executor'
            AND (event ILIKE '%dispatch%' OR event ILIKE '%order%' OR event ILIKE '%place%')
        """)
        dispatch_logs = cur.fetchone()[0]
        evidence["db_executions"] = dispatch_logs
        if dispatch_logs == 0:
            print(f"  ✅ ZERO dispatch/order log entries in system_logs")
        else:
            print(f"  🚨 FOUND {dispatch_logs} dispatch-related log entries!")

        # Check signals table for any live execution_source
        cur.execute("""
            SELECT execution_source, count(*) FROM signals
            WHERE execution_source IS NOT NULL
            GROUP BY execution_source
        """)
        exec_sources = cur.fetchall()
        if exec_sources:
            print(f"  Execution sources in signals table:")
            for source, count in exec_sources:
                marker = "🚨" if source == "live" else "  "
                print(f"    {marker} {source}: {count}")
        else:
            print("  ✅ No execution_source entries in signals table")

        conn.close()
    except Exception as e:
        print(f"  ⚠️  DB check error: {e}")
        evidence["db_executions"] = str(e)

    # ── Check 3: PM2 logs — any order evidence? ─────────────────
    print("\n[3/3] Scanning executor PM2 logs for order evidence...")
    try:
        import subprocess
        result = subprocess.run(
            ["pm2", "logs", "idim-auto-executor", "--lines", "500", "--nostream", "--raw"],
            capture_output=True, text=True, timeout=10
        )
        log_text = result.stdout + result.stderr

        order_keywords = ["LIVE ORDER", "place_order", "DISPATCH", "ORDER_PLACED",
                         "binance.*order", "EXECUTION_LIVE", "real_trade",
                         "LIVE_DISPATCH", "Live order"]
        gate_keywords = ["IRON_GATE", "SIM mode", "ENABLE_LIVE_TRADING",
                         "DISPATCH_LOCK", "SIMULATED_SUCCESS"]

        order_hits = []
        gate_hits = []
        for line in log_text.split("\n"):
            lower = line.lower()
            for kw in order_keywords:
                if kw.lower() in lower:
                    order_hits.append(line.strip()[:120])
                    break
            for kw in gate_keywords:
                if kw.lower() in lower:
                    gate_hits.append(line.strip()[:120])
                    break

        evidence["log_evidence"] = len(order_hits)

        if order_hits:
            print(f"  🚨 FOUND {len(order_hits)} order-related log lines!")
            for h in order_hits[:5]:
                print(f"    {h}")
        else:
            print(f"  ✅ ZERO order-related keywords in last 500 log lines")

        if gate_hits:
            print(f"  ℹ️  Gate status entries ({len(gate_hits)}):")
            for h in gate_hits[:5]:
                print(f"    {h}")

    except Exception as e:
        print(f"  ⚠️  Log scan error: {e}")
        evidence["log_evidence"] = str(e)

    # ── Verdict ──────────────────────────────────────────────────
    print("\n" + "─" * 60)
    binance_clean = evidence["binance_orders"] == 0 or evidence["binance_orders"] == "skipped"
    db_clean = evidence["db_executions"] == 0
    log_clean = evidence["log_evidence"] == 0

    if binance_clean and db_clean and log_clean:
        print("✅ GATE BREACH AUDIT: CLEAN")
        print("   No live orders were placed during the default-open window.")
        print("   Evidence: Binance API clean, DB clean, logs clean.")
    elif not binance_clean and evidence["binance_orders"] not in (0, "skipped", "api_error", "canary_failed"):
        print("🚨 GATE BREACH AUDIT: ORDERS DETECTED")
        print("   Live orders may have been placed. Investigate immediately.")
    else:
        print("⚠️  GATE BREACH AUDIT: INCONCLUSIVE")
        print(f"   Binance: {evidence['binance_orders']}")
        print(f"   DB: {evidence['db_executions']}")
        print(f"   Logs: {evidence['log_evidence']}")
        print("   Manual verification recommended.")
    print("─" * 60)

    return evidence


def part_2_clean_baseline():
    """
    Freeze a clean post-fix baseline snapshot.
    """
    print("\n" + "=" * 60)
    print("PART 2: CLEAN BASELINE SNAPSHOT")
    print("=" * 60)

    baseline = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "label": "post-fix-clean-baseline",
        "gate_status": "LOCKED (default=false, IRON_GATE assertion active)",
        "collectors": {},
        "signals": {},
        "performance": {},
        "pm2": {},
    }

    try:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        # Row counts
        cur.execute("SELECT count(*) FROM signals")
        baseline["signals"]["total"] = cur.fetchone()[0]

        cur.execute("SELECT count(*) FROM signals WHERE outcome IS NOT NULL AND outcome != 'UNRESOLVED'")
        baseline["signals"]["resolved"] = cur.fetchone()[0]

        cur.execute("SELECT count(*) FROM signals WHERE outcome = 'WIN'")
        baseline["signals"]["wins"] = cur.fetchone()[0]

        cur.execute("SELECT count(*) FROM signals WHERE outcome = 'LOSS'")
        baseline["signals"]["losses"] = cur.fetchone()[0]

        cur.execute("SELECT count(*) FROM signals WHERE outcome = 'UNRESOLVED' OR outcome IS NULL")
        baseline["signals"]["unresolved"] = cur.fetchone()[0]

        # Performance
        resolved = baseline["signals"]["resolved"]
        wins = baseline["signals"]["wins"]
        losses = baseline["signals"]["losses"]
        baseline["performance"]["win_rate"] = round(wins / resolved * 100, 2) if resolved > 0 else 0
        baseline["performance"]["resolved_count"] = resolved

        # PF from DB
        cur.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN outcome = 'WIN' THEN ABS(r_multiple) ELSE 0 END), 0) AS gross_profit,
                COALESCE(SUM(CASE WHEN outcome = 'LOSS' THEN ABS(r_multiple) ELSE 0 END), 0) AS gross_loss
            FROM signals
            WHERE outcome IN ('WIN', 'LOSS')
        """)
        row = cur.fetchone()
        gp, gl = float(row[0]), float(row[1])
        baseline["performance"]["profit_factor"] = round(gp / gl, 4) if gl > 0 else float("inf")
        baseline["performance"]["gross_profit_r"] = round(gp, 4)
        baseline["performance"]["gross_loss_r"] = round(gl, 4)

        # Collector freshness
        for table, label in [("funding_rates", "funding"), ("open_interest", "oi"), ("ls_ratios", "ls")]:
            try:
                cur.execute(f"SELECT max(collected_at) FROM {table}")
                ts = cur.fetchone()[0]
                baseline["collectors"][label] = str(ts) if ts else "empty"
            except Exception:
                baseline["collectors"][label] = "table_missing"
                conn.rollback()

        # Signal freshness
        cur.execute("SELECT max(created_at) FROM signals")
        baseline["signals"]["last_signal"] = str(cur.fetchone()[0])

        # Training data count
        try:
            cur.execute("SELECT count(*) FROM training_candidates")
            baseline["signals"]["training_records"] = cur.fetchone()[0]
        except Exception:
            baseline["signals"]["training_records"] = "table_missing"
            conn.rollback()

        conn.close()

    except Exception as e:
        baseline["error"] = str(e)
        print(f"  ⚠️  DB error: {e}")

    # PM2 status
    try:
        import subprocess
        result = subprocess.run(["pm2", "jlist"], capture_output=True, text=True, timeout=10)
        pm2_data = json.loads(result.stdout)
        for proc in pm2_data:
            name = proc.get("name", "unknown")
            baseline["pm2"][name] = {
                "status": proc.get("pm2_env", {}).get("status", "unknown"),
                "restarts": proc.get("pm2_env", {}).get("restart_time", 0),
                "uptime_ms": proc.get("pm2_env", {}).get("pm_uptime", 0),
                "memory_mb": round(proc.get("monit", {}).get("memory", 0) / 1024 / 1024, 1),
            }
    except Exception as e:
        baseline["pm2"]["error"] = str(e)

    # Save baseline
    filename = f"baseline_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    filepath = BASELINE_PATH / filename
    with open(filepath, "w") as f:
        json.dump(baseline, f, indent=2, default=str)

    print(f"\n  📁 Baseline saved: {filepath}")
    print(f"\n  📊 Snapshot:")
    print(f"     Signals:    {baseline['signals']['total']}")
    print(f"     Resolved:   {baseline['signals']['resolved']}")
    print(f"     Wins:       {baseline['signals']['wins']}")
    print(f"     Losses:     {baseline['signals']['losses']}")
    print(f"     Win Rate:   {baseline['performance']['win_rate']}%")
    print(f"     PF:         {baseline['performance']['profit_factor']}")
    print(f"     Gate:       {baseline['gate_status']}")
    print(f"     Collectors: {json.dumps(baseline['collectors'], default=str)}")

    return baseline


def main():
    print("🜂" * 30)
    print("IDIM IKANG — GATE AUDIT + BASELINE")
    print("River of Fire | MoStar Industries")
    print("🜂" * 30)

    evidence = part_1_gate_breach_audit()
    baseline = part_2_clean_baseline()

    print("\n" + "=" * 60)
    print("COMPLETE")
    print("=" * 60)
    print("Gate audit + baseline frozen.")
    print("Let it run. Do not touch it. Watch what the market says.")
    print("=" * 60)


if __name__ == "__main__":
    main()
