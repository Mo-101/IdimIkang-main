import os

CONFIG_VERSION = "v1.1-final"
LOGIC_VERSION = "v1.1-final"

# Database Configuration (Neon PostgreSQL / Local)
DATABASE_URL = os.getenv("DATABASE_URL", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "postgres")
DB_NAME = os.getenv("DB_NAME", "postgres")

# Telegram Alerts
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Target Pairs
PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

# Validated Phase 2 Parameters (v1.1-final)
MIN_SIGNAL_SCORE = 60.0
COOLDOWN_BARS = 32
ATR_SL_MULTIPLIER = 1.0
ATR_TP_MULTIPLIER = 3.0
VOLUME_RATIO_MIN = 1.1
MAX_SIGNALS_PER_PAIR_PER_DAY = 2

REGIME_WEIGHTS = {
    "STRONG_UPTREND": 2,
    "DOWNTREND": 1,
    "RANGING": 0,
    "UPTREND": -1,
    "STRONG_DOWNTREND": -2
}
