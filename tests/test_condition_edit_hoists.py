"""Editing which payload hoists each condition lists, their settings there, and the
conditions each load-chart point names (authored schema v13).

Every edit here is checked against the authored contract: a document that exports to a
valid v13 authored document still does after the edit (or the edit is refused and the
document left as it was).
"""

from __future__ import annotations

from typing import Callable

import pytest
from PyQt6.QtCore import Qt

from crane_statics.core.document_edit import (
    DocumentEditError,
    DocumentEditor,
    authored_document_error,
    build_contractual_point,
    build_payload_hoist,
)
from crane_statics.core.io import DocumentIOError, save_document
from crane_statics.core.hoist_daf import daf_is_derived, entered_daf, shown_daf
from crane_statics.core.session_model import SessionModel
from crane_statics.data import AuthoredDocument, document_to_authored_form, normalize_document
from crane_statics.data.models import ConditionSpec, CraneDocument
from crane_statics.qml_app.session import SessionState
from crane_statics.qml_app.viewmodels.model_vm import ModelViewModel
from tests.authored_helpers import load_example

RULES_EXAMPLE = "crane_input_22689_abs.yaml"  # ABS, two conditions, splitable MH
RULES_LESS_EXAMPLE = "crane_input_GT283.yaml"  # no rules, one condition ``default``
HOIST = "MH"


def _two_conditions(example: str) -> CraneDocument:
    """``example`` with exactly two conditions: a rules-less one gets a duplicate of its
    ``default``, one with more (22689_abs has three) keeps its first two."""
    doc = load_example(example)
    editor = DocumentEditor(doc)
    if len(doc.conditions) < 2:
        editor.duplicate_condition(next(iter(doc.conditions)))
    for name in list(doc.conditions)[2:]:
        editor.delete_condition(name)
    return doc


@pytest.fixture(params=[RULES_EXAMPLE, RULES_LESS_EXAMPLE], ids=["rules", "rules-less"])
def doc(request) -> CraneDocument:
    return _two_conditions(request.param)


def _names(doc: CraneDocument) -> tuple[str, str]:
    first, second = list(doc.conditions)[:2]
    return first, second


def _other_hoist(doc: CraneDocument) -> str:
    """A payload hoist other than ``HOIST`` usable in the first condition."""
    first = next(iter(doc.conditions.values()))
    return next(hid for hid in first.hoists if hid != HOIST)


def _exports_valid(doc: CraneDocument) -> dict:
    """The authored form of ``doc``, which must validate against the v13 models."""
    authored = document_to_authored_form(doc)
    AuthoredDocument.model_validate(authored)
    return authored


def _points(doc: CraneDocument, condition: str, hoist_id: str = HOIST, split: bool = False):
    entry = doc.conditions[condition].hoists[hoist_id]
    points = entry.split_contractual_points if split else entry.contractual_points
    return [(p.outreach_m, p.load_t) for p in points]


def _refused(doc: CraneDocument, action: Callable[[DocumentEditor], object]) -> str:
    snapshot = doc.model_dump_json()
    with pytest.raises(DocumentEditError) as caught:
        action(DocumentEditor(doc))
    assert doc.model_dump_json() == snapshot
    return str(caught.value)


# ----------------------------------------------------------------------
# DAF entry rule (one place for "1.0 vs None")
# ----------------------------------------------------------------------


def test_daf_entry_and_display_rule():
    assert shown_daf(None) == 1.0 and shown_daf(1.3) == 1.3
    assert entered_daf(None, rules=True) is None and entered_daf(None, rules=False) is None
    # Without rules 1.0 is the default factor: stored as no override.
    assert entered_daf(1.0, rules=False) is None
    assert entered_daf(1.2, rules=False) == 1.2
    # Under rules an entered 1.0 is an explicit override of the derived factor.
    assert entered_daf(1.0, rules=True) == 1.0


def test_daf_is_derived_only_under_rules_without_an_override():
    rules = load_example(RULES_EXAMPLE)
    rules_less = load_example(RULES_LESS_EXAMPLE)
    assert daf_is_derived(rules, None) and not daf_is_derived(rules, 1.0)
    assert not daf_is_derived(rules_less, None) and not daf_is_derived(rules_less, 1.2)


# ----------------------------------------------------------------------
# set_condition_hoist
# ----------------------------------------------------------------------


def test_set_condition_hoist_updates_settings_and_keeps_points(doc):
    _first, second = _names(doc)
    before = _points(doc, second)
    DocumentEditor(doc).set_condition_hoist(second, HOIST, 1.5, 0.5, 1.2)
    entry = doc.conditions[second].hoists[HOIST]
    assert (entry.offlead_deg, entry.sidelead_deg, entry.daf) == (1.5, 0.5, 1.2)
    assert _points(doc, second) == before
    DocumentEditor(doc).set_condition_hoist(second, HOIST, 1.5, 0.5, None)
    assert doc.conditions[second].hoists[HOIST].daf is None
    _exports_valid(doc)


def test_set_condition_hoist_on_an_unlisted_hoist_copies_the_points_of_the_first_listing():
    doc = _two_conditions(RULES_EXAMPLE)
    first, second = _names(doc)
    editor = DocumentEditor(doc)
    editor.remove_condition_hoist(second, HOIST)
    assert HOIST not in doc.conditions[second].hoists

    editor.set_condition_hoist(second, HOIST, 2.0, 0.0, None)

    entry = doc.conditions[second].hoists[HOIST]
    assert (entry.offlead_deg, entry.sidelead_deg, entry.daf) == (2.0, 0.0, None)
    assert _points(doc, second) == _points(doc, first)
    assert _points(doc, second, split=True) == _points(doc, first, split=True)
    assert _points(doc, second, split=True)  # MH is splitable: split points copied too
    _exports_valid(doc)


