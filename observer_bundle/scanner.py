#!/usr/bin/env python3
"""
Idim Ikang local observer scanner (v1.4 Institutional Sovereign Build).
Baseline-aligned observer for live market scanning on existing WSL2 sovereign stack.

Sovereign Master Equation:
  I[A,t] = G_beta * G_str * G_sq * G_vwap * G_vol * G_Omega * Q[A,t]

Active upgrades (all production, no mocks):
  - King's Gate (BTC Macro Alignment)           [G_beta]
  - Multi-Timeframe Alignment (1H EMA50)         [G_str]
  - Volatility Squeeze hard gate (BB/KC)         [G_sq]
  - Dynamic VWAP extension gate (epsilon=eps0+lambda*ATR/P) [G_vwap]
  - Volume conviction hard gate                  [G_vol]
  - Wolfram Five-Cell discipline filter          [G_Omega]
  - Phi-normalized Q ranking functional          [Q]
  - Connection pooling (psycopg2.pool)
  - Fire-and-forget async Telegram
  - UUID-stable candidate tracking
"""

from __future__ import annotations
import concurrent.futures
import json
import logging
import math
import os
import signal
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras

# Fix pandas FutureWarning for downcasting
pd.set_option('future.no_silent_downcasting', True)

# Custom JSON encoder for numpy types
class _NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)
import psycopg2.pool
import requests
import warnings
from dotenv import load_dotenv
from telegram_alerts import send_telegram_async

# Silence pandas noise
warnings.filterwarnings("ignore", category=FutureWarning, module="pandas")

# ─── Environment ───────────────────────────────────────────────────────────────
load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]
BINANCE_FUTURES_URL = "https://fapi.binance.com"
SCAN_INTERVAL_SECONDS = int(os.environ.get("SCAN_INTERVAL_SECONDS", "60"))
LOOKBACK_15M = int(os.environ.get("LOOKBACK_15M", "500"))
LOOKBACK_4H = int(os.environ.get("LOOKBACK_4H", "300"))

import config
import exchange_discovery

from microstructure_client import MicrostructureClient
from execution_intelligence import compute_execution_features

# Global client to ensure session re-use for fast execution snapshotting
_micro_client = MicrostructureClient()


# ─── Constants ─────────────────────────────────────────────────────────────────
LOGIC_VERSION = config.CURRENT_LOGIC_VERSION
CONFIG_VERSION = config.CURRENT_CONFIG_VERSION
POLICY_VERSION = getattr(config, "CURRENT_POLICY_VERSION", "phase2_v1")
CLASSIFIER_VERSION = getattr(config, "CLASSIFIER_VERSION", "family_v1")
POLICY_ACTIVATED_AT = getattr(config, "POLICY_ACTIVATED_AT", "2026-04-09T11:11:40Z")
UNIVERSE_REFRESH_INTERVAL = 900  # 15 minutes

MIN_SIGNAL_SCORE = config.MIN_SIGNAL_SCORE
COOLDOWN_BARS = 32
from idim_gate_patch import apply_gates
BLOCK_STRONG_UPTREND = getattr(config, "BLOCK_STRONG_UPTREND", True)
ATR_SL_MULTIPLIER = 1.0
ATR_TP_MULTIPLIER = 3.0

MAX_SIGNALS_PER_SCAN = 3
MAX_SIGNALS_PER_CELL = 1
MAX_SIGNALS_PER_SIDE = 2

# Doctrine tightenings (v1.3.1)
BLOCK_AGAINST_REGIME = config.BLOCK_AGAINST_REGIME
VOLUME_RATIO_MIN = config.VOLUME_RATIO_MIN
MAX_ATR_PCT_FOR_FULL_SL = config.MAX_ATR_PCT_FOR_FULL_SL
CAP_SL_MULTIPLIER_WHEN_WIDE = config.CAP_SL_MULTIPLIER_WHEN_WIDE
REQUIRE_PRICE_ABOVE_EMA_IN_STRONG_UPTREND = config.REQUIRE_PRICE_ABOVE_EMA_IN_STRONG_UPTREND
REQUIRE_RSI_ABOVE_50_IN_STRONG_UPTREND = config.REQUIRE_RSI_ABOVE_50_IN_STRONG_UPTREND

# Sovereign Master Equation parameters
REQUIRE_SQUEEZE_GATE = config.REQUIRE_SQUEEZE_GATE
VWAP_EPSILON_0 = config.VWAP_EPSILON_0
VWAP_LAMBDA = config.VWAP_LAMBDA
Q_ALPHA = config.Q_ALPHA

# Hardening parameters
SCANNER_WARMUP_BARS = config.SCANNER_WARMUP_BARS
DATA_FRESHNESS_MAX_SECONDS = config.DATA_FRESHNESS_MAX_SECONDS

# ─── Phase-2 FT Bridge (disabled by default) ───────────────────────────────────
BRIDGE_PHASE2_ENABLED = bool(getattr(config, "BRIDGE_PHASE2_ENABLED", False))
BRIDGE_STRATEGY_NAME = str(getattr(config, "BRIDGE_STRATEGY_NAME", "IdimSqueeze"))
BRIDGE_WEIGHT = float(getattr(config, "BRIDGE_WEIGHT", 0.15))
MAX_BRIDGE_BOOST = float(getattr(config, "MAX_BRIDGE_BOOST", 10.0))

# Signal family feature flags (multi-stack support)
ENABLE_TREND = bool(getattr(config, "ENABLE_TREND", True))
ENABLE_VOLATILITY = bool(getattr(config, "ENABLE_VOLATILITY", True))
ENABLE_MEAN_REVERSION = bool(getattr(config, "ENABLE_MEAN_REVERSION", False))
ENABLE_MOMENTUM = bool(getattr(config, "ENABLE_MOMENTUM", True))

# ─── Side-Balance Coherence Doctrine (v2.0) ──────────────────────────────────
COHERENCE_WINDOW = config.COHERENCE_WINDOW
SIDE_BALANCE_LAMBDA = config.SIDE_BALANCE_LAMBDA
MAX_COHERENCE_OFFSET = config.MAX_COHERENCE_OFFSET
COHERENCE_RESCUE_FLOOR = config.COHERENCE_RESCUE_FLOOR
SIDE_SEPARATION_MARGIN = config.SIDE_SEPARATION_MARGIN

# Profile-specific flags
COHERENCE_ENABLED = getattr(config, "COHERENCE_ENABLED", False)
SOFT_REGIME_GATE = getattr(config, "SOFT_REGIME_GATE", False)
SOFT_BTC_GATE = getattr(config, "SOFT_BTC_GATE", False)
REGIME_SOFT_PENALTY = getattr(config, "REGIME_SOFT_PENALTY", 12.0)
BTC_SOFT_PENALTY = getattr(config, "BTC_SOFT_PENALTY", 15.0)

class SideBalanceController:
    def __init__(self, window_n: int = 200):
        self.window_n = window_n
        self.history: List[str] = []  # List of "LONG" or "SHORT"
        self._lock = threading.Lock()
        self.long_share = 0.5
        self.skew = 0.0  # Positive = Long-heavy (Penalize Long, Boost Short)

    def initialize(self, conn):
        """Pre-load history from the signals table."""
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT side FROM signals ORDER BY ts DESC LIMIT %s",
                    (self.window_n,)
                )
                rows = cur.fetchall()
                with self._lock:
                    self.history = [r[0] for r in reversed(rows)]
                    self._recalc()
            logging.info(f"[COHERENCE] Initialized with {len(self.history)} signals. Share: {self.long_share:.2%} Skew: {self.skew:+.1f}")
        except Exception as e:
            logging.error(f"[COHERENCE] Init failed: {e}")

    def update(self, side: str):
        """Add new signal side and slide window."""
        with self._lock:
            self.history.append(side.upper())
            if len(self.history) > self.window_n:
                self.history.pop(0)
            self._recalc()

    def _recalc(self):
        if not self.history:
            self.long_share = 0.5
            self.skew = 0.0
            return
            
        self.long_share = self.history.count("LONG") / len(self.history)
        
        # SKEW Formula: lambda * (share - 0.5)
        # Result > 0 means Long-heavy -> Penalize Longs (-skew), Boost Shorts (+skew)
        # Result < 0 means Short-heavy -> Boost Longs (+abs_skew), Penalize Shorts (-abs_skew)
        raw_skew = SIDE_BALANCE_LAMBDA * (self.long_share - 0.5)
        self.skew = max(-MAX_COHERENCE_OFFSET, min(MAX_COHERENCE_OFFSET, raw_skew))

    def get_skew(self) -> float:
        with self._lock:
            return self.skew

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "rolling_n": len(self.history),
                "long_share": self.long_share,
                "skew": self.skew
            }

_side_controller = SideBalanceController(COHERENCE_WINDOW)

# ─── Family-Level Telemetry (per-cycle counters) ─────────────────────────────
# Tracks: family assignment counts, rejection reasons by family, gate kills
_family_telemetry = {
    "assigned": {"trend": 0, "volatility": 0, "mean_reversion": 0, "momentum": 0, "none": 0},
    "rejected_by_gate": {
        "min_score": {"trend": 0, "volatility": 0, "mean_reversion": 0, "momentum": 0, "none": 0},
        "squeeze": {"trend": 0, "volatility": 0, "mean_reversion": 0, "momentum": 0, "none": 0},
        "vwap": {"trend": 0, "volatility": 0, "mean_reversion": 0, "momentum": 0, "none": 0},
        "volume": {"trend": 0, "volatility": 0, "mean_reversion": 0, "momentum": 0, "none": 0},
        "exhaustion": {"trend": 0, "volatility": 0, "mean_reversion": 0, "momentum": 0, "none": 0},
        "1h_trend": {"trend": 0, "volatility": 0, "mean_reversion": 0, "momentum": 0, "none": 0},
        "btc_block": {"trend": 0, "volatility": 0, "mean_reversion": 0, "momentum": 0, "none": 0},
        "regime_block": {"trend": 0, "volatility": 0, "mean_reversion": 0, "momentum": 0, "none": 0},
    },
    "passed": {"trend": 0, "volatility": 0, "mean_reversion": 0, "momentum": 0, "none": 0},
    "short_attrition": {
        "short_emitted": 0,
        "short_near_miss_lt5": 0,
        "short_near_miss_lt10": 0,
        "short_killed_by_gate": 0,
        "short_floor_denied": 0,
        "short_template_zero": 0,
    }
}
_telemetry_lock = threading.Lock()


def _reset_family_telemetry():
    """Reset counters at start of each scan cycle."""
    global _family_telemetry
    with _telemetry_lock:
        _family_telemetry = {
            "assigned": {"trend": 0, "volatility": 0, "mean_reversion": 0, "momentum": 0, "failed_bounce": 0, "breakdown": 0, "none": 0},
            "rejected_by_gate": {
                "min_score": {"trend": 0, "volatility": 0, "mean_reversion": 0, "momentum": 0, "failed_bounce": 0, "breakdown": 0, "none": 0},
                "squeeze": {"trend": 0, "volatility": 0, "mean_reversion": 0, "momentum": 0, "failed_bounce": 0, "breakdown": 0, "none": 0},
                "vwap": {"trend": 0, "volatility": 0, "mean_reversion": 0, "momentum": 0, "failed_bounce": 0, "breakdown": 0, "none": 0},
                "volume": {"trend": 0, "volatility": 0, "mean_reversion": 0, "momentum": 0, "failed_bounce": 0, "breakdown": 0, "none": 0},
                "exhaustion": {"trend": 0, "volatility": 0, "mean_reversion": 0, "momentum": 0, "failed_bounce": 0, "breakdown": 0, "none": 0},
                "1h_trend": {"trend": 0, "volatility": 0, "mean_reversion": 0, "momentum": 0, "failed_bounce": 0, "breakdown": 0, "none": 0},
                "btc_block": {"trend": 0, "volatility": 0, "mean_reversion": 0, "momentum": 0, "failed_bounce": 0, "breakdown": 0, "none": 0},
                "regime_block": {"trend": 0, "volatility": 0, "mean_reversion": 0, "momentum": 0, "failed_bounce": 0, "breakdown": 0, "none": 0},
            },
            "passed": {"trend": 0, "volatility": 0, "mean_reversion": 0, "momentum": 0, "failed_bounce": 0, "breakdown": 0, "none": 0},
            "short_attrition": {
                "short_emitted": 0,
                "short_near_miss_lt5": 0,
                "short_near_miss_lt10": 0,
                "short_killed_by_gate": 0,
                "short_floor_denied": 0,
                "short_template_zero": 0,
            }
        }


def _log_family_telemetry():
    """Log family-level telemetry summary."""
    with _telemetry_lock:
        total_assigned = sum(_family_telemetry["assigned"].values())
        if total_assigned == 0:
            return
        
        # Build telemetry summary
        lines = ["[FAMILY TELEMETRY] ============================================"]
        lines.append(f"Total symbols classified: {total_assigned}")
        
        # SPRINT B: Output Short Attrition
        attr = _family_telemetry.get("short_attrition", {})
        attr_log = (
            f"  SHORT_ATTR: Emitted={attr.get('short_emitted', 0)} | "
            f"Miss<5={attr.get('short_near_miss_lt5', 0)} | "
            f"Miss<10={attr.get('short_near_miss_lt10', 0)} | "
            f"GateKilled={attr.get('short_killed_by_gate', 0)} | "
            f"FloorDenied={attr.get('short_floor_denied', 0)} | "
            f"TemplateZero={attr.get('short_template_zero', 0)}"
        )
        lines.append(attr_log)
        
        for family in ["trend", "volatility", "mean_reversion", "momentum", "none"]:
            assigned = _family_telemetry["assigned"][family]
            if assigned == 0:
                continue
            passed = _family_telemetry["passed"][family]
            lines.append(f"\n  {family.upper()}: assigned={assigned}, passed={passed}, killed={assigned-passed}")
            
            # Show rejection breakdown
            for gate, counts in _family_telemetry["rejected_by_gate"].items():
                if counts[family] > 0:
                    lines.append(f"    - killed by {gate}: {counts[family]}")
        
        lines.append("================================================================")
        logger.info("\n".join(lines))


_bridge_instance = None
_bridge_lock = threading.Lock()


def _get_ft_bridge():
    """
    Lazy-load a single bridge instance.
    Keeps scanner behavior unchanged when BRIDGE_PHASE2_ENABLED=False.
    """
    global _bridge_instance

    if not BRIDGE_PHASE2_ENABLED:
        return None

    if _bridge_instance is not None:
        return _bridge_instance

    with _bridge_lock:
        if _bridge_instance is None:
            try:
                from .ft_bridge import create_bridge
            except ImportError:
                from ft_bridge import create_bridge
            _bridge_instance = create_bridge(BRIDGE_STRATEGY_NAME)

    return _bridge_instance


def _merge_phase2_bridge_bonus(
    *,
    side: str,
    native_score: float,
    native_trace: Dict[str, Any],
    df15: pd.DataFrame,
    regime: str,
    alpha: Dict[str, Any],
    signal_family: str = "none",
) -> Tuple[float, Dict[str, Any]]:
    """
    Evaluate FT bridge in Phase 2 and merge a bounded bonus only AFTER
    native Phase-2 re-score. This prevents FT from reviving a native zero.
    Applies family-specific weighting for multi-stack support.
    """
    if not BRIDGE_PHASE2_ENABLED or native_score <= 0:
        return native_score, native_trace

    bridge = _get_ft_bridge()
    if bridge is None:
        return native_score, native_trace

    try:
        bridge_score, bridge_trace = bridge.evaluate_signal(df15, regime, alpha)
    except Exception:
        logger.exception("FT_BRIDGE_EVAL_ERROR side=%s regime=%s", side, regime)
        return native_score, native_trace

    bridge_trace = bridge_trace or {}
    ft_signals = bridge_trace.get("freqtrade_signals", {}) or {}

    enter_long = int(ft_signals.get("enter_long", 0) or 0)
    enter_short = int(ft_signals.get("enter_short", 0) or 0)

    matched = (
        (side == "LONG" and enter_long == 1) or
        (side == "SHORT" and enter_short == 1)
    )

    # Family-specific weight for multi-stack support
    family_weight = FAMILY_WEIGHTS.get(signal_family, 1.0)

    merged_trace = dict(native_trace or {})
    merged_trace["bridge"] = {
        "enabled": True,
        "strategy": BRIDGE_STRATEGY_NAME,
        "bridge_score": float(bridge_score or 0.0),
        "freqtrade_signals": ft_signals,
        "matched": matched,
        "weight": BRIDGE_WEIGHT,
        "family_weight": family_weight,
        "signal_family": signal_family,
        "max_boost": MAX_BRIDGE_BOOST,
    }

    if not matched:
        return native_score, merged_trace

    raw_bonus = max(float(bridge_score or 0.0), 0.0) * BRIDGE_WEIGHT * family_weight
    bonus = min(raw_bonus, MAX_BRIDGE_BOOST)

    merged_trace["bridge"]["raw_bonus"] = raw_bonus
    merged_trace["bridge"]["applied_bonus"] = bonus

    logger.info(
        "FT_BRIDGE_BONUS sym=%s side=%s native=%.2f bridge=%.2f bonus=%.2f",
        merged_trace.get("symbol", "n/a"),
        side,
        native_score,
        float(bridge_score or 0.0),
        bonus,
    )

    return native_score + bonus, merged_trace

# ─── State ─────────────────────────────────────────────────────────────────────
PAIRS: List[str] = []
_LAST_UNIVERSE_REFRESH: float = 0
_STOP = False
_LAST_SIGNAL: Optional[dict] = None
_START_TS = time.time()
_LAST_SCAN_TS: Optional[float] = None
_LAST_SCAN_GAP_SECONDS: Optional[float] = None

# ─── Logging ───────────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
os.makedirs("logs", exist_ok=True)
_fh = RotatingFileHandler("logs/scanner.log", maxBytes=100 * 1024 * 1024, backupCount=7)
_fh.setFormatter(_fmt)
logger.addHandler(_fh)

# --- Add StreamHandler for PM2 console capture ---
_sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(_fmt)
logger.addHandler(_sh)

# ─── Signal handling ───────────────────────────────────────────────────────────
def handle_stop(signum, frame):
    global _STOP
    _STOP = True

signal.signal(signal.SIGTERM, handle_stop)
signal.signal(signal.SIGINT, handle_stop)

