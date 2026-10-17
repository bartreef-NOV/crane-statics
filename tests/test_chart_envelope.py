"""Load-chart envelope: probe solves superpose to any vessel-motion / slew / wind case."""

from __future__ import annotations

import copy
import itertools
import math
import random
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from tests.chart_reference import reference_capacities
from crane_statics.calculation.engine import AllowableCapacity, AnalysisPoint, CraneCalculator
from crane_statics.calculation.vessel_frame import VesselInputs
from crane_statics.core import chart_envelope, load_document
from crane_statics.core.analysis_cases import _signed_candidates, analysis_mode_by_name
from crane_statics.core.chart_envelope import (
    build_probes,
    envelope_capacity,
    motion_channels,
    superpose,
)
from crane_statics.core.demand_extraction import extract_connection_component_response
from crane_statics.core.lead_channels import compose_lead_channel_point
from crane_statics.data.models import CraneDocument

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_GT283.yaml"
BOOM_ANGLE_DEG = 45.0
HOIST = "MH"
# Model vessel-motion limits, all nonzero (engine keyword -> limit).
LIMITS = {
    "accel_x_m_s2": 0.8,
    "accel_y_m_s2": 0.6,
    "accel_z_m_s2": 1.1,
    "roll_accel_rad_s2": 0.05,
    "pitch_accel_rad_s2": 0.03,
    "vessel_roll_deg": 4.0,
    "vessel_pitch_deg": 2.5,
}
CASES = 20
# Reference grid for the all-seven-limits oracle: with 128 sign cases, 5 deg steps in both
# slew and wind are ~660k full solves (~10 min) per boom angle, so this test uses 15 deg
# slew and 45 deg wind (axes and diagonals, ~25k solves); the fine-reference and
# split-mode tests use 5 deg steps in both on two vessel limits (4 sign cases).
REF_SLEW_STEP = 15.0
REF_WIND_STEP = 45.0


def _document(*, offset_boom_mass: bool) -> CraneDocument:
    doc = load_document(EXAMPLE)
    vm = doc.environment.vessel_motion
    vm.accel_x_m_s2 = LIMITS["accel_x_m_s2"]
    vm.accel_y_m_s2 = LIMITS["accel_y_m_s2"]
    vm.accel_z_m_s2 = LIMITS["accel_z_m_s2"]
    vm.roll_angular_accel_rad_s2 = LIMITS["roll_accel_rad_s2"]
    vm.pitch_angular_accel_rad_s2 = LIMITS["pitch_accel_rad_s2"]
    vm.roll_deg = LIMITS["vessel_roll_deg"]
    vm.pitch_deg = LIMITS["vessel_pitch_deg"]
    vm.reference_x_m = 3.0
    vm.reference_z_m = -2.0
    if offset_boom_mass:
        boom = next(b for b in doc.bodies if b.id == "boom")
        mp = boom.mass_points[0]
        mp.y_m = 1.7
        if mp.local_x_m is not None:
            mp.local_y_m = 1.7
    return doc


def _cases(seed: int) -> list[tuple[dict[str, Any], float, float]]:
    rng = random.Random(seed)
    cases = []
    for _ in range(CASES):
        motion = {k: rng.choice((-1.0, 1.0)) * v for k, v in LIMITS.items()}
        cases.append((motion, rng.uniform(0.0, 360.0), rng.uniform(0.0, 360.0)))
    return cases


def _flat(point: AnalysisPoint) -> dict[tuple[str, str], float]:
    flat = {("rope", r): float(v) for r, v in point.baseline_rope_tensions.items()}
    for entity, comps in point.baseline_reactions.items():
        for comp, value in comps.items():
            flat[(entity, comp)] = float(value)
    return flat


def _vessel_inputs(motion: dict[str, float], slew_deg: float) -> VesselInputs:
    return VesselInputs(
        accel_x_m_s2=motion["accel_x_m_s2"],
        accel_y_m_s2=motion["accel_y_m_s2"],
        accel_z_m_s2=motion["accel_z_m_s2"],
        roll_deg=motion["vessel_roll_deg"],
        pitch_deg=motion["vessel_pitch_deg"],
        slew_deg=slew_deg,
        roll_accel_rad_s2=motion["roll_accel_rad_s2"],
        pitch_accel_rad_s2=motion["pitch_accel_rad_s2"],
    )


