"""Runtime conditions own each payload hoist's lead limits, DAF and contractual points."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from crane_statics.core.io import _StrictIntSafeLoader
from crane_statics.data import normalize_document
from crane_statics.data.authored_form import document_to_authored_form

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _point(outreach_m: float, load_t: float, *conditions: str) -> dict:
    return {"outreach_m": outreach_m, "load_t": load_t, "conditions": list(conditions)}


def _two_condition_doc() -> dict:
    """A v13 document with conditions A and B sharing one hoist with different charts."""
    return {
        "schema": {"name": "crane-statics", "version": "14.0.0"},
        "metadata": {"name": "Two conditions"},
        "model_definition": {
            "environment": {"gravity_m_s2": 9.81, "air_density_kg_m3": 1.225},
            "conditions": {
                "A": {"wind_speed_m_s": 20.0, "hoists": {"MH": {"offlead_deg": 1.0}}},
                "B": {
                    "wind_speed_m_s": 10.0,
                    "hoists": {"MH": {"offlead_deg": 2.0, "sidelead_deg": 3.0, "daf": 1.2}},
                },
            },
            "structure": {
                "boom_width_m": 1.0,
                "slewing_bearing_diameter_m": 1.0,
                "boom_heel": {"x_m": 8.5, "z_m": 8.0},
                "upper_hinge": {"x_m": -11.0, "z_m": 52.3},
                "rear_hinge": {"x_m": -11.0, "z_m": 7.7},
                "front_hinge": {"x_m": 6.87, "z_m": 7.7},
            },
            "hoists": {
                "BH": {"reeving": [{"node": "boom_heel"}, {"node": "rear_top", "parts": 2}]},
                "MH": {
                    "reeving": [
                        {"node": "boom_heel"},
                        {"node": "hook", "body": "boom", "u_m": 40.0, "w_m": -2.0},
                    ],
                    "lower_block_mass_t": 10.0,
                    "falls": 4,
                    "load_chart": [
                        _point(12.0, 100.0, "A", "B"),
                        _point(20.0, 60.0, "A"),
                        _point(25.0, 50.0, "B"),
                    ],
                    "split": {
                        "lower_block_mass_t": 5.0,
                        "falls": 2,
                        "load_chart": [_point(10.0, 40.0, "A"), _point(30.0, 20.0, "B")],
                    },
                },
            },
        },
    }


def _migrated_example(name: str) -> dict:
    """An example's authored dict (the shipped examples are v13 files)."""
    with open(EXAMPLES / name, "r", encoding="utf-8-sig") as f:
        data: dict = yaml.load(f, Loader=_StrictIntSafeLoader)
    return data


def _pairs(points) -> list[tuple[float, float]]:
    return [(p.outreach_m, p.load_t) for p in points]


def test_condition_hoist_points_are_filtered_by_tag():
    doc = normalize_document(_two_condition_doc())

    a = doc.conditions["A"].hoists["MH"]
    b = doc.conditions["B"].hoists["MH"]
    assert _pairs(a.contractual_points) == [(12.0, 100.0), (20.0, 60.0)]
    assert _pairs(b.contractual_points) == [(12.0, 100.0), (25.0, 50.0)]
    assert _pairs(a.split_contractual_points) == [(10.0, 40.0)]
    assert _pairs(b.split_contractual_points) == [(30.0, 20.0)]
    assert (a.offlead_deg, a.sidelead_deg) == (1.0, 0.0)
    assert (b.offlead_deg, b.sidelead_deg) == (2.0, 3.0)


def test_outreach_bounds_span_all_conditions():
    doc = normalize_document(_two_condition_doc())

    hoist = next(h for h in doc.hoists if h.id == "MH")
    assert hoist.outreach_min_m == 10.0
    assert hoist.outreach_max_m == 30.0
    assert hoist.splitable_block is True
    for removed in (
        "hook_daf",
        "offlead_deg",
        "sidelead_deg",
        "contractual_points",
        "split_contractual_points",
    ):
        assert removed not in type(hoist).model_fields


def test_daf_none_preserved_when_omitted():
    doc = normalize_document(_two_condition_doc())

    assert doc.conditions["A"].hoists["MH"].daf is None
    assert doc.conditions["B"].hoists["MH"].daf == 1.2


def test_boom_hoist_is_in_no_condition():
    doc = normalize_document(_two_condition_doc())

    assert all("BH" not in c.hoists for c in doc.conditions.values())


