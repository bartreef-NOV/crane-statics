"""Load-chart envelope by superposition of probe solves (pure, Qt-free).

An analysis point's baseline (rope tensions and reactions at zero hook load) is affine in
the crane-frame load channels: accel x, y, z, pitch accel, roll accel, and the squared-speed
wind components along crane X and Y. Eight probe solves per boom angle therefore let any
vessel-motion / slew / wind case be assembled arithmetically. The hook sensitivities and the
lead channels do not depend on motion or wind and are taken from the zero probe.

``envelope_capacity`` takes the worst case over every vessel-motion sign case, every slew
angle, every wind angle and both lead signs without enumerating them; see its docstring.
``envelope_capacity_case`` also returns that case (``EnvelopeCase``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Any, Callable, Optional, Sequence

import numpy as np

from ..calculation.dynamic_factor import DynamicFactor, DynamicFactorLike, as_dynamic_factor
from ..calculation.engine import (
    AllowableCapacity,
    AnalysisPoint,
    CraneCalculator,
    resolve_connection_component_linear_response,
)
from ..calculation.vessel_frame import CraneFrameMotion, VesselInputs, crane_frame_motion
from ..data.models import VesselMotion
from .analysis_cases import _signed_candidates
from .chart_ranking import (
    _BEARING_COMPONENTS,
    _COARSE_SIDES,
    _EXACT_CANDIDATES,
    _MAGNITUDE_QUANTITIES,
    _SLEW_POLYGON_SIDES,
    _UPLIFT_COMPONENTS,
    _bearing_ranking,
    _radial_ranking,
    _rank_margin,
    _read_component,
    _ring,
    _ring_baselines,
)
from .lead_channels import compose_lead_channel_point
from .vessel_envelope import VESSEL_LIMIT_INPUTS, vessel_limit, vessel_motion_cases

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
    scales = [float(c) for c in channels]
    scales.append(float(wind_x_scale))
    scales.append(float(wind_y_scale))
    rope_plan, reaction_plan = _superpose_plan(probes)

    ropes: dict[str, float] = {}
    for rope_id, base, deltas in rope_plan:
        value = base
        for scale, delta in zip(scales, deltas):
            value += scale * delta
        ropes[rope_id] = value

    reactions: dict[str, dict[str, float]] = {}
    for entity_id, components in reaction_plan:
        out: dict[str, float] = {}
        for component, base, deltas in components:
            value = base
            for scale, delta in zip(scales, deltas):
                value += scale * delta
            out[component] = value
        reactions[entity_id] = out

    return replace(probes.zero, baseline_rope_tensions=ropes, baseline_reactions=reactions)


_RopePlan = list[tuple[str, float, list[float]]]
_ReactionPlan = list[tuple[str, list[tuple[str, float, list[float]]]]]
# The last probe set's plan: a sweep assembles many cases from one set before the next angle.
_last_plan: Optional[tuple[ProbeSet, tuple[_RopePlan, _ReactionPlan]]] = None


def _superpose_plan(probes: ProbeSet) -> tuple[_RopePlan, _ReactionPlan]:
    """Per rope and reaction component: the zero probe's value and each probe's delta from it.

    These do not depend on the case, so ``superpose`` only multiplies and adds. The order of
    ropes, entities and components is the one the plain set unions give.
    """
    global _last_plan
    cached = _last_plan
    if cached is not None and cached[0] is probes:
        return cached[1]

    zero = probes.zero
    others = [*probes.motion, probes.wind_x, probes.wind_y]
    rope_ids = set(zero.baseline_rope_tensions)
    for p in others:
        rope_ids |= set(p.baseline_rope_tensions)
    rope_plan: _RopePlan = []
    for rope_id in rope_ids:
        base = float(zero.baseline_rope_tensions.get(rope_id, 0.0))
        rope_plan.append(
            (
                rope_id,
                base,
                [float(p.baseline_rope_tensions.get(rope_id, 0.0)) - base for p in others],
            )
        )

    entity_ids = set(zero.baseline_reactions)
    for p in others:
        entity_ids |= set(p.baseline_reactions)
    reaction_plan: _ReactionPlan = []
    for entity_id in entity_ids:
        zero_comps = zero.baseline_reactions.get(entity_id, {})
        probe_comps = [p.baseline_reactions.get(entity_id, {}) for p in others]
        component_ids = set(zero_comps)
        for comps in probe_comps:
            component_ids |= set(comps)
        components = []
        for component in component_ids:
            base = float(zero_comps.get(component, 0.0))
            components.append(
                (component, base, [float(c.get(component, 0.0)) - base for c in probe_comps])
            )
        reaction_plan.append((entity_id, components))

    plan = (rope_plan, reaction_plan)
    _last_plan = (probes, plan)
    return plan


# --- worst case over vessel signs, slew, wind angle and lead signs ------------------------

# compute_analysis_point vessel keyword (VESSEL_LIMIT_INPUTS) -> VesselInputs field.
VESSEL_INPUT_FIELDS = {
    "accel_x_m_s2": "accel_x_m_s2",
    "accel_y_m_s2": "accel_y_m_s2",
    "accel_z_m_s2": "accel_z_m_s2",
    "roll_accel_rad_s2": "roll_accel_rad_s2",
    "pitch_accel_rad_s2": "pitch_accel_rad_s2",
    "vessel_roll_deg": "roll_deg",
    "vessel_pitch_deg": "pitch_deg",
}
_PLATFORM_BASE = "platform_base"


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
    """The harmonics of ``vessel``'s limits; cached, as they do not depend on the boom angle."""
    limits = tuple(vessel_limit(vessel, field) for field, _, _ in VESSEL_LIMIT_INPUTS)
    return _slew_harmonics_for(gravity, limits)