def _wind_scales(angle_deg: float) -> tuple[float, float]:
    c = math.cos(math.radians(angle_deg))
    s = math.sin(math.radians(angle_deg))
    return c * abs(c), s * abs(s)


@pytest.mark.parametrize("offset_boom_mass", [False, True], ids=["example", "boom_mass_y"])
@pytest.mark.parametrize("wind_speed", [None, 20.0], ids=["document_wind", "wind_20"])
def test_superposition_matches_direct_solve(
    offset_boom_mass: bool, wind_speed: float | None
) -> None:
    doc = _document(offset_boom_mass=offset_boom_mass)
    calc = CraneCalculator(doc)
    speed = float(doc.environment.max_wind_speed_m_s if wind_speed is None else wind_speed)
    gravity = abs(float(doc.environment.gravity_m_s2))
    overrides: dict[str, dict[str, Any]] | None = None
    probes = build_probes(calc, HOIST, BOOM_ANGLE_DEG, speed, overrides)
    assert probes is not None

    for motion, slew, wind_angle in _cases(seed=5):
        direct = calc.compute_analysis_point(
            BOOM_ANGLE_DEG,
            0.0,
            HOIST,
            wind_speed_m_s=speed,
            wind_angle_deg=wind_angle,
            crane_slewing_angle_deg=slew,
            hoist_runtime_overrides=overrides,
            offlead_deg=0.0,
            **motion,
        )
        assert direct is not None
        wx, wy = _wind_scales(wind_angle)
        got = superpose(probes, motion_channels(gravity, _vessel_inputs(motion, slew)), wx, wy)

        expected_flat, got_flat = _flat(direct), _flat(got)
        assert set(got_flat) == set(expected_flat)
        for key, value in expected_flat.items():
            assert got_flat[key] == pytest.approx(value, rel=1e-9, abs=1e-9), (key, motion, slew)
        assert got.sensitivity_rope_tensions == probes.zero.sensitivity_rope_tensions
        assert got.sensitivity_reactions == probes.zero.sensitivity_reactions
        # Load-bearing: the direct solve's hook sensitivities and lead unit channels do not
        # depend on motion, slew or wind, so the zero probe's stand in for every case.
        for name in _MOTION_INDEPENDENT:
            direct_channel = _flat_channel(getattr(direct, name))
            zero_channel = _flat_channel(getattr(probes.zero, name))
            assert set(zero_channel) == set(direct_channel), name
            for ck, value in direct_channel.items():
                assert zero_channel[ck] == pytest.approx(value, rel=1e-9, abs=1e-9), (name, ck)


_MOTION_INDEPENDENT = (
    "sensitivity_rope_tensions",
    "sensitivity_reactions",
    "offlead_lateral_unit_rope_tensions",
    "offlead_lateral_unit_reactions",
    "sidelead_lateral_unit_reactions",
)


def _flat_channel(channel: Any) -> dict[tuple[str, ...], float]:
    """Flatten a rope ({id: value}) or reaction ({id: {comp: value}}) channel; None -> {}."""
    flat: dict[tuple[str, ...], float] = {}
    for key, value in (channel or {}).items():
        if isinstance(value, dict):
            for comp, v in value.items():
                flat[(key, comp)] = float(v)
        else:
            flat[(key,)] = float(value)
    return flat


def test_motion_channels_are_zero_for_zero_inputs() -> None:
    assert motion_channels(9.81, VesselInputs()).tolist() == [0.0] * 5


def test_motion_channels_on_a_level_vessel_are_the_inputs() -> None:
    inputs = VesselInputs(
        accel_x_m_s2=0.1,
        accel_y_m_s2=0.2,
        accel_z_m_s2=0.3,
        pitch_accel_rad_s2=0.4,
        roll_accel_rad_s2=0.5,
    )
    assert motion_channels(9.81, inputs).tolist() == pytest.approx([0.1, 0.2, 0.3, 0.4, 0.5])


