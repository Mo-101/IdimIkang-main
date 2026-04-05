#!/usr/bin/env python3
"""
Wolfram Five-Cell Filter — Required Proof-of-Correctness Tests
"""

def passes_wolfram_five_cell_filter(regime: str, score: float) -> bool:
    """Wolfram exact five-cell filter. No pair-specific interpretation."""
    score_bucket = int(round(score))
    allowed = {
        ("STRONG_DOWNTREND", 55),
        ("STRONG_UPTREND", 60),
        ("DOWNTREND", 60),
        ("UPTREND", 45),
        ("RANGING", 65),
    }
    return (regime, score_bucket) in allowed


# === PASS tests ===
assert passes_wolfram_five_cell_filter("STRONG_DOWNTREND", 55.0) is True
assert passes_wolfram_five_cell_filter("STRONG_UPTREND", 60.0) is True
assert passes_wolfram_five_cell_filter("DOWNTREND", 60.0) is True
assert passes_wolfram_five_cell_filter("UPTREND", 45.0) is True
assert passes_wolfram_five_cell_filter("RANGING", 65.0) is True

# === FAIL tests ===
assert passes_wolfram_five_cell_filter("STRONG_DOWNTREND", 60.0) is False
assert passes_wolfram_five_cell_filter("STRONG_UPTREND", 55.0) is False
assert passes_wolfram_five_cell_filter("DOWNTREND", 55.0) is False
assert passes_wolfram_five_cell_filter("UPTREND", 60.0) is False
assert passes_wolfram_five_cell_filter("RANGING", 45.0) is False

# === Edge: float rounding ===
assert passes_wolfram_five_cell_filter("UPTREND", 44.6) is True   # rounds to 45
assert passes_wolfram_five_cell_filter("UPTREND", 45.4) is True   # rounds to 45
assert passes_wolfram_five_cell_filter("UPTREND", 44.4) is False  # rounds to 44
assert passes_wolfram_five_cell_filter("UPTREND", 45.5) is False  # rounds to 46

print("✅ All 14 Wolfram Five-Cell Filter tests passed.")
