"""
IDIM IKANG — Validated Configuration
Codex ID: mo-fin-idim-ikang-001
Logic Version: v1.0-tuned
Config Version: v1.0-tuned

LOCKED PARAMETERS — Wolfram verified, Claude validated.
DO NOT MODIFY without examiner approval.
"""

import os

# === LOCKED TRADING PARAMETERS ===
MIN_SIGNAL_SCORE = 45
COOLDOWN_BARS = 32
BLOCK_STRONG_UPTREND = True
ATR_SL_MULTIPLIER = 1.0
ATR_TP_MULTIPLIER = 3.0

# === INDICATOR PERIODS ===
INDICATOR_PERIODS = {
    "ema_fast": 20,
    "ema_slow": 50,
    "rsi": 14,
    "atr": 14,
    "volume_sma": 20
}

# === PAIR UNIVERSE ===
PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

# === TIMEFRAMES ===
TIMEFRAMES = {
    "trigger": "15m",
    "confirmation": "1h",
    "regime": "4h"
}

# === DATABASE ===
DATABASE_URL = os.getenv("DATABASE_URL", "")

# === TELEGRAM ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# === VERSION MARKERS ===
CONFIG_VERSION = "v1.0-tuned"
LOGIC_VERSION = "v1.0-tuned"

# === FULL CONFIG DICT (for passing to functions) ===
CONFIG = {
    "config_version": CONFIG_VERSION,
    "logic_version": LOGIC_VERSION,
    "pairs": PAIRS,
    "timeframes": TIMEFRAMES,
    "min_signal_score": MIN_SIGNAL_SCORE,
    "cooldown_bars": COOLDOWN_BARS,
    "block_strong_uptrend": BLOCK_STRONG_UPTREND,
    "atr_sl_multiplier": ATR_SL_MULTIPLIER,
    "atr_tp_multiplier": ATR_TP_MULTIPLIER,
    "indicator_periods": INDICATOR_PERIODS,
}