# ─── Connection pool ───────────────────────────────────────────────────────────
_db_pool: Optional[psycopg2.pool.SimpleConnectionPool] = None

def _init_pool() -> None:
    global _db_pool
    _db_pool = psycopg2.pool.SimpleConnectionPool(1, 10, DATABASE_URL)


def _ensure_training_table() -> None:
    """Auto-create training_candidates table if it doesn't exist."""
    CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS training_candidates (
        id BIGSERIAL PRIMARY KEY,
        ts TIMESTAMPTZ DEFAULT NOW(),
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        scan_profile TEXT NOT NULL,
        feature_version TEXT NOT NULL,
        signal_family TEXT,
        gate_profile JSONB,
        rejection_gate TEXT,
        would_have_passed_live BOOLEAN,
        regime TEXT,
        btc_regime TEXT,
        close_price NUMERIC,
        adx14 NUMERIC,
        rsi14 NUMERIC,
        atr_stretch NUMERIC,
        squeeze_on BOOLEAN,
        squeeze_fired BOOLEAN,
        vol_ratio NUMERIC,
        funding_rate NUMERIC,
        ls_ratio NUMERIC,
        score NUMERIC,
        outcome_label TEXT,
        outcome_pct NUMERIC,
        mae_pct NUMERIC,
        mfe_pct NUMERIC,
        horizon_bars INT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """
    INDEXES_SQL = """
    CREATE INDEX IF NOT EXISTS idx_training_candidates_symbol_ts ON training_candidates (symbol, ts DESC);
    CREATE INDEX IF NOT EXISTS idx_training_candidates_scan_profile ON training_candidates (scan_profile, ts DESC);
    CREATE INDEX IF NOT EXISTS idx_training_candidates_signal_family ON training_candidates (signal_family, ts DESC);
    CREATE INDEX IF NOT EXISTS idx_training_candidates_rejection_gate ON training_candidates (rejection_gate, ts DESC) WHERE rejection_gate IS NOT NULL;
    CREATE INDEX IF NOT EXISTS idx_training_candidates_outcome_label ON training_candidates (outcome_label, ts DESC) WHERE outcome_label IS NOT NULL;
    """
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute(CREATE_SQL)
            cur.execute(INDEXES_SQL)
            conn.commit()
            logger.info("[TRAINING_TABLE] Verified training_candidates table exists")
    except Exception as e:
        logger.warning(f"[TRAINING_TABLE] Could not create table: {e}")
    finally:
        if conn:
            conn.close()

def _ensure_signal_measurement_schema() -> None:
    """Ensure first-class execution context columns and calibration view exist on `signals`."""
    ALTER_SQL = """
    ALTER TABLE signals ADD COLUMN IF NOT EXISTS market_regime TEXT;
    ALTER TABLE signals ADD COLUMN IF NOT EXISTS btc_regime TEXT;
    ALTER TABLE signals ADD COLUMN IF NOT EXISTS signal_hour_utc INT;
    ALTER TABLE signals ADD COLUMN IF NOT EXISTS phase2_gate TEXT;
    ALTER TABLE signals ADD COLUMN IF NOT EXISTS phase2_allowed BOOLEAN;
    ALTER TABLE signals ADD COLUMN IF NOT EXISTS phase2_score_multiplier NUMERIC;
    ALTER TABLE signals ADD COLUMN IF NOT EXISTS setup_score NUMERIC;
    ALTER TABLE signals ADD COLUMN IF NOT EXISTS execution_score NUMERIC;
    ALTER TABLE signals ADD COLUMN IF NOT EXISTS policy_version TEXT;
    ALTER TABLE signals ADD COLUMN IF NOT EXISTS policy_activated_at TIMESTAMPTZ;
    """
    INDEXES_SQL = """
    CREATE INDEX IF NOT EXISTS idx_signals_policy_version_ts ON signals (policy_version, ts DESC);
    CREATE INDEX IF NOT EXISTS idx_signals_market_context ON signals (market_regime, side, signal_hour_utc, ts DESC);
    CREATE INDEX IF NOT EXISTS idx_signals_btc_regime_ts ON signals (btc_regime, ts DESC);
    """
    VIEW_SQL = """
    CREATE OR REPLACE VIEW signal_context_calibration AS
    WITH base AS (
        SELECT
            COALESCE(policy_version, 'legacy') AS policy_version,
            COALESCE(market_regime, regime) AS market_regime,
            side,
            signal_hour_utc,
            COALESCE(btc_regime, NULLIF(reason_trace->>'btc_regime', ''), 'UNKNOWN') AS btc_regime,
            COALESCE(phase2_gate, NULLIF(reason_trace->>'phase2_gate', ''), 'allowed') AS phase2_gate,
            COALESCE(phase2_allowed, (reason_trace->>'phase2_allowed')::boolean, TRUE) AS phase2_allowed,
            outcome,
            r_multiple
        FROM signals
        WHERE outcome IS NOT NULL
    )
    SELECT
        policy_version,
        market_regime,
        side,
        signal_hour_utc,
        btc_regime,
        phase2_gate,
        phase2_allowed,
        COUNT(*) AS trades,
        SUM(CASE WHEN UPPER(outcome) IN ('WIN', 'LIVE_WIN', 'PARTIAL_WIN', 'LIVE_PARTIAL') THEN 1 ELSE 0 END) AS wins,
        SUM(CASE WHEN UPPER(outcome) IN ('LOSS', 'LIVE_LOSS') THEN 1 ELSE 0 END) AS losses,
        ROUND((AVG(CASE WHEN UPPER(outcome) IN ('WIN', 'LIVE_WIN', 'PARTIAL_WIN', 'LIVE_PARTIAL') THEN 1.0 ELSE 0.0 END) * 100)::numeric, 1) AS win_rate_pct,
        ROUND(AVG(r_multiple)::numeric, 4) AS avg_r,
        ROUND(AVG(CASE WHEN UPPER(outcome) IN ('WIN', 'LIVE_WIN', 'PARTIAL_WIN', 'LIVE_PARTIAL') THEN r_multiple END)::numeric, 4) AS avg_win_r,
        ROUND(ABS(AVG(CASE WHEN UPPER(outcome) IN ('LOSS', 'LIVE_LOSS') THEN r_multiple END))::numeric, 4) AS avg_loss_r_abs,
        ROUND((
            COALESCE(AVG(CASE WHEN UPPER(outcome) IN ('WIN', 'LIVE_WIN', 'PARTIAL_WIN', 'LIVE_PARTIAL') THEN r_multiple END), 0)
            * AVG(CASE WHEN UPPER(outcome) IN ('WIN', 'LIVE_WIN', 'PARTIAL_WIN', 'LIVE_PARTIAL') THEN 1.0 ELSE 0.0 END)
            -
            COALESCE(ABS(AVG(CASE WHEN UPPER(outcome) IN ('LOSS', 'LIVE_LOSS') THEN r_multiple END)), 0)
            * (1 - AVG(CASE WHEN UPPER(outcome) IN ('WIN', 'LIVE_WIN', 'PARTIAL_WIN', 'LIVE_PARTIAL') THEN 1.0 ELSE 0.0 END))
        )::numeric, 4) AS expectancy_r
    FROM base
    GROUP BY policy_version, market_regime, side, signal_hour_utc, btc_regime, phase2_gate, phase2_allowed;
    """
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute(ALTER_SQL)
            cur.execute(INDEXES_SQL)
            cur.execute(VIEW_SQL)
            conn.commit()
            logger.info("[SIGNAL_SCHEMA] Verified measurement columns and calibration view on signals")
    except Exception as e:
        logger.warning(f"[SIGNAL_SCHEMA] Could not ensure signal measurement schema: {e}")
    finally:
        if conn:
            conn.close()


def _get_conn():
    return _db_pool.getconn()

def _put_conn(conn) -> None:
    _db_pool.putconn(conn)

def db_conn():
    """Direct connection — used only inside scan_once advisory lock block."""
    return psycopg2.connect(DATABASE_URL)


# ─── Training Data Collection ─────────────────────────────────────────────────
def log_training_candidate(
    conn,
    symbol: str,
    side: str,
    latest: pd.Series,
    regime: str,
    btc_regime: str,
    score: float,
    rejection_gate: Optional[str],
    would_have_passed_live: bool,
    signal_family: str = "none",
    alpha: Optional[Dict] = None,
    scan_profile: str = "default",
    feature_version: str = "v1.0",
    family_indicators: Optional[Dict] = None,
    trace: Optional[Dict] = None,
    # NEW directional fields
    directional_long_score: Optional[float] = None,
    directional_short_score: Optional[float] = None,
    directional_net: Optional[float] = None,
    directional_margin: Optional[float] = None,
    directional_primary_side: Optional[str] = None,
) -> Optional[int]:
    """
    Record a training candidate with market state snapshot and return its row id.
    Called for both rejected (score=0) and passed signals.
    """
    if not getattr(config, 'DATA_COLLECTION_MODE', True):
        return None

    try:
        # Build gate profile snapshot (convert numpy types to native Python)
        gate_profile = {
            "min_signal_score": float(config.MIN_SIGNAL_SCORE),
            "adx_min_threshold": float(getattr(config, 'ADX_MIN_THRESHOLD', 20)),
            "atr_stretch_max": float(getattr(config, 'ATR_STRETCH_MAX', 1.5)),
            "require_squeeze_gate": bool(config.REQUIRE_SQUEEZE_GATE),
            "volume_ratio_min": float(config.VOLUME_RATIO_MIN),
            "block_against_regime": bool(config.BLOCK_AGAINST_REGIME),
        }

        # Calculate ATR stretch (distance from EMA in ATRs)
        atr_val = float(latest.get("atr14", 0))
        ema20 = float(latest.get("ema20", 0))
        close_price = float(latest.get("close", 0))
        atr_stretch = abs(close_price - ema20) / atr_val if atr_val > 0 else 0

        # Extract indicators (ensure native Python types)
        adx14 = float(latest.get("adx14", 0))
        rsi14 = float(latest.get("rsi14", 0))
        squeeze_on = bool(latest.get("squeeze_on", False))
        squeeze_fired = bool(latest.get("squeeze_fired", False))
        vol_ratio = float(latest.get("volume_ratio", 0))

        # Get derivatives alpha if available
        funding_rate = float(alpha.get("funding_rate", 0)) if alpha else 0
        ls_ratio = float(alpha.get("ls_ratio", 1.0)) if alpha else 1.0

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO training_candidates (
                    symbol, side, scan_profile, feature_version, signal_family, gate_profile,
                    rejection_gate, would_have_passed_live,
                    regime, btc_regime, close_price, adx14, rsi14, atr_stretch,
                    squeeze_on, squeeze_fired, vol_ratio, funding_rate, ls_ratio, score,
                    family_indicators, trace_data,
                    directional_long_score, directional_short_score, directional_net,
                    directional_margin, directional_primary_side
                ) VALUES (
                    %s, %s, %s, %s, %s, %s::jsonb,
                    %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s::jsonb, %s::jsonb,
                    %s, %s, %s, %s, %s
                )
                RETURNING id
                """,
                (
                    symbol, side, scan_profile, feature_version,
                    signal_family, json.dumps(gate_profile, cls=_NumpyEncoder),
                    rejection_gate, would_have_passed_live,
                    regime, btc_regime, close_price, adx14, rsi14, atr_stretch,
                    squeeze_on, squeeze_fired, vol_ratio, funding_rate, ls_ratio, score,
                    json.dumps(family_indicators or {}, cls=_NumpyEncoder),
                    json.dumps(trace or {}, cls=_NumpyEncoder),
                    directional_long_score,
                    directional_short_score,
                    directional_net,
                    directional_margin,
                    directional_primary_side,
                ),
            )
            row = cur.fetchone()
            return int(row[0]) if row else None
    except Exception as e:
        logger.warning(f"[TRAINING_LOG_ERROR] {symbol}: {e}")
        return None


def _update_training_candidate_phase2_metadata(
    conn,
    symbol: str,
    side: str,
    trace: Optional[Dict] = None,
    rejection_gate: Optional[str] = None,
    final_score: Optional[float] = None,
    would_have_passed_live: Optional[bool] = None,
    training_candidate_id: Optional[int] = None,
) -> None:
    """Attach Phase 2 execution metadata to the exact training row for this symbol/side."""
    if not getattr(config, 'DATA_COLLECTION_MODE', True):
        return

    try:
        with conn.cursor() as cur:
            if training_candidate_id is not None:
                cur.execute(
                    """
                    UPDATE training_candidates
                    SET rejection_gate = COALESCE(%s, rejection_gate),
                        would_have_passed_live = COALESCE(%s, would_have_passed_live),
                        score = COALESCE(%s, score),
                        trace_data = COALESCE(trace_data, '{}'::jsonb) || %s::jsonb
                    WHERE id = %s
                    """,
                    (
                        rejection_gate,
                        would_have_passed_live,
                        final_score,
                        json.dumps(trace or {}, cls=_NumpyEncoder),
                        training_candidate_id,
                    ),
                )
            else:
                cur.execute(
                    """
                    UPDATE training_candidates
                    SET rejection_gate = COALESCE(%s, rejection_gate),
                        would_have_passed_live = COALESCE(%s, would_have_passed_live),
                        score = COALESCE(%s, score),
                        trace_data = COALESCE(trace_data, '{}'::jsonb) || %s::jsonb
                    WHERE id = (
                        SELECT id
                        FROM training_candidates
                        WHERE symbol = %s AND side = %s
                        ORDER BY id DESC
                        LIMIT 1
                    )
                    """,
                    (
                        rejection_gate,
                        would_have_passed_live,
                        final_score,
                        json.dumps(trace or {}, cls=_NumpyEncoder),
                        symbol,
                        side,
                    ),
                )
            if cur.rowcount == 0:
                logger.warning(
                    "[TRAINING_PHASE2_UPDATE_MISS] No training row matched for %s %s (id=%s)",
                    symbol,
                    side,
                    training_candidate_id,
                )
    except Exception as e:
        logger.warning(f"[TRAINING_PHASE2_UPDATE_ERROR] {symbol} {side}: {e}")


# ─── Infrastructure ────────────────────────────────────────────────────────────
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def log_event(level: str, component: str, event: str, details: dict) -> None:
    """Pooled, exception-safe log write."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO system_logs(level, component, event, details) "
                "VALUES (%s, %s, %s, %s::jsonb)",
                (level, component, event, json.dumps(details, cls=_NumpyEncoder)),
            )
            conn.commit()
    except Exception as err:
        print(f"[log_event error] {err}", flush=True)
    finally:
        _put_conn(conn)

def send_telegram(message: str, reply_markup: Optional[dict] = None) -> None:
    """Dispatch Telegram alerts without blocking the scan loop."""
    send_telegram_async(
        message,
        reply_markup=reply_markup,
        context="scanner",
        logger=logging.getLogger(__name__),
    )

def alert_system_error(component: str, error_type: str, error_msg: str, details: dict = None) -> None:
    """Send critical system error alerts to Telegram."""
    alert_msg = f"""
<b> SYSTEM ERROR ALERT</b>
<b>Component:</b> {component}
<b>Type:</b> {error_type}
<b>Message:</b> {_escape_html(str(error_msg))}
<b>Time:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
    if details:
        alert_msg += f"\n<b>Details:</b>\n<pre>{_escape_html(str(details))}</pre>"
    
    send_telegram(alert_msg)

