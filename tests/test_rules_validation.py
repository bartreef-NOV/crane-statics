"""Document validation for ABS/DNV rules documents."""

import pytest

from crane_statics.core.io import DocumentIOError, load_document
from crane_statics.data.models import ConditionSpec, RulesSpec, VesselMotion, payload_hoist_ids
from crane_statics.rules import RulesValidationError, validate_rules_document
from tests.rules_docs import load_v13
from tests.authored_helpers import example_path

G = 9.81
GT283 = example_path("crane_input_GT283.yaml")


def _base():
    return load_v13(GT283)


def _listing(doc, conditions):
    """``conditions`` each listing the hoists of ``doc``'s first condition if it lists none."""
    hoists = next(iter(doc.conditions.values())).hoists
    return {
        n: c if c.hoists else c.model_copy(update={"hoists": dict(hoists)})
        for n, c in conditions.items()
    }


def _doc(standard="ABS", crane_class="offshore", conditions=None, ea=False, speed=False):
    doc = _base()
    ropes = [r.model_copy(update={"ea_kN": 40000.0} if ea else {}) for r in doc.ropes]
    hoists = [
        h.model_copy(update={"max_hoisting_speed_m_s": 0.3} if speed else {}) for h in doc.hoists
    ]
    return doc.model_copy(
        update={
            "rules": RulesSpec(standard=standard, crane_class=crane_class),
            "conditions": _listing(
                doc, conditions or {"c": ConditionSpec(name="c", wind_speed_m_s=10.0)}
            ),
            "ropes": ropes,
            "hoists": hoists,
        }
    )


def _offboard(**kw):
    base = dict(
        name="o",
        lift="offboard",
        wind_speed_m_s=10.0,
        significant_wave_height_m=2.0,
        v_in_m_s=0.5,
        v_t_m_s=0.5,
    )
    base.update(kw)
    return {"o": ConditionSpec(**base)}


def _fails(doc, *fragments):
    with pytest.raises(RulesValidationError) as info:
        validate_rules_document(doc)
    msg = str(info.value)
    assert "\n" not in msg
    for f in fragments:
        assert f in msg
    return msg


def test_legacy_document_skipped():
    validate_rules_document(_base())


def test_dnv_with_crane_class_rejected():
    _fails(_doc("DNV", "offshore"), "rules.crane_class")


def test_dnv_without_crane_class_ok():
    validate_rules_document(_doc("DNV", None))


def test_abs_without_crane_class_rejected():
    _fails(_doc("ABS", None), "rules.crane_class")


def test_heavy_lift_rejects_offboard():
    _fails(
        _doc(crane_class="heavy_lift", conditions=_offboard(), ea=True, speed=True),
        "conditions.o.lift",
        "offshore",
    )


@pytest.mark.parametrize("axis", ["x", "y", "z"])
def test_heavy_lift_accel_boundary(axis):
    def cond(g):
        motion = VesselMotion(**{f"accel_{axis}_m_s2": -g * G})
        return {"c": ConditionSpec(name="c", wind_speed_m_s=5.0, vessel_motion=motion)}

    validate_rules_document(_doc(crane_class="heavy_lift", conditions=cond(0.07)))
    _fails(
        _doc(crane_class="heavy_lift", conditions=cond(0.0701)),
        f"accel_{axis}_m_s2",
        "offshore",
    )


def test_offshore_accel_unrestricted():
    motion = VesselMotion(accel_z_m_s2=5.0)
    conds = {"c": ConditionSpec(name="c", wind_speed_m_s=5.0, vessel_motion=motion)}
    validate_rules_document(_doc(conditions=conds))


@pytest.mark.parametrize("field", ["v_in_m_s", "v_t_m_s", "significant_wave_height_m"])
def test_offboard_missing_field(field):
    _fails(_doc(conditions=_offboard(**{field: None}), ea=True, speed=True), field)


def test_offboard_valid_passes():
    validate_rules_document(_doc(conditions=_offboard(), ea=True, speed=True))


def test_offboard_payload_hoist_missing_speed():
    _fails(_doc(conditions=_offboard(), ea=True, speed=False), "max_hoisting_speed_m_s")


def test_offboard_missing_ea():
    _fails(_doc(conditions=_offboard(), ea=False, speed=True), "ea_kN")


def test_offboard_boom_hoist_missing_ea_only():
    doc = _doc(conditions=_offboard(), ea=True, speed=True)
    boom_rope = next(r.id for r in doc.ropes if r.tension_mode == "solve")
    ropes = [r.model_copy(update={"ea_kN": None}) if r.id == boom_rope else r for r in doc.ropes]
    boom = next(h.id for h in doc.hoists if h.rope_id == boom_rope)
    _fails(doc.model_copy(update={"ropes": ropes}), f"hoists.{boom}")


def test_onboard_only_needs_no_ea_or_speed():
    validate_rules_document(_doc(ea=False, speed=False))


def test_hook_height_override_bounds():
    doc = _doc()
    hid = payload_hoist_ids(doc)[0]
    hoist = next(h for h in doc.hoists if h.id == hid)
    lowest = hoist.lowest_hook_height_m
    top = lowest + hoist.max_hook_travel_m
    inside = {"c": ConditionSpec(name="c", wind_speed_m_s=1.0, hook_height_override_m=lowest)}
    validate_rules_document(doc.model_copy(update={"conditions": _listing(doc, inside)}))
    for bad in (lowest - 1.0, top + 1.0):
        conds = {"c": ConditionSpec(name="c", wind_speed_m_s=1.0, hook_height_override_m=bad)}
        _fails(
            doc.model_copy(update={"conditions": _listing(doc, conds)}), "hook_height_override_m"
        )
    # A condition that does not list a hoist does not bound its override by that hoist.
    unlisted = ConditionSpec(name="c", wind_speed_m_s=1.0, hook_height_override_m=lowest - 1.0)
    validate_rules_document(doc.model_copy(update={"conditions": {"c": unlisted}}))


def test_load_document_runs_validation(tmp_path):
    from crane_statics.core.io import save_document

    path = tmp_path / "bad.yaml"
    save_document(_doc("DNV", "offshore"), path)
    with pytest.raises(DocumentIOError, match="rules.crane_class"):
        load_document(path)