def test_rules_less_document_has_conditions_and_default_environment():
    doc = normalize_document(_migrated_example("crane_input_GT283.yaml"))

    assert doc.rules is None
    assert list(doc.conditions) == ["default"]
    condition = doc.conditions["default"]
    assert condition.wind_speed_m_s == 0.01
    assert condition.hoists["MH"].daf == 1.1
    # Wind and vessel motion live in the condition; the environment keeps runtime defaults.
    assert doc.environment.max_wind_speed_m_s == 20.0


def test_export_groups_points_shared_by_conditions():
    doc = normalize_document(_two_condition_doc())

    md = document_to_authored_form(doc)["model_definition"]

    mh = md["hoists"]["MH"]
    assert mh["load_chart"] == [
        _point(12.0, 100.0, "A", "B"),
        _point(20.0, 60.0, "A"),
        _point(25.0, 50.0, "B"),
    ]
    assert mh["split"]["load_chart"] == [_point(10.0, 40.0, "A"), _point(30.0, 20.0, "B")]
    for removed in ("daf", "offlead_deg", "sidelead_deg"):
        assert removed not in mh
    assert md["conditions"]["A"]["hoists"] == {"MH": {"offlead_deg": 1.0}}
    assert md["conditions"]["B"]["hoists"] == {
        "MH": {"offlead_deg": 2.0, "sidelead_deg": 3.0, "daf": 1.2}
    }
    assert "rules" not in md
    assert "max_wind_speed_m_s" not in md["environment"]
    assert "vessel_motion" not in md


def test_export_keeps_a_point_repeated_within_one_condition():
    data = _two_condition_doc()
    mh = data["model_definition"]["hoists"]["MH"]
    mh["load_chart"] = [_point(12.0, 100.0, "A", "B"), _point(12.0, 100.0, "A")]
    doc = normalize_document(data)

    exported = document_to_authored_form(doc)

    assert exported["model_definition"]["hoists"]["MH"]["load_chart"] == mh["load_chart"]
    assert normalize_document(exported).model_dump() == doc.model_dump()


def _round_trip_with_chart(load_chart: list[dict]):
    data = _two_condition_doc()
    data["model_definition"]["hoists"]["MH"]["load_chart"] = load_chart
    doc = normalize_document(data)
    exported = document_to_authored_form(doc)
    return doc, exported, normalize_document(exported)


def test_export_preserves_each_conditions_point_order_for_ascending_charts():
    # B's 10 m point first appears after A's points, but B's chart starts with it.
    doc, exported, reimported = _round_trip_with_chart(
        [
            _point(12.0, 100.0, "A"),
            _point(20.0, 60.0, "A"),
            _point(10.0, 120.0, "B"),
            _point(12.0, 100.0, "B"),
        ]
    )

    assert _pairs(doc.conditions["B"].hoists["MH"].contractual_points) == [
        (10.0, 120.0),
        (12.0, 100.0),
    ]
    assert exported["model_definition"]["hoists"]["MH"]["load_chart"] == [
        _point(10.0, 120.0, "B"),
        _point(12.0, 100.0, "A", "B"),
        _point(20.0, 60.0, "A"),
    ]
    assert reimported.model_dump() == doc.model_dump()


def test_export_preserves_conflicting_point_orders():
    # A has 12 then 20, B has 20 then 12: no single merged order serves both.
    doc, exported, reimported = _round_trip_with_chart(
        [_point(12.0, 100.0, "A"), _point(20.0, 60.0, "A", "B"), _point(12.0, 100.0, "B")]
    )

    assert _pairs(doc.conditions["B"].hoists["MH"].contractual_points) == [
        (20.0, 60.0),
        (12.0, 100.0),
    ]
    assert exported["model_definition"]["hoists"]["MH"]["load_chart"] == [
        _point(12.0, 100.0, "A"),
        _point(20.0, 60.0, "A", "B"),
        _point(12.0, 100.0, "B"),
    ]
    assert reimported.model_dump() == doc.model_dump()


@pytest.mark.parametrize(
    "example",
    [
        "crane_input_GT283.yaml",
        "crane_input_GT283_abs.yaml",
        "crane_input_13778_retracted.yaml",
        "crane_input_13778_retracted_dnv.yaml",
    ],
)
def test_round_trip_export_reimport_equal(example):
    doc = normalize_document(_migrated_example(example))

    reimported = normalize_document(deepcopy(document_to_authored_form(doc)))

    assert reimported.model_dump() == doc.model_dump()


def test_round_trip_export_reimport_equal_two_conditions():
    doc = normalize_document(_two_condition_doc())

    reimported = normalize_document(document_to_authored_form(doc))

    assert reimported.model_dump() == doc.model_dump()