def alert_operational_event(event_type: str, message: str, metrics: dict = None) -> None:
    """Send operational event alerts to Telegram."""
    alert_msg = f"""
<b> OPERATIONAL EVENT</b>
<b>Type:</b> {event_type}
<b>Message:</b> {_escape_html(message)}
<b>Time:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
    if metrics:
        metrics_str = "\n".join([f"  {k}: {v}" for k, v in metrics.items()])
        alert_msg += f"\n<b>Metrics:</b>\n<pre>{_escape_html(metrics_str)}</pre>"
    
    send_telegram(alert_msg)

def _escape_html(text: str) -> str:
    """Escape special characters for Telegram HTML."""
    import html
    return html.escape(str(text))

def format_sovereign_alert(sig: dict) -> Tuple[str, dict]:
    """Generate a Telegram-compatible HTML alert with a standard inline keyboard."""
    mode_text = "LIVE" if config.ENABLE_LIVE_TRADING else "SIMULATION"
    training_status = "DATA COLLECTION" if getattr(config, 'DATA_COLLECTION_MODE', False) else "NO DATA"
    signal_family_raw = str(sig.get('signal_family', 'none'))
    signal_family = _escape_html(signal_family_raw)
    scan_profile = _escape_html(sig.get('scan_profile', config.SCAN_PROFILE))
    btc_regime = _escape_html(sig.get('btc_regime', 'UNKNOWN'))
    family_emoji = {
        'trend': '',
        'volatility': '',
        'mean_reversion': '',
        'momentum': '',
        'none': '',
    }.get(signal_family_raw, '')

    html = [
        f"<b>IDIM-IKANG SOVEREIGN SIGNAL [{_escape_html(sig['logic_version'])}]</b>",
        f"<b>{_escape_html(mode_text)} MODE</b> | {_escape_html(training_status)}",
        f"<b>Profile:</b> {scan_profile} | <b>Feature:</b> {_escape_html(config.FEATURE_VERSION)}",
        f"<b>{_escape_html(sig['pair'])} | {_escape_html(sig['side'])}</b>",
        f"<i>Score: {_escape_html(sig['score'])} | Regime: {_escape_html(sig['regime'])} | BTC: {btc_regime}</i>",
        "",
        f"<b>Entry:</b> <code>{float(sig['entry']):.4f}</code>",
        f"<b>Stop:</b> <code>{float(sig['stop_loss']):.4f}</code>",
        f"<b>TP1 (Scale-out):</b> <code>{float(sig['tp1']):.4f}</code>",
        f"<b>TP2 (Runner):</b> <code>{float(sig['tp2']):.4f}</code>",
        "",
        f"<b>Family:</b> {family_emoji} {signal_family.upper()}",
        f"<b>Thresholds:</b> Score&gt;{_escape_html(config.MIN_SIGNAL_SCORE)} | ATR&lt;{_escape_html(config.ATR_STRETCH_MAX)} | Vol&gt;{_escape_html(config.VOLUME_RATIO_MIN)}",
        f"<b>Squeeze Gate:</b> {'ENABLED' if config.REQUIRE_SQUEEZE_GATE else 'DISABLED'}",
        "",
    ]

    trace = sig.get('reason_trace', {})
    gates = [
        ("G_sq", trace.get('recent_squeeze_fire', False)),
        ("G_vwap", abs(sig.get('vwap_delta', 0)) < 0.03),
        ("G_vol", (trace.get('volume_ratio', 0) or 0) >= config.VOLUME_RATIO_MIN),
        ("G_alpha", (trace.get('derivatives_bonus', 0) or 0) > 0),
    ]
    gate_str = " | ".join([f"{'PASS' if passed else 'MISS'} {name}" for name, passed in gates])
    html.append(f"<b>GATES:</b> {gate_str}")
    html.append("")

    if getattr(config, 'DATA_COLLECTION_MODE', False):
        html.extend([
            "<b>TRAINING CONTEXT</b>",
            "<i>All candidates logged to training_candidates table</i>",
            "<i>Market state snapshot captured for ML</i>",
            "",
        ])

    ts_value = sig['ts']
    ts_str = ts_value.strftime('%Y-%m-%d %H:%M:%S UTC') if hasattr(ts_value, 'strftime') else str(ts_value)
    html.extend([
        f"<pre>Executed: {_escape_html(ts_str)}</pre>",
        f"<pre>Logic: {_escape_html(sig['logic_version'])} | Config: {_escape_html(sig['config_version'])}</pre>",
        "<b>MoStar Industries</b> | <i>African Flame Initiative</i>",
    ])

    markup = {
        "inline_keyboard": [
            [
                {"text": f"{mode_text} DASHBOARD", "url": "https://idim-dashboard.internal"},
                {"text": "CHART", "url": f"https://www.tradingview.com/chart/?symbol=BINANCE:{sig['pair']}.P"},
            ],
            [
                {"text": str(config.SCAN_PROFILE).upper(), "url": "https://idim-dashboard.internal/profiles"},
                {"text": signal_family_raw.upper(), "url": "https://idim-dashboard.internal/families"},
            ],
        ]
    }

    return "\n".join(html), markup


def _get_execution_hour_utc(latest: pd.Series) -> int:
    ts = latest["close_time"]
    if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
        if hasattr(ts, "tz_convert"):
            return int(ts.tz_convert("UTC").hour)
        return int(ts.astimezone(timezone.utc).hour)
    return int(ts.hour)


def _execution_regime_time_adjustment(regime: str, side: str, latest: pd.Series) -> tuple[bool, float, Optional[str]]:
    """
    Phase-2-only execution control.
    Returns (blocked, multiplier, rejection_gate).
    """
    side = side.upper()
    hour_utc = _get_execution_hour_utc(latest)

    # Hard block: RANGING LONG
    if getattr(config, "BLOCK_RANGING_LONG", True):
        if regime == "RANGING" and side == "LONG":
            return True, 0.0, "phase2_ranging_long_block"

    # Hard block: dead hours
    if hour_utc in getattr(config, "DEAD_HOURS_UTC", set()):
        return True, 0.0, f"phase2_dead_hour_{hour_utc}"

    regime_mult = (
        getattr(config, "REGIME_SIDE_MULTIPLIER", {})
        .get(regime, {})
        .get(side, 1.0)
    )

    if regime_mult <= 0.0:
        return True, 0.0, f"phase2_regime_side_block_{regime}_{side}"

    hour_mult = getattr(config, "HOUR_MULTIPLIER", {}).get(hour_utc, 1.0)
    return False, float(regime_mult) * float(hour_mult), None


def _annotate_phase2_context(
    candidate: Dict[str, Any],
    *,
    phase2_allowed: bool,
    phase2_gate: Optional[str],
    phase2_score_multiplier: float,
    execution_score: Optional[float] = None,
) -> None:
    """Attach first-class measurement fields to the candidate and its trace."""
    candidate.setdefault("reason_trace", {})
    setup_score = float(candidate.get("raw_score", candidate.get("score", 0.0)))
    if execution_score is None:
        execution_score = float(candidate.get("score", 0.0))

    candidate["setup_score"] = setup_score
    candidate["execution_score"] = float(execution_score)
    candidate["signal_hour_utc"] = int(candidate.get("reason_trace", {}).get("execution_hour_utc", _get_execution_hour_utc(candidate["latest"])))
    candidate["market_regime"] = candidate.get("regime")
    candidate["phase2_gate"] = phase2_gate
    candidate["phase2_allowed"] = bool(phase2_allowed)
    candidate["phase2_score_multiplier"] = float(phase2_score_multiplier)
    candidate["policy_version"] = POLICY_VERSION
    candidate["policy_activated_at"] = POLICY_ACTIVATED_AT

    candidate["reason_trace"]["market_regime"] = candidate.get("regime")
    candidate["reason_trace"]["btc_regime"] = candidate.get("btc_regime", "UNKNOWN")
    candidate["reason_trace"]["setup_score"] = setup_score
    candidate["reason_trace"]["execution_score"] = float(execution_score)
    candidate["reason_trace"]["phase2_allowed"] = bool(phase2_allowed)
    candidate["reason_trace"]["phase2_gate"] = phase2_gate
    candidate["reason_trace"]["phase2_score_multiplier"] = float(phase2_score_multiplier)
    candidate["reason_trace"]["policy_version"] = POLICY_VERSION
    candidate["reason_trace"]["classifier_version"] = CLASSIFIER_VERSION
    candidate["reason_trace"]["policy_activated_at"] = POLICY_ACTIVATED_AT


def fetch_klines(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    url = f"{BINANCE_FUTURES_URL}/fapi/v1/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    from ops_covenant import resilient_get, infra_health
    r = resilient_get(url, params=params, timeout=20, max_retries=3)
    if r is None:
        raise ConnectionError(f"fetch_klines failed after retries: {symbol} {interval}")
    r.raise_for_status()
    cols = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "num_trades",
        "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore",
    ]
    df = pd.DataFrame(r.json(), columns=cols)
    numeric_columns = (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_asset_volume",
        "num_trades",
        "taker_buy_base_asset_volume",
        "taker_buy_quote_asset_volume",
    )
    for c in numeric_columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df[list(numeric_columns)] = df[list(numeric_columns)].fillna(0.0)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    # Finalised candles only
    now_ms = int(time.time() * 1000)
    df = df[df["close_time"].astype("int64") // 10 ** 6 <= now_ms].copy()
    return df.reset_index(drop=True)

# ─── Technical indicators ──────────────────────────────────────────────────────
def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)

def macd_hist(series: pd.Series) -> pd.Series:
    m = ema(series, 12) - ema(series, 26)
    return m - ema(m, 9)

def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    res = df.copy()
    prev_close = res["close"].shift(1)
    tr = pd.concat([
        res["high"] - res["low"],
        (res["high"] - prev_close).abs(),
        (res["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    up_move = res["high"] - res["high"].shift(1)
    down_move = res["low"].shift(1) - res["low"]
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    atr_s = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm).ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr_s
    minus_di = 100 * pd.Series(minus_dm).ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr_s
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean().fillna(0)

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ema20"] = ema(out["close"], 20)
    out["ema50"] = ema(out["close"], 50)
    out["adx14"] = adx(out, 14)
    out["rsi14"] = rsi(out["close"], 14)
    out["macd_hist"] = macd_hist(out["close"])
    out["atr14"] = atr(out, 14)
    out["volume_sma20"] = out["volume"].rolling(20).mean()

    # ── TTM Squeeze (BB inside KC = energy coiling) ────────────────────────
    out["sma20"] = out["close"].rolling(20).mean()
    out["std20"] = out["close"].rolling(20).std()
    out["bb_upper"] = out["sma20"] + 2 * out["std20"]
    out["bb_lower"] = out["sma20"] - 2 * out["std20"]
    out["kc_upper"] = out["ema20"] + 1.5 * out["atr14"]
    out["kc_lower"] = out["ema20"] - 1.5 * out["atr14"]
    out["squeeze_on"] = (out["bb_upper"] < out["kc_upper"]) & (out["bb_lower"] > out["kc_lower"])
    out["squeeze_fired"] = out["squeeze_on"].shift(1).fillna(False) & ~out["squeeze_on"]
    out["recent_squeeze_fire"] = out["squeeze_fired"].rolling(window=3).max().fillna(0).astype(bool)
    # Directional squeeze fire flags (Sprint C)
    out["fire_bullish"] = out["squeeze_fired"] & (out["close"] > out["open"])
    out["fire_bearish"] = out["squeeze_fired"] & (out["close"] < out["open"])
    out["recent_squeeze_fire_long"]  = out["fire_bullish"].rolling(window=3).max().fillna(0).astype(bool)
    out["recent_squeeze_fire_short"] = out["fire_bearish"].rolling(window=3).max().fillna(0).astype(bool)

    # ── Institutional Daily VWAP (resets at UTC midnight) ─────────────────
    _date = out["open_time"].dt.date
    _typ = (out["high"] + out["low"] + out["close"]) / 3
    _pv = _typ * out["volume"]
    out["vwap"] = (
        _pv.groupby(_date).cumsum()
        / out["volume"].groupby(_date).cumsum().replace(0, np.nan)
    ).fillna(out["close"])

    # CVD Lite (Rolling Session Pressure — Sprint C)
    # Replace cumulative CVD with short-window flow pressure.
    # cumsum() carries stale history; 4-bar rolling measures *current* buyer/seller aggression.
    out["taker_sell"] = out["volume"] - out["taker_buy_base_asset_volume"]
    out["cvd_delta"] = out["taker_buy_base_asset_volume"] - out["taker_sell"]
    out["cvd_4"]  = out["cvd_delta"].rolling(4).sum().fillna(0.0)
    out["cvd_8"]  = out["cvd_delta"].rolling(8).sum().fillna(0.0)
    out["cvd_lite"] = out["cvd_4"]   # canonical short-term pressure feature

    return out

# ─── Regime classification ────────────────────────────────────────────────────
def classify_regime(df4h: pd.DataFrame) -> str:
    x = df4h.copy()
    x["ema20"] = ema(x["close"], 20)
    x["ema50"] = ema(x["close"], 50)
    x["rsi14"] = rsi(x["close"], 14)
    x["adx"] = adx(x, 14)
    latest = x.iloc[-1]

    adx_v = latest["adx"]
    rsi_v = latest["rsi14"]
    up = latest["ema20"] > latest["ema50"]
    dn = latest["ema20"] < latest["ema50"]
    above = latest["close"] > latest["ema20"]
    below = latest["close"] < latest["ema20"]

    if adx_v > 30 and up and above and rsi_v > 55:   return "STRONG_UPTREND"
    if adx_v > 30 and dn and below and rsi_v < 45:   return "STRONG_DOWNTREND"
    if adx_v > 20 and up:                             return "UPTREND"
    if adx_v > 20 and dn:                             return "DOWNTREND"
    return "RANGING"

def get_btc_macro_regime() -> str:
    """G_beta source — fail-open to RANGING on API error."""
    try:
        return classify_regime(fetch_klines("BTCUSDT", "4h", LOOKBACK_4H))
    except Exception as e:
        log_event("WARN", "scanner", "btc_fetch_failed", {"error": str(e)})
        alert_system_error("btc_regime", "fetch_failed", str(e), {"fallback_regime": "RANGING"})
        return "RANGING"

def get_derivatives_alpha(conn, symbol: str) -> dict:
    """Fetches real-time institutional derivatives context from local PM2 collectors safely."""
    alpha = {"funding_rate": 0.0, "ls_ratio": 1.0}
    try:
        with conn.cursor() as cur:
            # Query funding (rollback on column/table mismatch)
            try:
                cur.execute("SELECT funding_rate FROM funding_rates WHERE symbol = %s ORDER BY ts DESC LIMIT 1", (symbol,))
                row = cur.fetchone()
                if row: alpha["funding_rate"] = float(row[0])
            except: conn.rollback()
            
            # Query LS Ratio
            try:
                cur.execute("SELECT long_short_ratio FROM ls_ratios WHERE symbol = %s ORDER BY ts DESC LIMIT 1", (symbol,))
                row = cur.fetchone()
                if row: alpha["ls_ratio"] = float(row[0])
            except: conn.rollback()
    except: pass
    return alpha

# ─── Cooldown ─────────────────────────────────────────────────────────────────
def cooldown_active(conn, pair: str, latest_ts: datetime) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ts FROM signals WHERE pair = %s ORDER BY ts DESC LIMIT 1",
            (pair,),
        )
        row = cur.fetchone()
    if not row:
        return False
    return (latest_ts - row[0]).total_seconds() < COOLDOWN_BARS * 15 * 60

# ─── Scoring ───────────────────────────────────────────────────────────────────
def _vol_ratio(latest: pd.Series) -> float:
    vsma = latest.get("volume_sma20")
    if vsma is None or (isinstance(vsma, float) and math.isnan(vsma)) or vsma == 0:
        return 0.0
    return float(latest["volume"]) / float(vsma)

# ─── Sprint C: Probability Scoring Helpers ─────────────────────────────────────
def _sigmoid(x: float) -> float:
    """Bounded logistic function. Output in (0, 1)."""
    return 1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, x))))

def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))

def _norm(value: float, lo: float, hi: float) -> float:
    """Linear normalization to [0, 1]. Returns 0.5 when range is degenerate."""
    if hi <= lo:
        return 0.5
    return _clip01((value - lo) / (hi - lo))

def score_long_probability(latest: pd.Series, regime: str, alpha: dict) -> Tuple[float, Dict]:
    """
    Sprint C: Calibrated logistic long score.
    Returns score in [0, 100] where 50 = breakeven (p=0.5 at sigmoid(0)).
    Coefficients are initial priors — will be refined from training_candidates outcomes.
    """
    ema_trend     = 1.0 if float(latest.get("ema20", 0)) > float(latest.get("ema50", 0)) else 0.0
    price_above   = 1.0 if float(latest.get("close", 0)) > float(latest.get("ema20", 0)) else 0.0
    rsi_bull      = _norm(float(latest.get("rsi14", 50)), 45.0, 65.0)
    macd_v        = float(latest.get("macd_hist", 0))
    macd_bull     = _norm(macd_v, 0.0, max(1e-6, abs(macd_v) + 1e-6))
    vol_confirm   = _norm(_vol_ratio(latest), 1.0, 2.0)
    cvd_v         = float(latest.get("cvd_lite", 0))   # now rolling 4-bar
    cvd_bull      = _norm(cvd_v, 0.0, max(1.0, abs(cvd_v) + 1.0))
    squeeze_long  = 1.0 if bool(latest.get("recent_squeeze_fire_long", False)) else 0.0

    funding  = float(alpha.get("funding_rate", 0.0) or 0.0)
    ls_ratio = float(alpha.get("ls_ratio", 1.0) or 1.0)

    regime_score = {"STRONG_UPTREND": 1.0, "UPTREND": 0.8, "RANGING": 0.4,
                    "DOWNTREND": 0.2, "STRONG_DOWNTREND": 0.0}.get(regime, 0.4)

    # --- Sprint D: Regime Prior (Sovereign Nudge) ---
    regime_prior = 0.0
    if regime == "UPTREND":
        regime_prior = float(getattr(config, "LONG_UPTREND_Z_PRIOR", 0.35))
    elif regime == "STRONG_UPTREND":
        regime_prior = float(getattr(config, "LONG_STRONG_UPTREND_Z_PRIOR", 0.50))

    z_pre_prior = (
        -2.20
        + 1.20 * ema_trend
        + 0.80 * price_above
        + 0.70 * rsi_bull
        + 0.60 * macd_bull
        + 0.50 * vol_confirm
        + 0.45 * cvd_bull
        + 0.35 * squeeze_long
        + 0.40 * regime_score
        - 0.30 * _clip01((ls_ratio - 1.0) / 2.0)
        + 0.20 * _clip01((-funding) / 0.01)
    )
    
    z = z_pre_prior + regime_prior
    pwin  = _sigmoid(z)
    score = 100.0 * pwin

    return score, {
        "family_tag": "prob_long", 
        "pwin": round(pwin, 4), 
        "z": round(z, 4),
        "z_pre_prior": round(z_pre_prior, 4),
        "regime_prior": round(regime_prior, 4),
        "volume_ratio": _vol_ratio(latest)
    }

def score_short_probability(latest: pd.Series, regime: str, alpha: dict) -> Tuple[float, Dict]:
    """
    Sprint C: Calibrated logistic short score.
    Symmetric counterpart to score_long_probability.
    """
    ema_bear      = 1.0 if float(latest.get("ema20", 0)) < float(latest.get("ema50", 0)) else 0.0
    price_below   = 1.0 if float(latest.get("close", 0)) < float(latest.get("ema20", 0)) else 0.0
    rsi_v         = float(latest.get("rsi14", 50))
    rsi_bear      = 1.0 - _norm(rsi_v, 35.0, 55.0)   # high RSI = bad for short
    macd_v        = float(latest.get("macd_hist", 0))
    macd_bear     = _norm(-macd_v, 0.0, max(1e-6, abs(macd_v) + 1e-6))
    vol_confirm   = _norm(_vol_ratio(latest), 1.0, 2.0)
    cvd_v         = float(latest.get("cvd_lite", 0))
    cvd_bear      = _norm(-cvd_v, 0.0, max(1.0, abs(cvd_v) + 1.0))
    squeeze_short = 1.0 if bool(latest.get("recent_squeeze_fire_short", False)) else 0.0

    funding  = float(alpha.get("funding_rate", 0.0) or 0.0)
    ls_ratio = float(alpha.get("ls_ratio", 1.0) or 1.0)

    regime_score = {"STRONG_DOWNTREND": 1.0, "DOWNTREND": 0.8, "RANGING": 0.4,
                    "UPTREND": 0.2, "STRONG_UPTREND": 0.0}.get(regime, 0.4)

    # --- Sprint D: Regime Prior (Sovereign Nudge) ---
    regime_prior = 0.0
    if regime == "DOWNTREND":
        regime_prior = float(getattr(config, "SHORT_DOWNTREND_Z_PRIOR", 0.35))
    elif regime == "STRONG_DOWNTREND":
        regime_prior = float(getattr(config, "SHORT_STRONG_DOWNTREND_Z_PRIOR", 0.50))

    z_pre_prior = (
        -2.25
        + 1.20 * ema_bear
        + 0.80 * price_below
        + 0.70 * rsi_bear
        + 0.60 * macd_bear
        + 0.50 * vol_confirm
        + 0.45 * cvd_bear
        + 0.35 * squeeze_short
        + 0.40 * regime_score
        + 0.35 * _clip01((ls_ratio - 1.0) / 2.0)
        + 0.20 * _clip01(funding / 0.01)
    )

    z = z_pre_prior + regime_prior
    pwin  = _sigmoid(z)
    score = 100.0 * pwin

    return score, {
        "family_tag": "prob_short", 
        "pwin": round(pwin, 4), 
        "z": round(z, 4),
        "z_pre_prior": round(z_pre_prior, 4),
        "regime_prior": round(regime_prior, 4),
        "volume_ratio": _vol_ratio(latest)
    }

# ─── Sprint C: Regime-Aware R:R ────────────────────────────────────────────────
def get_rr_multipliers(signal_family: str, regime: str, side: str) -> Tuple[float, float]:
    """
    Returns (sl_atr_mult, tp_atr_mult) based on signal family and regime context.
    - Counter-trend setups get tighter stops and nearer targets (lower R expectation)
    - With-trend setups get full extension
    - Ranging environments get conservative shaping
    """
    fam = (signal_family or "").lower()
    # Default: 1.0 SL, 4.0 TP
    sl_mult = 1.0
    tp_mult = 4.0

    # Counter‑trend (failed bounce) – tighter SL, still 3.5 TP
    if side == "SHORT" and fam == "failed_bounce":
        sl_mult = 0.8
        tp_mult = 3.5
    # Breakdown short (with‑trend)
    elif side == "SHORT" and fam == "breakdown":
        sl_mult = 1.0
        tp_mult = 4.5
    # Long trend
    elif side == "LONG" and fam == "trend":
        sl_mult = 1.0
        tp_mult = 4.5
    # Mean reversion (tighter)
    elif fam == "mean_reversion":
        sl_mult = 0.8
        tp_mult = 3.0

    return sl_mult, tp_mult

# ─── Sprint C: Score-Scaled Position Sizing ────────────────────────────────────
def risk_scale_from_score(score: float, min_scale: float = 0.50, max_scale: float = 1.50) -> float:
    """
    Monotone bounded scaling factor derived from signal score.
    score=50 → 1.0x base risk (breakeven conviction)
    score=100 → 1.5x (high conviction)
    score=0   → 0.5x (low conviction, still trades)
    Mathematically: raw = 1 + 0.5 * ((score-50)/50), clamped to [min, max].
    """
    raw = 1.0 + 0.5 * ((score - 50.0) / 50.0)
    return max(min_scale, min(max_scale, raw))

# ─── Sprint D: Probability Cutover Helpers ─────────────────────────────────────
def blend_primary_score(prob_score: float, legacy_score: float) -> float:
    """
    Transition blend: probability model is primary, legacy heuristic is shadow.
    w_prob * prob + w_legacy * legacy, both weights from config.
    Monotone in prob_score by construction (w_prob >= 0).
    """
    w_prob   = float(getattr(config, "PROBABILITY_PRIMARY_WEIGHT", 0.75))
    w_legacy = float(getattr(config, "LEGACY_SHADOW_WEIGHT", 0.25))
    return w_prob * float(prob_score) + w_legacy * float(legacy_score)

def min_probability_floor(side: str, family_tag: str, regime: str, hour_utc: int) -> float:
    """
    Per-side, per-family minimum probability floor (0-100 scale).
    Implements Controlled Tightening (The Sovereign Purge Hypothesis).
    """
    side = side.upper()
    fam  = (family_tag or "none").lower()

    # Ranging + breakdown short = always block (return >100)
    if regime == "RANGING" and side == "SHORT" and fam == "breakdown":
        return 101.0

    # 1. Hard-block RANGING except for mean_reversion
    if regime == "RANGING" and fam != "mean_reversion":
        return 101.0  # Impossible to pass

    # 2. Base side floors
    if side == "LONG":
        floor = float(getattr(config, "MIN_LONG_PROB_SCORE", 52.0))
    else:
        # Standard short floor
        floor = float(getattr(config, "MIN_SHORT_PROB_SCORE", 52.0))
        # Specialized short floors
        if fam == "failed_bounce":
            floor = float(getattr(config, "MIN_FAILED_BOUNCE_SHORT_PROB_SCORE", 55.0))

    # 3. Controlled Tightening Uplifts
    # 3a. Unclassified signals floor
    if fam == "none":
        floor = max(floor, float(getattr(config, "MIN_UNCLASSIFIED_PROB_SCORE", 55.0)))

    # 3b. Breakdown quarantine (+8.0 uplift)
    if fam == "breakdown":
        floor += float(getattr(config, "BREAKDOWN_THRESHOLD_UPLIFT", 8.0))

    # 3c. Degraded hour penalty (+5.0 uplift for UTC 6/7)
    degraded_hours = getattr(config, "DEGRADED_HOURS_UTC", {6, 7})
    if hour_utc in degraded_hours:
        floor += float(getattr(config, "DEGRADED_HOUR_THRESHOLD_UPLIFT", 5.0))

    return floor

def probability_gate(side: str, family_tag: str, prob_score: float, regime: str, hour_utc: int) -> Tuple[bool, str]:
    """
    Gate on raw probability score BEFORE blend.
    Checks intrinsic edge quality before context penalties are applied.
    Returns (passed, gate_name_if_failed).
    """
    fam = (family_tag or "none").lower()
    floor = min_probability_floor(side, family_tag, regime, hour_utc)
    if prob_score < floor:
        reason = f"prob_floor_{side.lower()}_{fam}_{floor:.1f}"
        if floor > 100:
            reason = f"toxic_regime_block_{regime}_{fam}"
        return False, reason
    return True, "prob_ok"

def score_long_signal(latest: pd.Series, regime: str, alpha: dict) -> Tuple[float, Dict]:
    reasons_pass, reasons_fail, tags = [], [], []
    score = 0.0

    # ADX classification (not hard gate) - used for signal family
    adx = latest.get("adx14", 0)
    if adx < 20:
        reasons_fail.append(f"ADX {adx:.1f} below 20 (chop zone)")
    elif adx >= 25:
        score += 10
        reasons_pass.append(f"ADX {adx:.1f} strong trend")
    else:
        reasons_pass.append(f"ADX {adx:.1f} moderate")
        
    # THE EXHAUSTION BLOCKER (Rubber Band Effect) - kept as hard gate
    atr14 = latest["atr14"]
    dist_from_ema = latest["close"] - latest["ema20"]
    if atr14 > 0:
        stretch_atr = dist_from_ema / atr14
        if stretch_atr > config.ATR_STRETCH_MAX:
            return 0.0, {
                "reasons_fail": [f"Exhausted: Price {stretch_atr:.1f} ATRs above EMA20 (max {config.ATR_STRETCH_MAX})"],
                "volume_ratio": float(_vol_ratio(latest) or 0.0),
            }

    # EMA alignment
    if latest["ema20"] > latest["ema50"]:
        score += 20; reasons_pass.append("EMA20 > EMA50 (trend aligned)")
    else:
        reasons_fail.append("EMA20 <= EMA50")

    # Price vs EMA20
    if latest["close"] > latest["ema20"]:
        score += 10; reasons_pass.append("Price above EMA20")
    else:
        reasons_fail.append("Price <= EMA20")

    # RSI
    rsi_v = latest["rsi14"]
    if 30 <= rsi_v <= 65:
        score += 15; reasons_pass.append(f"RSI {rsi_v:.1f} in bull zone")
    else:
        reasons_fail.append(f"RSI {rsi_v:.1f} outside bull zone")

    # MACD
    if latest["macd_hist"] > 0:
        score += 15; reasons_pass.append("MACD histogram positive")
    else:
        reasons_fail.append("MACD histogram <= 0")

    # Regime bonus
    regime_bonus = {
        "RANGING": 0, "UPTREND": 10, "STRONG_UPTREND": 0,
        "DOWNTREND": 5, "STRONG_DOWNTREND": 0,
    }.get(regime, 0)
    score += regime_bonus
    reasons_pass.append(f"Regime: {regime}")

    # Volume & CVD Alpha
    vol_ratio = _vol_ratio(latest)
    if vol_ratio >= 1.1:
        score += 15; reasons_pass.append(f"Volume ratio {vol_ratio:.2f} (confirmed)")
    else:
        reasons_fail.append(f"Volume ratio {vol_ratio:.2f} below 1.1")

    if latest.get("cvd_lite", 0) > 0:
        score += 15; reasons_pass.append("Aggressive Market Buying (Positive CVD)"); tags.append("CVD")

    # DERIVATIVES ALPHA MERGE
    funding = alpha.get("funding_rate", 0.0)
    ls_ratio = alpha.get("ls_ratio", 1.0)
    if funding < -0.005 and ls_ratio < 0.9:
        score += 30; reasons_pass.append(f"🔥 SHORT SQUEEZE ALPHA: Funding {funding:.4f}, LS {ls_ratio:.2f}"); tags.append("Squeeze")
    elif ls_ratio > 2.5:
        score -= 20; reasons_fail.append(f"Crowded Longs (LS {ls_ratio:.2f})")

    return score, {"reasons_pass": reasons_pass, "reasons_fail": reasons_fail, "volume_ratio": vol_ratio, "tags": tags}

# ─── SPRINT B: SHORT-SIDE ARSENAL ──────────────────────────────────────

def apply_short_context_penalties(
    raw_score: float,
    family_tag: str,
    regime: str,
    btc_regime: str,
) -> Tuple[float, Dict[str, Any]]:
    if raw_score <= 0:
        return 0.0, {"penalties": [], "blocked": False}

    penalties = []
    blocked = False

    # Regime logic
    if regime in ("UPTREND", "STRONG_UPTREND"):
        if family_tag == "failed_bounce":
            penalties.append(("uptrend_failed_bounce_penalty", config.FAILED_BOUNCE_UPTREND_PENALTY))
        elif config.GENERIC_SHORT_UPTREND_BLOCK:
            blocked = True

    # BTC logic
    if not blocked and btc_regime in ("UPTREND", "STRONG_UPTREND"):
        if family_tag == "failed_bounce":
            penalties.append(("btc_uptrend_failed_bounce_penalty", config.FAILED_BOUNCE_BTC_UPTREND_PENALTY))
        else:
            penalties.append(("btc_uptrend_short_penalty", config.GENERIC_SHORT_BTC_UPTREND_PENALTY))

    if blocked:
        return 0.0, {
            "penalties": penalties,
            "blocked": True,
            "rejection_gate": "regime_block_non_failed_bounce_short",
        }

    penalty_total = sum(p for _, p in penalties)
    final_score = max(0.0, raw_score - penalty_total)

    return final_score, {
        "penalties": penalties,
        "blocked": False,
        "penalty_total": float(penalty_total),
        "final_score": float(final_score),
    }

def score_failed_bounce_short(
    latest: pd.Series,
    prev_bar: pd.Series,
    regime: str,
    alpha: dict,
) -> Tuple[float, Dict]:
    reasons_pass, reasons_fail = [], []
    score = 0.0
    family_tag = "failed_bounce"

    atr14 = float(latest.get("atr14", 0.0) or 0.0)
    if atr14 <= 0:
        return 0.0, {
            "family_tag": family_tag,
            "reasons_fail": ["ATR unavailable"],
            "volume_ratio": 0.0,
        }

    # Structure: previous bar high > its EMA20, current close < its EMA20
    prev_high = float(prev_bar.get("high", 0.0))
    prev_ema20 = float(prev_bar.get("ema20", 0.0))
    latest_close = float(latest.get("close", 0.0))
    latest_ema20 = float(latest.get("ema20", 0.0))

    if not (prev_high > prev_ema20 and latest_close < latest_ema20):
        return 0.0, {
            "family_tag": family_tag,
            "reasons_fail": ["No failed-bounce structure"],
            "volume_ratio": 0.0,
        }

    reclaim_depth_atr = (prev_high - prev_ema20) / atr14
    if reclaim_depth_atr <= config.SHORT_FAILED_BOUNCE_RECLAIM_ATR_MAX:
        score += 20
        reasons_pass.append(f"Failed reclaim depth {reclaim_depth_atr:.2f} ATR")
    else:
        reasons_fail.append(f"Reclaim too extended {reclaim_depth_atr:.2f} ATR")

    # RSI rollover
    rsi_now = float(latest.get("rsi14", 50.0))
    rsi_prev = float(prev_bar.get("rsi14", 50.0))
    if 40.0 <= rsi_now <= 55.0 and rsi_now < rsi_prev:
        score += 15
        reasons_pass.append(f"RSI rollover {rsi_prev:.1f}->{rsi_now:.1f}")
    else:
        reasons_fail.append(f"RSI not rolling over ({rsi_prev:.1f}->{rsi_now:.1f})")

    # MACD rollover / bearish impulse
    macd_now = float(latest.get("macd_hist", 0.0))
    macd_prev = float(prev_bar.get("macd_hist", 0.0))
    if macd_now < macd_prev and macd_now <= 0:
        score += 15
        reasons_pass.append("MACD histogram rolled bearish")
    else:
        reasons_fail.append("MACD not bearish enough")

    # CVD deterioration
    cvd_now = float(latest.get("cvd_lite", 0.0))
    cvd_prev = float(prev_bar.get("cvd_lite", 0.0))
    if cvd_now < cvd_prev:
        score += 15
        reasons_pass.append("Negative CVD delta")
    else:
        reasons_fail.append("CVD not deteriorating")

    # Volume confirmation
    vol_ratio = _vol_ratio(latest)
    if vol_ratio >= 1.05:
        score += 10
        reasons_pass.append(f"Volume ratio {vol_ratio:.2f}")
    else:
        reasons_fail.append(f"Weak volume ratio {vol_ratio:.2f}")

    # Regime context: failed bounce is allowed in uptrends, rewarded lightly
    if regime in ("UPTREND", "STRONG_UPTREND"):
        score += 10
        reasons_pass.append(f"Counter-trend failed bounce in {regime}")
    elif regime == "RANGING":
        score += 5
        reasons_pass.append("Failed bounce in ranging regime")
    else:
        reasons_pass.append(f"Regime {regime}")

    # Derivatives context
    funding = float(alpha.get("funding_rate", 0.0) or 0.0)
    ls_ratio = float(alpha.get("ls_ratio", 1.0) or 1.0)
    if funding > 0 and ls_ratio > 1.2:
        score += 10
        reasons_pass.append(f"Crowded longs: funding={funding:.5f}, ls={ls_ratio:.2f}")

    return score, {
        "family_tag": family_tag,
        "reasons_pass": reasons_pass,
        "reasons_fail": reasons_fail,
        "volume_ratio": float(vol_ratio),
        "reclaim_depth_atr": float(reclaim_depth_atr),
    }

def score_breakdown_short(
    latest: pd.Series,
    regime: str,
    alpha: dict,
) -> Tuple[float, Dict]:
    reasons_pass, reasons_fail = [], []
    score = 0.0
    family_tag = "breakdown"

    atr14 = float(latest.get("atr14", 0.0) or 0.0)
    close = float(latest.get("close", 0.0))
    ema20 = float(latest.get("ema20", 0.0))
    ema50 = float(latest.get("ema50", 0.0))
    adx14 = float(latest.get("adx14", 0.0))
    macd = float(latest.get("macd_hist", 0.0))
    vol_ratio = _vol_ratio(latest)

    if atr14 <= 0 or close <= 0:
        return 0.0, {
            "family_tag": family_tag,
            "reasons_fail": ["ATR/close unavailable"],
            "volume_ratio": 0.0,
        }

    stretch_atr = (ema20 - close) / atr14 if close < ema20 else 0.0
    if stretch_atr > config.SHORT_BREAKDOWN_STRETCH_MAX:
        return 0.0, {
            "family_tag": family_tag,
            "reasons_fail": [f"Breakdown overextended {stretch_atr:.2f} ATR"],
            "volume_ratio": float(vol_ratio),
        }

    if ema20 < ema50:
        score += 20
        reasons_pass.append("EMA20 < EMA50")
    else:
        reasons_fail.append("EMA20 not below EMA50")

    if close < ema20:
        score += 15
        reasons_pass.append("Price below EMA20")
    else:
        reasons_fail.append("Price not below EMA20")

    if adx14 > 25:
        score += 15
        reasons_pass.append(f"ADX strong {adx14:.1f}")
    else:
        reasons_fail.append(f"ADX weak {adx14:.1f}")

    if macd < 0:
        score += 15
        reasons_pass.append("MACD histogram negative")
    else:
        reasons_fail.append("MACD not negative")

    if vol_ratio >= 1.20:
        score += 15
        reasons_pass.append(f"Volume ratio {vol_ratio:.2f}")
    else:
        reasons_fail.append(f"Volume weak {vol_ratio:.2f}")

    if regime in ("DOWNTREND", "STRONG_DOWNTREND"):
        score += 10
        reasons_pass.append(f"Regime support: {regime}")

    funding = float(alpha.get("funding_rate", 0.0) or 0.0)
    ls_ratio = float(alpha.get("ls_ratio", 1.0) or 1.0)
    if funding > 0 and ls_ratio > 1.1:
        score += 10
        reasons_pass.append(f"Long crowding: funding={funding:.5f}, ls={ls_ratio:.2f}")

    return score, {
        "family_tag": family_tag,
        "reasons_pass": reasons_pass,
        "reasons_fail": reasons_fail,
        "volume_ratio": float(vol_ratio),
        "stretch_atr": float(stretch_atr),
    }

def score_mean_reversion_short(latest: pd.Series, regime: str, alpha: dict) -> Tuple[float, Dict]:
    """Broader template targeting overextended structures snapping back."""
    reasons_pass, reasons_fail = [], []
    score = 0.0
    family_tag = "mean_reversion"

    # THE EXHAUSTION BLOCKER (Do not short if we've already dumped)
    atr14 = latest["atr14"]
    dist_from_ema = latest["ema20"] - latest["close"]
    if atr14 > 0 and latest.get("ema20") and latest.get("close"):
        stretch_atr = dist_from_ema / atr14
        if stretch_atr > config.ATR_STRETCH_MAX:
             return 0.0, {
                 "reasons_fail": [f"MR_Exhausted: Price {stretch_atr:.1f} ATRs below EMA"],
                 "volume_ratio": float(_vol_ratio(latest) or 0.0), "family_tag": family_tag
             }

    # 1. Price is Overextended to the upside (VWAP deviation or EMA stretch)
    if latest.get("vwap"):
        vwap_delta = (latest["close"] - latest["vwap"]) / latest["vwap"]
        # Allow either overextended above VWAP (short overbought) OR below VWAP with bearish structure
        if vwap_delta > config.SHORT_MEAN_REVERSION_VWAP_EXT_PCT:
            score += 15
            reasons_pass.append(f"Extended above VWAP (+{vwap_delta*100:.1f}%)")
        elif vwap_delta < -0.01 and latest["close"] < latest["ema20"]:
            # Already below VWAP but still bearish – give partial credit
            score += 8
            reasons_pass.append(f"Below VWAP with bearish structure ({vwap_delta*100:.1f}%)")
        else:
            reasons_fail.append(f"VWAP delta {vwap_delta*100:.1f}% not extreme")
    
    # 2. RSI Overbought but Rolling
    rsi_v = latest["rsi14"]
    if rsi_v > 65:
        score += 15; reasons_pass.append(f"RSI {rsi_v:.1f} Overbought territory")
    elif 55 <= rsi_v <= 65:
        score += 5; reasons_pass.append(f"RSI {rsi_v:.1f} High but rolling")
    else:
         reasons_fail.append(f"RSI {rsi_v:.1f} Too low to revert")

    # 3. Momentum Loss
    if latest["macd_hist"] < 0:
        score += 15; reasons_pass.append("MACD histogram turned negative")
    else:
        reasons_fail.append("MACD histogram still positive")

    # 4. Selling Volume Stepping In
    if latest.get("cvd_lite", 0) < 0:
        score += 10; reasons_pass.append("CVD Divergence (Sellers arriving)")

    return score, {"reasons_pass": reasons_pass, "reasons_fail": reasons_fail, "volume_ratio": float(_vol_ratio(latest) or 0.0), "family_tag": family_tag}

def score_short_signal(
    latest: pd.Series,
    prev_bar: pd.Series,
    regime: str,
    alpha: dict,
) -> Tuple[float, Dict]:
    fb_score, fb_trace = score_failed_bounce_short(latest, prev_bar, regime, alpha)
    bd_score, bd_trace = score_breakdown_short(latest, regime, alpha)
    mr_score, mr_trace = score_mean_reversion_short(latest, regime, alpha)

    candidates = [
        (fb_score, fb_trace),
        (bd_score, bd_trace),
        (mr_score, mr_trace),
    ]
    best_score, best_trace = max(candidates, key=lambda x: x[0])

    best_trace = dict(best_trace or {})
    best_trace["template_scores"] = {
        "failed_bounce": float(fb_score),
        "breakdown": float(bd_score),
        "mean_reversion": float(mr_score),
    }
    return best_score, best_trace

# ========== DIRECTIONAL SHADOW MODEL (SYMMETRIC) ==========
def compute_directional_score(
    latest: pd.Series,
    prev_bar: pd.Series,
    regime: str,
    alpha: dict,
    df15: pd.DataFrame,
) -> Dict[str, float]:
    """
    Symmetric directional scorer: long_score - short_score.
    Uses mirrored conditions (not identical templates) to estimate net directional edge.
    Returns dict with long_score, short_score, net, margin.
    """
    # ----- Long component (mirror of long conditions) -----
    long_score = 0.0
    # Trend alignment
    if latest["ema20"] > latest["ema50"]:
        long_score += 20
    # Price vs EMA20
    if latest["close"] > latest["ema20"]:
        long_score += 10
    # RSI bull zone
    rsi = latest["rsi14"]
    if 30 <= rsi <= 65:
        long_score += 15
    # MACD positive
    if latest["macd_hist"] > 0:
        long_score += 15
    # Volume conviction
    vol_ratio = _vol_ratio(latest)
    if vol_ratio >= 1.1:
        long_score += 15
    # CVD positive
    if latest.get("cvd_lite", 0) > 0:
        long_score += 15
    # Derivatives: short squeeze (funding negative, LS low) – long tailwind
    funding = alpha.get("funding_rate", 0.0)
    ls_ratio = alpha.get("ls_ratio", 1.0)
    if funding < -0.005 and ls_ratio < 0.9:
        long_score += 30

    # ----- Short component (mirror conditions) -----
    short_score = 0.0
    # Trend alignment (bearish)
    if latest["ema20"] < latest["ema50"]:
        short_score += 20
    # Price below EMA20
    if latest["close"] < latest["ema20"]:
        short_score += 10
    # RSI bear zone (symmetric around 50)
    if 35 <= rsi <= 65:
        short_score += 15
    # MACD negative
    if latest["macd_hist"] < 0:
        short_score += 15
    # Volume conviction (same)
    if vol_ratio >= 1.1:
        short_score += 15
    # CVD negative
    if latest.get("cvd_lite", 0) < 0:
        short_score += 15
    # Derivatives: crowded longs (funding positive, LS high) – short tailwind
    if funding > 0.005 and ls_ratio > 1.1:
        short_score += 30

    net = long_score - short_score
    margin = abs(net)
    primary_side = "LONG" if net > 0 else "SHORT" if net < 0 else "NEUTRAL"

    return {
        "directional_long_score": float(long_score),
        "directional_short_score": float(short_score),
        "directional_net": float(net),
        "directional_margin": float(margin),
        "directional_primary_side": primary_side,
    }


# ─── Signal construction ───────────────────────────────────────────────────────
def build_signal(
    pair: str, side: str, latest: pd.Series,
    regime: str, score: float, trace: Dict,
    sl_mult: float = ATR_SL_MULTIPLIER,
    signal_family: str = "none",
    family_indicators: Dict[str, Any] = None,
) -> dict:
    atr_v = float(latest["atr14"])
    entry = float(latest["close"])
    score_bucket = (int(score) // 5) * 5

    # Sprint C: Regime-aware R:R (replaces fixed 1.0/3.0 constants)
    rr_sl_mult, rr_tp_mult = get_rr_multipliers(signal_family, regime, side)
    # Honour caller-provided sl_mult if it differs from default (Phase 2 wide-ATR cap),
    # but apply the rr_sl_mult as a relative adjustment
    effective_sl_mult = sl_mult * rr_sl_mult
    stop = entry - effective_sl_mult * atr_v if side == "LONG" else entry + effective_sl_mult * atr_v

    # Scale-Out Targets — family/regime shaped
    tp1_mult = rr_tp_mult * 0.40   # scale-out at ~40% of full target
    tp1 = entry + (tp1_mult * atr_v) if side == "LONG" else entry - (tp1_mult * atr_v)
    tp2 = entry + (rr_tp_mult * atr_v) if side == "LONG" else entry - (rr_tp_mult * atr_v)

    # Sprint C: Score-scaled position sizing
    base_risk = float(config.RISK_PER_TRADE_USD)
    risk_scale = risk_scale_from_score(score)
    scaled_risk = base_risk * risk_scale
    stop_dist = abs(entry - stop)
    pos_size = scaled_risk / stop_dist if stop_dist > 0 else 0

    trace.update({
        "score_bucket": score_bucket,
        "cell_allowed": bool(True),
        "allowed_cell_key": [regime, score_bucket],
        "tp1": round(tp1, 8),
        "tp2": round(tp2, 8),
        # Sprint C telemetry
        "rr_sl_mult": round(effective_sl_mult, 3),
        "rr_tp_mult": round(rr_tp_mult, 3),
        "risk_scale": round(risk_scale, 3),
        "risk_usd": round(scaled_risk, 4),
        "position_size": round(pos_size, 8),
        "pwin": trace.get("pwin"),          # populated by prob models if used
        "z_score": trace.get("z"),          # logistic z, if populated
        "cvd_4": float(latest.get("cvd_4", latest.get("cvd_lite", 0))),
        "cvd_8": float(latest.get("cvd_8", 0)),
        "squeeze_fire_long": bool(latest.get("recent_squeeze_fire_long", False)),
        "squeeze_fire_short": bool(latest.get("recent_squeeze_fire_short", False)),
        "tags": trace.get("tags", []),
        "signal_family": signal_family,
        "family_indicators": family_indicators or {},
        "squeeze_on": bool(latest.get("squeeze_on", False)),
        "squeeze_fired": bool(latest.get("squeeze_fired", False)),
        "recent_squeeze_fire": bool(trace.get("recent_squeeze_fire", False)),
    })

    return {
        "signal_id": str(uuid.uuid4()),
        "pair": pair,
        "ts": latest["close_time"].to_pydatetime(),
        "side": side,
        "entry": entry,
        "stop_loss": stop,
        "tp1": round(tp1, 8),
        "tp2": round(tp2, 8),
        "take_profit": round(tp2, 8),  # legacy field
        "score": score,
        "regime": regime,
        "reason_trace": trace,
        "logic_version": LOGIC_VERSION,
        "config_version": CONFIG_VERSION,
        "signal_family": signal_family,
        # Sprint D Persistence Fields
        "prob_score":   trace.get("prob_score"),
        "legacy_score": trace.get("legacy_score"),
        "pwin":         trace.get("pwin"),
        "z_score":      trace.get("z"),  # Use 'z' as sent from analyze_pair
        "score_mode":   trace.get("score_mode"),
        "risk_scale":   trace.get("risk_scale"),
        "rr_sl_mult":   trace.get("rr_sl_mult"),
        "rr_tp_mult":   trace.get("rr_tp_mult"),
    }


# ─── Wolfram Five-Cell filter ──────────────────────────────────────────────────
def wolfram_cell_key(regime: str, score: float) -> tuple:
    return (regime, (int(score) // 5) * 5)

def passes_wolfram_five_cell_filter(regime: str, score: float, side: str = "") -> bool:
    """G_Omega: exact five-cell discipline gate."""
    score_bucket = (int(score) // 5) * 5
    if regime == "STRONG_UPTREND" and side.upper() == "SHORT": return False
    if regime == "STRONG_DOWNTREND" and side.upper() == "LONG": return False
    if BLOCK_STRONG_UPTREND and regime == "STRONG_UPTREND": return False
    
    # Simulation mode: permissive buckets for data collection
    if not config.ENABLE_LIVE_TRADING:
        allowed_sim = {
            ("STRONG_DOWNTREND", 20), ("STRONG_DOWNTREND", 25), ("STRONG_DOWNTREND", 30),
            ("STRONG_DOWNTREND", 35), ("STRONG_DOWNTREND", 40), ("STRONG_DOWNTREND", 45),
            ("STRONG_DOWNTREND", 50), ("STRONG_DOWNTREND", 55), ("STRONG_DOWNTREND", 60),
            ("STRONG_UPTREND",   20), ("STRONG_UPTREND",   25), ("STRONG_UPTREND",   30),
            ("STRONG_UPTREND",   35), ("STRONG_UPTREND",   40), ("STRONG_UPTREND",   45),
            ("STRONG_UPTREND",   50), ("STRONG_UPTREND",   55), ("STRONG_UPTREND",   60),
            ("DOWNTREND",        20), ("DOWNTREND",        25), ("DOWNTREND",        30),
            ("DOWNTREND",        35), ("DOWNTREND",        40), ("DOWNTREND",        45),
            ("DOWNTREND",        50), ("DOWNTREND",        55), ("DOWNTREND",        60),
            ("UPTREND",          20), ("UPTREND",          25), ("UPTREND",          30),
            ("UPTREND",          35), ("UPTREND",          40), ("UPTREND",          45),
            ("UPTREND",          50), ("UPTREND",          55), ("UPTREND",          60),
            ("RANGING",          20), ("RANGING",          25), ("RANGING",          30),
            ("RANGING",          35), ("RANGING",          40), ("RANGING",          45),
            ("RANGING",          50), ("RANGING",          55), ("RANGING",          60),
            ("RANGING",          65),
        }
        return (regime, score_bucket) in allowed_sim
    
    # Live mode: use the currently configured cohort cells.
    # Doctrine v2.0: Normalized thresholds (Standard baseline 55, UPTREND/DOWNTREND 50)
    allowed = getattr(config, "LIVE_ALLOWED_CELLS", {
        ("STRONG_DOWNTREND", 55),
        ("STRONG_UPTREND", 60),
        ("DOWNTREND", 50),
        ("UPTREND", 50),
        ("RANGING", 60),
    })
    return (regime, score_bucket) in allowed

def coherence_q_factor(side: str) -> float:
    skew = _side_controller.get_skew()
    if config.MAX_COHERENCE_OFFSET <= 0:
        return 1.0
    skew_norm = max(-1.0, min(1.0, skew / config.MAX_COHERENCE_OFFSET))
    bias = config.Q_SIDE_BIAS_MAX
    if side == "LONG":
        return 1.0 - bias * max(0.0, skew_norm) + bias * max(0.0, -skew_norm)
    else:
        return 1.0 + bias * max(0.0, skew_norm) - bias * max(0.0, -skew_norm)

# ─── Sovereign Q functional ────────────────────────────────────────────────────
def compute_Q(candidate: dict) -> float:
    """
    Phi-normalized quality ranking functional.
    I[A,t] = G_beta*G_str*G_sq*G_vwap*G_vol*G_Omega * Q[A,t]
    Q = sum_i alpha_i * Phi_i(feature_i),  all Phi in [0,1]
    """
    a = Q_ALPHA

    # Phi(VRatio): conviction. Cap at 5x.
    phi_vol = min(float(candidate.get("volume_ratio", 0.0)) / 5.0, 1.0)

    # Phi(1/StopPct): tight stop = high R:R. 0% → 1.0, 10% → 0.0.
    entry = float(candidate.get("entry", 0))
    sl    = float(candidate.get("stop_loss", 0))
    stop_pct = abs(entry - sl) / entry * 100.0 if entry > 0 else 999.0
    phi_stop = max(0.0, 1.0 - stop_pct / 10.0)

    # Phi(1/Rank): liquidity primacy. Rank 0 → 1.0, Rank 30 → 0.0.
    phi_rank = max(0.0, 1.0 - float(candidate.get("universe_rank", 29)) / 30.0)

    # Phi(VWAP proximity): 1/(1+|delta|). Closer to VWAP = better entry.
    phi_vwap = 1.0 / (1.0 + abs(float(candidate.get("vwap_delta", 0.0))))

    # Phi(Momentum): score/100 bounded [0,1].
    phi_mom = min(max(float(candidate.get("score", 0.0)) / 100.0, 0.0), 1.0)

    # Phi(OI ratio): OI vs mean. Default 0.5 when unavailable.
    phi_oi = min(max(float(candidate.get("oi_ratio", 0.5)) / 3.0, 0.0), 1.0)

    base_q = (
        a["vol_ratio"]    * phi_vol
        + a["inv_stop_pct"] * phi_stop
        + a["inv_rank"]     * phi_rank
        + a["vwap_prox"]    * phi_vwap
        + a["momentum"]     * phi_mom
        + a["oi_ratio"]     * phi_oi
    )

    return base_q * coherence_q_factor(candidate["side"])

# Alias kept for any external references
compute_rank_score = compute_Q

# ─── Top-N selector (Minority-Slot doctrine) ───────────────────────────────────────
def select_top_ranked_wolfram_signals(candidates: list) -> list:
    """
    Sovereign Minority-Slot Ranking (Sprint B).
    Guarantees: if ANY short survives all upstream gates, it gets the first slot.
    Remaining slots are filled by the highest-Q longs, then an optional second short.
    Falls back to pure-Q ranking when no shorts are present.
    """
    # A. G_Omega filter + annotate with stable UUID and Q score
    filtered = []
    for c in candidates:
        if passes_wolfram_five_cell_filter(c["regime"], c["score"], c.get("side", "")):
            c = dict(c)
            c["_cid"]       = str(uuid.uuid4())
            c["cell_key"]   = wolfram_cell_key(c["regime"], c["score"])
            c["rank_score"] = compute_Q(c)
            entry = float(c.get("entry", 0))
            c["stop_pct"]   = abs(entry - float(c.get("stop_loss", 0))) / entry * 100.0 if entry > 0 else 999.0
            filtered.append(c)

    if not filtered:
        return []

    # B. Separate by side and sort each pool by Q descending
    longs  = sorted([c for c in filtered if c["side"] == "LONG"],  key=lambda x: x["rank_score"], reverse=True)
    shorts = sorted([c for c in filtered if c["side"] == "SHORT"], key=lambda x: x["rank_score"], reverse=True)

    # Deduplicate by cell within each pool (max 1 per regime x score_bucket cell)
    def dedup_by_cell(pool):
        seen, out = set(), []
        for c in pool:
            if c["cell_key"] not in seen:
                seen.add(c["cell_key"])
                out.append(c)
        return out
    longs  = dedup_by_cell(longs)
    shorts = dedup_by_cell(shorts)

    selected = []

    # C. MINORITY SLOT: if any short exists, reserve the first slot for the best short
    if shorts:
        selected.append(shorts.pop(0))

    # D. Fill remaining slots with the best longs
    remaining = MAX_SIGNALS_PER_SCAN - len(selected)
    taken_long = 0
    for c in longs:
        if taken_long >= min(remaining, MAX_SIGNALS_PER_SIDE):
            break
        selected.append(c)
        taken_long += 1

    # E. If there is still a free slot and another short exists, take it
    if len(selected) < MAX_SIGNALS_PER_SCAN and shorts:
        selected.append(shorts.pop(0))

    # F. Hard-cap safety pass (auditable)
    final = []
    side_counts = {"LONG": 0, "SHORT": 0}
    for c in selected:
        if side_counts.get(c["side"], 0) >= MAX_SIGNALS_PER_SIDE:
            continue
        side_counts[c["side"]] = side_counts.get(c["side"], 0) + 1
        final.append(c)
        if len(final) >= MAX_SIGNALS_PER_SCAN:
            break

    # G. Log rejections (UUID-stable) and minority-slot result
    final_cids = {c["_cid"] for c in final}
    for c in filtered:
        if c["_cid"] not in final_cids:
            log_event("INFO", "scanner", "wolfram_top3_rank_reject", {
                "pair": c["pair"], "side": c["side"], "regime": c["regime"],
                "score": float(c["score"]), "cell_key": list(c["cell_key"]),
                "rank_score": float(round(c["rank_score"], 4)),
            })

    logger.info(
        "[MINORITY_SLOT] Selected: LONG=%d SHORT=%d | total_filtered=%d",
        side_counts.get("LONG", 0), side_counts.get("SHORT", 0), len(filtered),
    )
    return final


# ─── Universe management ───────────────────────────────────────────────────────
def refresh_active_universe() -> None:
    global PAIRS, _LAST_UNIVERSE_REFRESH
    try:
        new_pairs = exchange_discovery.get_top_liquid_symbols(limit=30)
        if new_pairs:
            PAIRS = new_pairs
            _LAST_UNIVERSE_REFRESH = time.time()
            log_event("INFO", "scanner", "universe_refresh", {
                "symbol_count": int(len(PAIRS)), "symbols": PAIRS,
            })
            logging.info(f"Universe refreshed: {len(PAIRS)} symbols.")
    except Exception as e:
        log_event("ERROR", "scanner", "universe_refresh_failed", {"error": str(e)})
        alert_system_error("universe", "refresh_failed", str(e))

# ─── Signal persistence ────────────────────────────────────────────────────────
def insert_signal(conn, sig: dict) -> None:
    global _LAST_SIGNAL

    # Update Coherence Controller (v2.0 Doctrine)
    _side_controller.update(sig["side"])


    reason_trace = sig.get("reason_trace", {}) or {}
    phase2_gate = sig.get("phase2_gate", reason_trace.get("phase2_gate"))
    phase2_allowed = bool(sig.get("phase2_allowed", reason_trace.get("phase2_allowed", True)))
    if not phase2_gate and phase2_allowed:
        phase2_gate = "allowed"

    signal_hour_utc = sig.get("signal_hour_utc", reason_trace.get("execution_hour_utc"))
    phase2_score_multiplier = float(
        sig.get(
            "phase2_score_multiplier",
            reason_trace.get("phase2_score_multiplier", reason_trace.get("execution_multiplier", 1.0)),
        )
    )
    setup_score = float(sig.get("setup_score", reason_trace.get("setup_score", sig.get("raw_score", sig.get("score", 0.0)))))
    execution_score = float(sig.get("execution_score", reason_trace.get("execution_score", sig.get("score", 0.0))))
    btc_regime = sig.get("btc_regime", reason_trace.get("btc_regime", "UNKNOWN"))
    market_regime = sig.get("market_regime", sig.get("regime"))
    policy_version = sig.get("policy_version", reason_trace.get("policy_version", POLICY_VERSION))
    policy_activated_at = sig.get("policy_activated_at", reason_trace.get("policy_activated_at", POLICY_ACTIVATED_AT))

    db_payload = {
        **sig,
        "market_regime": market_regime,
        "btc_regime": btc_regime,
        "signal_hour_utc": signal_hour_utc,
        "phase2_gate": phase2_gate,
        "phase2_allowed": phase2_allowed,
        "phase2_score_multiplier": phase2_score_multiplier,
        "setup_score": setup_score,
        "execution_score": execution_score,
        "policy_version": policy_version,
        "policy_activated_at": policy_activated_at,
        "reason_trace": json.dumps(reason_trace, cls=_NumpyEncoder),
        # Sprint D Calibration Fields
        "prob_score":   sig.get("prob_score"),
        "legacy_score": sig.get("legacy_score"),
        "pwin":         sig.get("pwin"),
        "score_mode":   sig.get("score_mode"),
        "z_score":      reason_trace.get("z_score"),
        "risk_scale":   reason_trace.get("risk_scale"),
        "rr_sl_mult":   reason_trace.get("rr_sl_mult"),
        "rr_tp_mult":   reason_trace.get("rr_tp_mult"),
    }

    # -- EXECUTION SNAPSHOT TIER --
    entry = float(sig["entry"])
    sl = float(sig["stop_loss"])
    risk_pct = abs(entry - sl) / entry if entry > 0 else 0.01
    target_notional_usd = config.RISK_PER_TRADE_USD / risk_pct if risk_pct > 0 else 50000.0

    pair = sig["pair"]
    side = sig["side"]
    
    # Synchronous block - fast fetch
    raw_snapshot = _micro_client.fetch_snapshot(pair)
    
    exec_score = None
    spread_bps = None
    est_slippage_bps = None
    exec_snapshot_ts = None
    exec_features = {}
    
    if raw_snapshot.get("success"):
        exec_features = compute_execution_features(raw_snapshot, target_notional_usd, side)
        if "error" not in exec_features:
            # We enforce the latency limit sanity check (skip saving score if > 2000ms as instructed)
            latency = exec_features.get("latency_ms", 0)
            if latency <= 2000:
                exec_score = exec_features.get("exec_score")
                spread_bps = exec_features.get("spread_bps")
                est_slippage_bps = exec_features.get("est_slippage_bps")
                exec_snapshot_ts = sig["ts"]
            else:
                logger.warning(f"Snapshot latency {latency}ms exceeded 2000ms bound for {pair}, discarding score.")
        else:
            logger.warning(f"Exec feature compute failed for {pair}: {exec_features['error']}")

    db_payload["spread_bps"] = spread_bps
    db_payload["est_slippage_bps"] = est_slippage_bps
    db_payload["execution_score"] = exec_score
    db_payload["execution_snapshot_ts"] = exec_snapshot_ts


    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO signals (
                signal_id, pair, ts, side, entry, stop_loss, take_profit,
                score, regime, market_regime, btc_regime, signal_hour_utc,
                phase2_gate, phase2_allowed, phase2_score_multiplier,
                setup_score, execution_score, spread_bps, est_slippage_bps, execution_snapshot_ts,
                policy_version, policy_activated_at,
                signal_family, reason_trace, logic_version, config_version,
                prob_score, legacy_score, pwin, z_score, score_mode, risk_scale, rr_sl_mult, rr_tp_mult
            ) VALUES (
                %(signal_id)s, %(pair)s, %(ts)s, %(side)s, %(entry)s,
                %(stop_loss)s, %(take_profit)s, %(score)s, %(regime)s,
                %(market_regime)s, %(btc_regime)s, %(signal_hour_utc)s,
                %(phase2_gate)s, %(phase2_allowed)s, %(phase2_score_multiplier)s,
                %(setup_score)s, %(execution_score)s, %(spread_bps)s, %(est_slippage_bps)s, %(execution_snapshot_ts)s,
                %(policy_version)s, %(policy_activated_at)s,
                %(signal_family)s, %(reason_trace)s::jsonb, %(logic_version)s, %(config_version)s,
                %(prob_score)s, %(legacy_score)s, %(pwin)s, %(z_score)s, %(score_mode)s, %(risk_scale)s, %(rr_sl_mult)s, %(rr_tp_mult)s
            ) ON CONFLICT (signal_id) DO NOTHING
            """,
            db_payload,
        )

        if exec_snapshot_ts is not None and "error" not in exec_features:
            # Store full microstructure snapshot
            cur.execute(
                """
                INSERT INTO execution_snapshots (
                    signal_id, ts, best_bid, best_ask, mid_price, spread_bps,
                    bid_depth_usd_1pct, ask_depth_usd_1pct, depth_imbalance, est_slippage_bps,
                    last_1m_range_bps, last_1m_trade_imbalance, latency_ms, exec_score
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s
                ) ON CONFLICT (signal_id) DO NOTHING
                """,
                (
                    sig["signal_id"], exec_snapshot_ts,
                    exec_features.get("best_bid"), exec_features.get("best_ask"),
                    exec_features.get("mid_price"), exec_features.get("spread_bps"),
                    exec_features.get("bid_depth_usd_1pct"), exec_features.get("ask_depth_usd_1pct"),
                    exec_features.get("depth_imbalance"), exec_features.get("est_slippage_bps"),
                    exec_features.get("last_1m_range_bps"), exec_features.get("latency_ms"),
                    exec_features.get("exec_score")
                )
            )

        conn.commit()
    _LAST_SIGNAL = {
        **sig,
        "ts": sig["ts"].isoformat(),
        "market_regime": market_regime,
        "btc_regime": btc_regime,
        "signal_hour_utc": signal_hour_utc,
        "phase2_gate": phase2_gate,
        "phase2_allowed": phase2_allowed,
        "phase2_score_multiplier": phase2_score_multiplier,
        "setup_score": setup_score,
        "execution_score": execution_score,
        "policy_version": policy_version,
        "policy_activated_at": policy_activated_at,
    }
    
    # Notify SSE clients via PostgreSQL NOTIFY
    try:
        # Convert numpy types to native Python for JSON serialization
        sig_for_notify = {
            "signal_id": sig["signal_id"],
            "pair": sig["pair"],
            "ts": sig["ts"].isoformat(),
            "side": sig["side"],
            "entry": float(sig["entry"]),
            "stop_loss": float(sig["stop_loss"]),
            "tp1": float(sig["tp1"]),
            "tp2": float(sig["tp2"]),
            "take_profit": float(sig["take_profit"]),
            "score": float(sig["score"]),
            "setup_score": setup_score,
            "execution_score": execution_score,
            "regime": sig["regime"],
            "market_regime": market_regime,
            "btc_regime": btc_regime,
            "signal_hour_utc": signal_hour_utc,
            "phase2_gate": phase2_gate,
            "phase2_allowed": phase2_allowed,
            "phase2_score_multiplier": phase2_score_multiplier,
            "policy_version": policy_version,
            "policy_activated_at": policy_activated_at,
            "scan_profile": sig.get("scan_profile", getattr(config, "SCAN_PROFILE", "default")),
            "reason_trace": reason_trace,
            "logic_version": sig["logic_version"],
            "config_version": sig["config_version"],
        }
        with conn.cursor() as cur:
            cur.execute("NOTIFY new_signal, %s", (json.dumps(sig_for_notify, cls=_NumpyEncoder),))
            conn.commit()
        
        # Fallback: Notify API directly via HTTP
        try:
            # The API port is usually 8787 based on PM2 config
            requests.post("http://localhost:8787/api/publish_signal", json=sig_for_notify, timeout=1)
        except Exception as e:
            logging.warning(f"Direct API notification failed: {e}")
            
    except Exception as e:
        logging.error(f"Failed to NOTIFY new_signal: {e}")

    # Bot API 9.6 Institutional Alerting
    logging.info(
        "[SIGNAL ALERT] phase2_inserted pair=%s side=%s score=%.1f",
        sig.get("pair"),
        sig.get("side"),
        float(sig.get("score", 0.0)),
    )
    try:
        alert_text, alert_markup = format_sovereign_alert(sig)
        send_telegram(alert_text, reply_markup=alert_markup)
    except Exception:
        logging.exception(
            "[SIGNAL ALERT] Failed to dispatch Telegram signal alert for %s %s",
            sig.get("pair"),
            sig.get("side"),
        )