@pytest.mark.parametrize(
    "args",
    [
        ("nope", HOIST, 1.0, 0.0, None),  # unknown condition
        (None, "nope", 1.0, 0.0, None),  # unknown hoist
        (None, "BH", 1.0, 0.0, None),  # the boom hoist cannot be listed
        (None, HOIST, -1.0, 0.0, None),
        (None, HOIST, 1.0, -0.5, None),
        (None, HOIST, 1.0, 0.0, 0.5),
    ],
    ids=["condition", "hoist", "boom", "offlead", "sidelead", "daf"],
)
def test_set_condition_hoist_refusals_leave_the_document_unchanged(doc, args):
    condition = args[0] if args[0] is not None else _names(doc)[1]
    _refused(doc, lambda e: e.set_condition_hoist(condition, *args[1:]))


# ----------------------------------------------------------------------
# remove_condition_hoist
# ----------------------------------------------------------------------


def test_remove_condition_hoist_drops_the_entry_and_its_point_tags(doc):
    first, second = _names(doc)
    DocumentEditor(doc).remove_condition_hoist(second, HOIST)
    assert HOIST not in doc.conditions[second].hoists
    assert all(second not in p.conditions for p in DocumentEditor(doc).tagged_chart(HOIST))
    _exports_valid(doc)


def test_remove_condition_hoist_refuses_the_last_condition_listing_it(doc):
    first, second = _names(doc)
    DocumentEditor(doc).remove_condition_hoist(second, HOIST)
    message = _refused(doc, lambda e: e.remove_condition_hoist(first, HOIST))
    assert HOIST in message and first in message


def test_remove_condition_hoist_refuses_to_empty_a_condition(doc):
    _first, second = _names(doc)
    editor = DocumentEditor(doc)
    listed = list(doc.conditions[second].hoists)
    for hoist_id in listed[:-1]:
        editor.remove_condition_hoist(second, hoist_id)
    message = _refused(doc, lambda e: e.remove_condition_hoist(second, listed[-1]))
    assert second in message


def test_remove_condition_hoist_refuses_an_unlisted_or_unknown_one(doc):
    _first, second = _names(doc)
    _refused(doc, lambda e: e.remove_condition_hoist(second, "nope"))
    _refused(doc, lambda e: e.remove_condition_hoist("nope", HOIST))
    DocumentEditor(doc).remove_condition_hoist(second, HOIST)
    _refused(doc, lambda e: e.remove_condition_hoist(second, HOIST))


# ----------------------------------------------------------------------
# tagged_chart / set_point_conditions
# ----------------------------------------------------------------------


def test_tagged_chart_lists_each_point_once_with_its_conditions(doc):
    first, second = _names(doc)
    chart = DocumentEditor(doc).tagged_chart(HOIST)
    assert [(p.outreach_m, p.load_t) for p in chart] == _points(doc, first)
    assert all(p.conditions == (first, second) for p in chart)


def test_set_point_conditions_untags_and_retags_a_point(doc):
    first, second = _names(doc)
    original = _points(doc, second)
    editor = DocumentEditor(doc)

    editor.set_point_conditions(HOIST, False, 0, [first])

    assert _points(doc, second) == original[1:]
    assert _points(doc, first) == original
    assert editor.tagged_chart(HOIST)[0].conditions == (first,)
    _exports_valid(doc)

    editor.set_point_conditions(HOIST, False, 0, [second, first])

    assert _points(doc, second) == original
    assert editor.tagged_chart(HOIST)[0].conditions == (first, second)
    _exports_valid(doc)


def test_set_point_conditions_on_split_points():
    doc = _two_conditions(RULES_EXAMPLE)
    first, second = _names(doc)
    original = _points(doc, second, split=True)
    DocumentEditor(doc).set_point_conditions(HOIST, True, 1, [second])
    assert _points(doc, first, split=True) == original[:1] + original[2:]
    assert _points(doc, second, split=True) == original
    assert _points(doc, first) == _points(doc, second)  # normal chart untouched
    _exports_valid(doc)


@pytest.mark.parametrize(
    "conditions",
    [[], ["nope"], ["{first}", "{first}"]],
    ids=["empty", "undefined", "repeated"],
)
def test_set_point_conditions_refuses_bad_names(doc, conditions):
    first, _second = _names(doc)
    names = [c.format(first=first) for c in conditions]
    _refused(doc, lambda e: e.set_point_conditions(HOIST, False, 0, names))


def test_set_point_conditions_refuses_a_condition_not_listing_the_hoist(doc):
    first, second = _names(doc)
    DocumentEditor(doc).remove_condition_hoist(second, HOIST)
    message = _refused(doc, lambda e: e.set_point_conditions(HOIST, False, 0, [first, second]))
    assert second in message and HOIST in message


def test_set_point_conditions_refuses_to_leave_a_condition_without_points():
    doc = _two_conditions(RULES_LESS_EXAMPLE)
    first, second = _names(doc)
    # GT283's trolley has a single chart point, named by both conditions.
    assert len(_points(doc, second, "trolley")) == 1
    message = _refused(doc, lambda e: e.set_point_conditions("trolley", False, 0, [first]))
    assert second in message and "trolley" in message


def test_set_point_conditions_refuses_a_bad_index_or_hoist(doc):
    first, _second = _names(doc)
    _refused(doc, lambda e: e.set_point_conditions(HOIST, False, 99, [first]))
    _refused(doc, lambda e: e.set_point_conditions("nope", False, 0, [first]))
    _refused(doc, lambda e: e.set_point_conditions("BH", False, 0, [first]))


