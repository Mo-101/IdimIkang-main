import os
import logging
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone, timedelta
import config

logger = logging.getLogger(__name__)

def db_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])

def check_circuit_breakers() -> bool:
    """
    Checks if trading should be halted based on daily loss limits.
    Returns True if trading is ALLOWED, False if HALTED.
    """
    try:
        with db_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Calculate daily PnL from outcome_tracker results
            # This is a simplified version; real implementation would track equity
            today = datetime.now(timezone.utc).date()
            cur.execute("""
                SELECT SUM(r_multiple) as total_r 
                FROM signals 
                WHERE outcome IN ('LOSS', 'WIN', 'PARTIAL_WIN', 'LIVE_WIN', 'LIVE_LOSS', 'LIVE_PARTIAL') 
                AND ts >= %s
            """, (today,))
            res = cur.fetchone()
            total_r = res['total_r'] or 0
            
            # Example: Halt if daily loss exceeds 3R
            if total_r <= -3.0:
                logger.warning(f"[CIRCUIT_BREAKER] Daily loss limit reached ({total_r}R). HALTING.")
                return False
                
            return True
    except Exception as e:
        logger.error(f"Circuit breaker check failed: {e}")
        return False # Safe default: halt if check fails

def deduplicate_signal(pair: str, side: str, cooldown_minutes: int = 60) -> bool:
    """
    Checks if a similar signal was recently emitted to avoid over-trading.
    Returns True if signal is UNIQUE, False if DUPLICATE.
    """
    try:
        with db_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cooldown_time = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
            cur.execute("""
                SELECT COUNT(*) as count 
                FROM signals 
                WHERE pair = %s AND side = %s AND ts >= %s
            """, (pair, side, cooldown_time))
            res = cur.fetchone()
            
            if res['count'] > 0:
                logger.info(f"[DEDUPLICATION] Signal for {pair} {side} already exists within {cooldown_minutes}m. SKIPPING.")
                return False
                
            return True
    except Exception as e:
        logger.error(f"Deduplication check failed: {e}")
        return True # Default to unique if check fails