# ─── Core scan loop ────────────────────────────────────────────────────────────
# ─── Accelerator Tuners (v1.9.5) ───────────────────────────────────────────
SCANNER_WORKERS = config.SCANNER_WORKERS
SCANNER_TIMEOUT = config.SCANNER_CYCLE_TIMEOUT_SECONDS
_scan_lock = threading.Lock()


def _classify_signal_family(latest: pd.Series, df15: pd.DataFrame, regime: str, side: str) -> Tuple[str, Dict[str, Any]]:
    """
    Classify signal into family based on multi-factor stack evaluation.
    Returns (family_name, family_indicators_dict)
    """
    ind = {}
    
    # Core indicators
    ind['adx14'] = float(latest.get('adx14', 0))
    ind['rsi14'] = float(latest.get('rsi14', 50))
    ind['ema20'] = float(latest.get('ema20', 0))
    ind['ema50'] = float(latest.get('ema50', 0))
    ind['close'] = float(latest.get('close', 0))
    ind['atr14'] = float(latest.get('atr14', 0))
    ind['macd_hist'] = float(latest.get('macd_hist', 0))
    ind['volume'] = float(latest.get('volume', 0))
    ind['volume_sma20'] = float(latest.get('volume_sma20', 1))
    ind['vol_ratio'] = ind['volume'] / max(ind['volume_sma20'], 1)
    
    # Squeeze indicators
    ind['squeeze_on'] = latest.get('squeeze_on', False)
    ind['squeeze_fired'] = latest.get('squeeze_fired', False)
    ind['recent_squeeze_fire'] = latest.get('recent_squeeze_fire', False)
    
    # ATR expansion
    if len(df15) >= 20:
        atr15 = df15['atr14'].iloc[-15:].mean()
        atr20 = df15['atr14'].iloc[-20:].mean()
        ind['atr_expansion'] = atr15 > atr20 * 1.1
    else:
        ind['atr_expansion'] = False
    
    # Price distance from EMA (for mean reversion)
    ema_dist = abs(ind['close'] - ind['ema20']) / max(ind['ema20'], 0.0001)
    ind['ema_distance_pct'] = ema_dist * 100
    
    # === TREND STACK ===
    # Scoring: 2-of-3 indicator alignment qualifies (EMA cross, ADX, MACD)
    is_trend = False
    if ENABLE_TREND:
        trend_hits = 0
        if side == "LONG":
            if ind['ema20'] > ind['ema50']:
                trend_hits += 1
            if ind['adx14'] >= 22:
                trend_hits += 1
            if ind['macd_hist'] > 0:
                trend_hits += 1
        else:
            if ind['ema20'] < ind['ema50']:
                trend_hits += 1
            if ind['adx14'] >= 22:
                trend_hits += 1
            if ind['macd_hist'] < 0:
                trend_hits += 1
        is_trend = trend_hits >= 2
    
    # === VOLATILITY STACK ===
    # Scoring: squeeze OR (atr_expansion + volume surge)
    is_volatility = False
    if ENABLE_VOLATILITY:
        is_volatility = (
            (ind['recent_squeeze_fire'] or ind['squeeze_fired']) and
            ind['vol_ratio'] >= 1.5
        ) or (
            ind['atr_expansion'] and
            ind['vol_ratio'] >= 2.0
        )
    
    # === MEAN REVERSION STACK ===
    is_mean_rev = False
    if ENABLE_MEAN_REVERSION:
        if side == "LONG":
            is_mean_rev = (
                ind['adx14'] < 22 and
                ind['rsi14'] < 35 and
                ind['ema_distance_pct'] > 0.8
            )
        else:
            is_mean_rev = (
                ind['adx14'] < 22 and
                ind['rsi14'] > 65 and
                ind['ema_distance_pct'] > 0.8
            )
    
    # === MOMENTUM STACK ===
    is_momentum = False
    if ENABLE_MOMENTUM:
        if len(df15) >= 3:
            rsi_prev = df15['rsi14'].iloc[-3:].mean()
            rsi_curr = ind['rsi14']
            rsi_rising = rsi_curr > rsi_prev
            rsi_falling = rsi_curr < rsi_prev
            
            if side == "LONG":
                is_momentum = rsi_rising and ind['vol_ratio'] >= 1.2
            else:
                is_momentum = rsi_falling and ind['vol_ratio'] >= 1.2
    
    # Priority: Volatility > Trend > Mean Reversion > Momentum
    if is_volatility:
        return "volatility", ind
    elif is_trend:
        return "trend", ind
    elif is_mean_rev:
        return "mean_reversion", ind
    elif is_momentum:
        return "momentum", ind
    else:
        return "none", ind


