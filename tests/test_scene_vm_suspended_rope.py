"""The Scene on a rules document: the suspended rope rides with the hook load."""

from __future__ import annotations

import pytest

from crane_statics.qml_app.session import SessionState
from crane_statics.qml_app.viewmodels.scene_vm import SceneViewModel
from crane_statics.rules import validate_rules_document
from crane_statics.data.models import ConditionSpec, CraneDocument, VesselMotion
from crane_statics.core import load_document
from tests.rules_docs import GT283, rules_doc
from tests.test_scene_view_model import MockCanvas

HOIST = "MH"
HOOK_T = 50.0
G = 9.81
DAF = 1.3
FALLS_T_PER_M = 20 * 9.17 / 1000.0  # GT283 MH: 20 falls of 9.17 kg/m


def _rules_doc() -> CraneDocument:
    cond = ConditionSpec(
        name="deck", lift="onboard", wind_speed_m_s=0.0, vessel_motion=VesselMotion()
    )
    doc = rules_doc("ABS", cond)
    hoists = [h.model_copy(update={"hook_daf": DAF}) if h.id == HOIST else h for h in doc.hoists]
    doc = doc.model_copy(update={"hoists": hoists})
    validate_rules_document(doc)
    return doc


def _vm(doc: CraneDocument) -> SceneViewModel:
    session = SessionState()
    vm = SceneViewModel(session)
    vm.bindCanvas(MockCanvas())
    session.model.set_document(doc)
    vm.selectHoist(HOIST)
    return vm


def _stored_kN(vm: SceneViewModel) -> float:
    state = vm._model.get_active_hoist_state()
    assert state is not None
    return float(state.scene_state.hook_load_kN)


def _fresh_kN(vm: SceneViewModel) -> float:
    return vm._hoist_state.payload_t_to_hook_force_kN(vm.hookLoadTonnes)


def test_rules_hook_force_follows_the_tackle_and_the_boom_angle() -> None:
    vm = _vm(_rules_doc())
    vm.setHookLoadTonnes(300.0)
    vm.setTackle(40.0)
    assert vm.hookLoadTonnes == 300.0
    assert _stored_kN(vm) == pytest.approx(_fresh_kN(vm), rel=1e-12)
    assert _stored_kN(vm) == pytest.approx(
        DAF * (300.0 + HOOK_T + 40.0 * FALLS_T_PER_M) * G, rel=1e-9
    )
    # The canvas drag path re-derives the force too.
    vm._on_canvas_tackle_changed(60.0)
    assert _stored_kN(vm) == pytest.approx(
        DAF * (300.0 + HOOK_T + 60.0 * FALLS_T_PER_M) * G, rel=1e-9
    )
    vm.setAngle(vm.angle - 2.0)
    assert _stored_kN(vm) == pytest.approx(_fresh_kN(vm), rel=1e-12)
    assert vm.hookLoadTonnes == 300.0


def test_legacy_hook_force_is_not_re_derived_on_a_tackle_change() -> None:
    vm = _vm(load_document(GT283))
    vm.setHookLoadTonnes(300.0)
    before = _stored_kN(vm)
    vm.setTackle(40.0)
    vm._on_canvas_tackle_changed(60.0)
    assert _stored_kN(vm) == before


def _equilibrium(vm: SceneViewModel) -> dict:
    inputs = vm._scene_inputs()
    assert inputs.document_dict is not None
    return vm._presenter.build_drawn_load_sections(
        document_dict=inputs.document_dict,
        analysis_point=inputs.analysis_point,
        node_positions=inputs.node_positions(),
        conditions=inputs.conditions,
    )


def test_rules_scene_equilibrium_check_passes_with_the_hook_paid_out() -> None:
    vm = _vm(_rules_doc())
    vm.setHookLoadTonnes(300.0)
    vm.setTackle(40.0)
    report = _equilibrium(vm)
    assert report["available"]
    failing = [s for s in report["sections"] if not s["passed"]]
    assert not failing, [(s.get("title"), s.get("force_residual")) for s in failing]
    assert report["passed"]


def test_rules_scene_draws_the_suspended_rope_in_the_hook_load() -> None:
    vm = _vm(_rules_doc())
    vm.setHookLoadTonnes(300.0)
    vm.setTackle(40.0)
    inputs = vm._scene_inputs()
    assert inputs.conditions.amplified_rope_hoist_id == HOIST
    assert inputs.document_dict is not None
    from crane_statics.core import drawn_loads

    loads = drawn_loads.build_body_loads(
        inputs.document_dict,
        hoist=drawn_loads.active_hoist_dict(inputs.document_dict, HOIST),
        conditions=inputs.conditions,
        node_positions=inputs.node_positions(),
        analysis_point=inputs.analysis_point,
    )
    by_category = dict(loads.categories)
    hook = by_category[drawn_loads.HOOK_LOAD]
    assert hook and "suspended rope 7.3 t" in hook[0].label
    # No rope-weight arrow at the hook any more: the falls hang in the hook load.
    hook_xz = inputs.node_positions()["__hook__MH"]
    rope = by_category[drawn_loads.ROPE_WEIGHT]
    assert rope
    assert not any(
        abs(v.world_x - hook_xz["x"]) < 1e-9 and abs(v.world_z - hook_xz["z"]) < 1e-9 for v in rope
    )
