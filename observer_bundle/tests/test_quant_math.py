import os
import sys
import pandas as pd
import numpy as np

# Ensure scanner can be imported from parent dir
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scanner import add_indicators

def test_cvd_lite_calculation(mock_klines_squeeze):
    """Verifies that CVD Lite is correctly computed as cumulative (taker_buy - taker_sell)."""
    df = add_indicators(mock_klines_squeeze)
    latest = df.iloc[-1]
    
    # Calculation mirror
    taker_buy = latest['taker_buy_base_asset_volume']
    taker_sell = latest['volume'] - taker_buy
    expected_delta = taker_buy - taker_sell
    
    # CVD should be cumulative, but our fixture is deterministic/random
    # The last row's CVD should match the sum of deltas
    all_taker_buy = df['taker_buy_base_asset_volume']
    all_taker_sell = df['volume'] - all_taker_buy
    expected_cumulative_cvd = (all_taker_buy - all_taker_sell).cumsum().iloc[-1]
    
    assert np.isclose(latest['cvd_lite'], expected_cumulative_cvd), "CVD Lite calculation failed"

def test_volatility_squeeze_detection(mock_klines_squeeze):
    """Ensures that tight volatility triggers the 'squeeze_on' flag."""
    df = add_indicators(mock_klines_squeeze)
    latest = df.iloc[-1]
    # With tight high/lows in the mock data, BB should compress inside KC
    assert latest['squeeze_on'] == True, "Failed to detect volatility compression (Squeeze)"
