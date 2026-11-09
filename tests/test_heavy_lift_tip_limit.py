"""ABS 2-2/11.3 heavy-lift 0.07 g limit on a_v at the boom tip: rejected at load, and a
rules error reaching the app is reported, not raised."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import QUrl

from crane_statics.calculation.engine import get_calculator
from crane_statics.core.io import DocumentIOError, load_document, save_document
from crane_statics.core.lift_factor import LiftFactors
from crane_statics.core.session_model import SessionModel
from crane_statics.core.sweep import run_mode_sweep
from crane_statics.data.models import ConditionSpec, CraneDocument, VesselMotion, payload_hoist_ids
from crane_statics.qml_app.session import SessionState
from crane_statics.qml_app.viewmodels.app_vm import AppViewModel
from crane_statics.rules import RulesValidationError, validate_rules_document
from crane_statics.rules.validation import (
    GRAVITY_M_S2,
    max_support_reach_m,
    tip_vertical_accel_g,
)

ROOT = Path(__file__).parent.parent
ABS_EXAMPLE = ROOT / "examples" / "crane_input_GT283_abs.yaml"
LEGACY_EXAMPLE = ROOT / "examples" / "crane_input_22689.yaml"


def _heavy_doc(accel_z: float, pitch_alpha: float) -> CraneDocument:
    doc = load_document(ABS_EXAMPLE)
    assert doc.rules is not None
    motion = VesselMotion(accel_z_m_s2=accel_z, pitch_angular_accel_rad_s2=pitch_alpha)
    cond = ConditionSpec(name="mild", wind_speed_m_s=10.0, vessel_motion=motion)
    return doc.model_copy(
        update={
            "rules": doc.rules.model_copy(update={"crane_class": "heavy_lift"}),
            "conditions": {"mild": cond},
        }
    )


#: The review's repro: a_z 0.061 g passes the linear check; the tip term does not.
REPRO = (0.6, 0.02)


def _max_reach(doc: CraneDocument) -> float:
    doc_dict = doc.model_dump()
    reaches = [max_support_reach_m(doc_dict, h) for h in payload_hoist_ids(doc)]
    assert all(r is not None for r in reaches)
    return max(r for r in reaches if r is not None)


def _repro_file(tmp_path: Path) -> Path:
    path = tmp_path / "heavy.yaml"
    save_document(_heavy_doc(*REPRO), path)  # without limits: nothing is evaluated
    return path


# --- load-time check ----------------------------------------------------------------------


def test_load_rejects_a_v_above_0_07_g_at_the_largest_tip_reach(tmp_path: Path) -> None:
    with pytest.raises(DocumentIOError) as err:
        load_document(_repro_file(tmp_path))
    message = str(err.value)
    assert "conditions.mild.vessel_motion: a_v" in message
    assert "largest boom-tip reach" in message and "lever arm" in message
    assert "0.07 g for heavy_lift" in message


def test_validation_names_the_condition_a_v_x_and_lever() -> None:
    doc = _heavy_doc(*REPRO)
    with pytest.raises(RulesValidationError) as err:
        validate_rules_document(doc)
    message = str(err.value)
    hoist = next(h for h in payload_hoist_ids(doc) if f"hoists.{h}'s" in message)
    reach = max_support_reach_m(doc.model_dump(), hoist)
    assert reach is not None
    a_v, lever = tip_vertical_accel_g(doc.conditions["mild"].vessel_motion, reach)
    assert f"a_v {a_v:.4g} g" in message
    assert f"(x {reach:g} m, lever arm {lever:g} m)" in message


def test_a_legal_heavy_lift_document_is_unaffected() -> None:
    doc = _heavy_doc(0.3, 0.002)
    a_v, _lever = tip_vertical_accel_g(doc.conditions["mild"].vessel_motion, _max_reach(doc))
    assert a_v < 0.07
    validate_rules_document(doc)
    model = SessionModel()
    model.set_document(doc)
    assert model.document is doc and model.design_limits
    payload = run_mode_sweep(doc, "MH", "normal", {"MH__rope_T": {"T": 1.0e4}}, 10.0, {})
    assert payload is not None and payload["curve_data"]


def test_the_reach_bounds_every_tip_the_profile_sees() -> None:
    """Load-time passes imply the per-point check passes: |support x| <= the reach."""
    doc = load_document(ABS_EXAMPLE)
    factors = LiftFactors(doc, get_calculator(doc))
    doc_dict = doc.model_dump()
    for hoist_id in payload_hoist_ids(doc):
        reach = max_support_reach_m(doc_dict, hoist_id)
        assert reach is not None
        tips = [abs(factors.support_x_m(hoist_id, a)) for a in range(-10, 91, 5)]
        assert max(tips) <= reach + 1e-9
        assert max(tips) > 0.9 * reach  # and the bound is not slack


def test_a_document_just_inside_the_bound_sweeps_every_payload_hoist() -> None:
    accel_z = 0.3
    probe = _heavy_doc(accel_z, 0.0)
    alpha = (0.0699 * GRAVITY_M_S2 - accel_z) / _max_reach(probe)
    doc = _heavy_doc(accel_z, alpha)
    validate_rules_document(doc)
    for hoist in doc.hoists:
        if hoist.id not in payload_hoist_ids(doc):
            continue
        limits = {f"{hoist.rope_id}_T": {"T": 1.0e4}}
        assert run_mode_sweep(doc, hoist.id, "normal", limits, 10.0, {}) is not None


# --- the app reports a rules error instead of raising -------------------------------------


def test_set_document_raises_before_changing_the_session() -> None:
    model = SessionModel()
    legal = _heavy_doc(0.3, 0.0)
    model.set_document(legal)
    limits = list(model.design_limits)
    with pytest.raises(RulesValidationError):
        model.set_document(_heavy_doc(*REPRO))  # not validated: set_document checks
    assert model.document is legal
    assert model.design_limits == limits


def _app() -> tuple[AppViewModel, list[tuple[str, str]]]:
    app_vm = AppViewModel(SessionState())
    messages: list[tuple[str, str]] = []
    app_vm.notification.connect(lambda msg, level: messages.append((msg, level)))
    return app_vm, messages


def test_opening_the_repro_reports_the_error(tmp_path: Path) -> None:
    app_vm, messages = _app()
    app_vm.openPath(str(LEGACY_EXAMPLE))
    before = app_vm.session.model.document
    app_vm.open(QUrl.fromLocalFile(str(_repro_file(tmp_path))))
    assert app_vm.session.model.document is before
    assert messages and messages[-1][1] == "error"
    assert "0.07 g for heavy_lift" in messages[-1][0]


def test_applying_an_unvalidated_repro_reports_the_error() -> None:
    app_vm, messages = _app()
    app_vm._apply_document(_heavy_doc(*REPRO), None, "applied")
    assert app_vm.session.model.document is None
    assert messages and messages[-1][1] == "error"
    assert "0.07 g for heavy_lift" in messages[-1][0]


def test_saving_the_repro_reports_the_error(tmp_path: Path) -> None:
    app_vm, messages = _app()
    app_vm.openPath(str(LEGACY_EXAMPLE))
    model = app_vm.session.model
    model.document = _heavy_doc(*REPRO)  # as if it were open
    target = tmp_path / "out.yaml"
    assert app_vm._write(target) is False
    assert messages and messages[-1][1] == "error"
    assert "0.07 g for heavy_lift" in messages[-1][0]


def test_the_scene_status_names_a_rules_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from crane_statics.qml_app.viewmodels.scene_vm import SceneViewModel
    from tests.test_scene_view_model import MockCanvas

    session = SessionState()
    scene = SceneViewModel(session)
    scene.bindCanvas(MockCanvas())
    session.model.set_document(_heavy_doc(0.3, 0.0))
    messages: list[str] = []
    scene.statusMessage.connect(messages.append)
    error = "conditions.mild.vessel_motion: a_v 0.08 g at the boom tip exceeds 0.07 g"

    def fail() -> None:
        raise RulesValidationError(error)

    monkeypatch.setattr(scene._calculator, "compute_current_result_rows", fail)
    scene._after_state_changed()
    assert messages == [error]


def test_the_chart_status_names_the_sweep_error() -> None:
    from crane_statics.qml_app.viewmodels.chart_vm import ChartViewModel

    session = SessionState()
    chart = ChartViewModel(session)
    session.model.set_document(_heavy_doc(0.3, 0.0))
    key = chart._wanted_key()
    assert key is not None
    chart._on_sweep_failed("conditions.mild.vessel_motion: a_v 0.08 g", key)
    assert chart.statusText == "⚠ Sweep error: conditions.mild.vessel_motion: a_v 0.08 g"
    chart.shutdown()
