"""
IdimTrendFollow.py
==================
Trend-following strategy orthogonal to Idim's native squeeze gate.

Alpha this adds over native Idim:
  - Requires 3-component trend score (EMA stack + price position + MACD)
  - RSI band filter prevents chasing at momentum extremes
  - No squeeze requirement — catches sustained trends that never compressed

Signal logic:
  LONG  — ADX >= 20, EMA20 > EMA50, price > EMA20, MACD hist > 0,
           RSI 30-65, volume >= 1.1, trend_score >= 2
  SHORT — ADX >= 20, EMA20 < EMA50, price < EMA20, MACD hist < 0,
           RSI 35-70, volume >= 1.1, trend_score >= 2

Author: The Flame Architect | MoStar Industries
"""

import pandas as pd
from .IStrategy_minimal import IStrategy


class IdimTrendFollow(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        if "volume_ratio" not in dataframe.columns:
            vol_sma = dataframe["volume"].rolling(20).mean()
            dataframe["volume_ratio"] = dataframe["volume"] / vol_sma.replace(0, float("nan"))

        # trend_score: 0-3, counts how many structural conditions align
        # 0 = no structure, 3 = fully stacked
        dataframe["trend_score"] = (
            (dataframe["ema20"] > dataframe["ema50"]).astype(int)
            + (dataframe["close"] > dataframe["ema20"]).astype(int)
            + (dataframe["macd_hist"] > 0).astype(int)
        )

        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0

        adx_ok          = dataframe["adx14"] >= 20
        vol_ok          = dataframe["volume_ratio"] >= 1.1
        strong_structure = dataframe["trend_score"] >= 2

        # LONG — all three structural components point up
        long_conditions = (
            adx_ok
            & (dataframe["ema20"] > dataframe["ema50"])
            & (dataframe["close"] > dataframe["ema20"])
            & (dataframe["macd_hist"] > 0)
            & (dataframe["rsi14"] >= 30) & (dataframe["rsi14"] <= 65)
            & vol_ok
            & strong_structure
        )

        # SHORT — all three structural components point down
        short_conditions = (
            adx_ok
            & (dataframe["ema20"] < dataframe["ema50"])
            & (dataframe["close"] < dataframe["ema20"])
            & (dataframe["macd_hist"] < 0)        # explicit < 0, not ~(> 0)
            & (dataframe["rsi14"] >= 35) & (dataframe["rsi14"] <= 70)
            & vol_ok
            & (dataframe["trend_score"] <= 1)      # inverse score for shorts
        )

        dataframe.loc[long_conditions,  "enter_long"]  = 1
        dataframe.loc[short_conditions, "enter_short"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """Idim executor owns exits. Columns required by interface only."""
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        return dataframe