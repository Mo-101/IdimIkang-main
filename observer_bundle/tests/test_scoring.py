import math
import os
import sys

# Ensure modules are importable from observer_bundle/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from scoring import apply_q_alpha, phi_normalize


def approx_equal(a, b, tol=1e-6):
    return abs(a - b) <= tol


def test_q_alpha_sum():
    total = sum(config.Q_ALPHA.values())
    assert approx_equal(total, 1.0), f"Q_ALPHA must sum to 1.0, got {total}"


def test_phi_normalize_basic():
    values = [10.0, 20.0, 5.0, 0.0]
    normalized = phi_normalize(values)

    assert all(0.0 <= v <= 1.0 for v in normalized)
    assert normalized[1] > normalized[0] > normalized[2] > normalized[3]


def test_phi_normalize_edge_cases():
    values = [0.0, 0.0, 0.0]
    normalized = phi_normalize(values)
    assert all(approx_equal(v, 1.0 / len(values)) for v in normalized)

    values = [1e9, 1.0, 0.5]
    normalized = phi_normalize(values)
    assert not any(math.isnan(v) or math.isinf(v) for v in normalized)


def test_apply_q_alpha_weights():
    normalized = {
        "vol_ratio": 0.5,
        "inv_stop_pct": 0.5,
        "inv_rank": 0.0,
        "vwap_prox": 0.0,
        "momentum": 0.0,
        "oi_ratio": 0.0,
    }
    score = apply_q_alpha(normalized, config.Q_ALPHA)
    expected = 0.5 * (config.Q_ALPHA["vol_ratio"] + config.Q_ALPHA["inv_stop_pct"])
    assert approx_equal(score, expected)
