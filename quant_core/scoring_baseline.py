import pandas as pd
from datetime import datetime, timezone
from config import (LOGIC_VERSION, CONFIG_VERSION, MIN_SIGNAL_SCORE,
                    COOLDOWN_BARS, BLOCK_STRONG_UPTREND, ATR_SL_MULTIPLIER, ATR_TP_MULTIPLIER, REGIME_WEIGHTS)

def score_long_signal(df_15m: pd.DataFrame, regime: dict):
    score = 0.0
    reasons = {}
    
    latest = df_15m.iloc[-1]
    price = latest['close']
    volume = latest['volume']
    vol_sma = latest['volume_sma_20']
    
    # Volume Confirmation (Soft contributor)
    vol_ratio = 0.0
    if not pd.isna(vol_sma) and vol_sma > 0:
        vol_ratio = volume / vol_sma
        if vol_ratio >= 1.1:
            score += 15
            reasons["volume_confirmation"] = round(vol_ratio, 2)
        else:
            reasons["volume_confirmation"] = round(vol_ratio, 2)

    # EMA Alignment (+20)
    ema_aligned = False
    if latest['ema_20'] > latest['ema_50'] > latest['ema_200']:
        score += 20
        ema_aligned = True
        reasons["ema_alignment"] = True

    # Price relative to EMA20 (+10)
    if price > latest['ema_20']:
        score += 10
        reasons["price_above_ema20"] = True

    # RSI zone alignment (+15)
    rsi = latest['rsi']
    if rsi < 40:
        score += 15
        reasons["rsi_alignment"] = round(rsi, 2)

    # MACD momentum alignment (+10)
    macd_hist = latest['macd_hist']
    if not pd.isna(macd_hist) and macd_hist > 0:
        score += 10
        reasons["macd_alignment"] = True

    # Regime blocking (pre-scoring veto)
    regime_name = regime['regime']
    if BLOCK_STRONG_UPTREND and regime_name == "STRONG_UPTREND":
        return 0.0, {"regime_block": "STRONG_UPTREND blocked"}
    
    # Regime weighting (±20)
    weight = REGIME_WEIGHTS.get(regime_name, 0)
    regime_score = weight * 10
    score += regime_score
    reasons["regime_weight"] = regime_score

    # EMA misalignment veto (hard rule)
    if not ema_aligned:
        return 0.0, {"ema_veto": "EMA alignment missing"}

    reasons["final_score"] = score
    return score, reasons

def score_short_signal(df_15m: pd.DataFrame, regime: dict):
    score = 0.0
    reasons = {}
    
    latest = df_15m.iloc[-1]
    price = latest['close']
    volume = latest['volume']
    vol_sma = latest['volume_sma_20']
    
    # Volume Confirmation (Soft contributor)
    vol_ratio = 0.0
    if not pd.isna(vol_sma) and vol_sma > 0:
        vol_ratio = volume / vol_sma
        if vol_ratio >= 1.1:
            score += 15
            reasons["volume_confirmation"] = round(vol_ratio, 2)
        else:
            reasons["volume_confirmation"] = round(vol_ratio, 2)

    # EMA Alignment (+20)
    ema_aligned = False
    if latest['ema_20'] < latest['ema_50'] < latest['ema_200']:
        score += 20
        ema_aligned = True
        reasons["ema_alignment"] = True

    # Price relative to EMA20 (+10)
    if price < latest['ema_20']:
        score += 10
        reasons["price_below_ema20"] = True

    # RSI zone alignment (+15)
    rsi = latest['rsi']
    if rsi > 60:
        score += 15
        reasons["rsi_alignment"] = round(rsi, 2)

    # MACD momentum alignment (+10)
    macd_hist = latest['macd_hist']
    if not pd.isna(macd_hist) and macd_hist < 0:
        score += 10
        reasons["macd_alignment"] = True

    # Regime blocking (pre-scoring veto)
    regime_name = regime['regime']
    if BLOCK_STRONG_UPTREND and regime_name == "STRONG_UPTREND":
        return 0.0, {"regime_block": "STRONG_UPTREND blocked"}
    
    # Regime weighting (±20)
    # For short, we invert the weight. STRONG_DOWNTREND is -2, so -(-2)*10 = +20.
    weight = REGIME_WEIGHTS.get(regime_name, 0)
    regime_score = -weight * 10
    score += regime_score
    reasons["regime_weight"] = regime_score

    # EMA misalignment veto (hard rule)
    if not ema_aligned:
        return 0.0, {"ema_veto": "EMA alignment missing"}

    reasons["final_score"] = score
    return score, reasons

def generate_signals(pair: str, df_15m: pd.DataFrame, regime: dict, last_signal_bars: dict, current_bar_index: int, daily_signal_counts: dict):
    if len(df_15m) < 200 or regime['regime'] == "unknown":
        return []

    latest = df_15m.iloc[-1]
    price = latest['close']
    atr = latest['atr']
    
    if pd.isna(atr) or price <= 0:
        return []

    ts = datetime.fromtimestamp(latest['close_time'] / 1000.0, tz=timezone.utc)
    
    signals = []
    
    # LONG
    long_score, long_reasons = score_long_signal(df_15m, regime)
    if long_score >= MIN_SIGNAL_SCORE:
        cooldown_key = f"{pair}:LONG"
        last_bar = last_signal_bars.get(cooldown_key, -9999)
        if (current_bar_index - last_bar) >= COOLDOWN_BARS:
            sl = price - (atr * ATR_SL_MULTIPLIER)
            tp = price + (atr * ATR_TP_MULTIPLIER)
            long_reasons["sl"] = round(sl, 6)
            long_reasons["tp"] = round(tp, 6)
            
            signals.append({
                "pair": pair,
                "timestamp": ts,
                "direction": "LONG",
                "regime": regime['regime'],
                "score": long_score,
                "entry_range": {"min": float(price * 0.999), "max": float(price * 1.001)},
                "stop_loss": float(sl),
                "take_profit": [{"level": 1, "price": float(tp)}],
                "reason_trace": long_reasons,
                "logic_version": LOGIC_VERSION,
                "config_version": CONFIG_VERSION
            })
            last_signal_bars[cooldown_key] = current_bar_index
            return signals

    # SHORT
    short_score, short_reasons = score_short_signal(df_15m, regime)
    if short_score >= MIN_SIGNAL_SCORE:
        cooldown_key = f"{pair}:SHORT"
        last_bar = last_signal_bars.get(cooldown_key, -9999)
        if (current_bar_index - last_bar) >= COOLDOWN_BARS:
            sl = price + (atr * ATR_SL_MULTIPLIER)
            tp = price - (atr * ATR_TP_MULTIPLIER)
            short_reasons["sl"] = round(sl, 6)
            short_reasons["tp"] = round(tp, 6)
            
            signals.append({
                "pair": pair,
                "timestamp": ts,
                "direction": "SHORT",
                "regime": regime['regime'],
                "score": short_score,
                "entry_range": {"min": float(price * 0.999), "max": float(price * 1.001)},
                "stop_loss": float(sl),
                "take_profit": [{"level": 1, "price": float(tp)}],
                "reason_trace": short_reasons,
                "logic_version": LOGIC_VERSION,
                "config_version": CONFIG_VERSION
            })
            last_signal_bars[cooldown_key] = current_bar_index

    return signals
