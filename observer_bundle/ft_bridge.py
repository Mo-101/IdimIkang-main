#!/usr/bin/env python3
"""
ft_bridge.py - FreqTrade Strategy Bridge for Idim Ikang

Thin adapter that translates FreqTrade IStrategy outputs into Idim's scoring format.
Allows Idim's sovereign scanner to leverage FreqTrade's DSL while maintaining
full control over execution, ranking, and risk management.

Design Principles:
- Scanner remains sovereign (no FreqTrade execution)
- Bridge is read-only (no state mutation)
- Clean separation: strategy DSL vs Idim gates
"""

import importlib
import logging
from typing import Dict, Tuple

import pandas as pd

try:
    from .ft_strategies.IStrategy_minimal import IStrategy
except ImportError:
    from ft_strategies.IStrategy_minimal import IStrategy

FT_STRATEGIES_PACKAGE_CANDIDATES = (
    "observer_bundle.ft_strategies",
    "ft_strategies",
)


def _import_strategy_module(strategy_name: str):
    last_exc = None
    for pkg in FT_STRATEGIES_PACKAGE_CANDIDATES:
        module_name = f"{pkg}.{strategy_name}"
        try:
            return importlib.import_module(module_name)
        except Exception as exc:
            last_exc = exc
    raise ImportError(f"Could not import FT strategy '{strategy_name}'") from last_exc

logger = logging.getLogger(__name__)


