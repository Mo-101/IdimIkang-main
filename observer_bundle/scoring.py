from __future__ import annotations

from typing import Dict, Iterable, List


def phi_normalize(values: Iterable[float]) -> List[float]:
    vals = [float(v) for v in values]
    if not vals:
        return []

    min_v = min(vals)
    shifted = [v - min_v for v in vals]
    total = sum(shifted)

    if total == 0:
        n = len(vals)
        return [1.0 / n] * n

    return [v / total for v in shifted]


def apply_q_alpha(normalized: Dict[str, float], q_alpha: Dict[str, float]) -> float:
    total = 0.0
    for key, weight in q_alpha.items():
        total += float(normalized.get(key, 0.0)) * float(weight)
    return total
