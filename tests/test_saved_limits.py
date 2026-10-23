"""Design limits that differ from the defaults are saved with the document."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from crane_statics.core import load_document, save_document
from crane_statics.core.io import DocumentIOError
from crane_statics.core.limit_factory import DesignLimitFactory

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"
ROPE_LIMIT = "MH__rope_T"


def _by_id(limits):
    return {limit.id: limit for limit in limits}


def _model_definition(path: Path) -> dict[str, Any]:
    return cast(
        "dict[str, Any]", yaml.safe_load(path.read_text(encoding="utf-8"))["model_definition"]
    )


def _with_limits(tmp_path: Path, limits: dict) -> Path:
    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    data["model_definition"]["limits"] = limits
    path = tmp_path / "limited.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_documents_without_a_limits_block_get_the_default_catalog():
    doc = load_document(EXAMPLE)

    assert doc.saved_limits == {}
    defaults = DesignLimitFactory.create_default(doc)
    assert [
        (lim.id, lim.max_kN, lim.enabled) for lim in DesignLimitFactory.create_for_document(doc)
    ] == [(lim.id, lim.max_kN, lim.enabled) for lim in defaults]


def test_saved_limits_override_the_defaults_and_leave_the_rest(tmp_path):
    saved = {ROPE_LIMIT: {"capacity_kN": 1234.5}, "rear_hinge_Fx": {"capacity_kN": 99.0}}
    doc = load_document(
        _with_limits(tmp_path, {**saved, "rear_hinge_Fz": {"capacity_kN": 5.0, "enabled": False}})
    )

    limits = _by_id(DesignLimitFactory.create_for_document(doc))
    defaults = _by_id(DesignLimitFactory.create_default(doc))

    assert (limits[ROPE_LIMIT].max_kN, limits[ROPE_LIMIT].enabled) == (1234.5, True)
    assert (limits["rear_hinge_Fx"].max_kN, limits["rear_hinge_Fx"].enabled) == (99.0, True)
    assert (limits["rear_hinge_Fz"].max_kN, limits["rear_hinge_Fz"].enabled) == (5.0, False)
    assert limits["front_hinge_Fx"].max_kN == defaults["front_hinge_Fx"].max_kN


def test_unchanged_limits_are_not_saved(tmp_path):
    doc = load_document(EXAMPLE)
    out = tmp_path / "out.yaml"

    save_document(doc, out, limits=DesignLimitFactory.create_for_document(doc))

    assert "limits" not in _model_definition(out)


def test_edited_limits_survive_a_save_and_load(tmp_path):
    doc = load_document(EXAMPLE)
    limits = DesignLimitFactory.create_for_document(doc)
    by_id = _by_id(limits)
    by_id[ROPE_LIMIT].max_kN = 4321.0
    by_id["rear_hinge_Fx"].max_kN = 77.0
    by_id["rear_hinge_Fx"].enabled = True
    by_id["front_hinge_Fz"].enabled = True
    by_id["front_hinge_Fz"].max_kN = 12.0
    out = tmp_path / "out.yaml"

    save_document(doc, out, limits=limits)

    assert set(_model_definition(out)["limits"]) == {ROPE_LIMIT, "rear_hinge_Fx", "front_hinge_Fz"}
    reloaded = _by_id(DesignLimitFactory.create_for_document(load_document(out)))
    assert reloaded[ROPE_LIMIT].max_kN == 4321.0
    assert reloaded["rear_hinge_Fx"].max_kN == 77.0
    assert (reloaded["front_hinge_Fz"].max_kN, reloaded["front_hinge_Fz"].enabled) == (12.0, True)


def test_a_limit_edited_back_to_its_default_is_dropped(tmp_path):
    doc = load_document(_with_limits(tmp_path, {ROPE_LIMIT: {"capacity_kN": 1.0}}))
    limits = DesignLimitFactory.create_default(doc)
    out = tmp_path / "out.yaml"

    save_document(doc, out, limits=limits)

    assert "limits" not in _model_definition(out)


def test_saving_without_session_limits_keeps_the_loaded_ones(tmp_path):
    doc = load_document(_with_limits(tmp_path, {ROPE_LIMIT: {"capacity_kN": 250.0}}))
    out = tmp_path / "out.yaml"

    save_document(doc, out)

    assert _model_definition(out)["limits"] == {ROPE_LIMIT: {"capacity_kN": 250.0, "enabled": True}}


@pytest.mark.parametrize(
    "entry", [{"capacity_kN": -1.0}, {"enabled": True}, {"capacity_kN": 1.0, "x": 1}]
)
def test_invalid_limit_entries_are_rejected(tmp_path, entry):
    with pytest.raises(DocumentIOError):
        load_document(_with_limits(tmp_path, {ROPE_LIMIT: entry}))
