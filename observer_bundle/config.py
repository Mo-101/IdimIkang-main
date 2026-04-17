#!/usr/bin/env python3
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()


def _env_flag(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _parse_utc(ts_value: str) -> datetime:
    try:
        return datetime.fromisoformat(ts_value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return datetime.max.replace(tzinfo=timezone.utc)


TEMP_DATA_BURST_ENABLED = _env_flag("TEMP_DATA_BURST_ENABLED", "true")
TEMP_DATA_BURST_END_UTC = os.environ.get("TEMP_DATA_BURST_END_UTC", "2026-04-12T23:59:59Z")
TEMP_DATA_BURST_ACTIVE = TEMP_DATA_BURST_ENABLED and datetime.now(timezone.utc) <= _parse_utc(TEMP_DATA_BURST_END_UTC)

# Versions
CURRENT_LOGIC_VERSION = "v1.5-quant-alpha"
CURRENT_CONFIG_VERSION = "v1.5-quant-alpha"
CLASSIFIER_VERSION = "family_v2"
CURRENT_POLICY_VERSION = os.environ.get(
    "CURRENT_POLICY_VERSION",
    "phase2_data_burst_v1_familyfix" if TEMP_DATA_BURST_ACTIVE else "phase2_v1",
)
POLICY_ACTIVATED_AT = os.environ.get(
    "POLICY_ACTIVATED_AT",
    "2026-04-09T12:30:00Z" if TEMP_DATA_BURST_ACTIVE else "2026-04-09T11:11:40Z",
)

# Outcome Rules
SIGNAL_EXPIRY_DAYS = int(os.environ.get("SIGNAL_EXPIRY_DAYS", "3"))

# v1.5-quant-alpha Risk Management
RISK_PER_TRADE_USD = 50.0  # Absolute USD risk per signal

# Streaming Telemetry
SSE_AUTH_TOKEN = os.environ.get("SSE_AUTH_TOKEN", "idim_dev_token_2026")
SSE_MAX_CONNECTIONS = int(os.environ.get("SSE_MAX_CONNECTIONS", "5"))

# Database
DATABASE_URL = os.environ.get("DATABASE_URL")

# ── Operational Covenant ──────────────────────────────────────────────────
# Env validation + execution doctrine + infra health
# Triple-gate: ENABLE_LIVE_TRADING + LIVE_TRADING_UNLOCK_TOKEN + token prefix
from ops_covenant import enforce_execution_doctrine, covenant_startup, infra_health

_COVENANT_STATUS = covenant_startup()

# 2. Live Trading Toggle (v1.9.4) — Doctrine-enforced
_DOCTRINE_LIVE, _DOCTRINE_REASON = enforce_execution_doctrine()
ENABLE_LIVE_TRADING = _DOCTRINE_LIVE

# ─── Hardening Parameters ────────────────────────────────────────────────────

# 1. Accelerator Performance (v1.9.5)
SCANNER_WORKERS = int(os.environ.get("SCANNER_WORKERS", "8"))
SCANNER_CYCLE_TIMEOUT_SECONDS = int(os.environ.get("SCANNER_CYCLE_TIMEOUT_SECONDS", "45"))
SCANNER_REFRESH_UNIVERSE_MINUTES = int(os.environ.get("SCANNER_REFRESH_UNIVERSE_MINUTES", "15"))

# 3. Warmup floor: minimum bars required before a signal can be emitted
SCANNER_WARMUP_BARS = int(os.environ.get("SCANNER_WARMUP_BARS", "100"))

# 2. Data Freshness: max seconds allowed since last kline close
DATA_FRESHNESS_MAX_SECONDS = 3600  # 1 hour (conservative for 15m/4h)

# 3. Standard Rejection Reason Codes
REJECTION_REASONS = {
    "REGIME_DIRECTION_CONFLICT": "Gate 1: Against macro regime direction",
    "WARMUP_FLOOR": "Gate 7: Insufficient data accumulation (< warmup floor)",
    "DATA_STALE": "Gate 8: Stale market data (last close too old)",
    "VOL_INSUFFICIENT": "Gate 2: Low-conviction volume ratio",
    "BTC_MACD_CONFLICT": "Gate 5: BTC King's Gate macro conflict",
    "MTFA_1H_CONFLICT": "Gate 6: 1H Multi-Timeframe Alignment conflict",
    "SQUEEZE_REQUIRED": "G_sq: Bollinger/Keltner compression required",
    "VWAP_OVEREXTENDED": "G_vwap: Price too far from institutional equilibrium",
}

# ─── Data Collection for Training (v1.0) ─────────────────────────────────────
# Always-on labeled dataset generation for gating model training.
# Records both rejections and passes with market state snapshots.
DATA_COLLECTION_MODE = True
FEATURE_VERSION = "v1.1"

# ─── Family flags ───────────────────────────────────────────────────────────
ENABLE_TREND = True
ENABLE_VOLATILITY = True
ENABLE_MEAN_REVERSION = True
ENABLE_MOMENTUM = True

# Scan profile selection: live strict vs sim loose
if ENABLE_LIVE_TRADING:
    if TEMP_DATA_BURST_ACTIVE:
        # Temporary 3-day expansion mode for richer post-analysis cohorts.
        SCAN_PROFILE = "live_data_burst_v1"
        MIN_SIGNAL_SCORE = 40
        ADX_MIN_THRESHOLD = 18
        ATR_STRETCH_MAX = 1.8
        REQUIRE_SQUEEZE_GATE = True
        VOLUME_RATIO_MIN = 1.05
        VWAP_EPSILON_0 = 0.0075
        VWAP_LAMBDA = 1.10
        ENABLE_MEAN_REVERSION = False
        BLOCK_STRONG_UPTREND = False
        LIVE_ALLOWED_CELLS = {
            ("STRONG_DOWNTREND", 50), ("STRONG_DOWNTREND", 55), ("STRONG_DOWNTREND", 60),
            ("DOWNTREND", 50), ("DOWNTREND", 55), ("DOWNTREND", 60),
            ("UPTREND", 40), ("UPTREND", 45), ("UPTREND", 50),
            ("STRONG_UPTREND", 55), ("STRONG_UPTREND", 60),
            ("RANGING", 60), ("RANGING", 65),
        }
    else:
        SCAN_PROFILE = "live_strict_v1"
        MIN_SIGNAL_SCORE = 55  # Normalize baseline to 55
        ADX_MIN_THRESHOLD = 20
        ATR_STRETCH_MAX = 1.5
        REQUIRE_SQUEEZE_GATE = True
        VOLUME_RATIO_MIN = 1.2
        VWAP_EPSILON_0 = 0.006
        VWAP_LAMBDA = 1.00
        ENABLE_MEAN_REVERSION = False
        BLOCK_STRONG_UPTREND = True
        LIVE_ALLOWED_CELLS = {
            ("STRONG_DOWNTREND", 55),
            ("STRONG_UPTREND", 60),
            ("DOWNTREND", 50),
            ("UPTREND", 50),
            ("RANGING", 60),
        }
else:
    # Sim loose thresholds for data collection (permissive)
    SCAN_PROFILE = "sim_loose_v1"
    MIN_SIGNAL_SCORE = 20
    ADX_MIN_THRESHOLD = 15
    ATR_STRETCH_MAX = 2.5
    REQUIRE_SQUEEZE_GATE = False
    VOLUME_RATIO_MIN = 0.90
    VWAP_EPSILON_0 = 0.012
    VWAP_LAMBDA = 1.50
    ENABLE_MEAN_REVERSION = True
    BLOCK_STRONG_UPTREND = False
    LIVE_ALLOWED_CELLS = {
        ("STRONG_DOWNTREND", 20), ("STRONG_DOWNTREND", 25), ("STRONG_DOWNTREND", 30),
        ("STRONG_DOWNTREND", 35), ("STRONG_DOWNTREND", 40), ("STRONG_DOWNTREND", 45),
        ("STRONG_DOWNTREND", 50), ("STRONG_DOWNTREND", 55), ("STRONG_DOWNTREND", 60),
        ("STRONG_UPTREND", 20), ("STRONG_UPTREND", 25), ("STRONG_UPTREND", 30),
        ("STRONG_UPTREND", 35), ("STRONG_UPTREND", 40), ("STRONG_UPTREND", 45),
        ("STRONG_UPTREND", 50), ("STRONG_UPTREND", 55), ("STRONG_UPTREND", 60),
        ("DOWNTREND", 20), ("DOWNTREND", 25), ("DOWNTREND", 30),
        ("DOWNTREND", 35), ("DOWNTREND", 40), ("DOWNTREND", 45),
        ("DOWNTREND", 50), ("DOWNTREND", 55), ("DOWNTREND", 60),
        ("UPTREND", 20), ("UPTREND", 25), ("UPTREND", 30),
        ("UPTREND", 35), ("UPTREND", 40), ("UPTREND", 45),
        ("UPTREND", 50), ("UPTREND", 55), ("UPTREND", 60),
        ("RANGING", 20), ("RANGING", 25), ("RANGING", 30),
        ("RANGING", 35), ("RANGING", 40), ("RANGING", 45),
        ("RANGING", 50), ("RANGING", 55), ("RANGING", 60), ("RANGING", 65),
    }

# ─── Doctrine Tightenings (v1.3.1) ──────────────────────────────────────────

# 1. Regime-direction consistency: block signals against primary regime direction
BLOCK_AGAINST_REGIME = True  # LONG in DOWNTREND or SHORT in UPTREND → reject

# 1b. Phase 2 execution gating (real-data path only)
# Training coverage remains unchanged; these controls only affect final candidate survival.
BLOCK_RANGING_LONG = True

# 1c. Side-Balance Coherence (v2.0 Doctrine)
COHERENCE_WINDOW = 200
COHERENCE_STABILIZING_BAND = (0.40, 0.60)
SIDE_BALANCE_LAMBDA = 25.0  # Dynamic offset sensitivity
MAX_COHERENCE_OFFSET = 15.0 # Max penalty/boost cap to prevent over-optimization
COHERENCE_RESCUE_FLOOR = 40.0 # Min raw score required to receive a coherence boost


if TEMP_DATA_BURST_ACTIVE and ENABLE_LIVE_TRADING:
    REGIME_SIDE_MULTIPLIER = {
        "STRONG_UPTREND":   {"LONG": 1.20, "SHORT": 0.00},
        "UPTREND":          {"LONG": 1.00, "SHORT": 0.80},
        "RANGING":          {"LONG": 0.00, "SHORT": 0.90},
        "DOWNTREND":        {"LONG": 0.80, "SHORT": 1.00},
        "STRONG_DOWNTREND": {"LONG": 0.00, "SHORT": 1.20},
    }
    DEAD_HOURS_UTC = {13}
    HOUR_MULTIPLIER = {
        16: 0.85,
        17: 0.80,
    }
else:
    REGIME_SIDE_MULTIPLIER = {
        "STRONG_UPTREND":   {"LONG": 1.30, "SHORT": 0.00},
        "UPTREND":          {"LONG": 1.00, "SHORT": 0.70},
        "RANGING":          {"LONG": 0.00, "SHORT": 0.80},
        "DOWNTREND":        {"LONG": 0.70, "SHORT": 1.00},
        "STRONG_DOWNTREND": {"LONG": 0.00, "SHORT": 1.30},
    }
    DEAD_HOURS_UTC = {13}
    HOUR_MULTIPLIER = {
        16: 0.75,
        17: 0.70,
    }

# 2. Volume filter: enforced as hard gate (was advisory)
# NOTE: VOLUME_RATIO_MIN is set in the SCAN_PROFILE if/else block above

# 3. Wide stop cap: if ATR/price > 2%, reduce SL multiplier
MAX_ATR_PCT_FOR_FULL_SL = 0.02   # 2% ATR/price threshold
CAP_SL_MULTIPLIER_WHEN_WIDE = 0.7  # Use 0.7x multiplier when ATR is wide

# 4. STRONG_UPTREND internal consistency for LONGs
REQUIRE_PRICE_ABOVE_EMA_IN_STRONG_UPTREND = True
REQUIRE_RSI_ABOVE_50_IN_STRONG_UPTREND = True

# ─── Sovereign Master Equation Parameters ────────────────────────────────────
# I[A,t] = G_β · G_str · G_sq · G_vwap · G_vol · G_Ω · Q[A,t]

# G_sq: Squeeze hard gate (requires recent BB-inside-KC compression burst)
# NOTE: REQUIRE_SQUEEZE_GATE is set in the SCAN_PROFILE if/else block above

# G_vwap: Dynamic VWAP extension gate
# ε(A,t) = ε₀ + λ · ATR/Price
# NOTE: VWAP_EPSILON_0 and VWAP_LAMBDA are set in the SCAN_PROFILE if/else block above

# Q functional: Φ-normalized alpha weights (must sum to 1.0)
# Q = α₁·Φ(VRatio) + α₂·Φ(1/StopPct) + α₃·Φ(1/Rank) + α₄·Φ(1/(1+|δ|)) + α₅·Φ(Mom) + α₆·Φ(OI)
Q_ALPHA = {
    "vol_ratio":    0.25,   # Volume conviction
    "inv_stop_pct": 0.22,   # Tight stop (R:R quality)
    "inv_rank":     0.18,   # Liquidity primacy
    "vwap_prox":    0.15,   # VWAP proximity (less extension = better)
    "momentum":     0.12,   # Score as momentum proxy
    "oi_ratio":     0.08,   # Open interest conviction (future collector)
}
