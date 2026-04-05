#!/usr/bin/env python3
import os
from dotenv import load_dotenv

load_dotenv()

# Versions
CURRENT_LOGIC_VERSION = "v1.5-quant-alpha"
CURRENT_CONFIG_VERSION = "v1.5-quant-alpha"

# Outcome Rules
SIGNAL_EXPIRY_DAYS = int(os.environ.get("SIGNAL_EXPIRY_DAYS", "3"))

# Streaming Telemetry
SSE_AUTH_TOKEN = os.environ.get("SSE_AUTH_TOKEN", "idim_dev_token_2026")
SSE_MAX_CONNECTIONS = int(os.environ.get("SSE_MAX_CONNECTIONS", "5"))

# Database
DATABASE_URL = os.environ.get("DATABASE_URL")

# ─── Hardening Parameters ────────────────────────────────────────────────────

# 1. Warmup floor: minimum bars required before a signal can be emitted
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

# ─── Doctrine Tightenings (v1.3.1) ──────────────────────────────────────────

# 1. Regime-direction consistency: block signals against primary regime direction
BLOCK_AGAINST_REGIME = True  # LONG in DOWNTREND or SHORT in UPTREND → reject

# 2. Volume filter: enforced as hard gate (was advisory)
VOLUME_RATIO_MIN = 1.2  # Minimum volume ratio required to emit a signal

# 3. Wide stop cap: if ATR/price > 2%, reduce SL multiplier
MAX_ATR_PCT_FOR_FULL_SL = 0.02   # 2% ATR/price threshold
CAP_SL_MULTIPLIER_WHEN_WIDE = 0.7  # Use 0.7x multiplier when ATR is wide

# 4. STRONG_UPTREND internal consistency for LONGs
REQUIRE_PRICE_ABOVE_EMA_IN_STRONG_UPTREND = True
REQUIRE_RSI_ABOVE_50_IN_STRONG_UPTREND = True

# ─── Sovereign Master Equation Parameters ────────────────────────────────────
# I[A,t] = G_β · G_str · G_sq · G_vwap · G_vol · G_Ω · Q[A,t]

# G_sq: Squeeze hard gate (requires recent BB-inside-KC compression burst)
REQUIRE_SQUEEZE_GATE = True   # Set False to re-enable as bonus only

# G_vwap: Dynamic VWAP extension gate
# ε(A,t) = ε₀ + λ · ATR/Price
VWAP_EPSILON_0 = 0.02    # Base tolerance (2%)
VWAP_LAMBDA = 0.5        # ATR scaling factor (adds ≈ 0.5 * ATR/P to tolerance)

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
