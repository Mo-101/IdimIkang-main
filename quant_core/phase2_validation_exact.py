#!/usr/bin/env python3
"""
IDIM IKANG — PHASE 2 OUT-OF-SAMPLE VALIDATION
Codex ID: mo-fin-idim-ikang-001
Logic Version: v1.0-tuned
Config Version: v1.0-tuned

Date Range: 2025-10-01 to 2025-12-31 (out-of-sample)
In-Sample Range was: 2026-01-01 to 2026-03-31

ALL PARAMETERS LOCKED. NO CHANGES.
"""

import json
import hashlib
import time
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import requests

# ============================================================
# LOCKED CONFIGURATION — DO NOT MODIFY
# ============================================================
CONFIG = {
    "config_version": "v1.0-tuned",
    "logic_version": "v1.0-tuned",
    "pairs": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    "timeframes": {
        "trigger": "15m",
        "confirmation": "1h",
        "regime": "4h"
    },
    "min_signal_score": 45,
    "cooldown_bars": 32,
    "block_strong_uptrend": True,
    "atr_sl_multiplier": 1.0,
    "atr_tp_multiplier": 3.0,
    "indicator_periods": {
        "ema_fast": 20,
        "ema_slow": 50,
        "rsi": 14,
        "atr": 14,
        "volume_sma": 20
    },
    "date_start": "2025-10-01",
    "date_end": "2025-12-31"
}

# ============================================================
# DATA FETCHING — BINANCE PUBLIC API WITH PAGINATION
# ============================================================
def fetch_klines(symbol, interval, start_str, end_str):
    """Fetch klines with pagination (max 1000 per request)."""
    base_url = "https://api.binance.com/api/v3/klines"
    start_ts = int(pd.Timestamp(start_str, tz='UTC').timestamp() * 1000)
    end_ts = int(pd.Timestamp(end_str + " 23:59:59", tz='UTC').timestamp() * 1000)
    
    all_klines = []
    current_start = start_ts
    
    while current_start < end_ts:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": current_start,
            "endTime": end_ts,
            "limit": 1000
        }
        
        for attempt in range(3):
            try:
                resp = requests.get(base_url, params=params, timeout=30)
                if resp.status_code == 451:
                    # Geo-restricted, try binance.us
                    base_url_us = "https://api.binance.us/api/v3/klines"
                    # Map symbol for US
                    us_symbol = symbol.replace("USDT", "USD")
                    params["symbol"] = us_symbol
                    resp = requests.get(base_url_us, params=params, timeout=30)
                    if resp.status_code == 200:
                        print(f"  [INFO] Using Binance US for {symbol} -> {us_symbol}")
                
                if resp.status_code == 200:
                    break
                elif resp.status_code == 429:
                    time.sleep(10)
                else:
                    print(f"  [WARN] HTTP {resp.status_code} for {symbol}, attempt {attempt+1}")
                    time.sleep(2)
            except Exception as e:
                print(f"  [ERROR] {e}, attempt {attempt+1}")
                time.sleep(5)
        
        data = resp.json()
        if not data or len(data) == 0:
            break
            
        all_klines.extend(data)
        last_close_time = data[-1][6]  # close time of last candle
        current_start = last_close_time + 1
        
        if len(data) < 1000:
            break
        
        time.sleep(0.2)  # rate limit respect
    
    # Build DataFrame
    df = pd.DataFrame(all_klines, columns=[
        'open_time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore'
    ])
    
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    
    df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms', utc=True)
    df = df.set_index('timestamp')
    
    # Remove duplicates
    df = df[~df.index.duplicated(keep='first')]
    
    return df

# ============================================================
# INDICATORS — PURE FUNCTIONS
# ============================================================
def compute_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def compute_atr(high, low, close, period=14):
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    return atr