def test_zero_wind_probes_reuse_the_zero_point() -> None:
    calc = CraneCalculator(_document(offset_boom_mass=False))
    probes = build_probes(calc, HOIST, BOOM_ANGLE_DEG, 0.0, None)
    assert probes is not None
    assert probes.wind_x is probes.zero
    assert probes.wind_y is probes.zero


def test_unknown_hoist_gives_no_probes() -> None:
    calc = CraneCalculator(_document(offset_boom_mass=False))
    assert build_probes(calc, "nope", BOOM_ANGLE_DEG, 10.0, None) is None


def test_probes_are_zero_lead_points() -> None:
    """The authored offlead must not be in the probes: envelope_capacity adds both signs."""
    doc = _document(offset_boom_mass=False)
    assert _hoist(doc).offlead_deg != 0.0
    calc = CraneCalculator(doc)
    probes = build_probes(calc, HOIST, BOOM_ANGLE_DEG, 0.0, None)
    assert probes is not None
    no_motion: dict[str, Any] = dict.fromkeys(LIMITS, 0.0)
    zero_lead = calc.compute_analysis_point(
        BOOM_ANGLE_DEG,
        0.0,
        HOIST,
        wind_speed_m_s=0.0,
        offlead_deg=0.0,
        sidelead_deg=0.0,
        crane_slewing_angle_deg=0.0,
        **no_motion,
    )
    assert zero_lead is not None
    assert probes.zero.sensitivity_rope_tensions == zero_lead.sensitivity_rope_tensions
    assert probes.zero.sensitivity_reactions == zero_lead.sensitivity_reactions


def test_vessel_limits_skip_probes_of_unused_channels() -> None:
    doc = _envelope_document(vessel_limits={"accel_z_m_s2": 1.1})
    calc = CraneCalculator(doc)
    vm = doc.environment.vessel_motion
    full = build_probes(calc, HOIST, BOOM_ANGLE_DEG, WIND_M_S, None)
    lean = build_probes(calc, HOIST, BOOM_ANGLE_DEG, WIND_M_S, None, vessel=vm)
    assert full is not None and lean is not None
    # Only heave is set: accel x, y and the angular channels stay zero at every slew.
    used = [p is not lean.zero for p in lean.motion]
    assert used == [False, False, True, False, False]
    hoist = _hoist(doc)
    for limits in ENVELOPE_LIMITS:
        caps = [
            envelope_capacity(
                calc,
                probes,
                limits,
                vessel=vm,
                offlead_deg=hoist.offlead_deg,
                sidelead_deg=hoist.sidelead_deg,
                hook_daf=hoist.hook_daf,
                hook_mass_t=hoist.hook_mass_t,
            )
            for probes in (full, lean)
        ]
        assert caps[1].max_allowable_load_kN == pytest.approx(
            caps[0].max_allowable_load_kN, rel=1e-12, abs=1e-12
        )


def test_probes_for_other_vessel_limits_are_rejected() -> None:
    """Lean probes for a heave-only vessel must not silently drop the full vessel's motion."""
    doc = _envelope_document(vessel_limits={"accel_z_m_s2": 1.1})
    calc = CraneCalculator(doc)
    lean = build_probes(
        calc, HOIST, BOOM_ANGLE_DEG, WIND_M_S, None, vessel=doc.environment.vessel_motion
    )
    assert lean is not None
    assert lean.solved == (False, False, True, False, False)
    full_vessel = _envelope_document().environment.vessel_motion
    hoist = _hoist(doc)
    with pytest.raises(ValueError, match="unsolved channels"):
        envelope_capacity(
            calc,
            lean,
            ENVELOPE_LIMITS[0],
            vessel=full_vessel,
            offlead_deg=hoist.offlead_deg,
            sidelead_deg=hoist.sidelead_deg,
            hook_daf=hoist.hook_daf,
            hook_mass_t=hoist.hook_mass_t,
        )


