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
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras
import psycopg2.pool
import requests
from dotenv import load_dotenv
from telegram import Bot

# ─── Environment ───────────────────────────────────────────────────────────────
load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
BINANCE_FUTURES_URL = "https://fapi.binance.com"
SCAN_INTERVAL_SECONDS = int(os.environ.get("SCAN_INTERVAL_SECONDS", "60"))
LOOKBACK_15M = int(os.environ.get("LOOKBACK_15M", "500"))
LOOKBACK_4H = int(os.environ.get("LOOKBACK_4H", "300"))

import config
import exchange_discovery

# ─── Constants ─────────────────────────────────────────────────────────────────
LOGIC_VERSION = config.CURRENT_LOGIC_VERSION
CONFIG_VERSION = config.CURRENT_CONFIG_VERSION
UNIVERSE_REFRESH_INTERVAL = 900  # 15 minutes

MIN_SIGNAL_SCORE = 45
COOLDOWN_BARS = 32
BLOCK_STRONG_UPTREND = True
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

def _get_conn():
    return _db_pool.getconn()

def _put_conn(conn) -> None:
    _db_pool.putconn(conn)

def db_conn():
    """Direct connection — used only inside scan_once advisory lock block."""
    return psycopg2.connect(DATABASE_URL)

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
                (level, component, event, json.dumps(details)),
            )
            conn.commit()
    except Exception as err:
        print(f"[log_event error] {err}", flush=True)
    finally:
        _put_conn(conn)