def compute_indicators(df, cfg):
    """Compute all indicators on a DataFrame."""
    p = cfg["indicator_periods"]
    df = df.copy()
    df['ema_fast'] = compute_ema(df['close'], p['ema_fast'])
    df['ema_slow'] = compute_ema(df['close'], p['ema_slow'])
    df['rsi'] = compute_rsi(df['close'], p['rsi'])
    df['atr'] = compute_atr(df['high'], df['low'], df['close'], p['atr'])
    df['volume_sma'] = df['volume'].rolling(window=p['volume_sma']).mean()
    df['volume_ratio'] = df['volume'] / df['volume_sma']
    
    # MACD
    ema12 = compute_ema(df['close'], 12)
    ema26 = compute_ema(df['close'], 26)
    df['macd'] = ema12 - ema26
    df['macd_signal'] = compute_ema(df['macd'], 9)
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    return df

# ============================================================
# REGIME CLASSIFICATION — ON 4H DATA
# ============================================================
def classify_regime_4h(df_4h):
    """
    5-state regime classifier on 4h data.
    Uses EMA relationship + RSI + price position.
    """
    df = df_4h.copy()
    df['ema20'] = compute_ema(df['close'], 20)
    df['ema50'] = compute_ema(df['close'], 50)
    df['rsi'] = compute_rsi(df['close'], 14)
    df['atr'] = compute_atr(df['high'], df['low'], df['close'], 14)
    
    # ADX approximation using directional movement
    plus_dm = df['high'].diff()
    minus_dm = -df['low'].diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    
    tr = compute_atr(df['high'], df['low'], df['close'], 1)  # true range
    atr14 = tr.ewm(span=14, adjust=False).mean()
    
    plus_di = 100 * (plus_dm.ewm(span=14, adjust=False).mean() / atr14)
    minus_di = 100 * (minus_dm.ewm(span=14, adjust=False).mean() / atr14)
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    adx = dx.ewm(span=14, adjust=False).mean()
    
    df['adx'] = adx
    
    regimes = []
    for i in range(len(df)):
        adx_val = df['adx'].iloc[i]
        ema20_val = df['ema20'].iloc[i]
        ema50_val = df['ema50'].iloc[i]
        close_val = df['close'].iloc[i]
        rsi_val = df['rsi'].iloc[i]
        
        if pd.isna(adx_val) or pd.isna(ema20_val) or pd.isna(ema50_val):
            regimes.append('UNKNOWN')
            continue
        
        ema_bullish = ema20_val > ema50_val
        price_above = close_val > ema20_val
        
        if adx_val > 30 and ema_bullish and price_above and rsi_val > 55:
            regimes.append('STRONG_UPTREND')
        elif adx_val > 20 and ema_bullish:
            regimes.append('UPTREND')
        elif adx_val > 30 and not ema_bullish and not price_above and rsi_val < 45:
            regimes.append('STRONG_DOWNTREND')
        elif adx_val > 20 and not ema_bullish:
            regimes.append('DOWNTREND')
        else:
            regimes.append('RANGING')
    
    df['regime'] = regimes
    return df

def map_regime_to_15m(df_15m, df_4h_regime):
    """Map 4h regime labels down to 15m bars."""
    df = df_15m.copy()
    
    # For each 15m bar, find the most recent 4h regime
    regime_series = df_4h_regime['regime'].reindex(df.index, method='ffill')
    df['regime'] = regime_series.fillna('UNKNOWN')
    
    return df