# --- envelope_capacity ----------------------------------------------------------------

ENVELOPE_LIMITS: list[dict[str, dict]] = [
    {"boom_hoist": {"T": 5000.0}},
    {"platform_base": {"fradial": 20000.0}},
    {"platform_base": {"max_bearing_line_load": 3000.0}},
    {"heel_point": {"Fx": 20000.0}},
]
LIMIT_IDS = ["boom_hoist_T", "fradial", "bearing_line_load", "heel_point_Fx"]
WIND_M_S = 20.0
UNSAFE_REL = 1e-6
CONSERVATIVE_REL = 0.005
_VESSEL_FIELDS = (
    "accel_x_m_s2",
    "accel_y_m_s2",
    "accel_z_m_s2",
    "roll_angular_accel_rad_s2",
    "pitch_angular_accel_rad_s2",
    "roll_deg",
    "pitch_deg",
)


def _envelope_document(
    *, vessel_limits: dict[str, float] | None = None, offset_boom_mass: bool = False
) -> CraneDocument:
    """GT283 at 20 m/s wind with the given vessel limits (default: all seven nonzero)."""
    doc = _document(offset_boom_mass=offset_boom_mass)
    doc.environment.max_wind_speed_m_s = WIND_M_S
    if vessel_limits is not None:
        vm = doc.environment.vessel_motion
        for field in _VESSEL_FIELDS:
            setattr(vm, field, float(vessel_limits.get(field, 0.0)))
    return doc


def _hoist(doc: CraneDocument) -> Any:
    return next(h for h in doc.hoists if h.id == HOIST)


def _fast(
    calc: CraneCalculator,
    doc: CraneDocument,
    angle: float,
    limits: dict[str, dict],
    *,
    overrides: dict[str, dict[str, Any]] | None = None,
    hook_mass_t: float | None = None,
) -> AllowableCapacity:
    hoist = _hoist(doc)
    probes = build_probes(calc, HOIST, angle, float(doc.environment.max_wind_speed_m_s), overrides)
    assert probes is not None
    return envelope_capacity(
        calc,
        probes,
        limits,
        vessel=doc.environment.vessel_motion,
        offlead_deg=hoist.offlead_deg,
        sidelead_deg=hoist.sidelead_deg,
        hook_daf=hoist.hook_daf,
        hook_mass_t=hoist.hook_mass_t if hook_mass_t is None else hook_mass_t,
    )


def _assert_within_band(fast: AllowableCapacity, ref: AllowableCapacity, label: str) -> None:
    f, r = fast.max_allowable_load_kN, ref.max_allowable_load_kN
    assert r > 0.0, f"{label}: reference capacity is zero, the comparison would be vacuous"
    print(f"{label}: fast {f:.6f} ref {r:.6f} ratio {f / r if r else float('nan'):.8f}")
    assert f <= r * (1.0 + UNSAFE_REL) + 1e-9, f"{label}: fast {f} above reference {r}"
    assert f >= r * (1.0 - CONSERVATIVE_REL) - 1e-9, f"{label}: fast {f} too far below {r}"
    assert fast.governing_limit_id == ref.governing_limit_id, label


def _compare_with_reference(
    doc: CraneDocument,
    angle: float,
    *,
    slew_step_deg: float,
    wind_step_deg: float,
    overrides: dict[str, dict[str, Any]] | None = None,
    hook_mass_t: float | None = None,
) -> None:
    calc = CraneCalculator(doc)
    hoist = _hoist(doc)
    mass = float(hoist.hook_mass_t if hook_mass_t is None else hook_mass_t)
    refs = reference_capacities(
        calc,
        doc,
        HOIST,
        angle,
        ENVELOPE_LIMITS,
        hook_daf=hoist.hook_daf,
        hook_mass_t=mass,
        overrides=overrides,
        slew_step_deg=slew_step_deg,
        wind_step_deg=wind_step_deg,
    )
    for limit_id, limits, ref in zip(LIMIT_IDS, ENVELOPE_LIMITS, refs):
        fast = _fast(calc, doc, angle, limits, overrides=overrides, hook_mass_t=mass)
        _assert_within_band(fast, ref, f"{limit_id} @ {angle} deg")