def test_split_points_of_a_non_splitable_hoist_are_refused():
    doc = _two_conditions(RULES_LESS_EXAMPLE)
    first, _second = _names(doc)
    _refused(doc, lambda e: e.set_point_conditions(HOIST, True, 0, [first]))


# ----------------------------------------------------------------------
# Condition rename / duplicate / delete / add
# ----------------------------------------------------------------------


def test_rename_condition_keeps_its_hoist_entries_and_point_tags(doc):
    first, second = _names(doc)
    entries = {hid: e.model_dump() for hid, e in doc.conditions[second].hoists.items()}
    editor = DocumentEditor(doc)
    renamed = doc.conditions[second].model_copy(update={"name": "renamed"})
    editor.update_condition(second, renamed)
    assert {hid: e.model_dump() for hid, e in doc.conditions["renamed"].hoists.items()} == entries
    assert all(p.conditions == (first, "renamed") for p in editor.tagged_chart(HOIST))
    _exports_valid(doc)


def test_update_condition_without_hoists_keeps_the_current_entries(doc):
    first, _second = _names(doc)
    entries = {hid: e.model_dump() for hid, e in doc.conditions[first].hoists.items()}
    DocumentEditor(doc).update_condition(first, ConditionSpec(name=first, wind_speed_m_s=12.0))
    assert doc.conditions[first].wind_speed_m_s == 12.0
    assert {hid: e.model_dump() for hid, e in doc.conditions[first].hoists.items()} == entries


def test_duplicate_condition_copies_entries_and_tags_its_points(doc):
    first, second = _names(doc)
    editor = DocumentEditor(doc)
    copy = editor.duplicate_condition(first)
    assert doc.conditions[copy].hoists == doc.conditions[first].hoists
    assert doc.conditions[copy].hoists[HOIST] is not doc.conditions[first].hoists[HOIST]
    assert all(copy in p.conditions for p in editor.tagged_chart(HOIST))
    _exports_valid(doc)


def test_delete_condition_drops_its_point_tags(doc):
    first, second = _names(doc)
    editor = DocumentEditor(doc)
    editor.delete_condition(second)
    assert all(p.conditions == (first,) for p in editor.tagged_chart(HOIST))
    _exports_valid(doc)


def test_last_condition_cannot_be_deleted(doc):
    first, second = _names(doc)
    DocumentEditor(doc).delete_condition(second)
    with pytest.raises(ValueError):
        DocumentEditor(doc).delete_condition(first)
    assert list(doc.conditions) == [first]


def test_delete_condition_refuses_to_strand_a_hoist(doc):
    first, second = _names(doc)
    DocumentEditor(doc).remove_condition_hoist(second, HOIST)
    message = _refused(doc, lambda e: e.delete_condition(first))
    assert HOIST in message


def test_add_condition_without_hoists_lists_those_of_the_first_condition(doc):
    first, _second = _names(doc)
    DocumentEditor(doc).add_condition(ConditionSpec(name="extra", wind_speed_m_s=10.0))
    assert doc.conditions["extra"].hoists == doc.conditions[first].hoists
    assert doc.conditions["extra"].wind_speed_m_s == 10.0
    _exports_valid(doc)


# ----------------------------------------------------------------------
# Hoist add / delete
# ----------------------------------------------------------------------


def test_add_hoist_makes_it_usable_in_every_condition_with_zero_offlead(doc):
    from tests.test_document_edit import _payload_hoist_like

    DocumentEditor(doc).add_hoist(_payload_hoist_like(doc, HOIST, "NEW"))
    for spec in doc.conditions.values():
        entry = spec.hoists["NEW"]
        assert (entry.offlead_deg, entry.sidelead_deg, entry.daf) == (0.0, 0.0, None)
        assert entry.contractual_points == [] and entry.split_contractual_points == []
        assert "BH" not in spec.hoists


def test_set_condition_hoist_usable(doc):
    first, second = _names(doc)
    editor = DocumentEditor(doc)
    assert not editor.set_condition_hoist_usable(second, HOIST, True)  # already usable
    assert editor.set_condition_hoist_usable(second, HOIST, False)
    assert HOIST not in doc.conditions[second].hoists
    assert not editor.set_condition_hoist_usable(second, HOIST, False)
    assert editor.set_condition_hoist_usable(second, HOIST, True)
    entry = doc.conditions[second].hoists[HOIST]
    assert (entry.offlead_deg, entry.sidelead_deg, entry.daf) == (0.0, 0.0, None)
    assert _points(doc, second) == _points(doc, first)
    _exports_valid(doc)
    _refused(doc, lambda e: e.set_condition_hoist_usable(second, "BH", True))
    _refused(doc, lambda e: e.set_condition_hoist_usable(second, "nope", False))


def test_enter_condition_hoist_stores_the_daf_under_the_documents_rules():
    rules = _two_conditions(RULES_EXAMPLE)
    DocumentEditor(rules).enter_condition_hoist(_names(rules)[1], HOIST, 1.0, 0.0, 1.0)
    assert rules.conditions[_names(rules)[1]].hoists[HOIST].daf == 1.0  # explicit override
    rules_less = _two_conditions(RULES_LESS_EXAMPLE)
    DocumentEditor(rules_less).enter_condition_hoist(_names(rules_less)[1], HOIST, 1.0, 0.0, 1.0)
    assert rules_less.conditions[_names(rules_less)[1]].hoists[HOIST].daf is None


def test_the_guard_refuses_an_edit_that_would_stop_the_document_saving(doc):
    from crane_statics.data.models import ConditionHoist

    first, _second = _names(doc)
    # A hoist entry without chart points: the authored contract rejects it.
    edited = doc.conditions[first].model_copy(
        update={"hoists": {HOIST: ConditionHoist(offlead_deg=0.0)}}
    )
    message = _refused(doc, lambda e: e.update_condition(first, edited))
    assert HOIST in message


