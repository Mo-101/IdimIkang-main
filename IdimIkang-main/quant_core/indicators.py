import pandas as pd
import numpy as np

def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = calculate_ema(series, fast)
    ema_slow = calculate_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(period).mean()

def calculate_sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()

def apply_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pure functions only. No randomness. No hidden state.
    """
    df['ema_20'] = calculate_ema(df['close'], 20)
    df['ema_50'] = calculate_ema(df['close'], 50)
    df['ema_200'] = calculate_ema(df['close'], 200)
    df['rsi'] = calculate_rsi(df['close'], 14)
    df['macd'], df['macd_signal'], df['macd_hist'] = calculate_macd(df['close'])
    df['atr'] = calculate_atr(df, 14)
    df['volume_sma_20'] = calculate_sma(df['volume'], 20)
    return df