@lru_cache(maxsize=8)
def _slew_harmonics_for(gravity: float, limits: tuple[float, ...]) -> _SlewHarmonics:
    vessel = VesselMotion(
        **{field: limit for (field, _, _), limit in zip(VESSEL_LIMIT_INPUTS, limits)}
    )
    means, cos_parts, sin_parts = [], [], []
    for case in vessel_motion_cases(vessel):
        fields = {VESSEL_INPUT_FIELDS[key]: float(value) for key, value in case.items()}
        c0, c90, c180, c270 = (
            motion_channels(gravity, VesselInputs(slew_deg=slew, **fields))
            for slew in (0.0, 90.0, 180.0, 270.0)
        )
        means.append(0.5 * (c0 + c180))
        cos_parts.append(0.5 * (c0 - c180))
        sin_parts.append(0.5 * (c90 - c270))
    harmonics = _SlewHarmonics(np.array(means), np.array(cos_parts), np.array(sin_parts))
    for part in (harmonics.mean, harmonics.cos_part, harmonics.sin_part):
        part.setflags(write=False)  # shared between callers through the cache
    return harmonics


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


@dataclass(frozen=True)
class EnvelopeCase:
    """The real case an envelope capacity was evaluated at, as Scene inputs.

    ``vessel_inputs`` holds the vessel-frame ``VesselInputs`` fields other than
    ``slew_deg``; ``wind_axis`` is the axis wind ("+X", "-X", "+Y", "-Y"), or "" when the
    limit does not respond to wind; the leads are signed; ``limit_id`` is the limit key.
    For a magnitude limit the slew is that of a vertex of the polygon circumscribing the
    slew ellipse (see ``_magnitude_capacity``), so re-solving the case at that slew can
    give a capacity slightly above the envelope's.
    """

    vessel_inputs: dict[str, float]
    slew_deg: float
    wind_axis: str
    offlead_deg: float
    sidelead_deg: float
    limit_id: str


@dataclass(frozen=True)
class _Lead:
    """The zero probe composed with one signed lead case."""

    point: AnalysisPoint
    offlead_deg: float
    sidelead_deg: float


def _leads(probes: ProbeSet, offlead_deg: float, sidelead_deg: float) -> list[_Lead]:
    return [
        _Lead(compose_lead_channel_point(probes.zero, offlead, sidelead), offlead, sidelead)
        for offlead in _signed_candidates(offlead_deg)
        for sidelead in _signed_candidates(sidelead_deg)
    ]