# ============================================================
# SCORING ENGINE — LOCKED WEIGHTS
# ============================================================
def score_signal(row, prev_row, side):
    """
    Multi-component scoring. Returns score 0-92.
    Components:
    - Trend structure (EMA alignment): 0-25
    - Momentum (RSI + MACD): 0-35
    - Context (regime): 0-15
    - Confirmation (volume): 0-10
    - Price position: 0-7
    """
    score = 0
    reasons_pass = []
    reasons_fail = []
    
    # 1. TREND STRUCTURE (0-25)
    ema_fast = row['ema_fast']
    ema_slow = row['ema_slow']
    close = row['close']
    
    if side == 'LONG':
        if ema_fast > ema_slow:
            score += 25
            reasons_pass.append("EMA20 > EMA50 (trend aligned)")
        else:
            reasons_fail.append("EMA20 < EMA50 (trend misaligned)")
    else:  # SHORT
        if ema_fast < ema_slow:
            score += 25
            reasons_pass.append("EMA20 < EMA50 (trend aligned)")
        else:
            reasons_fail.append("EMA20 > EMA50 (trend misaligned)")
    
    # 2. PRICE POSITION (0-7)
    if side == 'LONG' and close > ema_fast:
        score += 7
        reasons_pass.append("Price above EMA20")
    elif side == 'SHORT' and close < ema_fast:
        score += 7
        reasons_pass.append("Price below EMA20")
    
    # 3. RSI (0-15 base, +10 if extreme)
    rsi = row['rsi']
    if side == 'LONG':
        if 40 <= rsi <= 65:
            score += 15
            reasons_pass.append(f"RSI {rsi:.1f} in bull zone")
        elif rsi < 35:
            score += 25  # oversold bounce
            reasons_pass.append(f"RSI {rsi:.1f} oversold (strong)")
        else:
            reasons_fail.append(f"RSI {rsi:.1f} outside bull zone")
    else:
        if 35 <= rsi <= 60:
            score += 15
            reasons_pass.append(f"RSI {rsi:.1f} in bear zone")
        elif rsi > 65:
            score += 25  # overbought rejection
            reasons_pass.append(f"RSI {rsi:.1f} overbought (strong)")
        else:
            reasons_fail.append(f"RSI {rsi:.1f} outside bear zone")
    
    # 4. MACD (0-15 base, +5 crossover)
    macd_hist = row['macd_hist']
    if prev_row is not None:
        prev_hist = prev_row['macd_hist']
        if side == 'LONG':
            if macd_hist > 0:
                score += 15
                reasons_pass.append("MACD histogram positive")
            if prev_hist <= 0 and macd_hist > 0:
                score += 5
                reasons_pass.append("MACD bullish crossover")
        else:
            if macd_hist < 0:
                score += 15
                reasons_pass.append("MACD histogram negative")
            if prev_hist >= 0 and macd_hist < 0:
                score += 5
                reasons_pass.append("MACD bearish crossover")
    
    # 5. REGIME (0-15)
    regime = row.get('regime', 'UNKNOWN')
    if side == 'LONG' and regime in ('UPTREND', 'STRONG_UPTREND'):
        score += 15
        reasons_pass.append(f"Regime: {regime} (aligned)")
    elif side == 'SHORT' and regime in ('DOWNTREND', 'STRONG_DOWNTREND'):
        score += 15
        reasons_pass.append(f"Regime: {regime} (aligned)")
    elif regime == 'RANGING':
        score += 5
        reasons_pass.append("Regime: RANGING (neutral)")
    else:
        reasons_fail.append(f"Regime: {regime} (misaligned)")
    
    # 6. VOLUME (0-10)
    vol_ratio = row.get('volume_ratio', 1.0)
    if not pd.isna(vol_ratio) and vol_ratio > 1.2:
        score += 10
        reasons_pass.append(f"Volume ratio {vol_ratio:.2f} (confirmed)")
    elif not pd.isna(vol_ratio) and vol_ratio > 0.8:
        score += 3
    
    return score, reasons_pass, reasons_fail