# The guard on a document that already does not save (a hoist just added): an edit is
# refused when it adds a problem the document did not have, and accepted otherwise.


def _with_new_hoist() -> tuple[CraneDocument, DocumentEditor]:
    doc = load_example("crane_input_GT283_abs.yaml")
    editor = DocumentEditor(doc)
    support = next(h for h in doc.hoists if h.id == HOIST).support_node_id
    editor.add_hoist(build_payload_hoist("NEW", support or ""))
    return doc, editor


def test_the_guard_refuses_a_new_problem_while_the_document_does_not_save():
    doc, editor = _with_new_hoist()
    assert authored_document_error(doc)  # NEW is not charted yet
    # MH's last point in onboard_sea: the condition would list MH with no point.
    while len(editor.contractual_points(HOIST, "normal", "onboard_sea")) > 1:
        editor.delete_contractual_point(HOIST, 0, "normal", "onboard_sea")
    message = _refused(doc, lambda e: e.delete_contractual_point(HOIST, 0, "normal", "onboard_sea"))
    assert "'onboard_sea' lists hoist 'MH'" in message
    # A point the schema rejects outright (field-level problem) is refused too.
    message = _refused(
        doc,
        lambda e: e.add_contractual_point(
            "AH", build_contractual_point(-1.0, -2.0), "normal", "onboard_sea"
        ),
    )
    assert "AH" in message and "outreach_m" in message


def test_the_guard_accepts_a_step_towards_valid_while_the_document_does_not_save():
    doc, editor = _with_new_hoist()
    before = authored_document_error(doc)
    editor.add_chart_point("NEW", False, build_contractual_point(10.0, 5.0), ["onboard_sea"])
    after = authored_document_error(doc)
    assert _points(doc, "onboard_sea", "NEW") == [(10.0, 5.0)]
    assert after and set(after) < set(before)


def test_authored_document_error_lists_every_problem():
    doc, editor = _with_new_hoist()
    problems = authored_document_error(doc)
    # NEW's own fields (no reeving, no chart) and each condition listing it uncharted.
    assert any("NEW" in p and "reeving" in p for p in problems)
    assert any("NEW" in p and "load_chart" in p for p in problems)
    for name in doc.conditions:
        assert any(f"condition {name!r} lists hoist 'NEW'" in p for p in problems)
    assert len(problems) == len(set(problems))


def test_saving_a_document_that_does_not_save_lists_every_problem(tmp_path):
    doc, _editor = _with_new_hoist()
    with pytest.raises(DocumentIOError) as caught:
        save_document(doc, tmp_path / "out.yaml")
    lines = str(caught.value).splitlines()
    assert lines == authored_document_error(doc)
    assert len(lines) > 1


def test_delete_hoist_drops_its_entries_from_every_condition(doc):
    other = _other_hoist(doc)
    DocumentEditor(doc).delete_hoist(other)
    assert all(other not in spec.hoists for spec in doc.conditions.values())
    _exports_valid(doc)


# ----------------------------------------------------------------------
# Every edit keeps the document a valid v13 authored document, and the authored
# form re-reads to the same per-condition settings and charts.
# ----------------------------------------------------------------------


def _condition_view(doc: CraneDocument) -> dict:
    return {
        name: {
            hid: (
                e.offlead_deg,
                e.sidelead_deg,
                e.daf,
                [(p.outreach_m, p.load_t) for p in e.contractual_points],
                [(p.outreach_m, p.load_t) for p in e.split_contractual_points],
            )
            for hid, e in spec.hoists.items()
        }
        for name, spec in doc.conditions.items()
    }


def _remove_then_relist(editor: DocumentEditor, _first: str, second: str, other: str) -> None:
    editor.remove_condition_hoist(second, other)
    editor.set_condition_hoist(second, other, 0.0, 0.0, None)


EDITS: dict[str, Callable[[DocumentEditor, str, str, str], object]] = {
    "set_condition_hoist": lambda e, a, b, o: e.set_condition_hoist(b, HOIST, 1.5, 0.5, 1.2),
    "remove_then_relist": _remove_then_relist,
    "set_point_conditions": lambda e, a, b, o: e.set_point_conditions(HOIST, False, 0, [a]),
    "rename_condition": lambda e, a, b, o: e.update_condition(
        b, e.document.conditions[b].model_copy(update={"name": "renamed"})
    ),
    "duplicate_condition": lambda e, a, b, o: e.duplicate_condition(a),
    "delete_condition": lambda e, a, b, o: e.delete_condition(b),
    "add_condition": lambda e, a, b, o: e.add_condition(
        ConditionSpec(name="extra", wind_speed_m_s=10.0)
    ),
    "delete_hoist": lambda e, a, b, o: e.delete_hoist(o),
}


@pytest.mark.parametrize("edit", list(EDITS), ids=list(EDITS))
def test_every_edit_round_trips_through_a_valid_authored_document(doc, edit):
    first, second = _names(doc)
    EDITS[edit](DocumentEditor(doc), first, second, _other_hoist(doc))
    reread = normalize_document(_exports_valid(doc))
    assert _condition_view(reread) == _condition_view(doc)


# ----------------------------------------------------------------------
# Rules-less documents: offboard lifts need rules
# ----------------------------------------------------------------------


def test_rules_less_condition_cannot_be_offboard():
    doc = load_example(RULES_LESS_EXAMPLE)
    spec = doc.conditions["default"]
    offboard = spec.model_copy(
        update={
            "lift": "offboard",
            "significant_wave_height_m": 1.5,
            "v_in_m_s": 0.6,
            "v_t_m_s": 0.3,
        }
    )
    message = _refused(doc, lambda e: e.update_condition("default", offboard))
    assert "rules" in message
    added = offboard.model_copy(update={"name": "other"})
    _refused(doc, lambda e: e.add_condition(added))