def lead_points(probes: ProbeSet, offlead_deg: float, sidelead_deg: float) -> list[AnalysisPoint]:
    """The zero probe composed with every lead sign case (one point for zero leads)."""
    return [lead.point for lead in _leads(probes, offlead_deg, sidelead_deg)]


def _wind_axis(wind_x_scale: float, wind_y_scale: float) -> str:
    """Axis of a wind corner: scale +1 is the probe direction (+X at 0 deg, +Y at 90 deg)."""
    if wind_x_scale:
        return "+X" if wind_x_scale > 0.0 else "-X"
    if wind_y_scale:
        return "+Y" if wind_y_scale > 0.0 else "-Y"
    return ""


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
    hook_daf: DynamicFactor
    hook_mass_t: float
    # VesselInputs fields (no slew) of each sign case, in the harmonics' case order.
    vessel_cases: tuple[dict[str, float], ...]

    def capacity(self, point: AnalysisPoint, single_limit: dict[str, dict]) -> AllowableCapacity:
        return self.calc.compute_allowable_load(
            point, single_limit, hook_daf=self.hook_daf, hook_mass_t=self.hook_mass_t
        )

    def case(
        self,
        lead: _Lead,
        case: int,
        cos_phi: float,
        sin_phi: float,
        wind_axis: str,
        limit_id: str,
    ) -> EnvelopeCase:
        return EnvelopeCase(
            vessel_inputs=dict(self.vessel_cases[case]),
            slew_deg=math.degrees(math.atan2(sin_phi, cos_phi)),
            wind_axis=wind_axis,
            offlead_deg=lead.offlead_deg,
            sidelead_deg=lead.sidelead_deg,
            limit_id=limit_id,
        )


# A capacity with the case it was evaluated at (None where no single case applies).
_Candidate = tuple[AllowableCapacity, Optional[EnvelopeCase]]


def _lower(best: Optional[_Candidate], candidate: Optional[_Candidate]) -> Optional[_Candidate]:
    if candidate is None:
        return best
    if best is None or candidate[0].max_allowable_load_kN < best[0].max_allowable_load_kN:
        return candidate
    return best


def _linear_capacity(
    ctx: _LimitContext,
    lead: _Lead,
    limit_key: str,
    component: str,
    single_limit: dict[str, dict],
) -> Optional[_Candidate]:
    """Capacity at the cases of largest and smallest baseline of a linear limit.

    Per sign case the baseline over slew is ``B0 + P cos(phi) + Q sin(phi)``, extreme at
    ``B0 +/- hypot(P, Q)`` with ``phi = atan2(Q, P)`` (+180 deg for the minimum). Over wind
    angle the term ``a*u + b*v`` has ``|u| + |v| = 1`` and is extreme at an axis wind,
    ``+/- max(|a|, |b|)``. The capacity compute_allowable_load gives a linear limit never
    increases with the baseline (0 above the limit, ``(L - B)/s`` or unlimited below), so
    the worst case is the largest baseline; the smallest is evaluated too and the lower
    capacity kept. Both are real cases; the lower is returned with its case.
    """
    lead_point = lead.point
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
    no_wind = quantity.wind_x == 0.0 and quantity.wind_y == 0.0
    best: Optional[_Candidate] = None
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
        found = ctx.case(
            lead,
            case,
            sign * cos_phi,
            sign * sin_phi,
            "" if no_wind else _wind_axis(*wind),
            limit_key,
        )
        best = _lower(best, (ctx.capacity(point, single_limit), found))
    return best


