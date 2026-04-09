#!/usr/bin/env python3
"""
test_ft_bridge.py - Test harness for FreqTrade bridge integration

Quick validation that the bridge can load strategies and evaluate signals.
Run this to verify the FreqTrade integration before modifying the scanner.
"""

import sys
import logging
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def create_test_dataframe(periods=100, scenario='neutral'):
    """Create synthetic test data with Idim indicators."""
    import pandas as pd
    import numpy as np
    
    np.random.seed(42)  # For reproducible tests
    dates = pd.date_range('2024-01-01', periods=periods, freq='15min')
    
    # Scenario-based price generation
    if scenario == 'long':
        # LONG scenario: uptrend with squeeze fire
        base_price = 100
        trend = np.linspace(0, 10, periods)  # Strong uptrend
        noise = np.random.normal(0, 0.5, periods)
        prices = base_price + trend + noise
        volume = np.random.normal(2000000, 100000, periods)  # Very high volume for >=1.1 ratio
        
    elif scenario == 'short':
        # SHORT scenario: downtrend with squeeze fire
        base_price = 110
        trend = np.linspace(0, -10, periods)  # Strong downtrend
        noise = np.random.normal(0, 0.5, periods)
        prices = base_price + trend + noise
        volume = np.random.normal(2000000, 100000, periods)  # Very high volume for >=1.1 ratio
        
    else:  # neutral
        # Neutral scenario: sideways, low volume
        base_price = 100
        trend = np.linspace(0, 0, periods)  # No trend
        noise = np.random.normal(0, 1, periods)
        prices = base_price + trend + noise
        volume = np.random.normal(1000000, 200000, periods)  # Normal volume
    
    # Generate OHLCV data
    df = pd.DataFrame({
        'open_time': dates,
        'close': prices,
        'open': prices + np.random.normal(0, 0.5, periods),
        'high': prices + np.abs(np.random.normal(1, 0.5, periods)),
        'low': prices - np.abs(np.random.normal(1, 0.5, periods)),
        'volume': volume,
    })
    
    # Calculate Idim's core indicators
    df['ema20'] = df['close'].ewm(span=20).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df['rsi14'] = (100 - (100 / (1 + rs))).fillna(50)
    
    # MACD
    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    macd = ema12 - ema26
    df['macd_hist'] = macd - macd.ewm(span=9).mean()
    
    # ADX (simplified)
    df['adx14'] = 25 + np.random.normal(0, 5, periods)  # Around typical ADX values
    df['adx14'] = df['adx14'].clip(10, 50)  # Realistic range
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr14'] = true_range.ewm(alpha=1/14, min_periods=14).mean()
    
    # Volume SMA - manipulate for LONG/SHORT scenarios to ensure >=1.1 ratio
    df['volume_sma20'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_sma20']
    
    # Force volume ratio >= 1.1 for LONG/SHORT scenarios
    if scenario in ['long', 'short']:
        # Directly set volume ratio to meet requirement
        df['volume_ratio'] = 1.5  # Force >=1.1 ratio
    
    # Squeeze indicators with deterministic fire for test scenarios
    df['sma20'] = df['close'].rolling(20).mean()
    df['std20'] = df['close'].rolling(20).std()
    df['bb_upper'] = df['sma20'] + 2 * df['std20']
    df['bb_lower'] = df['sma20'] - 2 * df['std20']
    df['kc_upper'] = df['ema20'] + 1.5 * df['atr14']
    df['kc_lower'] = df['ema20'] - 1.5 * df['atr14']
    df['squeeze_on'] = (df['bb_upper'] < df['kc_upper']) & (df['bb_lower'] > df['kc_lower'])
    df['squeeze_fired'] = df['squeeze_on'].shift(1).fillna(False) & ~df['squeeze_on']
    
    # Force squeeze fire for LONG/SHORT scenarios
    if scenario in ['long', 'short']:
        # Create a squeeze fire at the end of the series
        df.loc[periods-5:periods-3, 'squeeze_on'] = True
        df.loc[periods-2:periods-1, 'squeeze_on'] = False
        df['squeeze_fired'] = df['squeeze_on'].shift(1).fillna(False) & ~df['squeeze_on']
    
    df['recent_squeeze_fire'] = df['squeeze_fired'].rolling(window=3).max().fillna(0).astype(bool)
    
    return df

def test_strategy_loading():
    """Test that all strategies can be loaded."""
    from ft_bridge import create_bridge
    
    strategies = ['IdimSqueeze', 'IdimTrendFollow', 'IdimMeanReversion']
    
    for strategy_name in strategies:
        try:
            bridge = create_bridge(strategy_name)
            logger.info(f"Successfully loaded {strategy_name}")
        except Exception as e:
            logger.error(f"Failed to load {strategy_name}: {e}")
            return False
    
    return True

def test_strategy_evaluation():
    """Test strategy evaluation with sample data."""
    from ft_bridge import create_bridge
    
    # Test IdimSqueeze strategy across all scenarios
    bridge = create_bridge('IdimSqueeze')
    
    scenarios = ['neutral', 'long', 'short']
    regimes = ['RANGING', 'STRONG_UPTREND', 'STRONG_DOWNTREND']
    
    for scenario in scenarios:
        df = create_test_dataframe(scenario=scenario)
        latest = df.iloc[-1]
        
        # Choose appropriate regime for scenario
        if scenario == 'long':
            regime = 'STRONG_UPTREND'
        elif scenario == 'short':
            regime = 'STRONG_DOWNTREND'
        else:
            regime = 'RANGING'
        
        # Evaluate strategy
        score, trace = bridge.evaluate_signal(df, regime, {})
        
        # Verify results
        assert isinstance(score, (int, float)), f"Score should be numeric, got {type(score)}"
        assert isinstance(trace, dict), f"Trace should be dict, got {type(trace)}"
        assert 'reasons_pass' in trace, "Trace should contain reasons_pass"
        assert 'reasons_fail' in trace, "Trace should contain reasons_fail"
        
        logger.info(f"\nScenario: {scenario.upper()}")
        logger.info(f"Regime: {regime}")
        logger.info(f"  Score: {score:.2f}")
        logger.info(f"  Pass reasons: {len(trace['reasons_pass'])}")
        logger.info(f"  Fail reasons: {len(trace['reasons_fail'])}")
        # Extract real FT signals from canonical output
        ft_signals = trace.get('freqtrade_signals', {})
        enter_long = int(ft_signals.get('enter_long', 0))
        enter_short = int(ft_signals.get('enter_short', 0))
        
        logger.info(f"  FreqTrade signals: LONG={enter_long}, SHORT={enter_short}")
        
        # Debug: Show actual conditions for LONG scenario
        if scenario == 'long':
            latest = df.iloc[-1]
            logger.info(f"  Debug - Latest conditions:")
            logger.info(f"    ADX: {latest.get('adx14', 'N/A')} (>=20 needed)")
            logger.info(f"    Squeeze fire: {latest.get('recent_squeeze_fire', 'N/A')} (True needed)")
            logger.info(f"    EMA20>EMA50: {latest.get('ema20', 'N/A')} > {latest.get('ema50', 'N/A')} = {latest.get('ema20', 0) > latest.get('ema50', 0)}")
            logger.info(f"    Volume ratio: {latest.get('volume_ratio', 'N/A')} (>=1.1 needed)")
            logger.info(f"    Price>EMA20: {latest.get('close', 'N/A')} > {latest.get('ema20', 'N/A')} = {latest.get('close', 0) > latest.get('ema20', 0)}")
            
            # Assert deterministic LONG fixture behavior
            assert enter_long == 1 and enter_short == 0, f"LONG scenario must produce (enter_long=1, enter_short=0), got ({enter_long}, {enter_short})"
            
        elif scenario == 'short':
            latest = df.iloc[-1]
            logger.info(f"  Debug - Latest conditions:")
            logger.info(f"    ADX: {latest.get('adx14', 'N/A')} (>=20 needed)")
            logger.info(f"    Squeeze fire: {latest.get('recent_squeeze_fire', 'N/A')} (True needed)")
            logger.info(f"    EMA20>EMA50: {latest.get('ema20', 'N/A')} > {latest.get('ema50', 'N/A')} = {latest.get('ema20', 0) > latest.get('ema50', 0)}")
            logger.info(f"    Volume ratio: {latest.get('volume_ratio', 'N/A')} (>=1.1 needed)")
            logger.info(f"    Price>EMA20: {latest.get('close', 'N/A')} > {latest.get('ema20', 'N/A')} = {latest.get('close', 0) > latest.get('ema20', 0)}")
            
            # Assert deterministic SHORT fixture behavior
            assert enter_long == 0 and enter_short == 1, f"SHORT scenario must produce (enter_long=0, enter_short=1), got ({enter_long}, {enter_short})"
            
        else:  # neutral
            # Assert deterministic NEUTRAL fixture behavior
            assert enter_long == 0 and enter_short == 0, f"NEUTRAL scenario must produce (enter_long=0, enter_short=0), got ({enter_long}, {enter_short})"
    
    return True

def test_bridge_integration():
    """Test full bridge integration."""
    logger.info("=== FreqTrade Bridge Integration Test ===\n")
    
    # Test 1: Strategy loading
    logger.info("1. Testing strategy loading...")
    if not test_strategy_loading():
        logger.error("Strategy loading test failed")
        return False
    
    # Test 2: Strategy evaluation
    logger.info("\n2. Testing strategy evaluation...")
    if not test_strategy_evaluation():
        logger.error("Strategy evaluation test failed")
        return False
    
    logger.info("\n=== All tests passed! ===")
    logger.info("Bridge is ready for integration with Idim scanner")
    return True

if __name__ == "__main__":
    success = test_bridge_integration()
    sys.exit(0 if success else 1)

