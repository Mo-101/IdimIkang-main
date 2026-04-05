import os
import sys
import pandas as pd

# Ensure scanner can be imported from parent dir
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scanner import score_long_signal

def test_micro_chop_blocker():
    """ADX < 20 should result in a hard reject (score 0)."""
    # ADX: 15.0 (Low momentum)
    latest = pd.Series({'adx14': 15.0, 'atr14': 1.0, 'close': 100, 'ema20': 99, 'ema50': 98, 'rsi14': 60, 'macd_hist': 0.5})
    alpha = {'funding_rate': 0.0, 'ls_ratio': 1.0}
    
    score, trace = score_long_signal(latest, 'UPTREND', alpha)
    assert score == 0.0
    assert "15m ADX < 20 (Micro Chop)" in trace['reasons_fail']

def test_exhaustion_blocker():
    """Price > 1.5 ATRs away from EMA20 should reject to prevent 'Rubber Band' snapback."""
    # Distance = 5. 1.5 * ATR = 3. 5 > 3. Should reject.
    latest = pd.Series({'adx14': 25.0, 'atr14': 2.0, 'close': 105, 'ema20': 100, 'ema50': 98, 'rsi14': 60, 'macd_hist': 0.5})
    alpha = {'funding_rate': 0.0, 'ls_ratio': 1.0}
    
    score, trace = score_long_signal(latest, 'UPTREND', alpha)
    assert score == 0.0
    assert any("Exhausted" in reason for reason in trace['reasons_fail'])

def test_short_squeeze_alpha_bonus():
    """High short interest and negative funding should award the +30 bonus."""
    latest = pd.Series({
        'adx14': 25.0, 'atr14': 1.0, 'close': 100, 'ema20': 99, 'ema50': 98, 
        'rsi14': 60, 'macd_hist': 0.5, 'volume': 1500, 'volume_sma20': 1000,
        'cvd_lite': 100.0 # Positive CVD
    })
    # Negative funding and Low LS ratio (Shorts dominant)
    alpha = {'funding_rate': -0.015, 'ls_ratio': 0.75}
    
    score, trace = score_long_signal(latest, 'UPTREND', alpha)
    assert score > 0
    assert any("SHORT SQUEEZE ALPHA" in reason for reason in trace['reasons_pass'])
    assert "Squeeze" in trace['tags']
