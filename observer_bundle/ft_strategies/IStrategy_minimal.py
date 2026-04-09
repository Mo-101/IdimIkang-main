"""
IStrategy_minimal.py
====================
Minimal IStrategy base for Idim-FreqTrade bridge.

Only signal generation methods are abstract.
All execution methods are no-ops — Idim's sovereign executor owns execution.
Subclasses implement only: populate_indicators, populate_entry_trend, populate_exit_trend.

Author: The Flame Architect | MoStar Industries
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional
import pandas as pd


class IStrategy(ABC):

    INTERFACE_VERSION: int = 3
    timeframe: str = "15m"

    # ── Abstract signal methods ───────────────────────────────────────────────

    @abstractmethod
    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """Add indicator columns to dataframe. Idim's core indicators already present."""

    @abstractmethod
    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """Set enter_long=1 / enter_short=1 columns."""

    @abstractmethod
    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """Set exit_long=1 / exit_short=1 columns. Idim executor owns actual exits."""

    # ── Execution no-ops — Idim sovereign executor handles all of these ───────

    def custom_stake_amount(self, **kwargs) -> float:
        return kwargs.get("proposed_stake", 0.0)

    def leverage(self, **kwargs) -> float:
        return 1.0

    def confirm_trade_entry(self, **kwargs) -> bool:
        return True

    def custom_stoploss(self, **kwargs) -> float:
        return -0.02

    def custom_exit(self, **kwargs) -> Optional[str]:
        return None

    def check_entry_timeout(self, **kwargs) -> bool:
        return False

    def check_exit_timeout(self, **kwargs) -> bool:
        return False

    def fill_exit_signals(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        return dataframe

    def informative_pairs(self):
        return []