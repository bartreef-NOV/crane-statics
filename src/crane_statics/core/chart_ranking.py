"""Closed-form ranking and ring helpers for magnitude-limit envelopes (pure, numpy only).

``chart_envelope._magnitude_capacity`` ranks every candidate worst case with these vectorised
forms of ``compute_allowable_load`` and evaluates only the front-runners exactly."""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

from ..calculation.capacity import QUADRATIC_SOLVER_TOLERANCE

# Magnitude limits: component -> quantities as (key, fallback key), read the way
# compute_allowable_load reads them. ``resultant`` applies to any reaction entity, the
# others to the platform base only.
_MAGNITUDE_QUANTITIES: dict[str, tuple[tuple[str, Optional[str]], ...]] = {
    "resultant": (("Fx", None), ("Fz", None)),
    "fradial": (("Fx", None), ("Fy", None)),
    "mradial": (("Mx", None), ("My", "M")),
    "max_bearing_line_load": (("Fz", None), ("Mx", None), ("My", "M")),
    "min_bearing_line_load": (("Fz", None), ("Mx", None), ("My", "M")),
}
_BEARING_COMPONENTS = frozenset({"max_bearing_line_load", "min_bearing_line_load"})
# Bearing limits on the uplift (the negated minimum line load) rather than the maximum.
_UPLIFT_COMPONENTS = frozenset({"min_bearing_line_load"})
# Sides of the polygon circumscribing the slew ellipse (see _magnitude_capacity). Its
# vertices overshoot the ellipse by 1/cos(pi/N) - 1 (3.8e-5 of the slew part at N = 360).
_SLEW_POLYGON_SIDES = 360
# Coarse slew ring used to drop sign cases that cannot hold a magnitude limit's minimum.
_COARSE_SIDES = 36
# Relative floor of the ranking-error allowance used to prune and to stop evaluating.
_RANK_ERROR_FLOOR = 1e-6
# Fewest magnitude-limit candidates evaluated through compute_allowable_load.
_EXACT_CANDIDATES = 20


def _read_component(comps: dict[str, float], key: str, fallback: Optional[str]) -> float:
    if fallback is None:
        return float(comps.get(key, 0.0))
    return float(comps.get(key, comps.get(fallback, 0.0)))


def _radial_ranking(limit: float, u: np.ndarray, v: np.ndarray, su: float, sv: float) -> np.ndarray:
    """``solve_radial_capacity_kN`` over arrays (ranking only)."""
    tol = QUADRATIC_SOLVER_TOLERANCE
    a = su * su + sv * sv
    b = 2.0 * (u * su + v * sv)
    c = u * u + v * v - limit * limit
    if a <= tol:
        safe_b = np.where(np.abs(b) <= tol, 1.0, b)
        h = np.where((np.abs(b) > tol) & (b > 0.0), np.maximum(0.0, -c / safe_b), np.inf)
    else:
        disc = b * b - 4.0 * a * c
        root = np.sqrt(np.maximum(0.0, disc))
        lower = (-b - root) / (2.0 * a)
        upper = (-b + root) / (2.0 * a)
        h = np.where(upper <= 0.0, 0.0, np.where(lower <= 0.0, upper, 0.0))
        h = np.where(disc < -tol, 0.0, h)
    return np.asarray(np.where(c > tol, 0.0, h))


def _bearing_ranking(
    limit: float,
    diameter: float,
    fz: np.ndarray,
    mx: np.ndarray,
    my: np.ndarray,
    sfz: float,
    smx: float,
    smy: float,
    *,
    uplift: bool = False,
) -> np.ndarray:
    """Largest hook load with bearing line load <= limit, in closed form (ranking only).

    With ``uplift`` the limit is on ``-(k1*Fz - k2*|M|)``, the negated minimum line load:
    the same convex problem with ``k1`` negated.

    The demand ``k1*Fz(H) + k2*|M(H)|`` is convex in H, so from a feasible start the
    capacity is the single crossing of ``|m0 + sm*H| = rho0 - sigma*H`` with
    ``rho0 = (L - k1*Fz0)/k2`` and ``sigma = k1*sFz/k2``: a root of the squared quadratic
    with ``rho0 - sigma*H >= 0``. The smallest such root is taken (it can only rank a
    candidate earlier); an infeasible start ranks 0.
    """
    k1 = 1.0 / (math.pi * diameter)
    k2 = 4.0 / (math.pi * diameter * diameter)
    if uplift:
        k1 = -k1
    rho0 = (limit - k1 * fz) / k2
    sigma = k1 * sfz / k2
    a = smx * smx + smy * smy - sigma * sigma
    b = 2.0 * (mx * smx + my * smy + rho0 * sigma)
    c = mx * mx + my * my - rho0 * rho0
    slack = 1e-9 * (np.abs(rho0) + 1.0)
    roots: list[np.ndarray] = []
    if abs(a) > 1e-12 * (smx * smx + smy * smy + sigma * sigma):
        disc = b * b - 4.0 * a * c
        root = np.sqrt(np.maximum(0.0, disc))
        for r in ((-b - root) / (2.0 * a), (-b + root) / (2.0 * a)):
            roots.append(np.where(disc >= 0.0, r, np.nan))
    else:
        safe_b = np.where(b == 0.0, 1.0, b)
        roots.append(np.where(b == 0.0, np.nan, -c / safe_b))
    h = np.full_like(fz, np.inf)
    for r in roots:
        valid = (r >= 0.0) & (rho0 - sigma * r >= -slack)
        h = np.where(valid & (r < h), r, h)
    demand0 = k1 * fz + k2 * np.hypot(mx, my)
    return np.asarray(np.where(demand0 > limit, 0.0, h))


def _rank_margin(rank_error: float, capacity_kN: float) -> float:
    """Allowance for ranking error: the largest error seen, at least ``_RANK_ERROR_FLOOR``.

    The floor (relative to the capacity, plus 1e-9 kN) covers proxy errors on vertices that
    were never evaluated; the ranking closed forms match compute_allowable_load to rounding
    (tests/test_chart_envelope.py checks rel 1e-6).
    """
    return max(rank_error, _RANK_ERROR_FLOOR * abs(capacity_kN) + 1e-9)


def _ring(sides: int, *, outer: bool) -> tuple[np.ndarray, np.ndarray]:
    """(cos, sin) of ``sides`` slews: points on the ellipse, or the circumscribing N-gon."""
    if not outer:
        phi = np.arange(sides) * (2.0 * math.pi / sides)
        return np.cos(phi), np.sin(phi)
    phi = (np.arange(sides) + 0.5) * (2.0 * math.pi / sides)
    stretch = 1.0 / math.cos(math.pi / sides)
    return stretch * np.cos(phi), stretch * np.sin(phi)


def _ring_baselines(
    b0: np.ndarray,
    p: np.ndarray,
    q: np.ndarray,
    corner_values: np.ndarray,
    cos_v: np.ndarray,
    sin_v: np.ndarray,
) -> np.ndarray:
    """Baselines (S, N, C, K): sign case x slew ring point x wind corner x quantity."""
    return np.asarray(
        b0[:, None, None, :]
        + cos_v[None, :, None, None] * p[:, None, None, :]
        + sin_v[None, :, None, None] * q[:, None, None, :]
        + corner_values[None, None, :, :]
    )
