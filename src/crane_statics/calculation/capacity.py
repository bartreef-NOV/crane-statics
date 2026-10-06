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


def solve_bearing_line_load_capacity_kN(
    limit: float,
    *,
    fz0: float,
    fz_s: float,
    mx0: float,
    mx_s: float,
    my0: float,
    my_s: float,
    diameter_m: float,
    tolerance: float = QUADRATIC_SOLVER_TOLERANCE,
    max_hook_load_kN: float = MAX_HOOK_LOAD_SEARCH_kN,
) -> float:
    """Largest H >= 0 with Fz/(pi D) + 4|(Mx, My)|/(pi D^2) <= limit, all affine in H.

    The line load is convex in H, so the allowed hook loads are one interval
    starting at zero, ending where c2·|M(H)| = limit - c1·Fz(H): the root of a
    quadratic. Answers match ``solve_capacity_limit_kN`` on the same demand,
    which is the fallback whenever the closed form is ill-conditioned.
    """
    c1 = 1.0 / (math.pi * diameter_m)
    c2 = 4.0 / (math.pi * diameter_m * diameter_m)

    def line_load(hook_kN: float) -> float:
        return c1 * (fz0 + fz_s * hook_kN) + c2 * math.hypot(
            mx0 + mx_s * hook_kN, my0 + my_s * hook_kN
        )

    def bisected() -> float:
        return solve_capacity_limit_kN(
            limit, line_load, tolerance=tolerance, max_hook_load_kN=max_hook_load_kN
        )

    if line_load(0.0) - limit > tolerance:
        return 0.0
    # A convex demand whose slope never turns positive never reaches the limit.
    if c1 * fz_s + c2 * math.hypot(mx_s, my_s) <= 0.0:
        return float("inf")

    r0, r1 = limit - c1 * fz0, -c1 * fz_s
    quad_a = c2 * c2 * (mx_s * mx_s + my_s * my_s) - r1 * r1
    quad_b = 2.0 * (c2 * c2 * (mx0 * mx_s + my0 * my_s) - r0 * r1)
    quad_c = c2 * c2 * (mx0 * mx0 + my0 * my0) - r0 * r0
    scale = max(abs(quad_a), abs(quad_b), abs(quad_c), 1e-300)

    roots: list[float] = []
    if abs(quad_a) <= 1e-12 * scale:
        if abs(quad_b) > 1e-12 * scale:
            roots.append(-quad_c / quad_b)
    else:
        discriminant = quad_b * quad_b - 4.0 * quad_a * quad_c
        if discriminant < 0.0:
            return bisected()
        stable = -0.5 * (quad_b + math.copysign(math.sqrt(discriminant), quad_b))
        roots.append(stable / quad_a)
        if stable != 0.0:
            roots.append(quad_c / stable)

    def polished(hook_kN: float) -> float:
        for _ in range(3):
            mx, my = mx0 + mx_s * hook_kN, my0 + my_s * hook_kN
            moment = math.hypot(mx, my)
            slope = c1 * fz_s + (c2 * (mx * mx_s + my * my_s) / moment if moment > 0.0 else 0.0)
            if slope <= 0.0:
                break
            hook_kN -= (line_load(hook_kN) - limit) / slope
        return hook_kN

    accept = 1e-9 * max(1.0, abs(limit))
    candidates = sorted(
        polished(h)
        for h in roots
        if math.isfinite(h) and h > 0.0 and r0 + r1 * h >= -accept * max(1.0, abs(r0))
    )
    for hook_kN in candidates:
        if hook_kN > 0.0 and abs(line_load(hook_kN) - limit) <= accept:
            return float("inf") if hook_kN > max_hook_load_kN else hook_kN
    return bisected()


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
