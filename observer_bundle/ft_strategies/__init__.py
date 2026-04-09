"""
ft_strategies - FreqTrade strategy implementations for Idim Ikang

This package contains FreqTrade-compatible strategies that can be loaded
by the ft_bridge.py adapter. Each strategy implements the IStrategy interface
but is designed to work with Idim's sovereign scoring system.

Strategy Design Principles:
- Implement IStrategy interface for FreqTrade compatibility
- Focus on signal generation (no execution logic)
- Work with Idim's indicator calculations
- Return clean 0/1/-1 signals in enter_long/enter_short columns
"""

from .IdimSqueeze import IdimSqueeze
from .IdimTrendFollow import IdimTrendFollow
from .IdimMeanReversion import IdimMeanReversion

__all__ = ['IdimSqueeze', 'IdimTrendFollow', 'IdimMeanReversion']