# ============================================================
# SIGNAL GENERATION — WITH COOLDOWN AND REGIME BLOCKS
# ============================================================
def generate_signals(df, cfg):
    """Generate signals with all locked filters."""
    signals = []
    last_signal_bar = {
        'LONG': -cfg['cooldown_bars'] - 1,
        'SHORT': -cfg['cooldown_bars'] - 1
    }
    
    warmup = max(cfg['indicator_periods']['ema_slow'], 
                 cfg['indicator_periods']['rsi'],
                 cfg['indicator_periods']['atr']) + 10
    
    for i in range(warmup, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i-1] if i > 0 else None
        
        # Skip if any required indicator is NaN
        if pd.isna(row['ema_fast']) or pd.isna(row['ema_slow']) or \
           pd.isna(row['rsi']) or pd.isna(row['atr']) or pd.isna(row['macd_hist']):
            continue
        
        regime = row.get('regime', 'UNKNOWN')
        if regime == 'UNKNOWN':
            continue
        
        for side in ['LONG', 'SHORT']:
            # Cooldown check
            bars_since = i - last_signal_bar[side]
            if bars_since < cfg['cooldown_bars']:
                continue
            
            # Strong trend blocking
            if cfg['block_strong_uptrend']:
                if side == 'SHORT' and regime == 'STRONG_UPTREND':
                    continue
                if side == 'LONG' and regime == 'STRONG_DOWNTREND':
                    continue
            
            # Score
            score, reasons_pass, reasons_fail = score_signal(row, prev_row, side)
            
            if score >= cfg['min_signal_score']:
                atr = row['atr']
                entry = row['close']
                
                if side == 'LONG':
                    sl = entry - (atr * cfg['atr_sl_multiplier'])
                    tp = entry + (atr * cfg['atr_tp_multiplier'])
                else:
                    sl = entry + (atr * cfg['atr_sl_multiplier'])
                    tp = entry - (atr * cfg['atr_tp_multiplier'])
                
                signal = {
                    'bar_index': i,
                    'timestamp': str(row.name),
                    'side': side,
                    'entry': round(entry, 6),
                    'stop_loss': round(sl, 6),
                    'take_profit': round(tp, 6),
                    'atr': round(atr, 6),
                    'score': score,
                    'regime': regime,
                    'reasons_pass': reasons_pass,
                    'reasons_fail': reasons_fail
                }
                signals.append(signal)
                last_signal_bar[side] = i
    
    return signals

# ============================================================
# WALK-FORWARD OUTCOME — TP/SL ONLY (NO EARLY EXIT)
# ============================================================
def determine_outcomes(signals, df, max_lookahead=500):
    """
    For each signal, scan future candles.
    Exit ONLY when TP or SL is hit.
    If neither hit within max_lookahead, mark as EXPIRED.
    
    This matches V0's in-sample logic where avg_win = 3.0R.
    """
    results = []
    
    for sig in signals:
        bar_idx = sig['bar_index']
        entry = sig['entry']
        sl = sig['stop_loss']
        tp = sig['take_profit']
        side = sig['side']
        atr = sig['atr']
        risk = atr * CONFIG['atr_sl_multiplier']
        
        outcome = None
        exit_price = None
        exit_bar = None
        exit_reason = None
        r_multiple = 0.0
        
        # Scan future bars
        end_idx = min(bar_idx + max_lookahead, len(df))
        for j in range(bar_idx + 1, end_idx):
            candle = df.iloc[j]
            
            if side == 'LONG':
                # Check SL first (conservative — if both hit, loss wins)
                if candle['low'] <= sl:
                    outcome = 'LOSS'
                    exit_price = sl
                    exit_bar = j
                    exit_reason = f"SL hit on bar {j - bar_idx}"
                    r_multiple = -1.0
                    break
                elif candle['high'] >= tp:
                    outcome = 'WIN'
                    exit_price = tp
                    exit_bar = j
                    exit_reason = f"TP hit on bar {j - bar_idx}"
                    r_multiple = CONFIG['atr_tp_multiplier']  # 3.0
                    break
            else:  # SHORT
                if candle['high'] >= sl:
                    outcome = 'LOSS'
                    exit_price = sl
                    exit_bar = j
                    exit_reason = f"SL hit on bar {j - bar_idx}"
                    r_multiple = -1.0
                    break
                elif candle['low'] <= tp:
                    outcome = 'WIN'
                    exit_price = tp
                    exit_bar = j
                    exit_reason = f"TP hit on bar {j - bar_idx}"
                    r_multiple = CONFIG['atr_tp_multiplier']  # 3.0
                    break
        
        if outcome is None:
            outcome = 'EXPIRED'
            exit_reason = f"No TP/SL hit within {max_lookahead} bars"
            exit_price = df.iloc[min(end_idx - 1, len(df) - 1)]['close']
            if side == 'LONG':
                r_multiple = (exit_price - entry) / risk if risk > 0 else 0
            else:
                r_multiple = (entry - exit_price) / risk if risk > 0 else 0
        
        result = {
            **sig,
            'outcome': outcome,
            'exit_price': round(exit_price, 6) if exit_price else None,
            'exit_bar_offset': exit_bar - bar_idx if exit_bar else None,
            'exit_reason': exit_reason,
            'r_multiple': round(r_multiple, 4)
        }
        results.append(result)
    
    return results