# ─── Worker Logic (DB-FREE) ──────────────────────────────────────────────────
def analyze_pair(pair_idx_tuple: Tuple[str, int], btc_regime: str, btc_blocks_longs: bool, btc_blocks_shorts: bool) -> Optional[dict]:
    """Market Data Fetch + Signal Compute (Strictly NO DB Access).
    
    Returns a dict with `pair`, `candidate` (pass), and `training_records`
    (list of pass/reject data). Training records are logged to DB in the
    `scan_once` main thread.
    """
    pair, idx = pair_idx_tuple
    training_records = []  # Collect all training candidates (pass + reject)
    candidate = None  # Only one candidate can pass per pair

    def _result_payload(candidate_result=None, records=None) -> dict:
        return {
            "pair": pair,
            "candidate": candidate_result,
            "training_records": records if records is not None else [],
        }
    
    try:
        # 1. Pipeline: Market Data Snapshot
        df15 = add_indicators(fetch_klines(pair, "15m", LOOKBACK_15M))
        df4  = fetch_klines(pair, "4h", LOOKBACK_4H)
        df1h = fetch_klines(pair, "1h", 100)
        
        regime = classify_regime(df4)
        df1h["ema50"] = ema(df1h["close"], 50)
        _l1h = df1h.iloc[-1]
        is_1h_bullish = _l1h["close"] > _l1h["ema50"]
        is_1h_bearish = _l1h["close"] < _l1h["ema50"]
        
        latest = df15.iloc[-1]
        prev_bar = df15.iloc[-2]

        # ── Sprint D: Probability-Primary Scoring ──────────────────────────────
        # Step 1: Legacy template scores (kept as shadow comparison baseline)
        long_score_legacy, long_trace_legacy = score_long_signal(latest, regime, {"funding_rate": 0, "ls_ratio": 1.0})
        short_score_pretemplates, short_trace_legacy = score_short_signal(latest, prev_bar, regime, {"funding_rate": 0, "ls_ratio": 1.0})

        # Step 2: Probability model scores (primary)
        long_score_prob,  long_trace_prob  = score_long_probability(latest, regime, {"funding_rate": 0, "ls_ratio": 1.0})
        short_score_prob, short_trace_prob = score_short_probability(latest, regime, {"funding_rate": 0, "ls_ratio": 1.0})

        # Step 3: Family tags — inherit legacy short tag if present
        long_family_tag  = str(long_trace_prob.get("family_tag", "prob_long"))
        short_family_tag = str(short_trace_legacy.get("family_tag",
                               short_trace_prob.get("family_tag", "prob_short")))

        # Step 4: Probability floor gate (intrinsic edge check BEFORE blending)
        hour_utc = latest["close_time"].hour
        long_prob_ok,  long_prob_gate  = probability_gate("LONG",  long_family_tag,  long_score_prob, regime, hour_utc)
        short_prob_ok, short_prob_gate = probability_gate("SHORT", short_family_tag, short_score_prob, regime, hour_utc)

        # Step 5: Blend or fall back to legacy
        if getattr(config, "USE_PROBABILITY_SCORER", True):
            long_score_raw  = blend_primary_score(long_score_prob,  long_score_legacy)  if long_prob_ok  else 0.0
            short_score_raw = blend_primary_score(short_score_prob, short_score_pretemplates) if short_prob_ok else 0.0
        else:
            long_score_raw  = long_score_legacy
            short_score_raw = short_score_pretemplates

        # Step 6: Compose full traces (probability primary + legacy shadow)
        _score_mode = "blended_probability_primary" if getattr(config, "USE_PROBABILITY_SCORER", True) else "legacy_only"

        long_trace = dict(long_trace_prob)
        long_trace["legacy_score"]    = float(long_score_legacy)
        long_trace["prob_score"]      = float(long_score_prob)
        long_trace["score_mode"]      = _score_mode
        long_trace["family_tag"]      = long_family_tag
        long_trace["probability_gate"] = long_prob_gate
        if not long_prob_ok:
            long_trace["rejection_gate"] = long_prob_gate
        long_trace["legacy_trace"]    = long_trace_legacy

        short_trace = dict(short_trace_prob)
        short_trace["legacy_score"]   = float(short_score_pretemplates)
        short_trace["prob_score"]     = float(short_score_prob)
        short_trace["score_mode"]     = _score_mode
        short_trace["family_tag"]     = short_family_tag
        short_trace["probability_gate"] = short_prob_gate
        if not short_prob_ok:
            short_trace["rejection_gate"] = short_prob_gate
        short_trace["legacy_trace"]   = short_trace_legacy
        if "template_scores" in short_trace_legacy:
            short_trace["template_scores"] = short_trace_legacy["template_scores"]

        # Step 7: Telemetry — visible in PM2 logs for cutover validation
        logger.info(
            "[SCORE CUTOVER] sym=%s regime=%s btc=%s "
            "long_prob=%.2f long_legacy=%.2f long_raw=%.2f "
            "short_prob=%.2f short_legacy=%.2f short_raw=%.2f "
            "long_gate=%s short_gate=%s short_family=%s",
            pair, regime, btc_regime,
            float(long_score_prob), float(long_score_legacy), float(long_score_raw),
            float(short_score_prob), float(short_score_pretemplates), float(short_score_raw),
            long_prob_gate, short_prob_gate, short_family_tag,
        )

        # Step 8: Short context penalties applied AFTER probability gating + blend
        if short_score_raw > 0:
            short_score_after_ctx, short_penalty_trace = apply_short_context_penalties(
                short_score_raw,
                short_family_tag,
                regime,
                btc_regime,
            )
            short_trace["context_penalties"] = short_penalty_trace
            short_score = short_score_after_ctx
        else:
            short_score = short_score_raw

        long_score = long_score_raw

        # --- Directional shadow model (symmetric, only logging) ---
        alpha_default = {"funding_rate": 0, "ls_ratio": 1.0}
        directional = compute_directional_score(latest, prev_bar, regime, alpha_default, df15)


        # 2. Dynamic Coherence Tuning (v2.0 Doctrine - Push/Pull Symmetry)
        # Only active in coherence-enabled profiles (sim_coherence_v1).
        # In live profiles, skew = 0 → no effect.
        if COHERENCE_ENABLED:
            skew = _side_controller.get_skew()
            
            long_score_raw  = long_score
            short_score_raw = short_score
            
            long_score_coh  = long_score_raw - skew
            short_score_coh = short_score_raw + skew
            
            # Do-No-Harm Floor: boost cannot rescue garbage
            if skew < 0 and long_score_raw < COHERENCE_RESCUE_FLOOR:
                long_adj = long_score_raw
            else:
                long_adj = long_score_coh
                
            if skew > 0 and short_score_raw < COHERENCE_RESCUE_FLOOR:
                short_adj = short_score_raw
            else:
                short_adj = short_score_coh
                
            long_score, short_score = long_adj, short_adj
        else:
            skew = 0.0
            short_score_coh = short_score  # not adjusted - define for telemetry refs below

        # 3. Gate Validation (Soft Penalties)
        if (time.time() - latest["close_time"].timestamp()) > DATA_FRESHNESS_MAX_SECONDS:
            return _result_payload()
        if len(df15) < SCANNER_WARMUP_BARS:
            return _result_payload()

        # Log zero scores to identify blockers (exhaustion, etc.)
        if long_score == 0.0 and long_trace.get("reasons_fail"):
            logger.info("SCORE_ZERO sym=%s side=LONG reason=%s adx14=%.2f family=pre-exhaustion",
                pair,
                long_trace["reasons_fail"][0],
                float(latest.get("adx14", 0))
            )
            # Track exhaustion kills (score = 0 from exhaustion blocker)
            if "Exhausted" in long_trace["reasons_fail"][0]:
                with _telemetry_lock:
                    _family_telemetry["rejected_by_gate"]["exhaustion"]["none"] += 1
                # Training record: exhaustion rejection
                signal_family, family_indicators = _classify_signal_family(latest, df15, regime, "LONG")
                training_records.append({
                    "pair": pair,
                    "side": "LONG",
                    "score": 0.0,
                    "signal_family": signal_family,
                    "family_indicators": family_indicators,
                    "rejection_gate": "exhaustion",
                    "would_have_passed_live": False,
                    "latest": latest,
                    "regime": regime,
                    "btc_regime": btc_regime,
                    "scan_profile": getattr(config, 'SCAN_PROFILE', 'default'),
                    "feature_version": getattr(config, 'FEATURE_VERSION', 'v1.0'),
                    "trace": long_trace,
                })
        if short_score == 0.0 and short_trace.get("reasons_fail"):
            logger.info("SCORE_ZERO sym=%s side=SHORT reason=%s adx14=%.2f family=pre-exhaustion",
                pair,
                short_trace["reasons_fail"][0],
                float(latest.get("adx14", 0))
            )
            if "Exhausted" in short_trace["reasons_fail"][0]:
                with _telemetry_lock:
                    _family_telemetry["rejected_by_gate"]["exhaustion"]["none"] += 1
                # Training record: exhaustion rejection
                signal_family, family_indicators = _classify_signal_family(latest, df15, regime, "SHORT")
                training_records.append({
                    "pair": pair,
                    "side": "SHORT",
                    "score": 0.0,
                    "signal_family": signal_family,
                    "family_indicators": family_indicators,
                    "rejection_gate": "exhaustion",
                    "would_have_passed_live": False,
                    "latest": latest,
                    "regime": regime,
                    "btc_regime": btc_regime,
                    "scan_profile": getattr(config, 'SCAN_PROFILE', 'default'),
                    "feature_version": getattr(config, 'FEATURE_VERSION', 'v1.0'),
                    "trace": short_trace,
                })

        # Keep track of what specifically killed the short
        short_rejection_gate = None
        _tpl = (short_trace.get("template_scores") or {})
        any_template_nonzero = any(v > 0 for v in _tpl.values()) if _tpl else short_score_pretemplates > 0
        if short_score == 0 and any_template_nonzero:
             short_rejection_gate = "exhaustion"

        # Track regime blocks before family classification
        # Profile-aware: soft penalty in sim, hard block in live.
        if BLOCK_AGAINST_REGIME:
            if regime in ("STRONG_DOWNTREND", "DOWNTREND") and long_score > 0:
                if SOFT_REGIME_GATE:
                    long_score -= REGIME_SOFT_PENALTY
                else:
                    long_score = 0
                with _telemetry_lock:
                    _family_telemetry["rejected_by_gate"]["regime_block"]["none"] += 1

        if btc_blocks_longs and long_score > 0:
            if SOFT_BTC_GATE:
                long_score -= BTC_SOFT_PENALTY
            else:
                long_score = 0
            with _telemetry_lock:
                _family_telemetry["rejected_by_gate"]["btc_block"]["none"] += 1

        if not is_1h_bullish and long_score > 0:
            long_score = 0
            with _telemetry_lock:
                _family_telemetry["rejected_by_gate"]["1h_trend"]["none"] += 1
        if not is_1h_bearish and short_score > 0:
            # Allow failed bounces to bypass 1h trend checks, they are inherently counter-trend structural plays
            if short_trace.get("family_tag") != "failed_bounce":
                short_score = 0
                short_rejection_gate = short_rejection_gate or "1h_trend"
                with _telemetry_lock:
                    _family_telemetry["rejected_by_gate"]["1h_trend"]["none"] += 1
        # >>> SPRINT B: Near-Miss & Hit-Rate Telemetry Block <<<
        with _telemetry_lock:
            if short_score_pretemplates == 0:
                _family_telemetry["short_attrition"]["short_template_zero"] += 1
            elif short_score_pretemplates > 0 and short_score_pretemplates < COHERENCE_RESCUE_FLOOR and short_score_coh >= COHERENCE_RESCUE_FLOOR:
                 # It would have survived with coherence, but raw was below floor
                 _family_telemetry["short_attrition"]["short_floor_denied"] += 1
            
            if short_score_pretemplates > 0: # It actually matched a template natively
                # Determine if it missed by <5, <10, <15 from baseline 50
                missed_by = max(0, 50 - short_score)
                miss_band = "<5" if missed_by <= 5 else ("<10" if missed_by <= 10 else ("<15" if missed_by <= 15 else ">15"))
                
                log_str = (
                    f"[SHORT_CANDIDATE] sym={pair} "
                    f"raw={short_score_pretemplates:.1f} coh_adj={short_score_coh:.1f} final={short_score:.1f} "
                    f"fb={_tpl.get('failed_bounce',0):.1f} bd={_tpl.get('breakdown',0):.1f} mr={_tpl.get('mean_reversion',0):.1f} "
                    f"family={short_trace.get('family_tag','none')} "
                )
                if short_score < 50:
                    short_rejection_gate = short_rejection_gate or "wolfram_five_cell (score < 50)"
                    log_str += f"NEAR_MISS: {miss_band} pt miss. KILLED_BY: {short_rejection_gate}"
                    
                    if missed_by <= 5:
                        _family_telemetry["short_attrition"]["short_near_miss_lt5"] += 1
                    elif missed_by <= 10:
                        _family_telemetry["short_attrition"]["short_near_miss_lt10"] += 1
                    else:
                        _family_telemetry["short_attrition"]["short_killed_by_gate"] += 1
                        
                else:
                    log_str += "SURVIVED_GATES: Pass to Wolfram / Post-Selection"
                    _family_telemetry["short_attrition"]["short_emitted"] += 1
    
                logger.info(log_str)
        # >>> END TELEMETRY BLOCK <<<

        price   = float(latest["close"])
        atr_val = float(latest["atr14"])

        for side, score, trace in (("LONG", long_score, long_trace), ("SHORT", short_score, short_trace)):
            # Classify signal family BEFORE gate checks (to track which family gets killed by which gate)
            signal_family, family_indicators = _classify_signal_family(latest, df15, regime, side)
            
            # (Sprint B) Override short family with the specific alpha template tag
            if side == "SHORT" and trace and "family_tag" in trace:
                signal_family = trace["family_tag"]
            
            with _telemetry_lock:
                _family_telemetry["assigned"][signal_family] += 1
            
            # Initialize training row with common fields
            training_row = {
                "pair": pair,
                "side": side,
                "score": score,
                "signal_family": signal_family,
                "family_indicators": family_indicators,
                "latest": latest,
                "regime": regime,
                "btc_regime": btc_regime,
                "scan_profile": getattr(config, 'SCAN_PROFILE', 'default'),
                "feature_version": getattr(config, 'FEATURE_VERSION', 'v1.0'),
                "trace": trace,
                "would_have_passed_live": False,
                "rejection_gate": None,
                "directional_long_score": directional["directional_long_score"],
                "directional_short_score": directional["directional_short_score"],
                "directional_net": directional["directional_net"],
                "directional_margin": directional["directional_margin"],
                "directional_primary_side": directional["directional_primary_side"],
            }
            
            # Initialize vwap_delta early to avoid scope issues
            vwap_delta = 0.0
            _vwap = latest.get("vwap")
            if _vwap and float(_vwap) > 0:
                vwap_delta = (price - float(_vwap)) / float(_vwap)
            
            # Check ALL rejection gates in order - capture first failure
            rejection_gate = None
            
            # 1. Score zero (exhaustion) - highest priority
            if score == 0.0:
                rejection_gate = "score_zero"
                with _telemetry_lock:
                    _family_telemetry["rejected_by_gate"]["exhaustion"][signal_family] += 1
            
            # 2. Min score gate
            elif score < MIN_SIGNAL_SCORE:
                rejection_gate = "min_score"
                with _telemetry_lock:
                    _family_telemetry["rejected_by_gate"]["min_score"][signal_family] += 1
            
            # 3. Regime block gate — only applies to LONG in downtrend.
            # Shorts are handled upstream by apply_short_context_penalties (bounded, auditable).
            elif BLOCK_AGAINST_REGIME:
                if regime in ("STRONG_DOWNTREND", "DOWNTREND") and side == "LONG":
                    rejection_gate = "regime_block"
                    with _telemetry_lock:
                        _family_telemetry["rejected_by_gate"]["regime_block"][signal_family] += 1
            
            # 4. BTC macro block gate
            elif (btc_blocks_longs and side == "LONG") or (btc_blocks_shorts and side == "SHORT"):
                rejection_gate = "btc_block"
                with _telemetry_lock:
                    _family_telemetry["rejected_by_gate"]["btc_block"][signal_family] += 1
            
            # 5. 1h trend block gate
            elif (not is_1h_bullish and side == "LONG") or (not is_1h_bearish and side == "SHORT"):
                rejection_gate = "1h_trend_block"
                with _telemetry_lock:
                    _family_telemetry["rejected_by_gate"]["1h_trend"][signal_family] += 1
            
            # 6. Squeeze gate
            elif REQUIRE_SQUEEZE_GATE and not latest.get("recent_squeeze_fire", False):
                rejection_gate = "squeeze"
                with _telemetry_lock:
                    _family_telemetry["rejected_by_gate"]["squeeze"][signal_family] += 1
            
            # 7. VWAP gate
            elif rejection_gate is None:
                epsilon = VWAP_EPSILON_0 + VWAP_LAMBDA * (atr_val / price)
                if (1 if side == "LONG" else -1) * vwap_delta > epsilon:
                    rejection_gate = "vwap"
                    with _telemetry_lock:
                        _family_telemetry["rejected_by_gate"]["vwap"][signal_family] += 1
            
            # 8. Volume gate
            if rejection_gate is None:
                vol_ratio = trace.get("volume_ratio", 0.0)
                if vol_ratio < VOLUME_RATIO_MIN:
                    rejection_gate = "volume"
                    with _telemetry_lock:
                        _family_telemetry["rejected_by_gate"]["volume"][signal_family] += 1
            
            # Set final status based on rejection gate
            if rejection_gate is None:
                # PASSED all gates
                training_row["would_have_passed_live"] = True
                training_row["rejection_gate"] = None
                with _telemetry_lock:
                    _family_telemetry["passed"][signal_family] += 1
                
                # Only set candidate if not already set (first side that passes wins)
                if candidate is None:
                    atr_pct = atr_val / price
                    sl_mult = ATR_SL_MULTIPLIER
                    if atr_pct > MAX_ATR_PCT_FOR_FULL_SL:
                        sl_mult = min(sl_mult, CAP_SL_MULTIPLIER_WHEN_WIDE)
                    
                    stop_price = price - sl_mult * atr_val if side == "LONG" else price + sl_mult * atr_val
                    
                    candidate = {
                        "pair": pair,
                        "side": side,
                        "latest": latest,
                        "regime": regime,
                        "score": score,
                        "reason_trace": trace,
                        "universe_rank": idx,
                        "volume_ratio": vol_ratio,
                        "entry": price,
                        "stop_loss": stop_price,
                        "vwap_delta": vwap_delta,
                        "df15": df15,
                        "btc_regime": btc_regime,
                        "signal_family": signal_family,
                        "family_indicators": family_indicators,
                        # Sprint D: probability scorer fields for ranking + telemetry
                        "pwin":         float(trace.get("pwin", 0.0)),
                        "prob_score":   float(trace.get("prob_score", score)),
                        "legacy_score": float(trace.get("legacy_score", score)),
                        "score_mode":   str(trace.get("score_mode", "legacy_only")),
                    }

            else:
                # REJECTED by specific gate
                training_row["rejection_gate"] = rejection_gate
            
            # Add training row to records (ALWAYS add, regardless of pass/fail)
            training_records.append(training_row)

        # Return both candidate (if any) and all training records (always 2 rows)
        return _result_payload(candidate, training_records)
    except Exception as e:
        logger.error(f"[SCAN ERROR] {pair}: {e}")
        return _result_payload(candidate, training_records)

