import os
import sys
import pandas as pd
import numpy as np

# Ensure scanner can be imported from parent dir
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scanner import build_signal

def test_dynamic_scale_out_targets():
    """Verifies that TP1 (1.2R) and TP2 (3.0R) are correctly calculated from ATR."""
    latest = pd.Series({
        'atr14': 2.0, 
        'close': 100.0, 
        'close_time': pd.Timestamp.utcnow()
    })
    trace = {"tags": ["CVD"]}
    
    signal = build_signal('BTCUSDT', 'LONG', latest, 'UPTREND', 60.0, trace)
    
    # Entry: 100. ATR: 2.
    # TP1 should be 100 + (1.2 * 2) = 102.4
    # TP2 should be 100 + (3.0 * 2) = 106.0
    assert signal['reason_trace']['tp1'] == 102.4
    assert signal['reason_trace']['tp2'] == 106.0
    
    # take_profit should default to TP2 for backward compatibility
    assert signal['take_profit'] == 106.0
    assert "CVD" in signal['reason_trace']['tags']
