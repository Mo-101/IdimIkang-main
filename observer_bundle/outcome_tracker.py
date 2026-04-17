#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import os
import time
import threading
import html
import logging
from datetime import timezone

import pandas as pd
import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

from telegram_alerts import send_telegram_async

load_dotenv()

import config
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)
DATABASE_URL = os.environ["DATABASE_URL"]
BINANCE_BASE_URL = os.environ.get("BINANCE_BASE_URL", "https://api.binance.com")
LOOP_SECONDS = 900
SIGNAL_EXPIRY_DAYS = config.SIGNAL_EXPIRY_DAYS


def send_telegram(message: str, reply_markup: dict | None = None) -> None:
    """Dispatch Telegram alerts without blocking the outcome tracker."""
    send_telegram_async(
        message,
        reply_markup=reply_markup,
        context="outcome_tracker",
        logger=logging.getLogger(__name__),
    )

def _escape_html(text: str) -> str:
    """Escape special characters for Telegram HTML."""
    return html.escape(str(text))


def _calc_pnl_pct(entry: float, exit_price: float, side: str) -> float:
    if entry <= 0 or exit_price <= 0:
        return 0.0
    if side == "LONG":
        return ((exit_price - entry) / entry) * 100.0
    return ((entry - exit_price) / entry) * 100.0


def _send_scale_out_alert(row: dict, updates_meta: dict) -> None:
    try:
        exit_price = float(updates_meta.get("exit_price", row["entry"]))
        pnl_pct = float(updates_meta.get("pnl_pct", 0.0))
        alert_msg = f"""
<b> SCALE-OUT HIT</b>
<b>Pair:</b> {_escape_html(row['pair'])}
<b>Side:</b> {_escape_html(row['side'])}
<b>Target:</b> TP1 Reached
<b>Entry → TP1:</b> <code>{float(row['entry']):.4f}</code> → <code>{exit_price:.4f}</code>
<b>PnL:</b> <code>{pnl_pct:+.2f}%</code>
<b>Partial Profit:</b> 0.6R Locked
<b>Trailing SL:</b> <code>{float(updates_meta['trailing_sl']):.4f}</code>
<b>MAE:</b> <code>{float(updates_meta.get('adverse_excursion', 0.0)):.2f}%</code>
<b>Time:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
        logger.info("[OUTCOME ALERT] Sending scale-out Telegram alert for %s %s", row['pair'], row['side'])
        send_telegram(alert_msg)
    except Exception:
        logger.exception("[OUTCOME ALERT] Failed to dispatch scale-out alert for %s %s", row.get('pair'), row.get('side'))


def _send_outcome_alert(row: dict, outcome: str, r_mult: float, updates_meta: dict | None) -> None:
    try:
        meta = updates_meta or {}
        exit_price = float(meta.get("exit_price", row["entry"]))
        pnl_pct = float(meta.get("pnl_pct", 0.0))
        adverse_excursion = float(meta.get("adverse_excursion", 0.0))
        outcome_label = "NEUTRAL" if outcome == "EXPIRED" else outcome
        alert_msg = f"""
