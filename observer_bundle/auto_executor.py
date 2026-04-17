import os
import json
import asyncio
import select
import logging
import threading
import html
import psycopg2
import psycopg2.extras
import config
import risk
from executor import get_hub
from datetime import datetime
from typing import Optional

from telegram_alerts import send_telegram_async

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ["DATABASE_URL"]


def send_telegram(message: str, reply_markup: Optional[dict] = None) -> None:
    """Dispatch Telegram alerts without blocking the auto executor."""
    send_telegram_async(
        message,
        reply_markup=reply_markup,
        context="auto_executor",
        logger=logger,
    )

def _escape_html(text: str) -> str:
    """Escape special characters for Telegram HTML."""
    return html.escape(str(text))


def _coerce_reason_trace(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            logger.warning("[AUTO_EXEC] Failed to decode reason_trace payload: %s", value)
    return {}


def _send_position_opened_alert(signal: dict, amount: float, res: dict) -> None:
    """Send a Telegram alert once a position is actually opened."""
    try:
        execution_source = res.get('execution_source') or 'simulated'
        trace = signal.get('reason_trace', {}) if isinstance(signal.get('reason_trace', {}), dict) else {}
        tp1 = signal.get('tp1') or trace.get('tp1') or signal.get('take_profit')
        tp2 = signal.get('tp2') or trace.get('tp2') or signal.get('take_profit')
        alert_msg = f"""
<b> POSITION OPENED</b>
<b>Pair:</b> {_escape_html(signal['pair'])}
<b>Side:</b> {_escape_html(signal['side'])}
<b>Entry:</b> <code>{float(signal['entry']):.4f}</code>
<b>Position Size:</b> <code>{float(amount):.8f}</code>
<b>Stop Loss:</b> <code>{float(signal['stop_loss']):.4f}</code>
<b>TP1:</b> <code>{float(tp1):.4f}</code>
<b>TP2:</b> <code>{float(tp2):.4f}</code>
<b>Order ID:</b> {_escape_html(res['order_id'])}
<b>Execution:</b> {_escape_html(execution_source)}
<b>Score:</b> {_escape_html(signal['score'])}
<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
        logger.info("[AUTO_EXEC] Sending position-opened Telegram alert for %s %s", signal['pair'], signal['side'])
        send_telegram(alert_msg)
    except Exception:
        logger.exception("[AUTO_EXEC] Failed to dispatch position-opened alert for %s %s", signal.get('pair'), signal.get('side'))


async def auto_execution_daemon():
    """
    Auto-Execution Daemon (v1.9.4):
    Listens for new signals and triggers orders based on risk checks.
    """
    conn = psycopg2.connect(DATABASE_URL)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("LISTEN new_signal;")
    
    # HARD-LOCK ASSERTION: Covenant doctrine at daemon startup
    from ops_covenant import covenant_startup, infra_health as _infra
    _covenant = covenant_startup()
    if config.ENABLE_LIVE_TRADING:
        logger.critical("[DOCTRINE] ⚠️ LIVE DISPATCH ACTIVE — Triple-gate unlocked. Token verified.")
    else:
        logger.info(f"[DOCTRINE] Gate locked. SIM mode only. Reason: {config._DOCTRINE_REASON}")
    logger.info(f"[DOCTRINE] Infra health: {_infra.overall_health():.0%}")
    
    logger.info("Auto-Execution Daemon listening for 'new_signal' notifications...")
    
    hub = get_hub()
    
    while True:
        if select.select([conn], [], [], 5) == ([], [], []):
            await asyncio.sleep(0.1)
        else:
            conn.poll()
            while conn.notifies:
                notify = conn.notifies.pop(0)
                try:
                    signal = json.loads(notify.payload)
                    signal['reason_trace'] = _coerce_reason_trace(signal.get('reason_trace'))
                    logger.info(f"[AUTO_EXEC] Processing signal: {signal['pair']} {signal['side']} Score: {signal['score']}")
                    
                    # 1. Circuit Breaker Check
                    if not risk.check_circuit_breakers():
                        logger.warning(f"[AUTO_EXEC] Circuit breaker HALTED execution for {signal['pair']}.")
                        continue
                        
                    # 2. Deduplication Check
                    if not risk.deduplicate_signal(signal['pair'], signal['side']):
                        logger.info(f"[AUTO_EXEC] Deduplication SKIPPED execution for {signal['pair']}.")
                        continue
                        
                    # 3. Dynamic Dispatch Check (v1.9.4)
                    if not config.ENABLE_LIVE_TRADING:
                        logger.info(f"[AUTO_EXEC] Live trading DISABLED. SIMULATING execution for {signal['pair']}.")
                        # Fall through to place_order which handles simulation internally
                        
                    # 4. Extract Position Size and Attach SL/TP (v1.9.5)
                    # Use position_size from scanner's risk calculation
                    amount = signal.get('reason_trace', {}).get('position_size', 0)
                    if amount <= 0:
                        logger.error(f"[AUTO_EXEC] Invalid position size for {signal['pair']}: {amount}. SKIPPING.")
                        continue

                    logger.info(f"[AUTO_EXEC] Dispatching {signal['side']} {amount} {signal['pair']} with SL: {signal['stop_loss']} TP: {signal['take_profit']}")
                    
                    res = hub.place_order(
                        exchange_name="BINANCE", # Default exchange
                        symbol=signal['pair'],
                        side=signal['side'],
                        order_type="MARKET",
                        amount=amount,
                        params={
                            "stopLossPrice": signal['stop_loss'],
                            "takeProfitPrice": signal['take_profit']
                        }
                    )
                    
                    if res['success']:
                        logger.info(f"[AUTO_EXEC] Order DISPATCHED: {res['order_id']}")
                        execution_source = res.get('execution_source') or 'simulated'
                        _send_position_opened_alert(signal, amount, res)
                        
                        # Record execution in DB (Truth Ladder Level 3)
                        try:
                            exchange_status = res.get('exchange_status')
                            with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
                                cur.execute("""
                                    UPDATE signals 
                                    SET execution_id = %s, 
                                        execution_source = %s,
                                        exchange_status = %s,
                                        updated_at = NOW()
                                    WHERE signal_id = %s
                                """, (res['order_id'], execution_source, exchange_status, signal['signal_id']))
                                conn.commit()
                        except Exception as e:
                            logger.error(f"[AUTO_EXEC] Failed to update signal with execution_id: {e}")
                    else:
                        logger.error(f"[AUTO_EXEC] Order FAILED: {res['error']}")
                        
                        # Send Telegram alert for order failure
                        alert_msg = f"""
<b> ORDER FAILED</b>
<b>Pair:</b> {signal['pair']}
<b>Side:</b> {signal['side']}
<b>Amount:</b> {amount}
<b>Error:</b> {_escape_html(str(res['error']))}
<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
                        send_telegram(alert_msg)
                        
                except Exception:
                    logger.exception("[AUTO_EXEC] Error in auto-execution loop while processing signal payload")
                    
        await asyncio.sleep(0.1)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(auto_execution_daemon())
