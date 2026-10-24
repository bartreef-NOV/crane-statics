"""A chart point's governing case, as Scene inputs, reproduces the chart value."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from crane_statics.calculation.engine import CraneCalculator
from crane_statics.calculation.rope_mass import hook_support_node_id
from crane_statics.calculation.solver.kinematics import KinematicsAdapter
from crane_statics.core import load_document
from crane_statics.core.analysis_cases import analysis_mode_by_name
from crane_statics.core.governing_case import GoverningCase, governing_case
from crane_statics.core.session_model import SceneState
from crane_statics.core.sweep import run_mode_sweep
from crane_statics.core.sweep_cache import (
    ComputeCache,
    ComputeScope,
    LimitResult,
    compute_fingerprint,
    limit_signature,
)
from crane_statics.data.models import CraneDocument

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"
HOIST = "MH"
STEP = 10.0
# MH__rope binds at short outreach, the bearing line load at mid outreach and rear_hinge Fx
# at long outreach; WH__rope does not respond to MH (see test_sweep_incremental).
LIMITS: dict[str, dict] = {
    "MH__rope": {"T": 1500.0},
    "platform_base": {"max_bearing_line_load": 6000.0},
    "rear_hinge": {"Fx": 5000.0},
    "WH__rope": {"T": 100000.0},
}
_MAGNITUDE = {"platform_base"}
_SCENE_FIELDS = set(SceneState.__dataclass_fields__)


@pytest.fixture(scope="module")
def doc() -> CraneDocument:
    document = load_document(EXAMPLE)
    vm = document.environment.vessel_motion
    vm.accel_x_m_s2 = 0.5
    vm.accel_z_m_s2 = 0.8
    vm.pitch_angular_accel_rad_s2 = 0.05
    vm.roll_deg = 2.0
    vm.pitch_deg = 1.5
    document.environment.max_wind_speed_m_s = 20.0
    return document


def _swept(doc: CraneDocument, mode: str) -> tuple[dict[str, Any], ComputeScope]:
    scope = ComputeCache().scope(compute_fingerprint(doc), HOIST, mode)
    payload = run_mode_sweep(doc, HOIST, mode, LIMITS, STEP, {}, compute_scope=scope)
    assert payload is not None and payload["n_points"] > 0
    return payload, scope


@pytest.fixture(scope="module")
def normal(doc: CraneDocument) -> tuple[dict[str, Any], ComputeScope]:
    return _swept(doc, "normal")


def _chart_result(
    doc: CraneDocument, scope: ComputeScope, outreach: float, lid: str
) -> LimitResult:
    """The per-limit result the sweep computed at ``outreach`` (read from its cache)."""
    angle = KinematicsAdapter(doc.model_dump()).outreach_to_angle(outreach, HOIST)
    assert angle is not None

    def missing() -> LimitResult:
        raise AssertionError(f"sweep did not evaluate {lid} at {outreach} m")

    return scope.limit_result(angle, limit_signature(lid, LIMITS[lid]), missing)


def _binding_outreach(payload: dict[str, Any], lid: str) -> float:
    """An outreach where ``lid`` is plotted, preferring one where it governs the curve."""
    series = {row[0]: row[3] for row in payload["limit_series"]}
    curve = dict(payload["curve_data"])
    points = series[lid]
    governing = [o for o, t in points if math.isclose(t, curve.get(o, math.inf), rel_tol=1e-12)]
    candidates = governing or [o for o, _ in points]
    return float(candidates[len(candidates) // 2])


def _scene_load_kN(doc: CraneDocument, case: GoverningCase) -> float:
    """The case solved as the Scene solves it: exact inputs, no envelope."""
    f = case.scene_fields
    hoist = next(h for h in doc.hoists if h.id == HOIST)
    mode = analysis_mode_by_name(hoist, case.mode_name)
    calc = CraneCalculator(doc)
    point = calc.compute_analysis_point(
        f["boom_angle_deg"],
        0.0,
        HOIST,
        wind_speed_m_s=f["wind_speed_m_s"],
        wind_direction=f["wind_direction"],
        accel_x_m_s2=f["accel_x_m_s2"],
        accel_y_m_s2=f["accel_y_m_s2"],
        accel_z_m_s2=f["accel_z_m_s2"],
        pitch_accel_rad_s2=f["pitch_accel_rad_s2"],
        roll_accel_rad_s2=f["roll_accel_rad_s2"],
        offlead_deg=f["offlead_deg"],
        sidelead_deg=f["sidelead_deg"],
        hoist_runtime_overrides=mode.runtime_overrides,
        tackle_length_m=f["tackle_length_m"],
        vessel_roll_deg=f["vessel_roll_deg"],
        vessel_pitch_deg=f["vessel_pitch_deg"],
        crane_slewing_angle_deg=f["crane_slewing_angle_deg"],
    )
    assert point is not None
    cap = calc.compute_allowable_load(
        point,
        {case.limit_id: LIMITS[case.limit_id]},
        hook_daf=hoist.hook_daf,
        hook_mass_t=mode.hook_mass_t,
    )
    return float(cap.max_allowable_load_kN)


@pytest.mark.parametrize("lid", ["MH__rope", "platform_base", "rear_hinge"])
def test_case_hook_load_equals_chart_point(
    doc: CraneDocument, normal: tuple[dict[str, Any], ComputeScope], lid: str
) -> None:
    payload, scope = normal
    outreach = _binding_outreach(payload, lid)
    chart = _chart_result(doc, scope, outreach, lid).load_kN
    case = governing_case(doc, HOIST, "normal", LIMITS, outreach, lid)
    assert case is not None
    assert case.limit_id == lid
    assert case.mode_name == "normal"
    assert case.outreach_m == outreach
    assert set(case.scene_fields) == _SCENE_FIELDS
    assert case.scene_fields["hook_load_auto"] is False
    assert case.scene_fields["wind_direction"] in {"+X", "-X", "+Y", "-Y"}
    assert case.scene_fields["wind_speed_m_s"] == doc.environment.max_wind_speed_m_s
    assert case.scene_fields["hook_load_kN"] == pytest.approx(chart, rel=1e-6)
    scene = _scene_load_kN(doc, case)
    if lid in _MAGNITUDE:
        assert scene == pytest.approx(chart, rel=1e-3)
        assert scene >= chart - 1e-9
    else:
        assert scene == pytest.approx(chart, rel=1e-6)


def test_none_limit_picks_lowest(
    doc: CraneDocument, normal: tuple[dict[str, Any], ComputeScope]
) -> None:
    payload, scope = normal
    picked = []
    for outreach, load_t in (payload["curve_data"][0], payload["curve_data"][-1]):
        results = {lid: _chart_result(doc, scope, outreach, lid) for lid in LIMITS}
        lowest = min(results, key=lambda lid: results[lid].load_kN)
        assert results[lowest].load_t == pytest.approx(load_t, rel=1e-12)  # the combined curve
        case = governing_case(doc, HOIST, "normal", LIMITS, outreach, None)
        assert case is not None
        assert case.limit_id == lowest
        assert case.scene_fields["hook_load_kN"] == pytest.approx(results[lowest].load_kN, rel=1e-6)
        picked.append(case.limit_id)
    assert len(set(picked)) == 2  # a different limit governs at each end


def test_unlimited_returns_none(
    doc: CraneDocument, normal: tuple[dict[str, Any], ComputeScope]
) -> None:
    payload, _scope = normal
    outreach = payload["curve_data"][0][0]
    # Not responsive to the MH hook load: never plotted.
    assert governing_case(doc, HOIST, "normal", LIMITS, outreach, "WH__rope") is None
    for unlimited in ({"MH__rope": {"T": 0.0}}, {"MH__rope": {"T": None}}, {}):
        assert governing_case(doc, HOIST, "normal", unlimited, outreach, None) is None
        assert governing_case(doc, HOIST, "normal", unlimited, outreach, "MH__rope") is None
    assert governing_case(doc, HOIST, "normal", LIMITS, outreach, "no_such_limit") is None
    assert governing_case(doc, HOIST, "normal", LIMITS, 1e6, "MH__rope") is None


@pytest.mark.parametrize("mode_name", ["normal", "split"])
def test_tackle_length_is_mode_value(doc: CraneDocument, mode_name: str) -> None:
    payload, scope = _swept(doc, mode_name)
    lid = "MH__rope"
    outreach = _binding_outreach(payload, lid)
    case = governing_case(doc, HOIST, mode_name, LIMITS, outreach, lid)
    assert case is not None
    assert case.mode_name == mode_name
    # The sweep evaluates the hook at the hoist's lowest hook height.
    doc_dict = doc.model_dump()
    angle = KinematicsAdapter(doc_dict).outreach_to_angle(outreach, HOIST)
    assert angle is not None
    support = KinematicsAdapter(doc_dict).compute_all_node_positions(angle)[
        hook_support_node_id(doc_dict, HOIST)
    ]
    hoist = next(h for h in doc.hoists if h.id == HOIST)
    height = float(hoist.lowest_hook_height_m)  # type: ignore[arg-type]
    expected = float(support["z"]) - min(float(support["z"]), height)
    assert case.scene_fields["tackle_length_m"] == pytest.approx(expected, abs=1e-9)
    assert case.scene_fields["tackle_length_m"] != SceneState().tackle_length_m
    chart = _chart_result(doc, scope, outreach, lid).load_kN
    assert _scene_load_kN(doc, case) == pytest.approx(chart, rel=1e-6)


def test_inapplicable_split_mode_returns_none(doc: CraneDocument) -> None:
    """WH has no split block: like run_mode_sweep, split gives nothing (not a normal case)."""
    wh = next(h for h in doc.hoists if h.id == "WH")
    assert analysis_mode_by_name(wh, "split").name == "normal"
    assert run_mode_sweep(doc, "WH", "split", {}, STEP, {}) is None
    limits = {"WH__rope": {"T": 100000.0}}
    lo, hi = float(wh.outreach_min_m or 0.0), float(wh.outreach_max_m or 0.0)
    outreach = round(0.5 * (lo + hi), 1)
    normal_case = governing_case(doc, "WH", "normal", limits, outreach, "WH__rope")
    assert normal_case is not None and normal_case.mode_name == "normal"
    assert governing_case(doc, "WH", "split", limits, outreach, "WH__rope") is None
    assert governing_case(doc, "WH", "split", limits, outreach, None) is None
