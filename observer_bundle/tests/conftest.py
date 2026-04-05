import pytest
import pandas as pd
import numpy as np

@pytest.fixture
def mock_klines_squeeze():
    """Generates 50 bars of tight consolidation to trigger the Squeeze."""
    dates = pd.date_range('2026-04-01', periods=50, freq='15min', tz='UTC')
    df = pd.DataFrame({
        'open_time': dates,
        'open': np.linspace(100, 100, 50),
        'high': np.linspace(100.5, 100.2, 50),
        'low': np.linspace(99.5, 99.8, 50),
        'close': np.linspace(100, 100, 50),
        'volume': np.random.uniform(1000, 2000, 50),
        'taker_buy_base_asset_volume': np.random.uniform(500, 1000, 50),
        'close_time': dates + pd.Timedelta(minutes=14, seconds=59)
    })
    return df