def send_telegram(message: str) -> None:
    """Fire-and-forget: daemon thread so it never blocks the scan loop."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    def _send():
        try:
            Bot(token=TELEGRAM_BOT_TOKEN).send_message(
                chat_id=TELEGRAM_CHAT_ID, text=message
            )
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()

# ─── Market data ───────────────────────────────────────────────────────────────
def fetch_klines(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    url = f"{BINANCE_FUTURES_URL}/fapi/v1/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    cols = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "num_trades",
        "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore",
    ]
    df = pd.DataFrame(r.json(), columns=cols)
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
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

    # ── Institutional Daily VWAP (resets at UTC midnight) ─────────────────
    _date = out["open_time"].dt.date
    _typ = (out["high"] + out["low"] + out["close"]) / 3
    _pv = _typ * out["volume"]
    out["vwap"] = (
        _pv.groupby(_date).cumsum()
        / out["volume"].groupby(_date).cumsum().replace(0, np.nan)
    ).fillna(out["close"])

    # CVD Lite (Cumulative Volume Delta)
    out["taker_sell"] = out["volume"] - out["taker_buy_base_asset_volume"]
    out["cvd_lite"] = (out["taker_buy_base_asset_volume"] - out["taker_sell"]).cumsum()

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

def score_long_signal(latest: pd.Series, regime: str, alpha: dict) -> Tuple[float, Dict]:
    reasons_pass, reasons_fail, tags = [], [], []
    score = 0.0

    # 1. THE MICRO-CHOP BLOCKER
    if latest.get("adx14", 0) < 20:
        return 0.0, {"reasons_fail": ["15m ADX < 20 (Micro Chop)"]}
        
    # 2. THE EXHAUSTION BLOCKER (Rubber Band Effect)
    atr14 = latest["atr14"]
    dist_from_ema = latest["close"] - latest["ema20"]
    if dist_from_ema > (1.5 * atr14):
        return 0.0, {"reasons_fail": [f"Exhausted: Price {dist_from_ema/atr14:.1f} ATRs above EMA20"]}

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

def score_short_signal(latest: pd.Series, regime: str, alpha: dict) -> Tuple[float, Dict]:
    reasons_pass, reasons_fail, tags = [], [], []
    score = 0.0

    # 1. THE MICRO-CHOP BLOCKER
    if latest.get("adx14", 0) < 20:
        return 0.0, {"reasons_fail": ["15m ADX < 20 (Micro Chop)"]}
        
    # 2. THE EXHAUSTION BLOCKER
    atr14 = latest["atr14"]
    dist_from_ema = latest["ema20"] - latest["close"]
    if dist_from_ema > (1.5 * atr14):
        return 0.0, {"reasons_fail": [f"Exhausted: Price {dist_from_ema/atr14:.1f} ATRs below EMA20"]}

    # EMA alignment
    if latest["ema20"] < latest["ema50"]:
        score += 20; reasons_pass.append("EMA20 < EMA50 (trend aligned)")
    else:
        reasons_fail.append("EMA20 >= EMA50")

    # Price vs EMA20
    if latest["close"] < latest["ema20"]:
        score += 10; reasons_pass.append("Price below EMA20")
    else:
        reasons_fail.append("Price >= EMA20")

    # RSI
    rsi_v = latest["rsi14"]
    if 35 <= rsi_v <= 70:
        score += 15; reasons_pass.append(f"RSI {rsi_v:.1f} in bear zone")
    else:
        reasons_fail.append(f"RSI {rsi_v:.1f} outside bear zone")

    # MACD
    if latest["macd_hist"] < 0:
        score += 15; reasons_pass.append("MACD histogram negative")
    else:
        reasons_fail.append("MACD histogram >= 0")

    # Regime bonus
    regime_bonus = {
        "RANGING": 0, "DOWNTREND": 10, "STRONG_DOWNTREND": 15,
        "UPTREND": 5, "STRONG_UPTREND": 0,
    }.get(regime, 0)
    score += regime_bonus
    reasons_pass.append(f"Regime: {regime}")

    # Volume & CVD Alpha
    vol_ratio = _vol_ratio(latest)
    if vol_ratio >= 1.1:
        score += 15; reasons_pass.append(f"Volume ratio {vol_ratio:.2f} (confirmed)")
    else:
        reasons_fail.append(f"Volume ratio {vol_ratio:.2f} below 1.1")

    if latest.get("cvd_lite", 0) < 0:
        score += 15; reasons_pass.append("Aggressive Market Selling (Negative CVD)"); tags.append("CVD")

    # DERIVATIVES ALPHA MERGE
    funding = alpha.get("funding_rate", 0.0)
    ls_ratio = alpha.get("ls_ratio", 1.0)
    if funding > 0.01 and ls_ratio > 2.5:
        score += 30; reasons_pass.append(f"🩸 LONG SQUEEZE ALPHA: Funding {funding:.4f}, LS {ls_ratio:.2f}"); tags.append("Squeeze")
    elif ls_ratio < 0.8:
        score -= 20; reasons_fail.append(f"Crowded Shorts (LS {ls_ratio:.2f})")

    return score, {"reasons_pass": reasons_pass, "reasons_fail": reasons_fail, "volume_ratio": vol_ratio, "tags": tags}

# ─── Signal construction ───────────────────────────────────────────────────────
def build_signal(
    pair: str, side: str, latest: pd.Series,
    regime: str, score: float, trace: Dict,
    sl_mult: float = ATR_SL_MULTIPLIER,
) -> dict:
    atr_v = float(latest["atr14"])
    entry = float(latest["close"])
    score_bucket = (int(score) // 5) * 5
    stop = entry - sl_mult * atr_v if side == "LONG" else entry + sl_mult * atr_v
    
    # Scale-Out Targets (v1.5 Strategy)
    tp1 = entry + (1.2 * atr_v) if side == "LONG" else entry - (1.2 * atr_v)
    tp2 = entry + (3.0 * atr_v) if side == "LONG" else entry - (3.0 * atr_v)
    
    trace.update({
        "score_bucket": score_bucket, 
        "cell_allowed": True, 
        "allowed_cell_key": [regime, score_bucket],
        "tp1": round(tp1, 8),
        "tp2": round(tp2, 8),
        "tags": trace.get("tags", [])
    })
    
    return {
        "signal_id": str(uuid.uuid4()),
        "pair": pair,
        "ts": latest["close_time"].to_pydatetime(),
        "side": side,
        "entry": entry,
        "stop_loss": stop,
        "take_profit": round(tp2, 8), # Default to runner for legacy
        "score": score,
        "regime": regime,
        "reason_trace": trace,
        "logic_version": LOGIC_VERSION,
        "config_version": CONFIG_VERSION,
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
    allowed = {
        ("STRONG_DOWNTREND", 55),
        ("STRONG_UPTREND",   60),
        ("DOWNTREND",        60),
        ("UPTREND",          45),
        ("RANGING",          65),
    }
    return (regime, score_bucket) in allowed

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

    return (
        a["vol_ratio"]    * phi_vol
        + a["inv_stop_pct"] * phi_stop
        + a["inv_rank"]     * phi_rank
        + a["vwap_prox"]    * phi_vwap
        + a["momentum"]     * phi_mom
        + a["oi_ratio"]     * phi_oi
    )

# Alias kept for any external references
compute_rank_score = compute_Q

# ─── Top-N selector ────────────────────────────────────────────────────────────
def select_top_ranked_wolfram_signals(candidates: list) -> list:
    # A. G_Omega filter + annotate with stable UUID
    filtered = []
    for c in candidates:
        if passes_wolfram_five_cell_filter(c["regime"], c["score"], c.get("side", "")):
            c = dict(c)
            c["_cid"]      = str(uuid.uuid4())
            c["cell_key"]  = wolfram_cell_key(c["regime"], c["score"])
            c["rank_score"] = compute_Q(c)
            entry = float(c.get("entry", 0))
            c["stop_pct"]  = abs(entry - float(c.get("stop_loss", 0))) / entry * 100.0 if entry > 0 else 999.0
            filtered.append(c)

    # B. Sort by Q descending
    filtered.sort(key=lambda x: x["rank_score"], reverse=True)

    # C. Max 1 per cell
    by_cell, seen = [], set()
    for c in filtered:
        if c["cell_key"] not in seen:
            seen.add(c["cell_key"])
            by_cell.append(c)

    # D. Max 2 per side
    by_side, counts = [], {"LONG": 0, "SHORT": 0}
    for c in by_cell:
        if counts.get(c["side"], 0) < MAX_SIGNALS_PER_SIDE:
            counts[c["side"]] = counts.get(c["side"], 0) + 1
            by_side.append(c)

    # E. Top 3 total
    final = by_side[:MAX_SIGNALS_PER_SCAN]

    # Log rejections (UUID-stable)
    final_cids = {c["_cid"] for c in final}
    for c in filtered:
        if c["_cid"] not in final_cids:
            log_event("INFO", "scanner", "wolfram_top3_rank_reject", {
                "pair": c["pair"], "side": c["side"], "regime": c["regime"],
                "score": c["score"], "cell_key": list(c["cell_key"]),
                "rank_score": round(c["rank_score"], 4),
            })

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
                "symbol_count": len(PAIRS), "symbols": PAIRS,
            })
            logging.info(f"Universe refreshed: {len(PAIRS)} symbols.")
    except Exception as e:
        log_event("ERROR", "scanner", "universe_refresh_failed", {"error": str(e)})

# ─── Signal persistence ────────────────────────────────────────────────────────
def insert_signal(conn, sig: dict) -> None:
    global _LAST_SIGNAL
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO signals (
                signal_id, pair, ts, side, entry, stop_loss, take_profit,
                score, regime, reason_trace, logic_version, config_version
            ) VALUES (
                %(signal_id)s, %(pair)s, %(ts)s, %(side)s, %(entry)s,
                %(stop_loss)s, %(take_profit)s, %(score)s, %(regime)s,
                %(reason_trace)s::jsonb, %(logic_version)s, %(config_version)s
            ) ON CONFLICT (signal_id) DO NOTHING
            """,
            {**sig, "reason_trace": json.dumps(sig["reason_trace"])},
        )
        conn.commit()
    _LAST_SIGNAL = {**sig, "ts": sig["ts"].isoformat()}
    send_telegram(
        f"Idim Ikang v1.5-quant-alpha\n{sig['pair']} {sig['side']}\n"
        f"Score: {sig['score']}\nRegime: {sig['regime']}\n"
        f"Entry: {sig['entry']:.4f}\nSL: {sig['stop_loss']:.4f}\nTP: {sig['take_profit']:.4f}"
    )