<b> TRADE OUTCOME</b>
<b>Pair:</b> {_escape_html(row['pair'])}
<b>Side:</b> {_escape_html(row['side'])}
<b>Outcome:</b> {_escape_html(outcome_label)}
<b>Entry → Exit:</b> <code>{float(row['entry']):.4f}</code> → <code>{exit_price:.4f}</code>
<b>PnL:</b> <code>{pnl_pct:+.2f}%</code>
<b>R Multiple:</b> <code>{float(r_mult):+.2f}R</code>
<b>MAE:</b> <code>{adverse_excursion:.2f}%</code>
<b>Duration:</b> {(datetime.now(timezone.utc) - row['ts']).days}d
<b>Time:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
        logger.info("[OUTCOME ALERT] Sending outcome Telegram alert for %s %s outcome=%s", row['pair'], row['side'], outcome_label)
        send_telegram(alert_msg)
    except Exception:
        logger.exception("[OUTCOME ALERT] Failed to dispatch outcome alert for %s %s", row.get('pair'), row.get('side'))


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
    # Determine if it's a futures pair (usually ends in USDT or has a specific format)
    # For Binance, futures klines are at /fapi/v1/klines
    is_futures = "USDT" in symbol # Simple heuristic
    
    if is_futures:
        base_url = "https://fapi.binance.com"
        endpoint = "/fapi/v1/klines"
    else:
        base_url = "https://api.binance.com"
        endpoint = "/api/v3/klines"
        
    url = f"{base_url}{endpoint}"
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
    trailing_sl = sig.get("trailing_sl")
    current_sl = float(trailing_sl) if trailing_sl is not None else float(sig["stop_loss"])

    # Adverse Excursion Tracking (MAE) in R-multiples
    max_adv_r = float(sig.get("adverse_excursion") or 0.0)
    initial_sl = float(sig["stop_loss"])
    r_dist = abs(entry - initial_sl) if abs(entry - initial_sl) > 0 else 1e-8

    def _meta(exit_price: float | None = None, **extra) -> dict:
        payload = {"adverse_excursion": max_adv_r}
        if exit_price is not None:
            payload["exit_price"] = float(exit_price)
            payload["pnl_pct"] = _calc_pnl_pct(entry, float(exit_price), side)
        payload.update(extra)
        return payload

    for _, row in df.iterrows():
        high, low = float(row["high"]), float(row["low"])

        # Track maximum adverse excursion in R-multiples
        current_adv_r = (entry - low) / r_dist if side == "LONG" else (high - entry) / r_dist
        max_adv_r = max(max_adv_r, current_adv_r)

        if side == "LONG":
            # 1. Check for Stop Loss / Breakeven
            if low <= current_sl:
                if is_partial:
                    return "WIN", 0.6, _meta(exit_price=current_sl)
                return "LOSS", -1.0, _meta(exit_price=current_sl)

            # 2. Check for Scale-out (TP1)
            if not is_partial and high >= tp1:
                return "HIT_TP1", 0.6, _meta(exit_price=tp1, is_partial=True, trailing_sl=entry)

            # 3. Check for Final Target (TP2)
            if high >= tp2:
                return "WIN", 2.1, _meta(exit_price=tp2)

        else:  # SHORT
            if high >= current_sl:
                if is_partial:
                    return "WIN", 0.6, _meta(exit_price=current_sl)
                return "LOSS", -1.0, _meta(exit_price=current_sl)

            if not is_partial and low <= tp1:
                return "HIT_TP1", 0.6, _meta(exit_price=tp1, is_partial=True, trailing_sl=entry)

            if low <= tp2:
                return "WIN", 2.1, _meta(exit_price=tp2)

    return None, None, {"adverse_excursion": max_adv_pct}


def run_once():
    expiry_threshold = datetime.now(timezone.utc) - timedelta(days=SIGNAL_EXPIRY_DAYS)
    
    with db_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, signal_id, pair, ts, side, entry, stop_loss, take_profit, reason_trace, is_partial, trailing_sl, adverse_excursion, execution_source
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
            
            # 2. Check for absolute expiry ONLY for live execution. Simulated rows must process history.
            is_live = row.get("execution_source") == "live"
            if is_live and sig_ts < expiry_threshold:
                outcome, r_mult = "EXPIRED", 0.0
                updates_meta = {
                    "exit_price": float(row["entry"]),
                    "pnl_pct": 0.0,
                    "adverse_excursion": float(row.get("adverse_excursion") or 0.0),
                }
                expired += 1
            else:
                # 3. Resolve using new Scale-out / Breakeven logic
                outcome, r_mult, updates_meta = resolve_signal(row)
            
            if outcome == "HIT_TP1" and updates_meta is not None:
                # Persist partial state and MAE but keep outcome NULL to continue tracking for TP2
                with db_conn() as conn, conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE signals
                        SET is_partial = TRUE, trailing_sl = %s, adverse_excursion = %s, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (updates_meta.get("trailing_sl"), updates_meta.get("adverse_excursion"), row["id"]),
                    )
                    conn.commit()
                log_event("INFO", "outcome_tracker", "scale_out_hit", {"signal_id": row["signal_id"], "pair": row["pair"]})
                
                # Send Telegram alert for scale-out
                _send_scale_out_alert(row, updates_meta)
            elif outcome is not None:
                # Final resolution: WIN or LOSS. Scaled-out winners remain WIN with a smaller R multiple.
                with db_conn() as conn, conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE signals
                        SET outcome = %s, r_multiple = %s, adverse_excursion = %s, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (outcome, r_mult, updates_meta["adverse_excursion"] if updates_meta is not None else None, row["id"]),
                    )
                    conn.commit()
                updates += 1
                
                # Send Telegram alert for outcome
                _send_outcome_alert(row, outcome, r_mult, updates_meta)
            else:
                # No resolution yet, but still update the adverse excursion if it changed
                if updates_meta is not None:
                    with db_conn() as conn, conn.cursor() as cur:
                        cur.execute(
                            "UPDATE signals SET adverse_excursion = %s, updated_at = NOW() WHERE id = %s",
                            (updates_meta["adverse_excursion"], row["id"]),
                        )
                        conn.commit()
        except Exception as e:
            errors += 1
            logger.exception("[OUTCOME TRACKER] Error while processing signal_id=%s pair=%s", row.get("signal_id"), row.get("pair"))
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
