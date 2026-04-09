"""
IdimSqueeze.py
==============
Baseline strategy: mirrors Idim's native squeeze gate in FreqTrade DSL.

Purpose: validate the ft_bridge adapter end-to-end.
Not intended as live alpha — it duplicates native Idim gates by design.
Real alpha strategies (OI, funding divergence, CVD) built separately.

Signal logic:
  LONG  — ADX >= 20, not overextended (< 1.5x ATR), recent squeeze fire,
           EMA20 > EMA50, price > EMA20, volume ratio >= 1.1
  SHORT — same gates, opposite direction

Author: The Flame Architect | MoStar Industries
"""

import pandas as pd
from .IStrategy_minimal import IStrategy


class IdimSqueeze(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """
        Squeeze indicators — only calculated if Idim hasn't already added them.
        Idim's add_indicators() runs first; this is a safety fallback only.
        """
        if "squeeze_on" not in dataframe.columns:
            sma20 = dataframe["close"].rolling(20).mean()
            std20 = dataframe["close"].rolling(20).std()
            bb_upper = sma20 + 2 * std20
            bb_lower = sma20 - 2 * std20
            kc_upper = dataframe["ema20"] + 1.5 * dataframe["atr14"]
            kc_lower = dataframe["ema20"] - 1.5 * dataframe["atr14"]

            dataframe["squeeze_on"] = (
                (bb_upper < kc_upper) & (bb_lower > kc_lower)
            )
            dataframe["squeeze_fired"] = (
                dataframe["squeeze_on"].shift(1).fillna(False) & ~dataframe["squeeze_on"]
            ).infer_objects(copy=False)
            dataframe["recent_squeeze_fire"] = (
                dataframe["squeeze_fired"].rolling(window=3).max().fillna(0)
                .astype(bool).infer_objects(copy=False)
            )

        if "volume_ratio" not in dataframe.columns:
            vol_sma = dataframe["volume"].rolling(20).mean()
            dataframe["volume_ratio"] = dataframe["volume"] / vol_sma.replace(0, float("nan"))

        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0

        adx_ok              = dataframe["adx14"] >= 20
        stretch             = (dataframe["close"] - dataframe["ema20"]) / dataframe["atr14"].replace(0, float("nan"))
        not_ext_long        = stretch <= 1.5
        not_ext_short       = stretch >= -1.5
        squeeze_triggered   = dataframe["recent_squeeze_fire"].astype(bool)
        trend_up            = dataframe["ema20"] > dataframe["ema50"]
        trend_down          = dataframe["ema20"] < dataframe["ema50"]
        vol_ok              = dataframe["volume_ratio"] >= 1.1
        price_above_ema20   = dataframe["close"] > dataframe["ema20"]
        price_below_ema20   = dataframe["close"] < dataframe["ema20"]

        dataframe.loc[
            adx_ok & not_ext_long  & squeeze_triggered & trend_up   & vol_ok & price_above_ema20,
            "enter_long"
        ] = 1

        dataframe.loc[
            adx_ok & not_ext_short & squeeze_triggered & trend_down & vol_ok & price_below_ema20,
            "enter_short"
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """Idim executor owns exits. Columns required by interface only."""
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        return dataframe