# ─── Core scan loop ────────────────────────────────────────────────────────────
def scan_once() -> None:
    global _LAST_SCAN_TS, _LAST_SCAN_GAP_SECONDS
    started = time.time()
    skip_lock = os.environ.get("SKIP_LOCK", "false").lower() == "true"

    if _LAST_SCAN_TS is not None:
        _LAST_SCAN_GAP_SECONDS = started - _LAST_SCAN_TS
        if _LAST_SCAN_GAP_SECONDS > SCAN_INTERVAL_SECONDS * 1.5:
            log_event("WARN", "scanner", "scan_gap_detected",
                      {"gap_seconds": round(_LAST_SCAN_GAP_SECONDS, 1)})
    _LAST_SCAN_TS = started

    # ── G_beta: BTC King's Gate ──────────────────────────────────────────────
    btc_regime = get_btc_macro_regime()
    btc_blocks_longs  = btc_regime in ("STRONG_DOWNTREND", "DOWNTREND")
    btc_blocks_shorts = btc_regime in ("STRONG_UPTREND",   "UPTREND")

    candidates = []

    with db_conn() as conn:
        with conn.cursor() as lock_cur:
            if not skip_lock:
                lock_cur.execute("SELECT pg_advisory_lock(1337);")
            try:
                log_event("INFO", "scanner", "scan_start",
                          {"universe_size": len(PAIRS), "btc_regime": btc_regime})

                for idx, pair in enumerate(PAIRS):
                    try:
                        df15   = add_indicators(fetch_klines(pair, "15m", LOOKBACK_15M))
                        df4    = fetch_klines(pair, "4h", LOOKBACK_4H)
                        regime = classify_regime(df4)

                        # ── G_str: 1H Multi-Timeframe Alignment ─────────────
                        df1h = fetch_klines(pair, "1h", 100)
                        df1h["ema50"] = ema(df1h["close"], 50)
                        _l1h = df1h.iloc[-1]
                        is_1h_bullish = _l1h["close"] > _l1h["ema50"]
                        is_1h_bearish = _l1h["close"] < _l1h["ema50"]

                        latest = df15.iloc[-1]
                        req_cols = ("ema20", "ema50", "rsi14", "macd_hist", "atr14", "volume_sma20")
                        if any(np.isnan(latest.get(k, np.nan)) for k in req_cols):
                            log_event("INFO", "scanner", "warmup_skip", {"pair": pair})
                            continue

                        # ── Gate 7: Warmup Floor ─────────────────────────────
                        if len(df15) < SCANNER_WARMUP_BARS:
                            msg = f"Insufficient bars ({len(df15)} < {SCANNER_WARMUP_BARS})"
                            log_event("INFO", "scanner", "gate7_warmup_reject", 
                                      {"pair": pair, "reason": "WARMUP_FLOOR", "detail": msg})
                            logging.info(f"[REJECT] {pair} - WARMUP_FLOOR: {msg}")
                            continue

                        # ── Gate 8: Data Freshness ───────────────────────────
                        last_close_ts = latest["close_time"].timestamp()
                        now_ts = time.time()
                        if (now_ts - last_close_ts) > DATA_FRESHNESS_MAX_SECONDS:
                            msg = f"Data stale ({round(now_ts - last_close_ts)}s old)"
                            log_event("INFO", "scanner", "gate8_freshness_reject",
                                      {"pair": pair, "reason": "DATA_STALE", "detail": msg})
                            logging.info(f"[REJECT] {pair} - DATA_STALE: {msg}")
                            continue

                        if cooldown_active(conn, pair,
                                           latest["close_time"].to_pydatetime()):
                            continue

                        # v1.5 Alpha Merge
                        alpha_data = get_derivatives_alpha(conn, pair)

                        long_score,  long_trace  = score_long_signal(latest, regime, alpha_data)
                        short_score, short_trace = score_short_signal(latest, regime, alpha_data)

                        # ── Gate 1: Regime-direction consistency ─────────────
                        if BLOCK_AGAINST_REGIME:
                            if regime in ("STRONG_UPTREND", "UPTREND") and short_score > 0:
                                log_event("INFO", "scanner", "gate1_regime_reject",
                                          {"pair": pair, "side": "SHORT", "reason": "REGIME_DIRECTION_CONFLICT", "regime": regime})
                                logging.info(f"[REJECT] {pair} - REGIME_DIRECTION_CONFLICT: SHORT in {regime}")
                                short_score = 0
                            if regime in ("STRONG_DOWNTREND", "DOWNTREND") and long_score > 0:
                                log_event("INFO", "scanner", "gate1_regime_reject",
                                          {"pair": pair, "side": "LONG", "reason": "REGIME_DIRECTION_CONFLICT", "regime": regime})
                                logging.info(f"[REJECT] {pair} - REGIME_DIRECTION_CONFLICT: LONG in {regime}")
                                long_score = 0

                        # ── Gate 5: BTC King's Gate ──────────────────────────
                        if btc_blocks_longs and long_score > 0:
                            log_event("INFO", "scanner", "gate5_btc_reject",
                                      {"pair": pair, "side": "LONG", "btc": btc_regime, "reason": "BTC_MACD_CONFLICT"})
                            logging.info(f"[REJECT] {pair} - BTC_MACD_CONFLICT: LONG vs BTC {btc_regime}")
                            long_score = 0
                        if btc_blocks_shorts and short_score > 0:
                            log_event("INFO", "scanner", "gate5_btc_reject",
                                      {"pair": pair, "side": "SHORT", "btc": btc_regime, "reason": "BTC_MACD_CONFLICT"})
                            logging.info(f"[REJECT] {pair} - BTC_MACD_CONFLICT: SHORT vs BTC {btc_regime}")
                            short_score = 0

                        # ── Gate 6: 1H MTFA ──────────────────────────────────
                        if not is_1h_bullish and long_score > 0:
                            log_event("INFO", "scanner", "gate6_mtfa_reject",
                                      {"pair": pair, "side": "LONG", "reason": "MTFA_1H_CONFLICT"})
                            logging.info(f"[REJECT] {pair} - MTFA_1H_CONFLICT: LONG below 1H EMA50")
                            long_score = 0
                        if not is_1h_bearish and short_score > 0:
                            log_event("INFO", "scanner", "gate6_mtfa_reject",
                                      {"pair": pair, "side": "SHORT", "reason": "MTFA_1H_CONFLICT"})
                            logging.info(f"[REJECT] {pair} - MTFA_1H_CONFLICT: SHORT above 1H EMA50")
                            short_score = 0

                        # ── Gate 4: STRONG_UPTREND internal consistency ───────
                        if regime == "STRONG_UPTREND" and long_score >= MIN_SIGNAL_SCORE:
                            price = float(latest["close"])
                            if REQUIRE_PRICE_ABOVE_EMA_IN_STRONG_UPTREND and price <= float(latest["ema20"]):
                                long_score = 0
                                log_event("INFO", "scanner", "gate4_reject",
                                          {"pair": pair, "reason": "price<=ema20 in STRONG_UPTREND"})
                            if REQUIRE_RSI_ABOVE_50_IN_STRONG_UPTREND and float(latest["rsi14"]) <= 50:
                                long_score = 0
                                log_event("INFO", "scanner", "gate4_reject",
                                          {"pair": pair, "reason": "RSI<=50 in STRONG_UPTREND"})

                        # ── Collection: G_sq + G_vwap + G_vol + ATR cap ───────
                        price   = float(latest["close"])
                        atr_val = float(latest["atr14"])

                        for side, score, trace in (
                            ("LONG",  long_score,  long_trace),
                            ("SHORT", short_score, short_trace),
                        ):
                            if score < MIN_SIGNAL_SCORE:
                                continue
                            if side == "SHORT" and score <= long_score and long_score >= MIN_SIGNAL_SCORE:
                                continue
                            if side == "LONG"  and score <  short_score and short_score >= MIN_SIGNAL_SCORE:
                                continue

                            direction = 1 if side == "LONG" else -1

                            # G_sq: Squeeze hard gate
                            if REQUIRE_SQUEEZE_GATE:
                                if not latest.get("recent_squeeze_fire", False):
                                    log_event("INFO", "scanner", "gsq_reject",
                                              {"pair": pair, "side": side, "reason": "SQUEEZE_REQUIRED"})
                                    logging.info(f"[REJECT] {pair} - SQUEEZE_REQUIRED for {side}")
                                    continue

                            # G_vwap: Dynamic epsilon gate
                            # ε(A,t) = ε₀ + λ · ATR/P
                            vwap_delta = 0.0
                            _vwap = latest.get("vwap")
                            if _vwap and float(_vwap) > 0 and not np.isnan(float(_vwap)):
                                vwap_delta = (price - float(_vwap)) / float(_vwap)
                                epsilon = VWAP_EPSILON_0 + VWAP_LAMBDA * (atr_val / price)
                                if direction * vwap_delta > epsilon:
                                    log_event("INFO", "scanner", "gvwap_reject", {
                                        "pair": pair, "side": side,
                                        "delta_pct": round(vwap_delta * 100, 2),
                                        "epsilon_pct": round(epsilon * 100, 2),
                                        "reason": "VWAP_OVEREXTENDED"
                                    })
                                    logging.info(f"[REJECT] {pair} - VWAP_OVEREXTENDED ({round(vwap_delta*100,2)}% > {round(epsilon*100,2)}%)")
                                    continue

                            # G_vol: Volume hard gate
                            vol_ratio = trace.get("volume_ratio", 0.0)
                            if vol_ratio < VOLUME_RATIO_MIN:
                                log_event("INFO", "scanner", "gate2_volume_reject", {
                                    "pair": pair, "side": side,
                                    "volume_ratio": round(vol_ratio, 3),
                                    "reason": "VOL_INSUFFICIENT"
                                })
                                logging.info(f"[REJECT] {pair} - VOL_INSUFFICIENT ({round(vol_ratio,2)} < {VOLUME_RATIO_MIN})")
                                continue

                            # Gate 3: ATR cap for wide stops
                            atr_pct = atr_val / price if price > 0 else 999.0
                            sl_mult = ATR_SL_MULTIPLIER
                            if atr_pct > MAX_ATR_PCT_FOR_FULL_SL:
                                sl_mult = min(sl_mult, CAP_SL_MULTIPLIER_WHEN_WIDE)
                                log_event("INFO", "scanner", "gate3_atr_cap", {
                                    "pair": pair, "atr_pct": round(atr_pct * 100, 2),
                                    "sl_mult": sl_mult,
                                })

                            stop_price = (
                                price - sl_mult * atr_val
                                if side == "LONG"
                                else price + sl_mult * atr_val
                            )

                            candidates.append({
                                "pair": pair, "side": side, "latest": latest,
                                "regime": regime, "score": score,
                                "reason_trace": trace, "universe_rank": idx,
                                "volume_ratio": vol_ratio, "entry": price,
                                "stop_loss": stop_price, "vwap_delta": vwap_delta,
                            })
                            break  # one side per pair

                    except Exception as pair_err:
                        log_event("ERROR", "scanner", "pair_scan_error",
                                  {"pair": pair, "error": str(pair_err)})

                # Ranking & selection
                selected = select_top_ranked_wolfram_signals(candidates)
                for c in selected:
                    sig = build_signal(
                        c["pair"], c["side"], c["latest"],
                        c["regime"], c["score"], c["reason_trace"],
                        sl_mult=ATR_SL_MULTIPLIER,
                    )
                    insert_signal(conn, sig)
                    log_event("INFO", "scanner", "signal_logged", {
                        "pair": c["pair"], "side": c["side"],
                        "regime": c["regime"], "score": c["score"],
                        "cell_key": list(c["cell_key"]),
                        "rank_score": round(c["rank_score"], 4),
                    })

            finally:
                if not skip_lock:
                    lock_cur.execute("SELECT pg_advisory_unlock(1337);")

    duration = time.time() - started
    log_event("INFO", "scanner", "scan_complete", {
        "duration_seconds": round(duration, 3),
        "candidates_found": len(candidates),
    })

# ─── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    _init_pool()  # Connection pool must be ready before first log_event
    refresh_active_universe()
    log_event("INFO", "scanner", "scanner_start", {
        "pairs": PAIRS,
        "logic_version": LOGIC_VERSION,
        "config_version": CONFIG_VERSION,
    })
    while not _STOP:
        try:
            if time.time() - _LAST_UNIVERSE_REFRESH > UNIVERSE_REFRESH_INTERVAL:
                refresh_active_universe()
            scan_once()
        except Exception as e:
            log_event("ERROR", "scanner", "scan_error", {"error": str(e)})
        time.sleep(SCAN_INTERVAL_SECONDS)
    log_event("INFO", "scanner", "scanner_stop",
              {"uptime_seconds": round(time.time() - _START_TS, 1)})

if __name__ == "__main__":
    main()