def _magnitude_capacity(
    ctx: _LimitContext,
    leads: Sequence[_Lead],
    limit_key: str,
    entity_id: str,
    component: str,
    limit: float,
    single_limit: dict[str, dict],
) -> _Candidate:
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
    The lowest evaluated vertex is returned with its case.
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
    if component in _BEARING_COMPONENTS:
        diameter = float(getattr(ctx.calc.doc.support_widths, "slewing_bearing_diameter_m", 1.0))
        if diameter <= 0.0:
            # compute_allowable_load rejects this diameter; let it raise.
            return ctx.capacity(leads[0].point, single_limit), None

    def _rank(sens: list[float], values: np.ndarray) -> np.ndarray:
        if component in _BEARING_COMPONENTS:
            return _bearing_ranking(
                limit,
                diameter,
                values[..., 0],
                values[..., 1],
                values[..., 2],
                sens[0],
                sens[1],
                sens[2],
                uplift=component in _UPLIFT_COMPONENTS,
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
            _read_component(lead.point.sensitivity_reactions.get(entity_id, {}), key, fallback)
            for key, fallback in quantities
        ]
        for lead in leads
    ]

    best: Optional[_Candidate] = None
    rank_error = 0.0

    def _evaluate(
        lead: int, case: int, cos_v: float, sin_v: float, corner: int, rank: float
    ) -> None:
        nonlocal best, rank_error
        channels = harmonics.channels(case, cos_v, sin_v)
        point = _case_point(ctx.probes, leads[lead].point, channels, *corners[corner])
        cap = ctx.capacity(point, single_limit)
        exact = cap.max_allowable_load_kN
        if math.isinf(rank) and not math.isinf(exact):
            # The ranking missed a finite capacity: no pruning, every fine vertex is evaluated.
            rank_error = math.inf
        elif not math.isinf(exact):
            rank_error = max(rank_error, abs(exact - rank))
        found = ctx.case(leads[lead], case, cos_v, sin_v, _wind_axis(*corners[corner]), limit_key)
        best = _lower(best, (cap, found))

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
    lowest = best[0].max_allowable_load_kN
    cutoff = lowest + _rank_margin(rank_error, lowest)

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
        current = best[0].max_allowable_load_kN
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
    hook_daf: DynamicFactorLike,
    hook_mass_t: float,
) -> AllowableCapacity:
    """Lowest allowable capacity over every case; see ``envelope_capacity_case``."""
    capacity, _ = envelope_capacity_case(
        calc,
        probes,
        limits,
        vessel=vessel,
        offlead_deg=offlead_deg,
        sidelead_deg=sidelead_deg,
        hook_daf=hook_daf,
        hook_mass_t=hook_mass_t,
    )
    return capacity


def envelope_capacity_case(
    calc: CraneCalculator,
    probes: ProbeSet,
    limits: dict[str, dict],
    *,
    vessel: VesselMotion,
    offlead_deg: float,
    sidelead_deg: float,
    hook_daf: DynamicFactorLike,
    hook_mass_t: float,
) -> tuple[AllowableCapacity, Optional[EnvelopeCase]]:
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
    ``governing_limit_id`` and the case it was evaluated at (``None`` when no limit
    applies).
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
        hook_daf=as_dynamic_factor(hook_daf),
        hook_mass_t=float(hook_mass_t),
        vessel_cases=tuple(
            {VESSEL_INPUT_FIELDS[key]: float(value) for key, value in case.items()}
            for case in vessel_motion_cases(vessel)
        ),
    )
    leads = _leads(probes, offlead_deg, sidelead_deg)
    best: Optional[_Candidate] = None
    for limit_key, components in limits.items():
        for component, limit_value in components.items():
            if not limit_value:
                continue
            single_limit = {limit_key: {component: limit_value}}
            entity_id, _ = calc.resolve_limit_target(limit_key, component)
            # Which branch compute_allowable_load takes depends on sensitivity keys only.
            magnitude = [lead for lead in leads if _is_magnitude(lead.point, entity_id, component)]
            if magnitude:
                best = _lower(
                    best,
                    _magnitude_capacity(
                        ctx,
                        magnitude,
                        limit_key,
                        entity_id,
                        component,
                        float(limit_value),
                        single_limit,
                    ),
                )
            for lead in leads:
                if not _is_magnitude(lead.point, entity_id, component):
                    best = _lower(
                        best, _linear_capacity(ctx, lead, limit_key, component, single_limit)
                    )
    if best is None:
        # No limit applies: compute_allowable_load reports the unlimited capacity.
        best = (ctx.capacity(probes.zero, limits), None)
    capacity, case = best
    # The worst case is over all wind angles, not one direction; the field would otherwise
    # carry the zero probe's direction.
    capacity.governing_wind_direction = None
    return capacity, case
