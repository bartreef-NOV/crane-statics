"""Load-chart envelope by superposition of probe solves (pure, Qt-free).

An analysis point's baseline (rope tensions and reactions at zero hook load) is affine in
the crane-frame load channels: accel x, y, z, pitch accel, roll accel, and the squared-speed
wind components along crane X and Y. Eight probe solves per boom angle therefore let any
vessel-motion / slew / wind case be assembled arithmetically. The hook sensitivities and the
lead channels do not depend on motion or wind and are taken from the zero probe.

``envelope_capacity`` takes the worst case over every vessel-motion sign case, every slew
angle, every wind angle and both lead signs without enumerating them; see its docstring.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Callable, Optional, Sequence

import numpy as np

from ..calculation.capacity import QUADRATIC_SOLVER_TOLERANCE
from ..calculation.engine import (
    AllowableCapacity,
    AnalysisPoint,
    CraneCalculator,
    resolve_connection_component_linear_response,
)
from ..calculation.vessel_frame import CraneFrameMotion, VesselInputs, crane_frame_motion
from ..data.models import VesselMotion
from .analysis_cases import _signed_candidates
from .lead_channels import compose_lead_channel_point
from .vessel_envelope import vessel_motion_cases

# Probe order for ``ProbeSet.motion`` and ``motion_channels``.
_PROBE_KWARGS = (
    "accel_x_m_s2",
    "accel_y_m_s2",
    "accel_z_m_s2",
    "pitch_accel_rad_s2",
    "roll_accel_rad_s2",
)
_PROBE_VALUE = 1.0
_WIND_ZERO = 1e-12


@dataclass(frozen=True)
class ProbeSet:
    """Probe solves at one boom angle; ``motion``: accel x, y, z, pitch accel, roll accel.

    ``solved[j]`` is False where motion probe ``j`` was not solved (the zero probe stands
    in); ``envelope_capacity`` rejects a vessel that moves such a channel.
    """

    zero: AnalysisPoint
    motion: tuple[AnalysisPoint, AnalysisPoint, AnalysisPoint, AnalysisPoint, AnalysisPoint]
    wind_x: AnalysisPoint
    wind_y: AnalysisPoint
    solved: tuple[bool, ...] = (True,) * len(_PROBE_KWARGS)


def build_probes(
    calc: CraneCalculator,
    hoist_id: str,
    boom_angle_deg: float,
    wind_speed_m_s: float,
    overrides: Optional[dict[str, dict[str, Any]]],
    *,
    vessel: Optional[VesselMotion] = None,
) -> Optional[ProbeSet]:
    """Solve the zero, unit-motion and wind probes on a level vessel at slew 0.

    On a level vessel at slew 0 the vessel-frame inputs equal the crane-frame channels, so
    each motion probe sets one input to +1 (m/s² or rad/s²). Returns ``None`` if any probe
    fails; with zero wind speed the wind probes are the zero probe.

    The probes are zero-lead points (offlead and sidelead 0): ``envelope_capacity`` adds
    the signed leads itself. Given ``vessel``, a motion probe whose channel is exactly zero
    in every sign case and slew of those limits is not solved (the zero probe stands in);
    such a probe would only ever be superposed with a zero weight. The returned set records
    which probes were solved, so it must only be used with those limits.
    """
    needed = [True] * len(_PROBE_KWARGS)
    if vessel is not None:
        harmonics = _slew_harmonics(abs(float(calc.doc.environment.gravity_m_s2)), vessel)
        needed = _used_channels(harmonics)

    def _solve(
        wind_speed: float = 0.0, wind_angle: float = 0.0, **motion: float
    ) -> Optional[AnalysisPoint]:
        kwargs: dict[str, Any] = dict.fromkeys(_PROBE_KWARGS, 0.0)
        kwargs.update(motion)
        return calc.compute_analysis_point(
            boom_angle_deg,
            0.0,
            hoist_id,
            wind_speed_m_s=wind_speed,
            wind_angle_deg=wind_angle,
            hoist_runtime_overrides=overrides,
            offlead_deg=0.0,
            sidelead_deg=0.0,
            crane_slewing_angle_deg=0.0,
            vessel_roll_deg=0.0,
            vessel_pitch_deg=0.0,
            **kwargs,
        )

    zero = _solve()
    if zero is None:
        return None
    motion = [
        _solve(**{name: _PROBE_VALUE}) if need else zero
        for name, need in zip(_PROBE_KWARGS, needed)
    ]
    if abs(float(wind_speed_m_s)) <= _WIND_ZERO:
        wind_x: Optional[AnalysisPoint] = zero
        wind_y: Optional[AnalysisPoint] = zero
    else:
        wind_x = _solve(wind_speed=float(wind_speed_m_s), wind_angle=0.0)
        wind_y = _solve(wind_speed=float(wind_speed_m_s), wind_angle=90.0)
    m0, m1, m2, m3, m4 = motion
    if m0 is None or m1 is None or m2 is None or m3 is None or m4 is None:
        return None
    if wind_x is None or wind_y is None:
        return None
    return ProbeSet(
        zero=zero,
        motion=(m0, m1, m2, m3, m4),
        wind_x=wind_x,
        wind_y=wind_y,
        solved=tuple(needed),
    )


def _channel_vector(motion: CraneFrameMotion) -> np.ndarray:
    return np.array(
        [
            motion.accel_x_m_s2,
            motion.accel_y_m_s2,
            motion.accel_z_m_s2,
            motion.pitch_accel_rad_s2,
            motion.roll_accel_rad_s2,
        ],
        dtype=float,
    )


def motion_channels(gravity: float, inputs: VesselInputs) -> np.ndarray:
    """Crane-frame channel deltas of ``inputs`` relative to all-zero inputs, shape (5,).

    Gravity tilt is folded in: a tilted vessel shows up as crane-frame acceleration.
    """
    return np.asarray(
        _channel_vector(crane_frame_motion(gravity, inputs))
        - _channel_vector(crane_frame_motion(gravity, VesselInputs()))
    )


def superpose(
    probes: ProbeSet,
    channels: Sequence[float] | np.ndarray,
    wind_x_scale: float,
    wind_y_scale: float,
) -> AnalysisPoint:
    """Assemble one case's baseline from the probes; sensitivities stay the zero point's."""
    zero = probes.zero
    terms = [(float(c), p) for c, p in zip(channels, probes.motion)]
    terms.append((float(wind_x_scale), probes.wind_x))
    terms.append((float(wind_y_scale), probes.wind_y))

    rope_ids = set(zero.baseline_rope_tensions)
    for _, p in terms:
        rope_ids |= set(p.baseline_rope_tensions)
    ropes: dict[str, float] = {}
    for rope_id in rope_ids:
        base = float(zero.baseline_rope_tensions.get(rope_id, 0.0))
        value = base
        for scale, p in terms:
            value += scale * (float(p.baseline_rope_tensions.get(rope_id, 0.0)) - base)
        ropes[rope_id] = value

    entity_ids = set(zero.baseline_reactions)
    for _, p in terms:
        entity_ids |= set(p.baseline_reactions)
    reactions: dict[str, dict[str, float]] = {}
    for entity_id in entity_ids:
        zero_comps = zero.baseline_reactions.get(entity_id, {})
        probe_comps = [(scale, p.baseline_reactions.get(entity_id, {})) for scale, p in terms]
        component_ids = set(zero_comps)
        for _, comps in probe_comps:
            component_ids |= set(comps)
        out: dict[str, float] = {}
        for component in component_ids:
            base = float(zero_comps.get(component, 0.0))
            value = base
            for scale, comps in probe_comps:
                value += scale * (float(comps.get(component, 0.0)) - base)
            out[component] = value
        reactions[entity_id] = out

    return replace(zero, baseline_rope_tensions=ropes, baseline_reactions=reactions)


# --- worst case over vessel signs, slew, wind angle and lead signs ------------------------

# compute_analysis_point vessel keyword (VESSEL_LIMIT_INPUTS) -> VesselInputs field.
_VESSEL_INPUT_FIELDS = {
    "accel_x_m_s2": "accel_x_m_s2",
    "accel_y_m_s2": "accel_y_m_s2",
    "accel_z_m_s2": "accel_z_m_s2",
    "roll_accel_rad_s2": "roll_accel_rad_s2",
    "pitch_accel_rad_s2": "pitch_accel_rad_s2",
    "vessel_roll_deg": "roll_deg",
    "vessel_pitch_deg": "pitch_deg",
}
_PLATFORM_BASE = "platform_base"
# Magnitude limits: component -> quantities as (key, fallback key), read the way
# compute_allowable_load reads them. ``resultant`` applies to any reaction entity, the
# others to the platform base only.
_MAGNITUDE_QUANTITIES: dict[str, tuple[tuple[str, Optional[str]], ...]] = {
    "resultant": (("Fx", None), ("Fz", None)),
    "fradial": (("Fx", None), ("Fy", None)),
    "mradial": (("Mx", None), ("My", "M")),
    "max_bearing_line_load": (("Fz", None), ("Mx", None), ("My", "M")),
}
# Sides of the polygon circumscribing the slew ellipse (see _magnitude_capacity). Its
# vertices overshoot the ellipse by 1/cos(pi/N) - 1 (3.8e-5 of the slew part at N = 360).
_SLEW_POLYGON_SIDES = 360
# Coarse slew ring used to drop sign cases that cannot hold a magnitude limit's minimum.
_COARSE_SIDES = 36
# Relative floor of the ranking-error allowance used to prune and to stop evaluating.
_RANK_ERROR_FLOOR = 1e-6
# Fewest magnitude-limit candidates evaluated through compute_allowable_load.
_EXACT_CANDIDATES = 20


@dataclass(frozen=True)
class _SlewHarmonics:
    """Channel vectors of every vessel sign case as exact first harmonics of slew.

    Sign case ``s`` at slew ``phi`` has channels ``mean[s] + cos(phi) * cos_part[s] +
    sin(phi) * sin_part[s]`` (shape (S, 5) each): slew only rotates the vessel-frame
    horizontal load and angular accelerations into the crane frame.
    """

    mean: np.ndarray
    cos_part: np.ndarray
    sin_part: np.ndarray

    def channels(self, case: int, cos_phi: float, sin_phi: float) -> np.ndarray:
        return np.asarray(
            self.mean[case] + cos_phi * self.cos_part[case] + sin_phi * self.sin_part[case]
        )


def _slew_harmonics(gravity: float, vessel: VesselMotion) -> _SlewHarmonics:
    means, cos_parts, sin_parts = [], [], []
    for case in vessel_motion_cases(vessel):
        fields = {_VESSEL_INPUT_FIELDS[key]: float(value) for key, value in case.items()}
        c0, c90, c180, c270 = (
            motion_channels(gravity, VesselInputs(slew_deg=slew, **fields))
            for slew in (0.0, 90.0, 180.0, 270.0)
        )
        means.append(0.5 * (c0 + c180))
        cos_parts.append(0.5 * (c0 - c180))
        sin_parts.append(0.5 * (c90 - c270))
    return _SlewHarmonics(np.array(means), np.array(cos_parts), np.array(sin_parts))


def _used_channels(harmonics: _SlewHarmonics) -> list[bool]:
    """Whether each motion channel is nonzero in some sign case at some slew."""
    return [
        bool(
            np.any(harmonics.mean[:, j])
            or np.any(harmonics.cos_part[:, j])
            or np.any(harmonics.sin_part[:, j])
        )
        for j in range(len(_PROBE_KWARGS))
    ]


def lead_points(probes: ProbeSet, offlead_deg: float, sidelead_deg: float) -> list[AnalysisPoint]:
    """The zero probe composed with every lead sign case (one point for zero leads)."""
    return [
        compose_lead_channel_point(probes.zero, offlead, sidelead)
        for offlead in _signed_candidates(offlead_deg)
        for sidelead in _signed_candidates(sidelead_deg)
    ]


@dataclass(frozen=True)
class _UnitBasis:
    """Superposed points for zero channels, each unit motion channel and each full wind axis.

    Built with ``superpose`` itself, so a quantity read from these points has exactly the
    affine coefficients of the points ``superpose`` assembles for any case.
    """

    zero: AnalysisPoint
    motion: tuple[AnalysisPoint, ...]
    wind_x: AnalysisPoint
    wind_y: AnalysisPoint


def _unit_basis(probes: ProbeSet) -> _UnitBasis:
    count = len(_PROBE_KWARGS)
    zeros = [0.0] * count
    motion = tuple(
        superpose(probes, [1.0 if k == j else 0.0 for k in range(count)], 0.0, 0.0)
        for j in range(count)
    )
    return _UnitBasis(
        zero=superpose(probes, zeros, 0.0, 0.0),
        motion=motion,
        wind_x=superpose(probes, zeros, 1.0, 0.0),
        wind_y=superpose(probes, zeros, 0.0, 1.0),
    )


@dataclass(frozen=True)
class _Affine:
    """Baseline of one quantity: ``zero + motion . channels + wind_x * u + wind_y * v``."""

    zero: float
    motion: np.ndarray
    wind_x: float
    wind_y: float


_Reader = Callable[[AnalysisPoint], Optional[float]]


def _affine(basis: _UnitBasis, read: _Reader) -> Optional[_Affine]:
    zero = read(basis.zero)
    if zero is None:
        return None
    deltas: list[float] = []
    for pt in (*basis.motion, basis.wind_x, basis.wind_y):
        value = read(pt)
        if value is None:
            return None
        deltas.append(float(value) - float(zero))
    return _Affine(float(zero), np.array(deltas[:-2]), deltas[-2], deltas[-1])


def _case_point(
    probes: ProbeSet,
    lead_point: AnalysisPoint,
    channels: Sequence[float] | np.ndarray,
    wind_x_scale: float,
    wind_y_scale: float,
) -> AnalysisPoint:
    """One case's baseline with the lead case's sensitivities."""
    case = superpose(probes, channels, wind_x_scale, wind_y_scale)
    return replace(
        lead_point,
        baseline_rope_tensions=case.baseline_rope_tensions,
        baseline_reactions=case.baseline_reactions,
    )


def _is_magnitude(lead_point: AnalysisPoint, entity_id: str, component: str) -> bool:
    """Whether compute_allowable_load treats this limit as a magnitude limit."""
    if entity_id not in lead_point.sensitivity_reactions:
        return False
    if component == "resultant":
        return True
    return component in _MAGNITUDE_QUANTITIES and entity_id == _PLATFORM_BASE


def _linear_reader(
    calc: CraneCalculator, lead_point: AnalysisPoint, limit_key: str, component: str
) -> Optional[_Reader]:
    """Baseline reader for a linear limit, following compute_allowable_load's branches.

    ``None`` (or a reader returning ``None``) where compute_allowable_load skips the limit.
    The branch depends only on sensitivity keys and local axes, the same for every case.
    """
    entity_id, rope_channel = calc.resolve_limit_target(limit_key, component)
    if entity_id in lead_point.sensitivity_reactions:

        def _reaction(pt: AnalysisPoint) -> Optional[float]:
            linear = resolve_connection_component_linear_response(pt, entity_id, component)
            return None if linear is None else float(linear[0])

        return _reaction
    if rope_channel in lead_point.sensitivity_rope_tensions:
        return lambda pt: float(pt.baseline_rope_tensions.get(rope_channel, 0.0))
    return None


@dataclass(frozen=True)
class _LimitContext:
    calc: CraneCalculator
    probes: ProbeSet
    basis: _UnitBasis
    harmonics: _SlewHarmonics
    hook_daf: float
    hook_mass_t: float

    def capacity(self, point: AnalysisPoint, single_limit: dict[str, dict]) -> AllowableCapacity:
        return self.calc.compute_allowable_load(
            point, single_limit, hook_daf=self.hook_daf, hook_mass_t=self.hook_mass_t
        )


def _lower(
    best: Optional[AllowableCapacity], cap: Optional[AllowableCapacity]
) -> Optional[AllowableCapacity]:
    if cap is None:
        return best
    if best is None or cap.max_allowable_load_kN < best.max_allowable_load_kN:
        return cap
    return best


def _linear_capacity(
    ctx: _LimitContext,
    lead_point: AnalysisPoint,
    limit_key: str,
    component: str,
    single_limit: dict[str, dict],
) -> Optional[AllowableCapacity]:
    """Capacity at the cases of largest and smallest baseline of a linear limit.

    Per sign case the baseline over slew is ``B0 + P cos(phi) + Q sin(phi)``, extreme at
    ``B0 +/- hypot(P, Q)`` with ``phi = atan2(Q, P)`` (+180 deg for the minimum). Over wind
    angle the term ``a*u + b*v`` has ``|u| + |v| = 1`` and is extreme at an axis wind,
    ``+/- max(|a|, |b|)``. The capacity compute_allowable_load gives a linear limit never
    increases with the baseline (0 above the limit, ``(L - B)/s`` or unlimited below), so
    the worst case is the largest baseline; the smallest is evaluated too and the lower
    capacity kept. Both are real cases.
    """
    reader = _linear_reader(ctx.calc, lead_point, limit_key, component)
    if reader is None:
        return None
    quantity = _affine(ctx.basis, reader)
    if quantity is None:
        return None
    harmonics = ctx.harmonics
    b0 = quantity.zero + harmonics.mean @ quantity.motion
    p = harmonics.cos_part @ quantity.motion
    q = harmonics.sin_part @ quantity.motion
    amplitude = np.hypot(p, q)
    x_dominant = abs(quantity.wind_x) >= abs(quantity.wind_y)
    best: Optional[AllowableCapacity] = None
    for sign in (1.0, -1.0):
        case = int(np.argmax(sign * b0 + amplitude))
        r = float(amplitude[case])
        cos_phi, sin_phi = (float(p[case]) / r, float(q[case]) / r) if r > 0.0 else (1.0, 0.0)
        channels = harmonics.channels(case, sign * cos_phi, sign * sin_phi)
        if x_dominant:
            wind = (sign * math.copysign(1.0, quantity.wind_x), 0.0)
        else:
            wind = (0.0, sign * math.copysign(1.0, quantity.wind_y))
        point = _case_point(ctx.probes, lead_point, channels, *wind)
        best = _lower(best, ctx.capacity(point, single_limit))
    return best


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
) -> np.ndarray:
    """Largest hook load with bearing line load <= limit, in closed form (ranking only).

    The demand ``k1*Fz(H) + k2*|M(H)|`` is convex in H, so from a feasible start the
    capacity is the single crossing of ``|m0 + sm*H| = rho0 - sigma*H`` with
    ``rho0 = (L - k1*Fz0)/k2`` and ``sigma = k1*sFz/k2``: a root of the squared quadratic
    with ``rho0 - sigma*H >= 0``. The smallest such root is taken (it can only rank a
    candidate earlier); an infeasible start ranks 0.
    """
    k1 = 1.0 / (math.pi * diameter)
    k2 = 4.0 / (math.pi * diameter * diameter)
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


def _magnitude_capacity(
    ctx: _LimitContext,
    lead_points: Sequence[AnalysisPoint],
    entity_id: str,
    component: str,
    limit: float,
    single_limit: dict[str, dict],
) -> AllowableCapacity:
    """Lower bound of a magnitude limit's capacity over all slews, wind angles and leads.

    For a fixed sensitivity the set of (baseline, hook load) meeting the limit is convex
    (norm of an affine map plus a linear term), so the capacity is concave in the baseline
    where the baseline alone is feasible and zero elsewhere; its minimum over a polytope is
    at a vertex. Per sign case the reachable baselines are the slew ellipse plus the wind
    term ``a*u + b*v`` over ``|u| + |v| = 1`` (a diamond with the four axis winds as
    corners). Both lie inside the Minkowski sum of an N-gon circumscribing the ellipse and
    the diamond, whose vertices are N-gon vertices plus an axis wind. The minimum over
    those vertices is therefore never above the true minimum over all slews and wind
    angles, and below it only through the 1/cos(pi/N) overshoot.

    Stage 1 bounds each sign case with a coarse N-gon and evaluates the best real case on
    the coarse ring exactly; sign cases whose bound is above that real capacity cannot hold
    the minimum and are dropped. Stage 2 ranks the fine N-gon vertices of the rest with
    vectorised closed forms of the compute_allowable_load solvers, then evaluates them
    through compute_allowable_load in rank order until no unevaluated vertex can be lower
    (its rank minus the largest rank error seen is not below the best exact capacity).
    """
    quantities = _MAGNITUDE_QUANTITIES[component]
    affines: list[_Affine] = []
    for key, fallback in quantities:

        def _read(pt: AnalysisPoint, key: str = key, fallback: Optional[str] = fallback) -> float:
            return _read_component(pt.baseline_reactions.get(entity_id, {}), key, fallback)

        affine = _affine(ctx.basis, _read)
        assert affine is not None  # _read always returns a value
        affines.append(affine)

    diameter = 1.0
    if component == "max_bearing_line_load":
        diameter = float(getattr(ctx.calc.doc.support_widths, "slewing_bearing_diameter_m", 1.0))
        if diameter <= 0.0:
            # compute_allowable_load rejects this diameter; let it raise.
            return ctx.capacity(lead_points[0], single_limit)

    def _rank(sens: list[float], values: np.ndarray) -> np.ndarray:
        if component == "max_bearing_line_load":
            return _bearing_ranking(
                limit,
                diameter,
                values[..., 0],
                values[..., 1],
                values[..., 2],
                sens[0],
                sens[1],
                sens[2],
            )
        return _radial_ranking(limit, values[..., 0], values[..., 1], sens[0], sens[1])

    harmonics = ctx.harmonics
    d = np.stack([a.motion for a in affines], axis=1)  # (5, K)
    b0 = np.array([a.zero for a in affines]) + harmonics.mean @ d  # (S, K)
    p = harmonics.cos_part @ d
    q = harmonics.sin_part @ d
    wind_a = np.array([a.wind_x for a in affines])
    wind_b = np.array([a.wind_y for a in affines])
    corners = [(0.0, 0.0)]
    if np.any(wind_a) or np.any(wind_b):
        corners = [(1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0)]
    corner_values = np.array([u * wind_a + v * wind_b for u, v in corners])  # (C, K)
    sens_by_lead = [
        [
            _read_component(lead.sensitivity_reactions.get(entity_id, {}), key, fallback)
            for key, fallback in quantities
        ]
        for lead in lead_points
    ]

    best: Optional[AllowableCapacity] = None
    rank_error = 0.0

    def _evaluate(
        lead: int, case: int, cos_v: float, sin_v: float, corner: int, rank: float
    ) -> None:
        nonlocal best, rank_error
        channels = harmonics.channels(case, cos_v, sin_v)
        point = _case_point(ctx.probes, lead_points[lead], channels, *corners[corner])
        cap = ctx.capacity(point, single_limit)
        exact = cap.max_allowable_load_kN
        if math.isinf(rank) and not math.isinf(exact):
            # The ranking missed a finite capacity: no pruning, every fine vertex is evaluated.
            rank_error = math.inf
        elif not math.isinf(exact):
            rank_error = max(rank_error, abs(exact - rank))
        best = _lower(best, cap)

    # Stage 1: a real capacity from the coarse ring and a lower bound per sign case.
    ring_cos, ring_sin = _ring(_COARSE_SIDES, outer=False)
    coarse_cos, coarse_sin = _ring(_COARSE_SIDES, outer=True)
    on_ring = _ring_baselines(b0, p, q, corner_values, ring_cos, ring_sin)
    coarse = _ring_baselines(b0, p, q, corner_values, coarse_cos, coarse_sin)
    bounds = []
    for lead, sens in enumerate(sens_by_lead):
        ranks = _rank(sens, on_ring)
        case, side, corner = (int(i) for i in np.unravel_index(int(np.argmin(ranks)), ranks.shape))
        _evaluate(
            lead,
            case,
            float(ring_cos[side]),
            float(ring_sin[side]),
            corner,
            float(ranks[case, side, corner]),
        )
        bounds.append(_rank(sens, coarse).min(axis=(1, 2)))
    assert best is not None
    # A sign case is dropped only if its bound, less the rank error allowance, is above a
    # capacity that a real case reaches.
    cutoff = best.max_allowable_load_kN + _rank_margin(rank_error, best.max_allowable_load_kN)

    # Stage 2: fine N-gon vertices of the sign cases that can still hold the minimum.
    fine_cos, fine_sin = _ring(_SLEW_POLYGON_SIDES, outer=True)
    ranks_parts, index_parts = [], []
    for lead, sens in enumerate(sens_by_lead):
        keep = np.nonzero(bounds[lead] <= cutoff)[0]
        if keep.size == 0:
            continue
        ranks = _rank(
            sens, _ring_baselines(b0[keep], p[keep], q[keep], corner_values, fine_cos, fine_sin)
        )
        case_i, side_i, corner_i = np.unravel_index(np.arange(ranks.size), ranks.shape)
        ranks_parts.append(ranks.ravel())
        index_parts.append(
            np.stack([np.full(ranks.size, lead), keep[case_i], side_i, corner_i], axis=1)
        )
    if not ranks_parts:
        return best
    all_ranks = np.concatenate(ranks_parts)
    all_index = np.concatenate(index_parts)
    order = np.argsort(all_ranks, kind="stable")
    for position, flat in enumerate(order):
        rank = float(all_ranks[flat])
        current = best.max_allowable_load_kN
        if position >= _EXACT_CANDIDATES and not rank - _rank_margin(rank_error, current) < current:
            break
        lead, case, side, corner = (int(i) for i in all_index[flat])
        _evaluate(lead, case, float(fine_cos[side]), float(fine_sin[side]), corner, rank)
    return best


def envelope_capacity(
    calc: CraneCalculator,
    probes: ProbeSet,
    limits: dict[str, dict],
    *,
    vessel: VesselMotion,
    offlead_deg: float,
    sidelead_deg: float,
    hook_daf: float,
    hook_mass_t: float,
) -> AllowableCapacity:
    """Lowest allowable capacity over every vessel sign case, slew, wind angle and lead sign.

    The baseline is affine in the crane-frame channels and the per-axis wind scales, and
    the channels are exact first harmonics of slew, so no case is enumerated:

    - linear limits use the closed-form extremes of their baseline (``_linear_capacity``);
    - magnitude limits (``resultant``, ``fradial``, ``mradial``, ``max_bearing_line_load``)
      use vertices of a polytope that contains every reachable baseline, so the result is
      never above the true minimum (``_magnitude_capacity``).

    Sensitivities do not depend on motion, slew or wind; each lead sign case composes them
    once from ``probes.zero``. Every capacity comes from ``compute_allowable_load`` on an
    assembled point, one limit at a time; the lowest is returned with its
    ``governing_limit_id``.
    """
    gravity = abs(float(calc.doc.environment.gravity_m_s2))
    harmonics = _slew_harmonics(gravity, vessel)
    missing = [
        name
        for name, used, solved in zip(_PROBE_KWARGS, _used_channels(harmonics), probes.solved)
        if used and not solved
    ]
    if missing:
        raise ValueError(
            "probes were built for other vessel-motion limits; unsolved channels: "
            + ", ".join(missing)
        )
    ctx = _LimitContext(
        calc=calc,
        probes=probes,
        basis=_unit_basis(probes),
        harmonics=harmonics,
        hook_daf=float(hook_daf),
        hook_mass_t=float(hook_mass_t),
    )
    leads = lead_points(probes, offlead_deg, sidelead_deg)
    best: Optional[AllowableCapacity] = None
    for limit_key, components in limits.items():
        for component, limit_value in components.items():
            if not limit_value:
                continue
            single_limit = {limit_key: {component: limit_value}}
            entity_id, _ = calc.resolve_limit_target(limit_key, component)
            # Which branch compute_allowable_load takes depends on sensitivity keys only.
            magnitude = [lead for lead in leads if _is_magnitude(lead, entity_id, component)]
            if magnitude:
                best = _lower(
                    best,
                    _magnitude_capacity(
                        ctx, magnitude, entity_id, component, float(limit_value), single_limit
                    ),
                )
            for lead in leads:
                if not _is_magnitude(lead, entity_id, component):
                    best = _lower(
                        best, _linear_capacity(ctx, lead, limit_key, component, single_limit)
                    )
    if best is None:
        # No limit applies: compute_allowable_load reports the unlimited capacity.
        best = ctx.capacity(probes.zero, limits)
    # The worst case is over all wind angles, not one direction; the field would otherwise
    # carry the zero probe's direction.
    best.governing_wind_direction = None
    return best