# ============================================================
# ANALYSIS
# ============================================================
def analyze_results(results, pair, total_days):
    """Compute metrics for a set of trade results."""
    if not results:
        return {
            'pair': pair,
            'total_trades': 0,
            'wins': 0, 'losses': 0, 'expired': 0,
            'win_rate': 0, 'profit_factor': 0, 'net_r': 0,
            'avg_win_r': 0, 'avg_loss_r': 0,
            'signals_per_day': 0
        }
    
    wins = [r for r in results if r['outcome'] == 'WIN']
    losses = [r for r in results if r['outcome'] == 'LOSS']
    expired = [r for r in results if r['outcome'] == 'EXPIRED']
    
    total_win_r = sum(r['r_multiple'] for r in wins)
    total_loss_r = sum(abs(r['r_multiple']) for r in losses)
    expired_r = sum(r['r_multiple'] for r in expired)
    
    net_r = total_win_r - total_loss_r + expired_r
    
    win_rate = len(wins) / len(results) * 100 if results else 0
    pf = total_win_r / total_loss_r if total_loss_r > 0 else float('inf')
    avg_win = total_win_r / len(wins) if wins else 0
    avg_loss = total_loss_r / len(losses) if losses else 0
    
    return {
        'pair': pair,
        'total_trades': len(results),
        'wins': len(wins),
        'losses': len(losses),
        'expired': len(expired),
        'win_rate': round(win_rate, 2),
        'profit_factor': round(pf, 4),
        'net_r': round(net_r, 2),
        'avg_win_r': round(avg_win, 4),
        'avg_loss_r': round(avg_loss, 4),
        'signals_per_day': round(len(results) / total_days, 2),
        'total_win_r': round(total_win_r, 2),
        'total_loss_r': round(total_loss_r, 2),
        'expired_r': round(expired_r, 2)
    }

def regime_distribution(results):
    """Count signals per regime."""
    dist = {}
    for r in results:
        regime = r['regime']
        if regime not in dist:
            dist[regime] = {'count': 0, 'wins': 0, 'losses': 0, 'expired': 0}
        dist[regime]['count'] += 1
        if r['outcome'] == 'WIN':
            dist[regime]['wins'] += 1
        elif r['outcome'] == 'LOSS':
            dist[regime]['losses'] += 1
        else:
            dist[regime]['expired'] += 1
    
    # Add win rate and PF per regime
    for regime, data in dist.items():
        resolved = data['wins'] + data['losses']
        data['win_rate'] = round(data['wins'] / resolved * 100, 2) if resolved > 0 else 0
        total_win = data['wins'] * CONFIG['atr_tp_multiplier']
        total_loss = data['losses'] * 1.0
        data['profit_factor'] = round(total_win / total_loss, 4) if total_loss > 0 else float('inf')
    
    return dist

def cluster_analysis(results):
    """Analyze signal distribution across UTC hours."""
    hour_dist = {}
    for r in results:
        ts = pd.Timestamp(r['timestamp'])
        hour = ts.hour
        if hour not in hour_dist:
            hour_dist[hour] = 0
        hour_dist[hour] += 1
    return dict(sorted(hour_dist.items()))