@pytest.mark.slow
@pytest.mark.parametrize("angle", [20.0, 45.0, 70.0])
def test_envelope_never_exceeds_the_reference(angle: float) -> None:
    """All seven vessel limits, 20 m/s wind and the example's nonzero leads."""
    doc = _envelope_document()
    hoist = _hoist(doc)
    assert hoist.offlead_deg != 0.0 and hoist.sidelead_deg != 0.0
    vm = doc.environment.vessel_motion
    assert all(getattr(vm, field) != 0.0 for field in _VESSEL_FIELDS)
    _compare_with_reference(doc, angle, slew_step_deg=REF_SLEW_STEP, wind_step_deg=REF_WIND_STEP)


@pytest.mark.slow
@pytest.mark.parametrize("offset_boom_mass", [False, True], ids=["example", "boom_mass_y"])
def test_envelope_matches_a_fine_reference(offset_boom_mass: bool) -> None:
    """5 deg slew and wind steps (off-axis wind included) on sway and roll angle.

    ``boom_mass_y`` gives the boom mass a y offset, so sway/roll signs are not mirrors.
    """
    doc = _envelope_document(
        vessel_limits={"accel_y_m_s2": 0.6, "roll_deg": 4.0}, offset_boom_mass=offset_boom_mass
    )
    _compare_with_reference(doc, 20.0, slew_step_deg=5.0, wind_step_deg=5.0)


@pytest.mark.slow
def test_envelope_with_split_mode_overrides() -> None:
    doc = _envelope_document(vessel_limits={"accel_x_m_s2": 0.8, "pitch_deg": 2.5})
    split = _hoist(doc).model_copy(
        update={"splitable_block": True, "split_falls": 10, "split_hook_mass_t": 30.0}
    )
    mode = analysis_mode_by_name(split, "split")
    assert mode.name == "split" and mode.runtime_overrides
    _compare_with_reference(
        doc,
        45.0,
        slew_step_deg=5.0,
        wind_step_deg=5.0,
        overrides=mode.runtime_overrides,
        hook_mass_t=mode.hook_mass_t,
    )


def _lead_cases(hoist: Any) -> list[tuple[float, float]]:
    return list(
        itertools.product(
            _signed_candidates(hoist.offlead_deg), _signed_candidates(hoist.sidelead_deg)
        )
    )


def test_zero_limits_and_no_wind_equal_the_single_solve() -> None:
    doc = _envelope_document(vessel_limits={})
    doc.environment.max_wind_speed_m_s = 0.0
    calc = CraneCalculator(doc)
    hoist = _hoist(doc)
    pt = calc.compute_analysis_point(
        BOOM_ANGLE_DEG, 0.0, HOIST, wind_speed_m_s=0.0, offlead_deg=0.0, sidelead_deg=0.0
    )
    assert pt is not None
    for limits in ENVELOPE_LIMITS:
        expected = min(
            (
                calc.compute_allowable_load(
                    compose_lead_channel_point(pt, off, side),
                    limits,
                    hook_daf=hoist.hook_daf,
                    hook_mass_t=hoist.hook_mass_t,
                )
                for off, side in _lead_cases(hoist)
            ),
            key=lambda cap: cap.max_allowable_load_kN,
        )
        got = _fast(calc, doc, BOOM_ANGLE_DEG, limits)
        assert got.max_allowable_load_kN == pytest.approx(
            expected.max_allowable_load_kN, rel=1e-9
        ), limits
        assert got.max_allowable_load_t == pytest.approx(expected.max_allowable_load_t, rel=1e-9)
        assert got.governing_limit_id == expected.governing_limit_id