def test_rules_less_condition_accepts_the_other_fields():
    # Only the lift is rules-only in the authored contract (the sea-state fields are inert).
    doc = load_example(RULES_LESS_EXAMPLE)
    spec = doc.conditions["default"].model_copy(update={"significant_wave_height_m": 1.5})
    DocumentEditor(doc).update_condition("default", spec)
    _exports_valid(doc)


# ----------------------------------------------------------------------
# SessionModel.set_scene_condition
# ----------------------------------------------------------------------


def test_set_scene_condition_rejects_an_unknown_name():
    doc = _two_conditions(RULES_EXAMPLE)
    first, second = _names(doc)
    session = SessionModel()
    session.set_document(doc)
    before = (session.scene_condition_name, session.scene_case_name)

    assert not session.set_scene_condition("nope", None, seed=True)

    assert (session.scene_condition_name, session.scene_case_name) == before
    assert session.set_scene_condition(second, None, seed=True)
    assert session.scene_condition_name == second


def test_a_renamed_condition_is_followed_by_the_scene_and_renamed_condition():
    doc = _two_conditions(RULES_EXAMPLE)
    first, second = _names(doc)
    session = SessionModel()
    session.set_document(doc)
    assert session.set_scene_condition(second, None, seed=True)

    for old, new in ((second, "b"), ("b", "c")):
        renamed = doc.conditions[old].model_copy(update={"name": new})
        DocumentEditor(doc).update_condition(old, renamed)
        session.condition_renamed(old, new)

    assert session.scene_condition_name == "c"
    assert session.scene_condition().condition_name == "c"
    assert session.renamed_condition(second) == "c" and session.renamed_condition("b") == "c"
    assert session.renamed_condition(first) == first  # still in the document
    assert session.renamed_condition("unknown") == "unknown"
    assert session.renamed_condition(None) is None
    session.set_document(doc)  # another document: no renames carried over
    assert session.renamed_condition(second) == second


# ----------------------------------------------------------------------
# Model view model: the per-condition hoist table and the tagged chart points
# ----------------------------------------------------------------------


def _vm(example: str = RULES_EXAMPLE):
    session = SessionState()
    vm = ModelViewModel(session)
    session.model.set_document(_two_conditions(example))
    session.model.history._window = 0.0
    failed: list[str] = []
    edited: list[int] = []
    vm.editFailed.connect(failed.append)
    vm.modelEdited.connect(lambda: edited.append(1))
    return session, vm, failed, edited


def test_condition_hoist_rows_under_rules_flag_a_derived_daf():
    session, vm, _failed, _edited = _vm(RULES_EXAMPLE)
    doc = session.model.document
    first, _second = _names(doc)
    rows = vm.conditionHoists
    assert [r["hoistId"] for r in rows] == ["MH", "WH", "SH"]
    mh = rows[0]
    entry = doc.conditions[first].hoists["MH"]
    assert mh["usable"] is True
    assert mh["offleadDeg"] == entry.offlead_deg and mh["sideleadDeg"] == entry.sidelead_deg
    assert mh["daf"] == entry.daf
    assert mh["dafDerived"] is (entry.daf is None)
    assert mh["dafShown"] == (None if entry.daf is None else entry.daf)


def test_condition_hoist_rows_without_rules_show_the_constant_daf():
    _session, vm, _failed, _edited = _vm(RULES_LESS_EXAMPLE)
    rows = {r["hoistId"]: r for r in vm.conditionHoists}
    assert set(rows) == {"MH", "AH", "trolley"}
    assert all(r["dafDerived"] is False for r in rows.values())
    assert all(isinstance(r["dafShown"], float) for r in rows.values())


def test_set_condition_hoist_slot_edits_the_selected_condition():
    session, vm, failed, edited = _vm(RULES_EXAMPLE)
    doc = session.model.document
    _first, second = _names(doc)
    vm.selectCondition(second)
    vm.setConditionHoist("MH", 3.0, 1.0, 1.25)
    entry = session.model.document.conditions[second].hoists["MH"]
    assert (entry.offlead_deg, entry.sidelead_deg, entry.daf) == (3.0, 1.0, 1.25)
    assert failed == [] and edited == [1]
    row = next(r for r in vm.conditionHoists if r["hoistId"] == "MH")
    assert (row["offleadDeg"], row["daf"], row["dafDerived"]) == (3.0, 1.25, False)
    # None (cleared) puts the derived factor back.
    vm.setConditionHoist("MH", 3.0, 1.0, None)
    assert session.model.document.conditions[second].hoists["MH"].daf is None
    assert session.model.undo()
    assert session.model.document.conditions[second].hoists["MH"].daf == 1.25


def test_set_condition_hoist_slot_failure_signals_and_changes_nothing():
    session, vm, failed, edited = _vm(RULES_EXAMPLE)
    snapshot = session.model.document.model_dump_json()
    vm.setConditionHoist("MH", -1.0, 0.0, None)
    assert len(failed) == 1 and edited == []
    assert session.model.document.model_dump_json() == snapshot


