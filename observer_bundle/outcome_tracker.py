#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import os
import time
from datetime import timezone

import pandas as pd
import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

load_dotenv()

import config
from datetime import datetime, timezone, timedelta

DATABASE_URL = os.environ["DATABASE_URL"]
BINANCE_BASE_URL = os.environ.get("BINANCE_BASE_URL", "https://api.binance.com")
LOOP_SECONDS = 900
SIGNAL_EXPIRY_DAYS = config.SIGNAL_EXPIRY_DAYS


def db_conn():
    return psycopg2.connect(DATABASE_URL)


def log_event(level: str, component: str, event: str, details: dict):
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO system_logs(level, component, event, details) VALUES (%s,%s,%s,%s::jsonb)",
            (level, component, event, json.dumps(details)),
        )
        conn.commit()


def fetch_since(symbol: str, start_ms: int, interval: str = "15m", limit: int = 1000):
    url = f"{BINANCE_BASE_URL}/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "startTime": start_ms, "limit": limit}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    cols = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "num_trades",
        "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
    ]
    df = pd.DataFrame(r.json(), columns=cols)
    if df.empty:
        return df
    for c in ["open", "high", "low", "close"]:
        df[c] = df[c].astype(float)
    return df


def resolve_signal(sig: dict) -> tuple[str | None, float | None, dict | None]:
    ts_ms = int(sig["ts"].timestamp() * 1000)
    df = fetch_since(sig["pair"], ts_ms)
    if df.empty:
        return None, None, None

    side = sig["side"]
    entry = float(sig["entry"])
    
    # Scale-out targets from reason_trace
    trace = sig.get("reason_trace", {})
    tp1 = float(trace.get("tp1", sig["take_profit"]))
    tp2 = float(trace.get("tp2", sig["take_profit"]))
    
    # State from DB
    is_partial = sig.get("is_partial", False)
    current_sl = float(sig.get("trailing_sl")) if sig.get("trailing_sl") else float(sig["stop_loss"])

    for _, row in df.iterrows():
        high, low = float(row["high"]), float(row["low"])
        
        if side == "LONG":
            # 1. Check for Stop Loss / Breakeven
            if low <= current_sl:
                if is_partial:
                    return "PARTIAL_WIN", 0.6, None # 0.6R secured at TP1, 0R on the rest
                return "LOSS", -1.0, None
            
            # 2. Check for Scale-out (TP1)
            if not is_partial and high >= tp1:
                # Trigger Breakeven migration
                return "HIT_TP1", 0.6, {"is_partial": True, "trailing_sl": entry}
            
            # 3. Check for Final Target (TP2)
            if high >= tp2:
                # 0.6R (from TP1 stage) + 1.5R (remaining 50% at 3R) = 2.1R total
                return "WIN", 2.1, None
                
        else: # SHORT
            if high >= current_sl:
                if is_partial:
                    return "PARTIAL_WIN", 0.6, None
                return "LOSS", -1.0, None
            
            if not is_partial and low <= tp1:
                return "HIT_TP1", 0.6, {"is_partial": True, "trailing_sl": entry}
            
            if low <= tp2:
                return "WIN", 2.1, None
                
    return None, None, None


def run_once():
    expiry_threshold = datetime.now(timezone.utc) - timedelta(days=SIGNAL_EXPIRY_DAYS)
    
    with db_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, signal_id, pair, ts, side, entry, stop_loss, take_profit, reason_trace, is_partial, trailing_sl
            FROM signals
            WHERE outcome IS NULL
            ORDER BY ts ASC
            LIMIT 500
            """
        )
        rows = cur.fetchall()

    updates = 0
    expired = 0
    errors = 0
    
    for row in rows:
        try:
            # 1. Define sig_ts correctly
            sig_ts = row["ts"]
            if sig_ts.tzinfo is None:
                sig_ts = sig_ts.replace(tzinfo=timezone.utc)
            
            outcome, r_mult, updates_meta = None, None, None
            
            # 2. Check for expiry first
            if sig_ts < expiry_threshold:
                outcome, r_mult = "EXPIRED", 0.0
                expired += 1
            else:
                # 3. Resolve using new Scale-out / Breakeven logic
                outcome, r_mult, updates_meta = resolve_signal(row)
            
            if outcome == "HIT_TP1":
                # Persist partial state but keep outcome NULL to continue tracking for TP2
                with db_conn() as conn, conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE signals
                        SET is_partial = TRUE, trailing_sl = %s, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (updates_meta["trailing_sl"], row["id"]),
                    )
                    conn.commit()
                log_event("INFO", "outcome_tracker", "scale_out_hit", {"signal_id": row["signal_id"], "pair": row["pair"]})
            elif outcome is not None:
                # Final resolution: WIN, LOSS, or PARTIAL_WIN (hit BE after TP1)
                with db_conn() as conn, conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE signals
                        SET outcome = %s, r_multiple = %s, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (outcome, r_mult, row["id"]),
                    )
                    conn.commit()
                updates += 1
        except Exception as e:
            errors += 1
            log_event("ERROR", "outcome_tracker", "per_signal_error", {"signal_id": row["signal_id"], "error": str(e)})

    log_event("INFO", "outcome_tracker", "tracker_run_complete", {
        "checked": len(rows), 
        "updated": updates, 
        "expired": expired,
        "errors": errors
    })


import logging
from logging.handlers import RotatingFileHandler

# Log configuration
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')

# Rotating file handler
os.makedirs("logs", exist_ok=True)
fh = RotatingFileHandler('logs/outcome_tracker.log', maxBytes=100*1024*1024, backupCount=7)
fh.setFormatter(formatter)
logger.addHandler(fh)

# Console handler — disabled under PM2 to prevent duplicate log lines
# ch = logging.StreamHandler()
# ch.setFormatter(formatter)
# logger.addHandler(ch)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()

    if args.loop:
        while True:
            try:
                run_once()
            except Exception as e:
                log_event("ERROR", "outcome_tracker", "tracker_error", {"error": str(e)})
            time.sleep(LOOP_SECONDS)
    else:
        run_once()


if __name__ == "__main__":
    main()
