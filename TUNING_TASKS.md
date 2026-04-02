# Idim Ikang - Phase 2 Tuning Tasks

## Step 1: Baseline Reproduction

- Replace phase2_runner.py with phase2_validation.py (canonical script)
- Run against Oct-Dec 2025 data
- Confirm PF lands near 1.20
- Verify mathematical integrity

## Step 2: Tuning Tasks (apply one at a time)

### Task 1: Score Threshold Optimization

- Raise MIN_SIGNAL_SCORE incrementally from 45
- Target: 2-5 signals/day (currently ~2.72/day)
- Test values: 50, 55, 60
- After each change: rerun and report PF, WR, signals/day

### Task 2: BLOCK_STRONG_UPTREND Enforcement

- Verify regime blocking is properly enforced in scoring.py
- Current: Pre-scoring veto for STRONG_UPTREND
- Test: Remove blocking temporarily to measure impact
- After change: rerun and report regime breakdown

### Task 3: EMA Veto vs Cap Impact

- Current: EMA misalignment = hard veto (score = 0)
- Historical: EMA misalignment = score cap (max 60)
- Test both approaches:
  - Veto (current): score_long_signal returns 0.0
  - Cap: min(score, 60) with "score_cap" reason
- After each: rerun and compare signal count, PF, WR

## Execution Order

1. Baseline reproduction (must hit PF ≈ 1.20)
2. Task 1: Score threshold tuning
3. Task 2: Regime blocking verification  
4. Task 3: EMA enforcement comparison

## Reporting Requirements

After each change, provide:

- Aggregate PF, WR, signals/day
- Per-pair breakdown (BTC, ETH, SOL)
- Regime analysis (DOWNTREND, UPTREND, STRONG_UPTREND)
- Mathematical verification (expected vs reported PF)
- Recommendation: proceed/adjust/revert

## Success Criteria

- Final PF ≥ 1.20
- Signals/day: 2-5 range
- Determinism: PASS
- Mathematical verification: all matches true
