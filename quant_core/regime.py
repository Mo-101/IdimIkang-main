"""
IDIM IKANG — Validated Indicator Module
Codex ID: mo-fin-idim-ikang-001
Logic Version: v1.0-tuned

These are the EXACT indicator implementations that produced PF 1.2019
on the Wolfram-verified out-of-sample run. DO NOT MODIFY.
"""

import pandas as pd


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average — pure function."""
    return series.ewm(span=period, adjust=False).mean()


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index — pure function."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range — pure function."""
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    return atr


def apply_all_indicators(df: pd.DataFrame, config: dict = None) -> pd.DataFrame:
    """
    Compute all indicators on a DataFrame.
    Config keys used: indicator_periods.ema_fast, ema_slow, rsi, atr, volume_sma
    """
    if config is None:
        config = {
            "indicator_periods": {
                "ema_fast": 20,
                "ema_slow": 50,
                "rsi": 14,
                "atr": 14,
                "volume_sma": 20
            }
        }

    p = config["indicator_periods"]
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