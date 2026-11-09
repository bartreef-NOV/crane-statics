"""ABS 2-2/11.3 heavy-lift 0.07 g limit on a_v at the boom tip: checked at load over each
payload hoist's rated angles (operating range and contractual points), so nothing later
raises it; a rules error that still reaches the app is reported, not raised."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import QUrl

from crane_statics.calculation.engine import get_calculator
from crane_statics.calculation.solver.kinematics import KinematicsAdapter, hoist_angle_bounds
from crane_statics.core.analysis_cases import iter_hoist_analysis_modes
from crane_statics.core.io import DocumentIOError, load_document, save_document
from crane_statics.core.lift_factor import LiftFactors
from crane_statics.core.limit_factory import DesignLimitFactory
from crane_statics.core.session_model import SessionModel
from crane_statics.core.sweep import run_mode_sweep
from crane_statics.data.models import (
    ConditionSpec,
    CraneDocument,
    Hoist,
    VesselMotion,
    payload_hoist_ids,
)
from crane_statics.qml_app.session import SessionState
from crane_statics.qml_app.viewmodels.app_vm import AppViewModel
from crane_statics.rules import RulesValidationError, validate_rules_document
from crane_statics.rules.validation import (
    GRAVITY_M_S2,
    HEAVY_LIFT_MAX_ACCEL_G,
    heavy_lift_tip_reach_m,
    tip_vertical_accel_g,
)

ROOT = Path(__file__).parent.parent
ABS_EXAMPLE = ROOT / "examples" / "crane_input_GT283_abs.yaml"
LEGACY_EXAMPLE = ROOT / "examples" / "crane_input_22689.yaml"
EXCESS = "0.07 g for heavy_lift"
A_Z = 0.3


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


def _payload_hoists(doc: CraneDocument) -> list[Hoist]:
    ids = set(payload_hoist_ids(doc))
    return [h for h in doc.hoists if h.id in ids]


def _reach(doc: CraneDocument, hoist: Hoist) -> float:
    reach = heavy_lift_tip_reach_m(doc, hoist)
    assert reach is not None
    return reach


def _threshold_alpha(reach_m: float) -> float:
    """The pitch angular acceleration putting a_v at exactly 0.07 g at ``reach_m``."""
    return (HEAVY_LIFT_MAX_ACCEL_G * GRAVITY_M_S2 - A_Z) / reach_m


def _rated_angles(doc: CraneDocument, hoist: Hoist) -> tuple[float, float]:
    kin = KinematicsAdapter(doc.model_dump())
    lo, hi = hoist_angle_bounds(kin, hoist.id, hoist.outreach_min_m, hoist.outreach_max_m)
    for point in (*hoist.contractual_points, *hoist.split_contractual_points):
        angle = kin.outreach_to_angle(point.outreach_m, hoist.id)
        if angle is not None:
            lo, hi = min(lo, angle), max(hi, angle)
    return lo, hi


def _repro_file(tmp_path: Path) -> Path:
    path = tmp_path / "heavy.yaml"
    save_document(_heavy_doc(*REPRO), path)  # without limits: nothing is evaluated
    return path


def _sweep_warnings(doc: CraneDocument, hoist: Hoist) -> list[str]:
    """Every provenance warning of every mode's sweep of ``hoist`` (none may raise)."""
    warnings: list[str] = []
    for mode in iter_hoist_analysis_modes(hoist):
        limits = {f"{hoist.rope_id}_T": {"T": 1.0e4}}
        payload = run_mode_sweep(doc, hoist.id, mode.name, limits, 2.5, {})
        assert payload is not None
        warnings += [w for _x, _r, ws, _c in payload["provenance"] for w in ws]
    return warnings


# --- the load-time bound ------------------------------------------------------------------


def test_the_reach_is_the_largest_tip_over_the_rated_angles() -> None:
    """Tight: sampled over the hoist's rated angles, the support x reaches the bound."""
    doc = load_document(ABS_EXAMPLE)
    factors = LiftFactors(doc, get_calculator(doc))
    reaches = {}
    for hoist in _payload_hoists(doc):
        reach = _reach(doc, hoist)
        lo, hi = _rated_angles(doc, hoist)
        steps = 400
        tips = [
            abs(factors.support_x_m(hoist.id, lo + (hi - lo) * i / steps)) for i in range(steps + 1)
        ]
        assert max(tips) <= reach * (1.0 + 1e-12)
        assert max(tips) >= 0.99 * reach
        reaches[hoist.id] = reach
    # GT283: the boom tips of the operating ranges, not the full boom.
    assert reaches["MH"] < 30.0 and reaches["AH"] < 80.0 and reaches["trolley"] < 80.0


def test_the_review_repro_with_a_small_angular_acceleration_loads() -> None:
    doc = _heavy_doc(0.3, 0.005)
    validate_rules_document(doc)
    for hoist in _payload_hoists(doc):
        assert not any(EXCESS in w for w in _sweep_warnings(doc, hoist)), hoist.id


def test_load_rejects_a_v_above_0_07_g_at_the_largest_tip_reach(tmp_path: Path) -> None:
    with pytest.raises(DocumentIOError) as err:
        load_document(_repro_file(tmp_path))
    message = str(err.value)
    assert "conditions.mild.vessel_motion: a_v" in message
    assert "largest boom-tip reach in its operating range" in message
    assert "lever arm" in message and EXCESS in message