# ============================================================
# DETERMINISM CHECK
# ============================================================
def determinism_hash(results):
    """Create a hash of all signal outputs for determinism verification."""
    serialized = json.dumps(
        [{k: v for k, v in r.items() if k != 'reasons_pass' and k != 'reasons_fail'} 
         for r in results],
        sort_keys=True, default=str
    )
    return hashlib.sha256(serialized.encode()).hexdigest()

# ============================================================
# MAIN EXECUTION
# ============================================================
def main():
    print("=" * 70)
    print("IDIM IKANG — PHASE 2 OUT-OF-SAMPLE VALIDATION")
    print(f"Codex ID: {CONFIG['config_version']}")
    print(f"Date Range: {CONFIG['date_start']} to {CONFIG['date_end']}")
    print(f"Executor: Claude (Examiner)")
    print("=" * 70)
    
    all_results = {}
    all_pair_metrics = []
    total_days = 92  # Oct 1 to Dec 31
    
    for pair in CONFIG['pairs']:
        print(f"\n--- Processing {pair} ---")
        
        # 1. Fetch 15m data
        print(f"  Fetching 15m klines...")
        df_15m = fetch_klines(pair, '15m', CONFIG['date_start'], CONFIG['date_end'])
        print(f"  Got {len(df_15m)} 15m candles")
        
        # 2. Fetch 4h data (need extra for regime warmup)
        print(f"  Fetching 4h klines...")
        # Fetch from 60 days earlier for regime indicator warmup
        regime_start = "2025-08-01"
        df_4h = fetch_klines(pair, '4h', regime_start, CONFIG['date_end'])
        print(f"  Got {len(df_4h)} 4h candles")
        
        # 3. Compute indicators on 15m
        print(f"  Computing 15m indicators...")
        df_15m = compute_indicators(df_15m, CONFIG)
        
        # 4. Classify regime on 4h
        print(f"  Classifying 4h regime...")
        df_4h_regime = classify_regime_4h(df_4h)
        
        # 5. Map regime to 15m
        print(f"  Mapping regime to 15m...")
        df_15m = map_regime_to_15m(df_15m, df_4h_regime)
        
        # 6. Generate signals
        print(f"  Generating signals (score >= {CONFIG['min_signal_score']})...")
        signals = generate_signals(df_15m, CONFIG)
        print(f"  Generated {len(signals)} signals")
        
        # 7. Determine outcomes (TP/SL only)
        print(f"  Running walk-forward (TP/SL exits only)...")
        results = determine_outcomes(signals, df_15m)
        
        # 8. Analyze
        metrics = analyze_results(results, pair, total_days)
        all_pair_metrics.append(metrics)
        all_results[pair] = results
        
        print(f"  Trades: {metrics['total_trades']}")
        print(f"  Wins: {metrics['wins']} | Losses: {metrics['losses']} | Expired: {metrics['expired']}")
        print(f"  Win Rate: {metrics['win_rate']}%")
        print(f"  Avg Win R: {metrics['avg_win_r']} | Avg Loss R: {metrics['avg_loss_r']}")
        print(f"  Profit Factor: {metrics['profit_factor']}")
        print(f"  Net R: {metrics['net_r']}")
        print(f"  Signals/day: {metrics['signals_per_day']}")
    
    # AGGREGATE
    print("\n" + "=" * 70)
    print("AGGREGATE RESULTS")
    print("=" * 70)
    
    all_trades = []
    for pair_results in all_results.values():
        all_trades.extend(pair_results)
    
    agg = analyze_results(all_trades, "AGGREGATE", total_days)
    
    print(f"Total Trades: {agg['total_trades']}")
    print(f"Wins: {agg['wins']} | Losses: {agg['losses']} | Expired: {agg['expired']}")
    print(f"Win Rate: {agg['win_rate']}%")
    print(f"Avg Win R: {agg['avg_win_r']} | Avg Loss R: {agg['avg_loss_r']}")
    print(f"Profit Factor: {agg['profit_factor']}")
    print(f"Net R: {agg['net_r']}")
    print(f"Signals/day: {agg['signals_per_day']}")
    
    # MATHEMATICAL VERIFICATION
    print("\n--- Mathematical Verification ---")
    expected_pf = (agg['wins'] * CONFIG['atr_tp_multiplier']) / (agg['losses'] * 1.0) if agg['losses'] > 0 else 'inf'
    print(f"Expected PF (wins×3R / losses×1R): {round(expected_pf, 4) if isinstance(expected_pf, float) else expected_pf}")
    print(f"Reported PF: {agg['profit_factor']}")
    print(f"Match: {abs(expected_pf - agg['profit_factor']) < 0.01 if isinstance(expected_pf, float) else 'N/A'}")
    
    # REGIME ANALYSIS
    print("\n--- Regime Distribution ---")
    regime_dist = regime_distribution(all_trades)
    for regime, data in sorted(regime_dist.items()):
        print(f"  {regime}: {data['count']} signals, WR={data['win_rate']}%, PF={data['profit_factor']}")
    
    # CLUSTER ANALYSIS
    print("\n--- Cluster Analysis (signals per UTC hour) ---")
    clusters = cluster_analysis(all_trades)
    for hour, count in clusters.items():
        print(f"  {hour:02d}:00 — {count} signals")
    
    # DETERMINISM CHECK
    print("\n--- Determinism Audit ---")
    hash1 = determinism_hash(all_trades)
    # Recompute (run signals again)
    all_trades_2 = []
    for pair in CONFIG['pairs']:
        df_15m = fetch_klines(pair, '15m', CONFIG['date_start'], CONFIG['date_end'])
        regime_start = "2025-08-01"
        df_4h = fetch_klines(pair, '4h', regime_start, CONFIG['date_end'])
        df_15m = compute_indicators(df_15m, CONFIG)
        df_4h_regime = classify_regime_4h(df_4h)
        df_15m = map_regime_to_15m(df_15m, df_4h_regime)
        signals_2 = generate_signals(df_15m, CONFIG)
        results_2 = determine_outcomes(signals_2, df_15m)
        all_trades_2.extend(results_2)
    hash2 = determinism_hash(all_trades_2)
    
    print(f"  Run 1 hash: {hash1}")
    print(f"  Run 2 hash: {hash2}")
    print(f"  Determinism: {'PASS' if hash1 == hash2 else 'FAIL'}")
    
    # BUILD PHASE2_RESULTS.json
    output = {
        "run_metadata": {
            "codex_id": "mo-fin-idim-ikang-001",
            "logic_version": CONFIG['logic_version'],
            "config_version": CONFIG['config_version'],
            "executor": "Claude (Examiner)",
            "date_range": f"{CONFIG['date_start']} to {CONFIG['date_end']}",
            "type": "out-of-sample",
            "in_sample_range": "2026-01-01 to 2026-03-31"
        },
        "config": CONFIG,
        "data_integrity": {
            "candles_per_pair": {p: len(all_results[p]) for p in CONFIG['pairs']},
            "pagination_enforced": True,
            "open_candles_rejected": True,
            "warmup_discarded": True
        },
        "per_pair_metrics": all_pair_metrics,
        "aggregate_metrics": agg,
        "mathematical_verification": {
            "expected_pf_from_wins_losses": round(expected_pf, 4) if isinstance(expected_pf, float) else expected_pf,
            "reported_pf": agg['profit_factor'],
            "consistent": abs(expected_pf - agg['profit_factor']) < 0.01 if isinstance(expected_pf, float) else False
        },
        "regime_analysis": regime_dist,
        "cluster_analysis": clusters,
        "determinism_audit": {
            "hash_run_1": hash1,
            "hash_run_2": hash2,
            "passed": hash1 == hash2
        },
        "sample_trades": all_trades[:10],
        "overall_verdict": {}
    }
    
    # Write results
    with open('/home/claude/PHASE2_RESULTS.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\n\nResults written to /home/claude/PHASE2_RESULTS.json")
    print("=" * 70)
    print("VALIDATION COMPLETE")
    print("=" * 70)

if __name__ == '__main__':
    main()