class FreqTradeBridge:
    """
    Adapter layer between FreqTrade strategies and Idim's scoring system.
    
    Usage:
        bridge = FreqTradeBridge("ft_strategies.IdimSqueeze")
        score, trace = bridge.evaluate_signal(df15, regime, alpha)
    """
    
    def __init__(self, strategy_module_path: str):
        """
        Initialize bridge with a FreqTrade strategy.
        
        Args:
            strategy_module_path: Module path like "ft_strategies.IdimSqueeze"
        """
        self.strategy_path = strategy_module_path
        self.strategy = self._load_strategy()
        
    def _load_strategy(self) -> IStrategy:
        """Dynamically load FreqTrade strategy."""
        try:
            module_path, class_name = self.strategy_path.rsplit(".", 1)
            module = _import_strategy_module(class_name)
            strategy_class = getattr(module, class_name, None)
            
            if strategy_class is None:
                raise AttributeError(f"Strategy class '{class_name}' not found")
                
            if not hasattr(strategy_class, 'INTERFACE_VERSION') or not hasattr(strategy_class, 'populate_indicators'):
                raise ValueError(f"{class_name} is not a valid IStrategy")
                
            strategy = strategy_class()
            if not isinstance(strategy, IStrategy):
                raise TypeError(f"{class_name} does not implement IStrategy")
                
            return strategy
            
        except Exception as e:
            logger.error(f"Failed to load strategy {self.strategy_path}: {e}")
            raise
    
    def evaluate_signal(self, 
                        df: pd.DataFrame, 
                        regime: str, 
                        alpha: Dict) -> Tuple[float, Dict]:
        """
        Evaluate a symbol using FreqTrade strategy and return Idim-compatible score.
        
        Args:
            df: 15m DataFrame with indicators already calculated
            regime: Current market regime (RANGING, UPTREND, etc.)
            alpha: Derivatives context dict
            
        Returns:
            Tuple of (score, trace_dict) compatible with Idim's scoring format
        """
        try:
            # Ensure required indicators exist (Idim already calculates these)
            required_indicators = ['close', 'high', 'low', 'volume', 'ema20', 'ema50', 
                                 'rsi14', 'macd_hist', 'adx14', 'atr14',
                                 'volume_ratio', 'squeeze_on', 'squeeze_fired', 
                                 'recent_squeeze_fire']
            missing = [ind for ind in required_indicators if ind not in df.columns]
            if missing:
                raise ValueError(f"Missing indicators: {missing}")
            
            # Call FreqTrade strategy methods
            df_with_indicators = self._call_populate_indicators(df)
            df_with_signals = self._call_populate_signals(df_with_indicators)
            
            # Extract latest signals
            latest = df_with_signals.iloc[-1]
            
            # Convert FreqTrade signals to Idim scoring format
            return self._translate_to_idim_score(latest, regime, alpha)
            
        except Exception as e:
            logger.error(f"Strategy evaluation failed: {e}")
            return 0.0, {"reasons_fail": [f"Strategy error: {str(e)}"]}
    
    def _call_populate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Safely call strategy's populate_indicators."""
        try:
            # Make a copy to avoid mutations
            df_copy = df.copy()
            result_df = self.strategy.populate_indicators(df_copy, {'pair': 'TEST'})
            return result_df if result_df is not None else df_copy
        except Exception as e:
            logger.warning(f"populate_indicators failed: {e}")
            return df
    
    def _call_populate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Call entry/exit signal methods."""
        try:
            df_copy = df.copy()
            
            # Entry signals
            if hasattr(self.strategy, 'populate_entry_trend'):
                df_copy = self.strategy.populate_entry_trend(df_copy, {'pair': 'TEST'})
            
            # Exit signals  
            if hasattr(self.strategy, 'populate_exit_trend'):
                df_copy = self.strategy.populate_exit_trend(df_copy, {'pair': 'TEST'})
                
            return df_copy
        except Exception as e:
            logger.warning(f"Signal population failed: {e}")
            return df
    
    def _translate_to_idim_score(self, latest: pd.Series, regime: str, alpha: Dict) -> Tuple[float, Dict]:
        """
        Convert FreqTrade signals to Idim's scoring format.
        
        FreqTrade uses 0/1/-1 in 'enter_long', 'enter_short' columns.
        Idim needs a continuous score and detailed trace.
        """
        reasons_pass = []
        reasons_fail = []
        score = 0.0
        
        # Extract FreqTrade signals
        enter_long = int(latest.get('enter_long', 0) or 0)
        enter_short = int(latest.get('enter_short', 0) or 0)
        
        # Note: ADX gate is enforced by native scanner - not duplicated here
        adx = float(latest.get('adx14', 0))
        if adx < 20:
            reasons_fail.append("adx_below_20_seen_in_bridge")
        else:
            reasons_pass.append("adx_ok")
        
        # EMA alignment
        if latest['ema20'] > latest['ema50']:
            score += 20; reasons_pass.append("EMA20 > EMA50 (trend aligned)")
        else:
            reasons_fail.append("EMA20 <= EMA50")
        
        # Price vs EMA20
        if latest['close'] > latest['ema20']:
            score += 10; reasons_pass.append("Price above EMA20")
        else:
            reasons_fail.append("Price <= EMA20")
        
        # RSI
        rsi_v = float(latest.get('rsi14', 50))
        if 30 <= rsi_v <= 65:
            score += 15; reasons_pass.append(f"RSI {rsi_v:.1f} in bull zone")
        else:
            reasons_fail.append(f"RSI {rsi_v:.1f} outside bull zone")
        
        # MACD
        if latest.get('macd_hist', 0) > 0:
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
        
        # FreqTrade signal bonus (if present)
        if enter_long == 1:
            score += 25; reasons_pass.append("FreqTrade LONG signal")
        elif enter_short == 1:
            score += 25; reasons_pass.append("FreqTrade SHORT signal")
        
        # Volume check
        vol_ratio = float(latest.get('volume', 0)) / float(latest.get('volume_sma20', 1))
        if vol_ratio >= 1.1:
            score += 15; reasons_pass.append(f"Volume ratio {vol_ratio:.2f} (confirmed)")
        else:
            reasons_fail.append(f"Volume ratio {vol_ratio:.2f} below 1.1")
        
        # Derivatives alpha (same as Idim)
        funding = alpha.get("funding_rate", 0.0)
        ls_ratio = alpha.get("ls_ratio", 1.0)
        if funding < -0.005 and ls_ratio < 0.9:
            score += 30; reasons_pass.append(f"SHORT SQUEEZE ALPHA: Funding {funding:.4f}, LS {ls_ratio:.2f}")
        elif ls_ratio > 2.5:
            score -= 20; reasons_fail.append(f"Crowded Longs (LS {ls_ratio:.2f})")
        
        trace = {
            "reasons_pass": reasons_pass,
            "reasons_fail": reasons_fail,
            "volume_ratio": vol_ratio,
            "freqtrade_signals": {
                "enter_long": int(enter_long),
                "enter_short": int(enter_short)
            }
        }
        
        return score, trace


def create_bridge(strategy_name: str) -> FreqTradeBridge:
    """
    Factory function to create bridge instances.
    
    Args:
        strategy_name: Strategy class name (e.g., "IdimSqueeze")
        
    Returns:
        FreqTradeBridge instance
    """
    module_path = f"ft_strategies.{strategy_name}"
    return FreqTradeBridge(module_path)


# Test harness (can be called from scanner for validation)
def test_bridge(strategy_name: str = "IdimSqueeze"):
    """Test bridge with sample data."""
    import numpy as np
    
    # Create sample DataFrame
    dates = pd.date_range('2024-01-01', periods=100, freq='15T')
    df = pd.DataFrame({
        'open_time': dates,
        'close': np.random.normal(100, 2, 100),
        'high': np.random.normal(102, 2, 100),
        'low': np.random.normal(98, 2, 100),
        'volume': np.random.normal(1000000, 100000, 100),
    })
    
    # Add basic indicators (Idim would calculate these)
    df['ema20'] = df['close'].ewm(span=20).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()
    df['rsi14'] = 50 + np.random.normal(0, 10, 100)
    df['macd_hist'] = np.random.normal(0, 0.001, 100)
    df['adx14'] = 25 + np.random.normal(0, 5, 100)
    df['atr14'] = 2.0 + np.random.normal(0, 0.5, 100)
    df['volume_sma20'] = df['volume'].rolling(20).mean()
    
    try:
        bridge = create_bridge(strategy_name)
        score, trace = bridge.evaluate_signal(df, "UPTREND", {"funding_rate": 0, "ls_ratio": 1.0})
        print(f"Bridge test successful: score={score}, reasons_pass={len(trace['reasons_pass'])}")
        return True
    except Exception as e:
        print(f"Bridge test failed: {e}")
        return False


if __name__ == "__main__":
    test_bridge()