def scan_once() -> None:
    """Main thread orchestrator (Serial Writes / Parallel Compute)."""
    global _LAST_SCAN_TS
    
    if not _scan_lock.acquire(blocking=False):
        logger.warning("[SCAN SKIPPED] previous cycle still running")
        return

    try:
        # Reset family telemetry for this cycle
        _reset_family_telemetry()
        
        started = time.time()
        btc_regime = get_btc_macro_regime()
        btc_blocks_longs  = btc_regime in ("STRONG_DOWNTREND", "DOWNTREND")
        btc_blocks_shorts = btc_regime in ("STRONG_UPTREND",   "UPTREND")
        
        # Parallel Execution
        pair_tasks = [(pair, i) for i, pair in enumerate(PAIRS)]
        results = []
        passed_count = 0
        rejected_count = 0
        error_count = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=SCANNER_WORKERS) as executor:
            futures = {
                executor.submit(analyze_pair, task, btc_regime, btc_blocks_longs, btc_blocks_shorts): task[0]
                for task in pair_tasks
            }
            try:
                for future in concurrent.futures.as_completed(futures, timeout=SCANNER_TIMEOUT):
                    sym = futures[future]
                    try:
                        res = future.result()
                        if res:
                            results.append(res)
                            passed_count += 1
                        else:
                            rejected_count += 1
                    except Exception as exc:
                        error_count += 1
                        logger.error(f"[FUTURE ERROR] {sym}: {exc}")
            except concurrent.futures.TimeoutError:
                logger.warning(f"[SCAN TIMEOUT] cycle exceeded {SCANNER_TIMEOUT}s; ignoring stragglers")

        # Serialized Persistence (Main Thread)
        candidates = []
        with db_conn() as conn:
            # Log ALL training candidates (passes + rejections) to training table
            for r in results:
                if "pair" not in r:
                    logger.error("PHASE2_SKIP result missing pair key: %s", r)
                    continue
                training_records = r.get("training_records", [])
                for tr in training_records:
                    if "pair" not in tr:
                        logger.error("PHASE2_SKIP training record missing pair key: %s", tr)
                        continue
                    # Enhanced training data logging with all fields
                    inserted_training_id = log_training_candidate(
                        conn=conn,
                        symbol=tr["pair"],
                        side=tr["side"],
                        latest=tr["latest"],
                        regime=tr["regime"],
                        btc_regime=tr["btc_regime"],
                        score=tr["score"],
                        rejection_gate=tr["rejection_gate"],
                        would_have_passed_live=tr["would_have_passed_live"],
                        signal_family=tr["signal_family"],
                        alpha=None,  # Will be fetched below for passes
                        scan_profile=tr.get("scan_profile", "default"),
                        feature_version=tr.get("feature_version", "v1.0"),
                        family_indicators=tr.get("family_indicators", {}),
                        trace=tr.get("trace", {}),
                        # NEW
                        directional_long_score=tr.get("directional_long_score"),
                        directional_short_score=tr.get("directional_short_score"),
                        directional_net=tr.get("directional_net"),
                        directional_margin=tr.get("directional_margin"),
                        directional_primary_side=tr.get("directional_primary_side"),
                    )
                    tr["training_candidate_id"] = inserted_training_id
                    candidate_ref = r.get("candidate")
                    if candidate_ref and candidate_ref.get("pair") == tr["pair"] and candidate_ref.get("side") == tr["side"]:
                        candidate_ref["_training_candidate_id"] = inserted_training_id
            # Commit training data batch
            conn.commit()
            training_records_count = sum(len(r.get('training_records', [])) for r in results)
            logger.info(f"[TRAINING_DATA] Logged {training_records_count} training records")
            
            # Telegram operational alert for training data
            if training_records_count > 0:
                alert_operational_event("training_data", f"Logged {training_records_count} training records", {"record_count": training_records_count})
            
            # Process candidates (if any) for Phase 2
            pairs_processed = len(results)
            setups_viable_pre_phase2 = 0
            setups_blocked_phase2 = 0
            for r in results:
                if "pair" not in r:
                    logger.error("PHASE2_SKIP result missing pair key: %s", r)
                    continue
                candidate = r.get("candidate")
                if not candidate:
                    continue

                setups_viable_pre_phase2 += 1
                candidate.setdefault("reason_trace", {})
                candidate["reason_trace"]["execution_hour_utc"] = _get_execution_hour_utc(candidate["latest"])

                # Cooldown check
                if cooldown_active(conn, candidate["pair"], candidate["latest"]["close_time"].to_pydatetime()):
                    candidate["raw_score"] = float(candidate.get("score", 0.0))
                    candidate["reason_trace"]["phase2_rejection_gate"] = "phase2_cooldown"
                    candidate["reason_trace"]["execution_multiplier"] = 1.0
                    candidate["reason_trace"]["raw_score"] = float(candidate["raw_score"])
                    candidate["reason_trace"]["final_score"] = float(candidate.get("score", 0.0))
                    _annotate_phase2_context(
                        candidate,
                        phase2_allowed=False,
                        phase2_gate="phase2_cooldown",
                        phase2_score_multiplier=1.0,
                        execution_score=float(candidate.get("score", 0.0)),
                    )
                    _update_training_candidate_phase2_metadata(
                        conn,
                        symbol=candidate["pair"],
                        side=candidate["side"],
                        trace=candidate["reason_trace"],
                        rejection_gate="phase2_cooldown",
                        final_score=float(candidate.get("score", 0.0)),
                        would_have_passed_live=False,
                        training_candidate_id=candidate.get("_training_candidate_id"),
                    )
                    logger.info(
                        "[PHASE2_REJECT] pair=%s side=%s gate=%s raw=%.2f final=%.2f exec_mult=%.2f",
                        candidate["pair"],
                        candidate["side"],
                        "phase2_cooldown",
                        float(candidate["reason_trace"]["raw_score"]),
                        float(candidate["reason_trace"]["final_score"]),
                        float(candidate["reason_trace"]["execution_multiplier"]),
                    )
                    setups_blocked_phase2 += 1
                    continue

                # Real derivatives alpha for Phase 2
                alpha = get_derivatives_alpha(conn, candidate["pair"])

                # Native Phase-2 re-score (this is the sovereign score)
                if candidate["side"] == "LONG":
                    candidate["score"], candidate["reason_trace"] = score_long_signal(candidate["latest"], candidate["regime"], alpha)
                else:
                    _df15 = candidate.get("df15")
                    _prev_bar = _df15.iloc[-2] if _df15 is not None and len(_df15) >= 2 else candidate["latest"]
                    candidate["score"], candidate["reason_trace"] = score_short_signal(candidate["latest"], _prev_bar, candidate["regime"], alpha)

                candidate.setdefault("reason_trace", {})
                candidate["reason_trace"]["execution_hour_utc"] = _get_execution_hour_utc(candidate["latest"])

                # If native score dies here, FT may not revive it.
                if candidate["score"] <= 0:
                    candidate["raw_score"] = float(candidate.get("score", 0.0))
                    candidate["reason_trace"]["phase2_rejection_gate"] = "phase2_rescore_zero"
                    candidate["reason_trace"]["execution_multiplier"] = 1.0
                    candidate["reason_trace"]["raw_score"] = float(candidate["raw_score"])
                    candidate["reason_trace"]["final_score"] = float(candidate.get("score", 0.0))
                    _annotate_phase2_context(
                        candidate,
                        phase2_allowed=False,
                        phase2_gate="phase2_rescore_zero",
                        phase2_score_multiplier=1.0,
                        execution_score=float(candidate.get("score", 0.0)),
                    )
                    _update_training_candidate_phase2_metadata(
                        conn,
                        symbol=candidate["pair"],
                        side=candidate["side"],
                        trace=candidate["reason_trace"],
                        rejection_gate="phase2_rescore_zero",
                        final_score=float(candidate.get("score", 0.0)),
                        would_have_passed_live=False,
                        training_candidate_id=candidate.get("_training_candidate_id"),
                    )
                    logger.info(
                        "[PHASE2_REJECT] pair=%s side=%s gate=%s raw=%.2f final=%.2f exec_mult=%.2f",
                        candidate["pair"],
                        candidate["side"],
                        "phase2_rescore_zero",
                        float(candidate["reason_trace"]["raw_score"]),
                        float(candidate["reason_trace"]["final_score"]),
                        float(candidate["reason_trace"]["execution_multiplier"]),
                    )
                    setups_blocked_phase2 += 1
                    continue

                # FT bridge may only boost already-valid native survivors.
                if BRIDGE_PHASE2_ENABLED:
                    candidate["score"], candidate["reason_trace"] = _merge_phase2_bridge_bonus(
                        side=candidate["side"],
                        native_score=float(candidate["score"]),
                        native_trace=candidate["reason_trace"],
                        df15=candidate["df15"],
                        regime=candidate["regime"],
                        alpha=alpha,
                        signal_family=candidate.get("signal_family", "none"),
                    )

                # Preserve raw score before execution multiplier.
                candidate["raw_score"] = float(candidate["score"])

                # NEW: regime/time execution control (Phase 2 only)
                blocked, exec_mult, exec_gate = _execution_regime_time_adjustment(
                    candidate["regime"],
                    candidate["side"],
                    candidate["latest"],
                )

                candidate.setdefault("reason_trace", {})
                candidate["reason_trace"]["raw_score"] = float(candidate["raw_score"])
                candidate["reason_trace"]["execution_hour_utc"] = _get_execution_hour_utc(candidate["latest"])

                if blocked:
                    candidate["score"] = 0.0
                    candidate["reason_trace"]["execution_multiplier"] = 0.0
                    candidate["reason_trace"]["phase2_rejection_gate"] = exec_gate
                    candidate["reason_trace"]["final_score"] = 0.0
                    _annotate_phase2_context(
                        candidate,
                        phase2_allowed=False,
                        phase2_gate=exec_gate,
                        phase2_score_multiplier=0.0,
                        execution_score=0.0,
                    )
                    _update_training_candidate_phase2_metadata(
                        conn,
                        symbol=candidate["pair"],
                        side=candidate["side"],
                        trace=candidate["reason_trace"],
                        rejection_gate=exec_gate,
                        final_score=0.0,
                        would_have_passed_live=False,
                        training_candidate_id=candidate.get("_training_candidate_id"),
                    )
                    logger.info(
                        "[PHASE2_REJECT] pair=%s side=%s gate=%s raw=%.2f final=%.2f exec_mult=%.2f",
                        candidate["pair"],
                        candidate["side"],
                        exec_gate,
                        float(candidate["reason_trace"]["raw_score"]),
                        float(candidate["reason_trace"]["final_score"]),
                        float(candidate["reason_trace"]["execution_multiplier"]),
                    )
                    setups_blocked_phase2 += 1
                    continue

                candidate["score"] = float(candidate["score"]) * float(exec_mult)
                candidate["reason_trace"]["execution_multiplier"] = float(exec_mult)
                candidate["reason_trace"]["final_score"] = float(candidate["score"])

                # Re-check floor after regime/time weighting.
                if candidate["score"] < MIN_SIGNAL_SCORE:
                    candidate["reason_trace"]["phase2_rejection_gate"] = "phase2_post_multiplier_min_score"
                    _annotate_phase2_context(
                        candidate,
                        phase2_allowed=False,
                        phase2_gate="phase2_post_multiplier_min_score",
                        phase2_score_multiplier=float(exec_mult),
                        execution_score=float(candidate["score"]),
                    )
                    _update_training_candidate_phase2_metadata(
                        conn,
                        symbol=candidate["pair"],
                        side=candidate["side"],
                        trace=candidate["reason_trace"],
                        rejection_gate="phase2_post_multiplier_min_score",
                        final_score=float(candidate["score"]),
                        would_have_passed_live=False,
                        training_candidate_id=candidate.get("_training_candidate_id"),
                    )
                    logger.info(
                        "[PHASE2_REJECT] pair=%s side=%s gate=%s raw=%.2f final=%.2f exec_mult=%.2f",
                        candidate["pair"],
                        candidate["side"],
                        "phase2_post_multiplier_min_score",
                        float(candidate["reason_trace"]["raw_score"]),
                        float(candidate["reason_trace"]["final_score"]),
                        float(candidate["reason_trace"]["execution_multiplier"]),
                    )
                    setups_blocked_phase2 += 1
                    continue

                _annotate_phase2_context(
                    candidate,
                    phase2_allowed=True,
                    phase2_gate=None,
                    phase2_score_multiplier=float(candidate.get("reason_trace", {}).get("execution_multiplier", 1.0)),
                    execution_score=float(candidate["score"]),
                )
                _update_training_candidate_phase2_metadata(
                    conn,
                    symbol=candidate["pair"],
                    side=candidate["side"],
                    trace=candidate["reason_trace"],
                    rejection_gate=None,
                    final_score=float(candidate["score"]),
                    would_have_passed_live=True,
                    training_candidate_id=candidate.get("_training_candidate_id"),
                )
                candidates.append(candidate)

            selected = select_top_ranked_wolfram_signals(candidates)
            # ── Idim Gate Patch v1 (Post-Execution Selection) ──────
            emitted = []
            for s in selected:
                # Normalizing for apply_gates expectation
                _s_dict = {
                    'pair': s['pair'],
                    'side': s['side'],
                    'score': float(s['score']),
                    'regime': s.get('regime', ''),
                    'btc_regime': s.get('btc_regime', 'UNKNOWN'),
                    'family': (s.get('signal_family') or 'none').upper()
                }
                
                ok, reason = apply_gates(_s_dict)
                if not ok:
                    logger.info(
                        '[GATE_BLOCKED] reason=%s pair=%s side=%s score=%.2f regime=%s family=%s',
                        reason, s['pair'], s['side'], s['score'], 
                        s.get('regime', ''), s.get('signal_family', 'none')
                    )
                    continue
                
                emitted.append(s)
            # ── end v1.5 Filter Patch ──────────────────────────────

            for s in emitted:
                sig = build_signal(
                    s["pair"], s["side"], s["latest"], s["regime"], s["score"], s["reason_trace"],
                    signal_family=s.get("signal_family", "none"),
                    family_indicators=s.get("family_indicators", {}),
                )
                sig["btc_regime"] = s.get("btc_regime", btc_regime)
                sig["market_regime"] = s.get("market_regime", s["regime"])
                sig["signal_hour_utc"] = int(s.get("signal_hour_utc", _get_execution_hour_utc(s["latest"])))
                sig["phase2_gate"] = s.get("phase2_gate") or "allowed"
                sig["phase2_allowed"] = bool(s.get("phase2_allowed", True))
                sig["phase2_score_multiplier"] = float(s.get("phase2_score_multiplier", s.get("reason_trace", {}).get("execution_multiplier", 1.0)))
                sig["setup_score"] = float(s.get("setup_score", s.get("raw_score", s["score"])))
                sig["execution_score"] = float(s.get("execution_score", s["score"]))
                sig["policy_version"] = s.get("policy_version", POLICY_VERSION)
                sig["policy_activated_at"] = s.get("policy_activated_at", POLICY_ACTIVATED_AT)
                sig["scan_profile"] = getattr(config, "SCAN_PROFILE", "default")
                insert_signal(conn, sig)
                log_event("INFO", "scanner", "phase2_inserted", {
                    "pair": s["pair"],
                    "side": s["side"],
                    "score": float(s["score"]),
                    "setup_score": float(sig.get("setup_score", s.get("raw_score", s["score"]))),
                    "execution_score": float(sig.get("execution_score", s["score"])),
                    "execution_multiplier": float(sig.get("phase2_score_multiplier", s.get("reason_trace", {}).get("execution_multiplier", 1.0))),
                    "signal_family": s.get("signal_family", "none"),
                    "btc_regime": sig.get("btc_regime"),
                    "signal_hour_utc": sig.get("signal_hour_utc"),
                    "phase2_allowed": sig.get("phase2_allowed"),
                    "policy_version": sig.get("policy_version"),
                    "scan_profile": sig.get("scan_profile"),
                })

            duration = time.time() - started
            _LAST_SCAN_TS = started
            
            # Coherence Monitoring (v2.0 Doctrine)
            coh = _side_controller.get_stats()
            delta_coh = abs(coh['long_share'] - 0.5)
            skew_label = "L-Heavy" if coh['skew'] > 0 else "S-Heavy" if coh['skew'] < 0 else "Neutral"
            coh_status = "ACTIVE" if COHERENCE_ENABLED else "MONITOR-ONLY"
            logging.info(
                f"[COHERENCE] status={coh_status} | long_share={coh['long_share']:.1%} | "
                f"delta={delta_coh:.3f} | skew={coh['skew']:+.1f} ({skew_label}) | "
                f"window={coh['rolling_n']}/{COHERENCE_WINDOW} | "
                f"gates=regime:{'soft' if SOFT_REGIME_GATE else 'hard'}/btc:{'soft' if SOFT_BTC_GATE else 'hard'}"
            )

            # Family-level telemetry summary (strategic visibility)
            _log_family_telemetry()


            _v15_blocked = len(selected) - len(emitted)
            
            # Heartbeat Summary
            logging.info(
                f"[CYCLE COMPLETE] universe={len(PAIRS)} | "
                f"pairs_processed={pairs_processed} | viable_pre_phase2={setups_viable_pre_phase2} | "
                f"blocked_phase2={setups_blocked_phase2} | v15_gate_blocked={_v15_blocked} | signals_emitted={len(emitted)} | "
                f"worker_rejected={rejected_count} | errors={error_count} | "
                f"duration={duration:.2f}s | next={SCAN_INTERVAL_SECONDS}s"
            )
            
            log_event("INFO", "scanner", "scan_complete", {
                "duration": float(round(duration, 2)),
                "pairs_processed": int(pairs_processed),
                "setups_viable_pre_phase2": int(setups_viable_pre_phase2),
                "setups_blocked_phase2": int(setups_blocked_phase2),
                "v15_gate_blocked": int(_v15_blocked),
                "signals_emitted": int(len(emitted)),
                "worker_rejected": int(rejected_count),
                "errors": int(error_count),
                "legacy_candidates": int(passed_count),
            })
            
            # Telegram operational alert for cycle completion
            metrics = {
                "universe_size": len(PAIRS),
                "pairs_processed": pairs_processed,
                "setups_viable_pre_phase2": setups_viable_pre_phase2,
                "setups_blocked_phase2": setups_blocked_phase2,
                "worker_rejected": rejected_count,
                "errors": error_count,
                "signals_emitted": len(emitted),
                "legacy_candidates": passed_count,
                "duration_sec": round(duration, 2),
                "next_scan_sec": SCAN_INTERVAL_SECONDS
            }
            alert_operational_event(
                "cycle_complete",
                f"Scan cycle completed: {pairs_processed} pairs / {len(emitted)} signals emitted",
                metrics,
            )
            
    except Exception as e:
        logger.error(f"[FATAL SCAN ERROR] {e}")
        alert_system_error("scanner", "fatal_scan_error", str(e))
    finally:
        _scan_lock.release()

