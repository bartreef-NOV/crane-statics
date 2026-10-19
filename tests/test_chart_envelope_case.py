"""The envelope keeps its argmax case, and the Scene re-evaluates it to the chart value."""

from __future__ import annotations

import dataclasses

import pytest

from crane_statics.calculation.engine import AllowableCapacity, CraneCalculator
from crane_statics.calculation.vessel_frame import VesselInputs
from crane_statics.core.chart_envelope import (
    EnvelopeCase,
    build_probes,
    envelope_capacity,
    envelope_capacity_case,
)
from crane_statics.data.models import CraneDocument
from tests.test_chart_envelope import (
    BOOM_ANGLE_DEG,
    ENVELOPE_LIMITS,
    HOIST,
    LIMIT_IDS,
    WIND_M_S,
    _envelope_document,
    _hoist,
)

_VESSEL_FIELDS = {f.name for f in dataclasses.fields(VesselInputs)} - {"slew_deg"}
_WIND_AXES = {"+X", "-X", "+Y", "-Y"}
_LINEAR = [
    (i, lim) for i, lim in zip(LIMIT_IDS, ENVELOPE_LIMITS) if i in ("boom_hoist_T", "heel_point_Fx")
]
_MAGNITUDE = [
    ("heel_resultant", {"heel_point": {"resultant": 20000.0}}),
    ("fradial", {"platform_base": {"fradial": 20000.0}}),
    ("bearing_line_load", {"platform_base": {"max_bearing_line_load": 3000.0}}),
]


def _envelope(
    calc: CraneCalculator, doc: CraneDocument, limits: dict[str, dict]
) -> tuple[AllowableCapacity, EnvelopeCase | None]:
    hoist = _hoist(doc)
    probes = build_probes(calc, HOIST, BOOM_ANGLE_DEG, WIND_M_S, None)
    assert probes is not None
    return envelope_capacity_case(
        calc,
        probes,
        limits,
        vessel=doc.environment.vessel_motion,
        offlead_deg=hoist.offlead_deg,
        sidelead_deg=hoist.sidelead_deg,
        hook_daf=hoist.hook_daf,
        hook_mass_t=hoist.hook_mass_t,
    )


def _scene_capacity(
    calc: CraneCalculator, doc: CraneDocument, case: EnvelopeCase, limits: dict[str, dict]
) -> AllowableCapacity:
    """The case solved directly, as the Scene would: no superposition, no envelope."""
    hoist = _hoist(doc)
    v = case.vessel_inputs
    point = calc.compute_analysis_point(
        BOOM_ANGLE_DEG,
        0.0,
        HOIST,
        wind_speed_m_s=WIND_M_S,
        wind_direction=case.wind_axis or "+X",
        accel_x_m_s2=v["accel_x_m_s2"],
        accel_y_m_s2=v["accel_y_m_s2"],
        accel_z_m_s2=v["accel_z_m_s2"],
        pitch_accel_rad_s2=v["pitch_accel_rad_s2"],
        roll_accel_rad_s2=v["roll_accel_rad_s2"],
        vessel_roll_deg=v["roll_deg"],
        vessel_pitch_deg=v["pitch_deg"],
        crane_slewing_angle_deg=case.slew_deg,
        offlead_deg=case.offlead_deg,
        sidelead_deg=case.sidelead_deg,
    )
    assert point is not None
    return calc.compute_allowable_load(
        point, limits, hook_daf=hoist.hook_daf, hook_mass_t=hoist.hook_mass_t
    )


def _assert_case_shape(case: EnvelopeCase | None, doc: CraneDocument) -> EnvelopeCase:
    assert case is not None
    assert set(case.vessel_inputs) == _VESSEL_FIELDS
    assert case.wind_axis in _WIND_AXES
    hoist = _hoist(doc)
    assert abs(case.offlead_deg) == pytest.approx(abs(hoist.offlead_deg))
    assert abs(case.sidelead_deg) == pytest.approx(abs(hoist.sidelead_deg))
    return case


