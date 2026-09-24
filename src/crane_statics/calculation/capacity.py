"""Reusable hook-load capacity inversion primitives."""

from __future__ import annotations

import math
from collections.abc import Callable

# ─────────────────────────────────────────────────────────────────────────────
# Numeric Tolerance Constants
# ─────────────────────────────────────────────────────────────────────────────

QUADRATIC_SOLVER_TOLERANCE = 1e-9  # Tolerance for quadratic discriminant and coefficient tests
BINARY_SEARCH_ITERATIONS = 80  # Number of iterations for capacity binary search
MAX_HOOK_LOAD_SEARCH_kN = 1e9  # Maximum hook load to search (fallback upper bound)


def solve_radial_capacity_kN(
    limit_kN: float,
    base_u: float,
    base_v: float,
    sensitivity_u: float,
    sensitivity_v: float,
    tolerance: float = QUADRATIC_SOLVER_TOLERANCE,
) -> float:
    """Solve sqrt((u0 + su*H)^2 + (v0 + sv*H)^2) <= limit for H >= 0."""
    limit = float(limit_kN)
    quadratic_a = sensitivity_u * sensitivity_u + sensitivity_v * sensitivity_v
    quadratic_b = 2.0 * (base_u * sensitivity_u + base_v * sensitivity_v)
    quadratic_c = base_u * base_u + base_v * base_v - limit * limit

    if quadratic_c > tolerance:
        return 0.0

    if abs(quadratic_a) <= tolerance:
        if abs(quadratic_b) <= tolerance:
            return float("inf")
        candidate = -quadratic_c / quadratic_b
        if quadratic_b > 0.0:
            return max(0.0, candidate)
        return float("inf")

    discriminant = quadratic_b * quadratic_b - 4.0 * quadratic_a * quadratic_c
    if discriminant < -tolerance:
        return 0.0
    root = math.sqrt(max(0.0, discriminant))
    lower = (-quadratic_b - root) / (2.0 * quadratic_a)
    upper = (-quadratic_b + root) / (2.0 * quadratic_a)
    if upper < lower:
        lower, upper = upper, lower
    if upper <= 0.0:
        return 0.0
    if lower <= 0.0 <= upper:
        return upper
    return 0.0


def solve_capacity_limit_kN(
    limit: float,
    demand_at_hook_load: Callable[[float], float],
    tolerance: float = QUADRATIC_SOLVER_TOLERANCE,
    max_hook_load_kN: float = MAX_HOOK_LOAD_SEARCH_kN,
    iterations: int = BINARY_SEARCH_ITERATIONS,
) -> float:
    """Find the largest hook load whose monotonic demand stays within a limit."""
    limit_value = float(limit)

    def gap(hook_load_kN: float) -> float:
        return float(demand_at_hook_load(hook_load_kN)) - limit_value

    if gap(0.0) > tolerance:
        return 0.0

    high = 1.0
    low_ok = 0.0
    gap_high = gap(high)
    while gap_high <= tolerance and high < max_hook_load_kN:
        low_ok = high
        high *= 2.0
        gap_high = gap(high)

    if gap_high <= tolerance:
        return float("inf")

    low = low_ok
    for _ in range(iterations):
        middle = 0.5 * (low + high)
        if gap(middle) <= 0.0:
            low = middle
        else:
            high = middle
    return max(0.0, low)