def main() -> None:
    _init_pool()
    _ensure_training_table()  # Auto-create training table if missing
    _ensure_signal_measurement_schema()
    
    # Initialize Side-Balance Coherence Controller (v2.0 Doctrine)
    with db_conn() as conn:
        _side_controller.initialize(conn)
        
    refresh_active_universe()

    
    # Handshake
    mode_suffix = (
        f"\n<b>Mode:</b> {config.SCAN_PROFILE} | <b>Policy:</b> {POLICY_VERSION}"
        + (
            f" | <b>Burst until:</b> {getattr(config, 'TEMP_DATA_BURST_END_UTC', 'n/a')}"
            if getattr(config, 'TEMP_DATA_BURST_ACTIVE', False)
            else ""
        )
    )
    handshake = (
        f"<b>🜂 Idim Ikang Sovereign Accelerator Online</b>\n"
        f"<i>Parallel Engine [v1.9.5] active with {SCANNER_WORKERS} workers.</i>"
        f"{mode_suffix}"
    )
    logger.info("[SCANNER_MODE] profile=%s policy=%s burst_active=%s burst_until=%s", config.SCAN_PROFILE, POLICY_VERSION, getattr(config, 'TEMP_DATA_BURST_ACTIVE', False), getattr(config, 'TEMP_DATA_BURST_END_UTC', 'n/a'))
    send_telegram(handshake)

    while not _STOP:
        try:
            if time.time() - _LAST_UNIVERSE_REFRESH > UNIVERSE_REFRESH_INTERVAL:
                refresh_active_universe()
            scan_once()
        except Exception as e:
            logger.error(f"Main loop escape: {e}")
        time.sleep(SCAN_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