def test_validation_names_the_condition_a_v_and_the_real_reach() -> None:
    doc = _heavy_doc(*REPRO)
    with pytest.raises(RulesValidationError) as err:
        validate_rules_document(doc)
    message = str(err.value)
    hoist = next(h for h in _payload_hoists(doc) if f"hoists.{h.id}'s" in message)
    reach = _reach(doc, hoist)
    a_v, lever = tip_vertical_accel_g(doc.conditions["mild"].vessel_motion, reach)
    assert f"a_v {a_v:.4g} g" in message
    assert f"(x {reach:g} m, lever arm {lever:g} m)" in message


@pytest.mark.parametrize("hoist_id", ["MH", "AH", "trolley"])
def test_load_check_passing_means_no_later_check_fails(hoist_id: str) -> None:
    """Invariant, per payload hoist at its own threshold: just below it, sweeps of every
    mode (contractual points included) run without the 0.07 g excess; just above, the
    document is rejected at load."""
    probe = _heavy_doc(A_Z, 0.0)
    hoist = next(h for h in _payload_hoists(probe) if h.id == hoist_id)
    alpha = _threshold_alpha(_reach(probe, hoist))

    below = _heavy_doc(A_Z, 0.999 * alpha)
    hoist = next(h for h in below.hoists if h.id == hoist_id)
    assert not any(EXCESS in w for w in _sweep_warnings(below, hoist))
    with pytest.raises(RulesValidationError, match=EXCESS):
        validate_rules_document(_heavy_doc(A_Z, 1.001 * alpha))


def test_a_document_just_inside_the_bound_opens_sweeps_and_shows() -> None:
    """Load check passed: set_document (limit auto-set), every sweep and the Scene at every
    hoist and at a free angle beyond the operating range raise nothing."""
    from crane_statics.qml_app.viewmodels.scene_vm import SceneViewModel
    from tests.test_scene_view_model import MockCanvas

    probe = _heavy_doc(A_Z, 0.0)
    alpha = _threshold_alpha(max(_reach(probe, h) for h in _payload_hoists(probe)))
    doc = _heavy_doc(A_Z, 0.999 * alpha)
    validate_rules_document(doc)
    for hoist in _payload_hoists(doc):
        assert not any(EXCESS in w for w in _sweep_warnings(doc, hoist)), hoist.id

    session = SessionState()
    scene = SceneViewModel(session)
    scene.bindCanvas(MockCanvas())
    session.model.set_document(doc)
    assert session.model.design_limits
    for hoist in _payload_hoists(doc):
        session.model.select_payload_hoist(hoist.id)
        scene.setAngle(0.0)  # the Scene's free angle, beyond the rated range
        assert scene._analysis_point is not None, hoist.id


def test_beyond_the_rated_range_the_profile_warns_instead_of_raising() -> None:
    doc = _heavy_doc(*REPRO)  # not validated
    for hoist in _payload_hoists(doc):
        warnings = _sweep_warnings(doc, hoist)
        assert any(EXCESS in w and "outside the hoist's operating range" in w for w in warnings)


# --- the app reports a rules error instead of raising -------------------------------------


def _raise_rules_error(*_args: object, **_kwargs: object) -> None:
    raise RulesValidationError("conditions.mild.vessel_motion: a rules error")


def test_set_document_raises_before_changing_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = SessionModel()
    legal = _heavy_doc(A_Z, 0.0)
    model.set_document(legal)
    limits = list(model.design_limits)
    monkeypatch.setattr(DesignLimitFactory, "create_for_document", _raise_rules_error)
    with pytest.raises(RulesValidationError):
        model.set_document(_heavy_doc(A_Z, 0.001))
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
    assert EXCESS in messages[-1][0]


def test_a_rules_error_on_apply_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    app_vm, messages = _app()
    monkeypatch.setattr(DesignLimitFactory, "create_for_document", _raise_rules_error)
    app_vm._apply_document(_heavy_doc(A_Z, 0.0), None, "applied")
    assert app_vm.session.model.document is None
    assert messages and messages[-1] == (
        "Failed to open document: conditions.mild.vessel_motion: a rules error",
        "error",
    )


def test_a_rules_error_on_save_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app_vm, messages = _app()
    app_vm.openPath(str(LEGACY_EXAMPLE))
    monkeypatch.setattr(DesignLimitFactory, "saved_limits_for", _raise_rules_error)
    assert app_vm._write(tmp_path / "out.yaml") is False  # save_document wraps it
    assert messages and messages[-1][1] == "error"
    assert "a rules error" in messages[-1][0]


def test_the_scene_status_names_a_rules_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from crane_statics.qml_app.viewmodels.scene_vm import SceneViewModel
    from tests.test_scene_view_model import MockCanvas

    session = SessionState()
    scene = SceneViewModel(session)
    scene.bindCanvas(MockCanvas())
    session.model.set_document(_heavy_doc(A_Z, 0.0))
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
    session.model.set_document(_heavy_doc(A_Z, 0.0))
    key = chart._wanted_key()
    assert key is not None
    chart._on_sweep_failed("conditions.mild.vessel_motion: a_v 0.08 g", key)
    assert chart.statusText == "⚠ Sweep error: conditions.mild.vessel_motion: a_v 0.08 g"
    chart.shutdown()