def test_zero_leads_collapse_to_one_case(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = _envelope_document()
    calc = CraneCalculator(doc)
    probes = build_probes(calc, HOIST, BOOM_ANGLE_DEG, WIND_M_S, None)
    assert probes is not None
    calls: list[tuple[float, float]] = []
    original = chart_envelope.compose_lead_channel_point

    def _counting(pt: AnalysisPoint, off: float, side: float) -> AnalysisPoint:
        calls.append((off, side))
        return original(pt, off, side)

    monkeypatch.setattr(chart_envelope, "compose_lead_channel_point", _counting)
    limits = {**ENVELOPE_LIMITS[0], **ENVELOPE_LIMITS[1], **ENVELOPE_LIMITS[3]}
    envelope_capacity(
        calc,
        probes,
        limits,
        vessel=doc.environment.vessel_motion,
        offlead_deg=0.0,
        sidelead_deg=0.0,
        hook_daf=1.1,
        hook_mass_t=50.0,
    )
    assert calls == [(0.0, 0.0)]


@pytest.mark.parametrize(
    ("entity", "component"),
    [
        ("platform_base", "fradial"),
        ("platform_base", "mradial"),
        ("heel_point", "resultant"),
        ("platform_base", "max_bearing_line_load"),
    ],
)
def test_magnitude_rankings_match_compute_allowable_load(entity: str, component: str) -> None:
    """The vectorised ranking closed forms agree with compute_allowable_load."""
    doc = _envelope_document()
    calc = CraneCalculator(doc)
    probes = build_probes(calc, HOIST, BOOM_ANGLE_DEG, WIND_M_S, None)
    assert probes is not None
    quantities = chart_envelope._MAGNITUDE_QUANTITIES[component]
    diameter = float(doc.support_widths.slewing_bearing_diameter_m or 1.0)
    rng = random.Random(11)
    seen = set()
    for _ in range(80):
        lead = compose_lead_channel_point(
            probes.zero, rng.choice((-1.0, 1.0)), rng.choice((-2.5, 2.5))
        )
        channels = [rng.uniform(-3.0, 3.0) for _ in range(5)]
        point = chart_envelope._case_point(
            probes, lead, channels, rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0)
        )
        demand0 = extract_connection_component_response(point, 0.0, entity, component, diameter)
        assert demand0 is not None
        limit = rng.uniform(0.8, 3.0) * demand0
        base = [
            np.array([chart_envelope._read_component(point.baseline_reactions[entity], k, f)])
            for k, f in quantities
        ]
        sens = [
            chart_envelope._read_component(point.sensitivity_reactions[entity], k, f)
            for k, f in quantities
        ]
        if component == "max_bearing_line_load":
            ranked = chart_envelope._bearing_ranking(limit, diameter, *base, *sens)
        else:
            ranked = chart_envelope._radial_ranking(limit, *base, *sens)
        exact = calc.compute_allowable_load(point, {entity: {component: limit}})
        seen.add("zero" if exact.max_allowable_load_kN == 0.0 else "positive")
        assert float(ranked[0]) == pytest.approx(exact.max_allowable_load_kN, rel=1e-6, abs=1e-6)
    assert seen == {"zero", "positive"}


def _lead_state(pt: AnalysisPoint) -> tuple[Any, ...]:
    return copy.deepcopy(
        (
            pt.sensitivity_rope_tensions,
            pt.sensitivity_reactions,
            pt.baseline_rope_tensions,
            pt.baseline_reactions,
            pt.offlead_lateral_unit_rope_tensions,
            pt.offlead_lateral_unit_reactions,
            pt.sidelead_lateral_unit_reactions,
        )
    )


def test_envelope_leaves_the_probe_lead_channels_unchanged() -> None:
    doc = _envelope_document()
    calc = CraneCalculator(doc)
    probes = build_probes(calc, HOIST, BOOM_ANGLE_DEG, WIND_M_S, None)
    assert probes is not None
    before = _lead_state(probes.zero)
    for limits in ENVELOPE_LIMITS:
        envelope_capacity(
            calc,
            probes,
            limits,
            vessel=doc.environment.vessel_motion,
            offlead_deg=1.0,
            sidelead_deg=2.5,
            hook_daf=1.1,
            hook_mass_t=50.0,
        )
    assert _lead_state(probes.zero) == before
