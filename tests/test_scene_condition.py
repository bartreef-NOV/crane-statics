"""The Scene runs under the Load Chart's condition, and a governing case under its own case.

A chart point shown in the Scene must reproduce the chart: the payload the Scene shows is
the chart's load, and the limit that governed reads 100 %. That holds only when the Scene
solves under the condition and profile case that governed (factor, lateral, foundation
scales and the condition's environment), not the document's first condition.
"""

from __future__ import annotations

import pytest

from crane_statics.calculation.engine import get_calculator
from crane_statics.core.governing_case import governing_case
from crane_statics.data.models import CraneDocument, VesselMotion
from crane_statics.qml_app.session import SessionState
from crane_statics.qml_app.viewmodels.chart_vm import ChartViewModel
from crane_statics.qml_app.viewmodels.scene_vm import SceneViewModel
from tests.rules_docs import gale, rules_doc
from tests.test_lift_factor import _rules, _sea
from tests.test_scene_view_model import MockCanvas

HOIST = "MH"
STEP = 4.5
CALM = VesselMotion(accel_x_m_s2=0.3, roll_deg=3.0, pitch_deg=4.0, reference_z_m=-1.0)


def _vms(doc: CraneDocument) -> tuple[SessionState, SceneViewModel, ChartViewModel]:
    session = SessionState()
    scene = SceneViewModel(session)
    scene.bindCanvas(MockCanvas())
    chart = ChartViewModel(session)
    chart.set_scene_view_model(scene)
    chart.setOutreachStep(STEP)
    session.model.set_document(doc)
    chart.selectHoist(HOIST)
    chart._cancel_all()
    return session, scene, chart


def _abs_doc() -> CraneDocument:
    """ABS, an onboard gale first and an offboard sea condition second (EA 90000 kN)."""
    return _rules(rules_doc("ABS", gale(wind=30.0), _sea()), daf=1.0)


def _dnv_doc() -> CraneDocument:
    doc = rules_doc("DNV", gale(wind=30.0), gale("calm", wind=36.0, motion=CALM))
    hoists = [h.model_copy(update={"hook_daf": 1.0}) for h in doc.hoists]
    return doc.model_copy(update={"hoists": hoists})


def _governing_utilization(scene: SceneViewModel, limit_id: str) -> float:
    dl = scene._model.design_limits_by_id[limit_id]
    rows = [*scene._rope_result_rows, *scene._connection_result_rows]
    if dl.kind == "rope":
        matches = [r for r in rows if r.kind == "rope" and r.limit_kN is not None]
        matches = [r for r in matches if r.runtime_id and limit_id.startswith(str(r.runtime_id))]
    else:
        matches = [
            r
            for r in rows
            if r.entity_id == dl.entity_id and r.component == dl.component and r.limit_kN
        ]
    assert matches, limit_id
    return max(float(r.utilization_pct) for r in matches)


def _check_points(scene: SceneViewModel, chart: ChartViewModel, condition: str) -> list:
    doc = scene._model.document
    assert doc is not None
    points = chart.curvePoints
    assert len(points) >= 2
    cases = []
    for x, load_t in (points[0], points[-1]):
        case = governing_case(doc, HOIST, "normal", chart._enabled_limits(), x, None, condition)
        assert case is not None and case.condition_name == condition
        scene.apply_governing_case(case, "Governing case")
        model = scene._model
        assert (model.scene_condition_name, model.scene_case_name) == (
            case.condition_name,
            case.case_name,
        )
        assert scene.hookLoadTonnes == pytest.approx(load_t, rel=1e-6)
        # The limit that governed reads 100 % (a magnitude limit: at most 0.1 % off).
        assert _governing_utilization(scene, case.limit_id) == pytest.approx(100.0, abs=0.15)
        rows = [*scene._rope_result_rows, *scene._connection_result_rows]
        worst = max(float(r.utilization_pct) for r in rows if r.limit_kN)
        assert worst == pytest.approx(100.0, abs=0.15)
        cases.append(case)
    return cases


def test_abs_scene_reproduces_a_point_of_the_second_condition() -> None:
    _session, scene, chart = _vms(_abs_doc())
    chart.setCurrentCondition("sea")
    chart._cancel_all()
    chart.drawBlocking()
    cases = _check_points(scene, chart, "sea")
    assert {c.case_name for c in cases} == {"In-service"}
    assert all(c.hook_lateral is not None for c in cases)
    scene.restoreInputs()
    # Restore puts the Scene back under the chart's condition.
    assert scene._model.scene_condition().name == "sea/In-service"
    chart.shutdown()


def test_dnv_scene_reproduces_case_ii_points_of_the_second_condition() -> None:
    _session, scene, chart = _vms(_dnv_doc())
    chart.setCurrentCondition("calm")
    chart._cancel_all()
    chart.drawBlocking()
    cases = _check_points(scene, chart, "calm")
    assert "Case II" in {c.case_name for c in cases}
    assert all(c.hook_lateral is not None for c in cases if c.case_name == "Case II")
    chart.shutdown()