def test_usable_checkbox_and_remove_slot():
    session, vm, failed, _edited = _vm(RULES_EXAMPLE)
    doc = session.model.document
    first, second = _names(doc)
    vm.selectCondition(second)
    vm.setConditionHoistUsable("WH", False)
    assert "WH" not in session.model.document.conditions[second].hoists
    row = next(r for r in vm.conditionHoists if r["hoistId"] == "WH")
    assert row["usable"] is False and row["offleadDeg"] is None
    vm.setConditionHoistUsable("WH", True)
    entry = session.model.document.conditions[second].hoists["WH"]
    assert entry.offlead_deg == 0.0
    assert _points(session.model.document, second, "WH") == _points(
        session.model.document, first, "WH"
    )
    vm.removeConditionHoist("WH")
    assert "WH" not in session.model.document.conditions[second].hoists
    assert failed == []
    vm.selectCondition(first)
    vm.removeConditionHoist("WH")  # the last condition listing WH: refused
    assert failed and "WH" in session.model.document.conditions[first].hoists


def test_chart_point_rows_and_set_point_conditions_slot():
    session, vm, failed, _edited = _vm(RULES_EXAMPLE)
    doc = session.model.document
    first, second = _names(doc)
    vm.selectHoist("MH")
    rows = vm.chartPoints
    assert len(rows) == len(_points(doc, first))
    assert rows[0]["index"] == 0 and rows[0]["conditions"] == [first, second]
    assert (rows[0]["outreachM"], rows[0]["loadT"]) == _points(doc, first)[0]

    vm.setPointConditions(0, [first])
    assert failed == []
    assert vm.chartPoints[0]["conditions"] == [first]
    assert len(_points(session.model.document, second)) == len(rows) - 1

    vm.setContractualMode("split")
    split_rows = vm.chartPoints
    assert len(split_rows) == len(_points(doc, first, split=True))
    vm.setPointConditions(0, ["nope"])
    assert failed


def test_explicit_daf_one_through_the_slot():
    # Under rules an entered 1.0 overrides the derived factor; without rules it is the
    # default factor and stored as no override.
    session, vm, failed, _edited = _vm(RULES_EXAMPLE)
    vm.setConditionHoist("MH", 0.0, 0.0, 1.0)
    first = _names(session.model.document)[0]
    assert session.model.document.conditions[first].hoists["MH"].daf == 1.0
    row = next(r for r in vm.conditionHoists if r["hoistId"] == "MH")
    assert (row["daf"], row["dafShown"], row["dafDerived"]) == (1.0, 1.0, False)
    vm.setConditionHoist("MH", 0.0, 0.0, "")
    assert session.model.document.conditions[first].hoists["MH"].daf is None

    session, vm, failed, _edited = _vm(RULES_LESS_EXAMPLE)
    vm.setConditionHoist("MH", 0.0, 0.0, 1.0)
    first = _names(session.model.document)[0]
    assert session.model.document.conditions[first].hoists["MH"].daf is None
    assert failed == []


@pytest.mark.parametrize("stored", [1.0, None], ids=["explicit-1.0", "derived"])
def test_an_unrelated_hoist_form_edit_keeps_the_condition_daf(stored):
    """Regression: an explicit DAF 1.0 under rules was reset to None (derived) by any
    edit of the hoist form. The form no longer carries the DAF or the lead limits at
    all (they are edited per condition), so it cannot touch them."""
    session, vm, failed, _edited = _vm(RULES_EXAMPLE)
    first, second = _names(session.model.document)
    vm.setConditionHoist("MH", 0.0, 0.0, stored)
    row = [h["id"] for h in vm.hoistList].index("MH")
    fields = vm.hoistFields(row)
    assert not {"hook_daf", "offlead_deg", "sidelead_deg"} & set(fields)
    mass = fields["lower_block_mass_t"]
    others = session.model.document.conditions[second].hoists["MH"].model_dump()

    assert vm.setHoistField(row, "lower_block_mass_t", mass + 1.0)

    doc = session.model.document
    assert next(h for h in doc.hoists if h.id == "MH").lower_block_mass_t == mass + 1.0
    entry = doc.conditions[first].hoists["MH"]
    assert (entry.offlead_deg, entry.sidelead_deg, entry.daf) == (0.0, 0.0, stored)
    assert doc.conditions[second].hoists["MH"].model_dump() == others
    # A DAF key sent with the form (an old caller) is not a field of the hoist: ignored.
    assert vm.updateHoist(row, {**vm.hoistFields(row), "hook_daf": 1.4, "offlead_deg": 9.0})
    entry = session.model.document.conditions[first].hoists["MH"]
    assert (entry.offlead_deg, entry.daf) == (0.0, stored)
    assert failed == []


# ----------------------------------------------------------------------
# Load-chart points carrying their conditions: add / update / delete
# ----------------------------------------------------------------------


def test_add_chart_point_goes_to_each_named_condition_in_outreach_order(doc):
    first, second = _names(doc)
    editor = DocumentEditor(doc)
    before_first, before_second = _points(doc, first), _points(doc, second)
    outreach = (before_first[0][0] + before_first[1][0]) / 2.0

    editor.add_chart_point(HOIST, False, build_contractual_point(outreach, 7.5), [second])

    assert _points(doc, first) == before_first
    assert _points(doc, second) == [before_second[0], (outreach, 7.5), *before_second[1:]]
    chart = editor.tagged_chart(HOIST)
    assert (chart[1].outreach_m, chart[1].load_t, chart[1].conditions) == (outreach, 7.5, (second,))
    _exports_valid(doc)


def test_add_chart_point_defaults_to_every_condition_listing_the_hoist(doc):
    first, second = _names(doc)
    editor = DocumentEditor(doc)
    assert editor.usable_conditions(HOIST) == [first, second]
    far = max(p[0] for p in _points(doc, first)) + 10.0

    editor.add_chart_point(HOIST, False, build_contractual_point(far, 1.0))

    assert _points(doc, first)[-1] == _points(doc, second)[-1] == (far, 1.0)
    assert editor.tagged_chart(HOIST)[-1].conditions == (first, second)
    _exports_valid(doc)

    # Not usable in ``second`` any more: the default names ``first`` only.
    editor.remove_condition_hoist(second, HOIST)
    assert editor.usable_conditions(HOIST) == [first]
    editor.add_chart_point(HOIST, False, build_contractual_point(far + 1.0, 0.5))
    assert editor.tagged_chart(HOIST)[-1].conditions == (first,)
    _exports_valid(doc)


