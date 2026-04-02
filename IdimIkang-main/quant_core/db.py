import asyncpg
from datetime import datetime, timezone
import json
from config import DATABASE_URL, DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME

async def get_pool():
    if DATABASE_URL:
        return await asyncpg.create_pool(dsn=DATABASE_URL)
    return await asyncpg.create_pool(
        user=DB_USER, password=DB_PASS,
        database=DB_NAME, host=DB_HOST, port=DB_PORT
    )

async def append_log(pool, event_type: str, message: str):
    """Append-only logging. No updates, no deletes."""
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO logs (event_type, message, timestamp) VALUES ($1, $2, $3)",
            event_type, message, datetime.now(timezone.utc)
        )

async def append_signal(pool, signal_data: dict):
    """
    Append-only signal storage.
    Signal invalid if any required field missing.
    """
    required_fields = [
        "pair", "timestamp", "regime", "score", "entry_range",
        "stop_loss", "take_profit", "reason_trace", "logic_version", "config_version"
    ]
    
    for f in required_fields:
        if f not in signal_data or signal_data[f] is None:
            raise ValueError(f"Signal rejected: Missing required field '{f}'")

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO signals (
                pair, timestamp, regime, score, entry_range, stop_loss,
                take_profit, reason_trace, logic_version, config_version
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            signal_data["pair"],
            signal_data["timestamp"],
            signal_data["regime"],
            signal_data["score"],
            json.dumps(signal_data["entry_range"]),
            signal_data["stop_loss"],
            json.dumps(signal_data["take_profit"]),
            json.dumps(signal_data["reason_trace"]),
            signal_data["logic_version"],
            signal_data["config_version"]
        )