def test_dnv_scene_reproduces_the_first_condition_too() -> None:
    _session, scene, chart = _vms(_dnv_doc())
    chart.drawBlocking()
    _check_points(scene, chart, "gale")
    chart.shutdown()


def test_the_scene_follows_the_chart_condition_at_its_most_severe_case() -> None:
    session, scene, chart = _vms(_dnv_doc())
    model = session.model
    assert model.scene_condition().name == "gale/Case II"
    state = model.get_active_hoist_state()
    assert state is not None
    assert state.scene_state.wind_speed_m_s == 30.0
    chart.setCurrentCondition("calm")
    chart._cancel_all()
    assert model.scene_condition().name == "calm/Case II"
    # The sliders restart at the condition's case: its wind, its 1.5x heel and trim, no
    # accelerations (DNV Case III is out of scope).
    assert state.scene_state.wind_speed_m_s == 36.0
    assert state.scene_state.vessel_roll_deg == pytest.approx(1.5 * CALM.roll_deg)
    assert state.scene_state.vessel_pitch_deg == pytest.approx(1.5 * CALM.pitch_deg)
    assert state.scene_state.accel_x_m_s2 == 0.0
    # The Scene solves and draws the condition's environment (its motion reference point).
    scene_doc = scene._hoist_state.scene_document()
    assert scene_doc is not None and scene_doc.environment.vessel_motion.reference_z_m == -1.0
    kinematics = scene._kinematics.kinematics()
    assert kinematics is not None
    assert kinematics.doc["environment"]["vessel_motion"]["reference_z_m"] == -1.0
    assert model.document is not None
    assert scene._hoist_state.scene_calculator(model.document).doc is scene_doc
    chart.shutdown()


def test_a_legacy_scene_is_untouched() -> None:
    from tests.test_chart_view_model import EXAMPLE
    from crane_statics.core.io import load_document

    doc = load_document(EXAMPLE)
    session, scene, chart = _vms(doc)
    model = session.model
    assert chart.conditionNames == []
    assert model.scene_condition().spec is None
    assert scene._hoist_state.scene_document() is doc
    assert scene._hoist_state.scene_calculator(doc) is get_calculator(doc)
    kinematics = scene._kinematics.kinematics()
    assert kinematics is not None and kinematics.doc == doc.model_dump()
    before = model.get_active_hoist_state()
    assert before is not None
    wind = before.scene_state.wind_speed_m_s
    scene.follow_chart_condition("default")  # no-op on a legacy document
    assert before.scene_state.wind_speed_m_s == wind
    assert not model.set_scene_condition("x", None, seed=True)
    chart.shutdown()


def test_the_governing_case_label_names_its_condition_and_case() -> None:
    from tests.qt_helpers import wait_until

    _session, scene, chart = _vms(_dnv_doc())
    chart.drawBlocking()
    chart._refresh_timer.stop()
    chart.showGoverningCase("", chart.curvePoints[0][0])
    wait_until(lambda: chart._case_request is None)
    label = scene.governingCaseLabel
    assert label.startswith("Governing case: ") and "(gale / Case " in label
    chart.shutdown()


def test_unknown_condition_falls_back_to_the_first() -> None:
    session, _scene, chart = _vms(_dnv_doc())
    session.model.scene_condition_name = "gone"
    assert session.model.scene_condition().name == "gale/Case II"
    chart.shutdown()


@pytest.mark.parametrize(
    "build, condition, case_name",
    [(_dnv_doc, "calm", "Case II"), (_abs_doc, "sea", "In-service")],
    ids=["dnv-case-ii", "abs-second-condition"],
)
def test_a_governing_lateral_limit_reads_100_percent(build, condition, case_name) -> None:
    """Platform-base Fy responds to the hook lateral only: it governs and reads 100 %."""
    session, scene, chart = _vms(build())
    dl = session.model.design_limits_by_id["platform_base_Fy"]
    dl.enabled, dl.max_kN = True, 2200.0
    session.model.mark_content_changed()
    chart.setCurrentCondition(condition)
    chart._cancel_all()
    chart.drawBlocking()
    cases = _check_points(scene, chart, condition)
    assert {c.limit_id for c in cases} == {"platform_base_Fy"}
    assert {c.case_name for c in cases} == {case_name}
    chart.shutdown()


def test_a_rules_document_does_not_offer_its_placeholder_environment() -> None:
    from crane_statics.core.io import load_document
    from crane_statics.qml_app.models.document_forms import (
        environment_from_conditions,
        set_environment_value,
    )
    from tests.test_chart_view_model import EXAMPLE

    rules = _dnv_doc()
    assert environment_from_conditions(rules)
    assert not set_environment_value(rules, "max_wind_speed_m_s", 99.0)
    assert not set_environment_value(rules, "roll_deg", 9.0)
    assert set_environment_value(rules, "gravity_m_s2", 9.80665)  # not per condition
    legacy = load_document(EXAMPLE)
    assert not environment_from_conditions(legacy)
    assert set_environment_value(legacy, "max_wind_speed_m_s", 99.0)