def test_add_chart_point_on_the_split_chart():
    doc = _two_conditions(RULES_EXAMPLE)
    first, second = _names(doc)
    normal = _points(doc, first)
    DocumentEditor(doc).add_chart_point(HOIST, True, build_contractual_point(0.5, 3.0), [first])
    assert _points(doc, first, split=True)[0] == (0.5, 3.0)
    assert (0.5, 3.0) not in _points(doc, second, split=True)
    assert _points(doc, first) == normal
    _exports_valid(doc)


@pytest.mark.parametrize(
    "conditions",
    [[], ["nope"], ["{first}", "{first}"]],
    ids=["empty", "undefined", "repeated"],
)
def test_add_chart_point_refuses_bad_names(doc, conditions):
    first, _second = _names(doc)
    names = [c.format(first=first) for c in conditions]
    point = build_contractual_point(30.0, 1.0)
    _refused(doc, lambda e: e.add_chart_point(HOIST, False, point, names))


def test_add_chart_point_refuses_a_condition_not_listing_the_hoist_or_a_bad_chart(doc):
    first, second = _names(doc)
    DocumentEditor(doc).remove_condition_hoist(second, HOIST)
    point = build_contractual_point(30.0, 1.0)
    message = _refused(doc, lambda e: e.add_chart_point(HOIST, False, point, [second]))
    assert second in message and HOIST in message
    _refused(doc, lambda e: e.add_chart_point("BH", False, point, [first]))
    _refused(doc, lambda e: e.add_chart_point("nope", False, point, [first]))


def test_update_chart_point_changes_it_in_every_condition_naming_it(doc):
    first, second = _names(doc)
    editor = DocumentEditor(doc)
    original = _points(doc, first)
    new = (original[0][0] + 0.25, original[0][1] - 1.0)

    editor.update_chart_point(HOIST, False, 0, build_contractual_point(*new))

    assert _points(doc, first) == _points(doc, second) == [new, *original[1:]]
    assert editor.tagged_chart(HOIST)[0].conditions == (first, second)
    _exports_valid(doc)


def test_update_chart_point_can_retag_in_the_same_edit(doc):
    first, second = _names(doc)
    editor = DocumentEditor(doc)
    original = _points(doc, first)
    new = (original[0][0], original[0][1] + 5.0)

    editor.update_chart_point(HOIST, False, 0, build_contractual_point(*new), [second])

    assert _points(doc, first) == original[1:]
    assert _points(doc, second) == [new, *original[1:]]
    _exports_valid(doc)


def test_update_chart_point_refusals_change_nothing(doc):
    first, _second = _names(doc)
    point = build_contractual_point(30.0, 1.0)
    _refused(doc, lambda e: e.update_chart_point(HOIST, False, 99, point))
    _refused(doc, lambda e: e.update_chart_point(HOIST, False, 0, point, []))
    _refused(doc, lambda e: e.update_chart_point(HOIST, False, 0, point, ["nope"]))
    # A negative outreach does not save (authored ``outreach_m >= 0``): the guard refuses.
    bad = build_contractual_point(-5.0, 1.0)
    assert "outreach_m" in _refused(doc, lambda e: e.update_chart_point(HOIST, False, 0, bad))
    assert "outreach_m" in _refused(doc, lambda e: e.add_chart_point(HOIST, False, bad, [first]))


def test_delete_chart_point_removes_it_from_every_condition_naming_it(doc):
    first, second = _names(doc)
    editor = DocumentEditor(doc)
    original = _points(doc, first)

    editor.delete_chart_point(HOIST, False, 0)

    assert _points(doc, first) == _points(doc, second) == original[1:]
    _exports_valid(doc)


def test_delete_chart_point_refuses_to_leave_a_condition_without_points():
    doc = _two_conditions(RULES_LESS_EXAMPLE)
    _first, second = _names(doc)
    message = _refused(doc, lambda e: e.delete_chart_point("trolley", False, 0))
    assert "trolley" in message
    _refused(doc, lambda e: e.delete_chart_point(HOIST, False, 99))
    _refused(doc, lambda e: e.delete_chart_point(HOIST, True, 0))  # not splitable


def test_chart_point_edits_use_the_saved_files_point_indices():
    """The indices the editor takes are the saved file's: after a merge where the two
    conditions order their points differently, index k is the k-th authored point."""
    doc = _two_conditions(RULES_EXAMPLE)
    first, second = _names(doc)
    editor = DocumentEditor(doc)
    editor.set_point_conditions(HOIST, False, 0, [first])  # point 0 names only ``first``
    saved = document_to_authored_form(doc)
    authored = saved["model_definition"]["hoists"][HOIST]["load_chart"]
    chart = editor.tagged_chart(HOIST)
    assert [(p["outreach_m"], p["load_t"], tuple(p["conditions"])) for p in authored] == [
        (p.outreach_m, p.load_t, p.conditions) for p in chart
    ]
    editor.delete_chart_point(HOIST, False, 1)
    assert _points(doc, second) == [(p.outreach_m, p.load_t) for p in chart[2:]]


# ----------------------------------------------------------------------
# Model view model: the tagged chart-point table
# ----------------------------------------------------------------------


