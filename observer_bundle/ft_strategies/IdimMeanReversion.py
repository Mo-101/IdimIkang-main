"""
IdimMeanReversion.py
====================
Mean-reversion strategy for ranging markets — orthogonal to Idim's trend gates.

Alpha this adds over native Idim:
  - Targets ADX 15-25 ranging zone Idim's trend strategies avoid
  - RSI extremes + BB touch as confluence for reversal entries
  - Volume spike confirms institutional participation at extremes

Signal logic:
  LONG  — ADX 15-25 (ranging), RSI < 32, price at/below BB lower,
           volume spike >= 1.5x, MACD hist weakening (magnitude < median)
  SHORT — ADX 15-25 (ranging), RSI > 68, price at/above BB upper,
           volume spike >= 1.5x, MACD hist weakening

Key fix over previous version:
  - trend_weakening was `abs(macd_hist) < 0.001` — effectively never True on
    crypto where MACD hist is in price units (dollars/sats).
    Fixed to: MACD hist magnitude below its own rolling median.
  - Division-by-zero guards on rsi_stoch and bb_position.

Author: The Flame Architect | MoStar Industries
"""

import numpy as np
import pandas as pd
from .IStrategy_minimal import IStrategy


class IdimMeanReversion(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        if "bb_upper" not in dataframe.columns:
            sma20 = dataframe["close"].rolling(20).mean()
            std20 = dataframe["close"].rolling(20).std()
            dataframe["bb_upper"] = sma20 + 2 * std20
            dataframe["bb_lower"] = sma20 - 2 * std20
            dataframe["sma20"]    = sma20

        if "volume_ratio" not in dataframe.columns:
            vol_sma = dataframe["volume"].rolling(20).mean()
            dataframe["volume_ratio"] = dataframe["volume"] / vol_sma.replace(0, float("nan"))

        # RSI stochastic — how extreme is RSI relative to its recent range
        # Division-by-zero guard: when min == max (flat RSI), default to 0.5
        rsi_min = dataframe["rsi14"].rolling(14).min()
        rsi_max = dataframe["rsi14"].rolling(14).max()
        rsi_range = (rsi_max - rsi_min).replace(0, float("nan"))
        dataframe["rsi_stoch"] = ((dataframe["rsi14"] - rsi_min) / rsi_range).fillna(0.5)

        # MACD histogram weakening — magnitude below its own 20-bar rolling median
        # This is relative to the instrument's own volatility regime, not a fixed threshold
        macd_abs = dataframe["macd_hist"].abs()
        dataframe["macd_hist_median"] = macd_abs.rolling(20).median()
        dataframe["trend_weakening"] = macd_abs < dataframe["macd_hist_median"]

        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0

        # Ranging zone: ADX 15-25
        # Lower bound 15 filters pure noise; upper bound 25 keeps us out of trends
        ranging = (dataframe["adx14"] >= 15) & (dataframe["adx14"] <= 25)

        vol_spike        = dataframe["volume_ratio"] >= 1.5
        trend_weakening  = dataframe["trend_weakening"]

        # LONG — oversold extreme
        long_conditions = (
            ranging
            & (dataframe["rsi14"] < 32)
            & (dataframe["close"] <= dataframe["bb_lower"])
            & (dataframe["rsi_stoch"] < 0.2)
            & vol_spike
            & trend_weakening
        )

        # SHORT — overbought extreme
        short_conditions = (
            ranging
            & (dataframe["rsi14"] > 68)
            & (dataframe["close"] >= dataframe["bb_upper"])
            & (dataframe["rsi_stoch"] > 0.8)
            & vol_spike
            & trend_weakening
        )

        dataframe.loc[long_conditions,  "enter_long"]  = 1
        dataframe.loc[short_conditions, "enter_short"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """Idim executor owns exits. Columns required by interface only."""
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        return dataframe