@pytest.mark.parametrize(("label", "limits"), _LINEAR, ids=[i for i, _ in _LINEAR])
def test_linear_limit_case_reproduces_capacity(label: str, limits: dict[str, dict]) -> None:
    doc = _envelope_document()
    calc = CraneCalculator(doc)
    cap, case = _envelope(calc, doc, limits)
    case = _assert_case_shape(case, doc)
    assert case.limit_id == next(iter(limits)) == cap.governing_limit_id
    assert 0.0 < cap.max_allowable_load_kN < float("inf"), label
    scene = _scene_capacity(calc, doc, case, limits)
    assert scene.max_allowable_load_kN == pytest.approx(cap.max_allowable_load_kN, rel=1e-6)
    assert scene.governing_limit_id == cap.governing_limit_id


@pytest.mark.parametrize(("label", "limits"), _MAGNITUDE, ids=[i for i, _ in _MAGNITUDE])
def test_magnitude_limit_case_within_tolerance(label: str, limits: dict[str, dict]) -> None:
    doc = _envelope_document()
    calc = CraneCalculator(doc)
    cap, case = _envelope(calc, doc, limits)
    case = _assert_case_shape(case, doc)
    assert case.limit_id == next(iter(limits)) == cap.governing_limit_id
    chart = cap.max_allowable_load_kN
    assert 0.0 < chart < float("inf"), label
    scene = _scene_capacity(calc, doc, case, limits).max_allowable_load_kN
    assert scene == pytest.approx(chart, rel=1e-3)
    assert scene >= chart - 1e-9


def test_combined_limits_case_names_the_governing_limit() -> None:
    doc = _envelope_document()
    calc = CraneCalculator(doc)
    limits = {k: v for lim in ENVELOPE_LIMITS for k, v in lim.items()}
    cap, case = _envelope(calc, doc, limits)
    case = _assert_case_shape(case, doc)
    assert case.limit_id == cap.governing_limit_id
    scene = _scene_capacity(calc, doc, case, {case.limit_id: limits[case.limit_id]})
    assert scene.max_allowable_load_kN == pytest.approx(cap.max_allowable_load_kN, rel=1e-3)


def test_no_vessel_motion_single_case() -> None:
    doc = _envelope_document(vessel_limits={})
    calc = CraneCalculator(doc)
    limits = ENVELOPE_LIMITS[0]
    cap, case = _envelope(calc, doc, limits)
    case = _assert_case_shape(case, doc)
    assert case.vessel_inputs == dict.fromkeys(_VESSEL_FIELDS, 0.0)
    scene = _scene_capacity(calc, doc, case, limits)
    assert scene.max_allowable_load_kN == pytest.approx(cap.max_allowable_load_kN, rel=1e-6)


def test_no_wind_gives_no_wind_axis() -> None:
    doc = _envelope_document()
    calc = CraneCalculator(doc)
    hoist = _hoist(doc)
    probes = build_probes(calc, HOIST, BOOM_ANGLE_DEG, 0.0, None)
    assert probes is not None
    for limits in (ENVELOPE_LIMITS[0], _MAGNITUDE[0][1]):
        _, case = envelope_capacity_case(
            calc,
            probes,
            limits,
            vessel=doc.environment.vessel_motion,
            offlead_deg=hoist.offlead_deg,
            sidelead_deg=hoist.sidelead_deg,
            hook_daf=hoist.hook_daf,
            hook_mass_t=hoist.hook_mass_t,
        )
        assert case is not None and case.wind_axis == ""


def test_no_applicable_limit_has_no_case() -> None:
    doc = _envelope_document()
    calc = CraneCalculator(doc)
    cap, case = _envelope(calc, doc, {"boom_hoist": {"T": 0.0}})
    assert case is None
    assert cap.max_allowable_load_kN == float("inf")


def test_envelope_capacity_is_the_first_element() -> None:
    doc = _envelope_document()
    calc = CraneCalculator(doc)
    hoist = _hoist(doc)
    probes = build_probes(calc, HOIST, BOOM_ANGLE_DEG, WIND_M_S, None)
    assert probes is not None
    kwargs = dict(
        vessel=doc.environment.vessel_motion,
        offlead_deg=hoist.offlead_deg,
        sidelead_deg=hoist.sidelead_deg,
        hook_daf=hoist.hook_daf,
        hook_mass_t=hoist.hook_mass_t,
    )
    for limits in [*ENVELOPE_LIMITS, _MAGNITUDE[0][1]]:
        cap, _ = envelope_capacity_case(calc, probes, limits, **kwargs)
        assert envelope_capacity(calc, probes, limits, **kwargs) == cap