def test_chart_point_table_rows_carry_their_conditions():
    session, vm, failed, _edited = _vm(RULES_EXAMPLE)
    first, second = _names(session.model.document)
    vm.selectHoist(HOIST)
    model = vm.contractualModel
    assert model.rowCount() == len(vm.chartPoints) == len(_points(session.model.document, first))
    headers = [model.headerData(c, Qt.Orientation.Horizontal) for c in range(model.columnCount())]
    assert headers == ["Outreach (m)", "Load (t)", "Conditions"]
    conditions = model.data(model.index(0, 2))
    assert conditions == f"{first}, {second}"
    assert not model.isCellEditable(0, 2) and model.isCellEditable(0, 0)
    assert vm.chartConditionNames == [first, second]
    assert vm.chartPointFields(0)["conditions"] == [first, second]
    assert failed == []


def test_chart_point_slots_add_update_delete():
    session, vm, failed, edited = _vm(RULES_EXAMPLE)
    first, second = _names(session.model.document)
    vm.selectHoist(HOIST)
    original = _points(session.model.document, first)
    rows = len(vm.chartPoints)

    vm.addChartPoint({"outreach_m": 200.0, "load_t": 1.0})  # default: every condition
    assert vm.chartPoints[-1]["conditions"] == [first, second]
    vm.addChartPoint({"outreach_m": 210.0, "load_t": 0.5, "conditions": [second]})
    assert vm.chartPoints[-1]["conditions"] == [second]
    assert len(vm.chartPoints) == rows + 2

    assert vm.updateChartPoint(0, {"outreach_m": original[0][0], "load_t": 1234.0})
    assert _points(session.model.document, second)[0] == (original[0][0], 1234.0)
    # A cell edit goes through the same slot, in every condition naming the point.
    model = vm.contractualModel
    assert model.commitCell(0, 1, "1500.000")
    assert _points(session.model.document, first)[0] == (original[0][0], 1500.0)

    vm.deleteChartPoint(len(vm.chartPoints) - 1)
    assert (210.0, 0.5) not in _points(session.model.document, second)
    assert failed == []
    assert session.model.undo()
    assert (210.0, 0.5) in _points(session.model.document, second)


def test_chart_point_slot_refusals_signal_and_change_nothing():
    session, vm, failed, edited = _vm(RULES_LESS_EXAMPLE)
    vm.selectHoist("trolley")
    snapshot = session.model.document.model_dump_json()
    vm.deleteChartPoint(0)  # the only point of both conditions
    vm.addChartPoint({"outreach_m": 1.0, "load_t": 1.0, "conditions": ["nope"]})
    assert not vm.updateChartPoint(5, {"outreach_m": 1.0, "load_t": 1.0})
    assert len(failed) == 3 and edited == []
    assert session.model.document.model_dump_json() == snapshot


def test_chart_point_table_ignores_the_scene_condition():
    """The table is the saved chart: switching the Scene's condition changes nothing."""
    session, vm, _failed, _edited = _vm(RULES_EXAMPLE)
    vm.selectHoist(HOIST)
    rows = vm.chartPoints
    _first, second = _names(session.model.document)
    assert session.model.set_scene_condition(second, None, seed=True)
    assert vm.chartPoints == rows


def test_per_condition_point_edits_refuse_what_would_not_save(doc):
    """The Load Chart workspace edits one condition's chart: validity-guarded too (were:
    a negative outreach or load, or deleting every point of a hoist there, accepted and
    the document no longer saved)."""
    first, _second = _names(doc)
    count = len(_points(doc, first))
    bad = build_contractual_point(-5.0, 1.0)
    negative_load = build_contractual_point(30.0, -1.0)
    _refused(doc, lambda e: e.add_contractual_point(HOIST, bad, "normal", first))
    _refused(doc, lambda e: e.add_contractual_point(HOIST, negative_load, "normal", first))
    _refused(doc, lambda e: e.update_contractual_point(HOIST, 0, bad, "normal", first))

    editor = DocumentEditor(doc)
    for _ in range(count - 1):
        editor.delete_contractual_point(HOIST, 0, "normal", first)
    assert len(_points(doc, first)) == 1
    # The last point of the hoist there: refused.
    message = _refused(doc, lambda e: e.delete_contractual_point(HOIST, 0, "normal", first))
    assert HOIST in message and first in message


def test_per_condition_add_goes_in_outreach_order(doc):
    first, second = _names(doc)
    before = _points(doc, first)
    outreach = (before[0][0] + before[1][0]) / 2.0
    DocumentEditor(doc).add_contractual_point(
        HOIST, build_contractual_point(outreach, 9.0), "normal", first
    )
    assert _points(doc, first) == [before[0], (outreach, 9.0), *before[1:]]
    assert _points(doc, second) == before
    _exports_valid(doc)


def test_chart_view_model_reports_a_refused_point_edit():
    from crane_statics.qml_app.viewmodels.chart_vm import ChartViewModel

    session = SessionState()
    vm = ChartViewModel(session)
    session.model.set_document(load_example(RULES_LESS_EXAMPLE))
    session.model.select_payload_hoist("trolley")  # one chart point in ``default``
    assert vm.selectedHoistId == "trolley"
    snapshot = session.model.document.model_dump_json()
    vm.deleteContractualPoint(0)
    assert "trolley" in vm.statusText
    vm.addContractualPoint({"outreach_m": -3.0, "load_t": 1.0})
    assert "outreach_m" in vm.statusText
    assert session.model.document.model_dump_json() == snapshot
    assert not session.model.dirty
    vm.shutdown()


def test_has_rules_follows_the_document():
    _session, vm, _failed, _edited = _vm(RULES_EXAMPLE)
    assert vm.hasRules is True
    _session, vm, _failed, _edited = _vm(RULES_LESS_EXAMPLE)
    assert vm.hasRules is False
