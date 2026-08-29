"""Unit tests for rope reeving length / rope-on-winch calculations."""

from pathlib import Path

import pytest

from crane_statics.calculation.rope_mass import (
    compute_reeved_length_m,
    compute_reference_reeved_length_m,
    compute_rope_on_winch,
    compute_winch_marker_masses_kg,
    find_winch_node_ids,
    resolve_total_rope_length_m,
)
from crane_statics.calculation.solver.kinematics import KinematicsAdapter
from crane_statics.core.io import load_document

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"


@pytest.fixture
def example_doc_dict():
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    return load_document(EXAMPLE).model_dump()


def _synthetic_doc_dict(
    *,
    rope_length_m=None,
    max_hook_travel_m=10.0,
    winch_node_ids=("winch_a",),
    falls=2,
    split_falls=None,
):
    segments = []
    for winch_id in winch_node_ids:
        segments.append({"from_node_id": winch_id, "to_node_id": "sheave", "mult": 1})
    segments.append({"from_node_id": "sheave", "to_node_id": "hook", "mult": falls})

    nodes = [
        {"id": "platform_base", "body": "platform", "x_m": 0.0, "z_m": 0.0},
        {"id": "boom_heel", "body": "platform", "x_m": 0.0, "z_m": 5.0},
        {
            "id": "sheave",
            "body": "boom",
            "x_m": 0.0,
            "z_m": 0.0,
            "local_x_m": 20.0,
            "local_z_m": 0.0,
        },
        {"id": "hook", "body": "boom", "x_m": 0.0, "z_m": 0.0, "below_node_id": "sheave"},
    ]
    for winch_id in winch_node_ids:
        nodes.append({"id": winch_id, "body": "platform", "x_m": -5.0, "z_m": 2.0})

    return {
        "nodes": nodes,
        "ropes": [{"id": "rope_a", "segments": segments, "linear_mass_kg_m": 0.0}],
        "hoists": [
            {
                "id": "hoist_a",
                "rope_id": "rope_a",
                "support_node_id": "sheave",
                "load_node_id": "hook",
                "max_hook_travel_m": max_hook_travel_m,
                "linear_mass_kg_m": 5.0,
                "rope_length_m": rope_length_m,
                "falls": falls,
                "split_falls": split_falls,
            }
        ],
    }


class TestWinchNodeDetection:
    def test_finds_winch_nodes_case_insensitively(self):
        doc_dict = _synthetic_doc_dict(winch_node_ids=("MH_Winch",))
        assert find_winch_node_ids(doc_dict, "hoist_a") == ["MH_Winch"]

    def test_no_winch_node_returns_empty(self):
        doc_dict = _synthetic_doc_dict(winch_node_ids=("drum_a",))
        assert find_winch_node_ids(doc_dict, "hoist_a") == []

    def test_multiple_winch_nodes(self):
        doc_dict = _synthetic_doc_dict(winch_node_ids=("winch_a", "winch_b"))
        assert find_winch_node_ids(doc_dict, "hoist_a") == ["winch_a", "winch_b"]

    def test_unknown_hoist_returns_empty(self):
        doc_dict = _synthetic_doc_dict()
        assert find_winch_node_ids(doc_dict, "no_such_hoist") == []


class TestReeledLength:
    def test_reeved_length_increases_with_hook_travel(self):
        doc_dict = _synthetic_doc_dict()
        kin = KinematicsAdapter(doc_dict)
        positions_short = dict(kin.compute_all_node_positions(0.0))
        positions_short["hook"] = {
            "x": positions_short["sheave"]["x"],
            "z": positions_short["sheave"]["z"] - 5.0,
        }
        positions_long = dict(kin.compute_all_node_positions(0.0))
        positions_long["hook"] = {
            "x": positions_long["sheave"]["x"],
            "z": positions_long["sheave"]["z"] - 20.0,
        }

        short_len = compute_reeved_length_m(doc_dict, "hoist_a", positions_short)
        long_len = compute_reeved_length_m(doc_dict, "hoist_a", positions_long)

        assert short_len is not None and long_len is not None
        assert long_len > short_len

    def test_reference_length_uses_max_travel_and_zero_boom_angle(self):
        doc_dict = _synthetic_doc_dict(max_hook_travel_m=15.0)
        kin = KinematicsAdapter(doc_dict)
        positions = dict(kin.compute_all_node_positions(0.0))
        positions["hook"] = {"x": positions["sheave"]["x"], "z": positions["sheave"]["z"] - 15.0}

        expected = compute_reeved_length_m(doc_dict, "hoist_a", positions)
        actual = compute_reference_reeved_length_m(doc_dict, "hoist_a")

        assert actual == pytest.approx(expected)

    def test_unknown_hoist_returns_none(self):
        doc_dict = _synthetic_doc_dict()
        assert compute_reeved_length_m(doc_dict, "no_such_hoist", {}) is None


class TestTotalRopeLength:
    def test_specified_length_is_used_verbatim(self):
        doc_dict = _synthetic_doc_dict(rope_length_m=123.0)
        assert resolve_total_rope_length_m(doc_dict, "hoist_a") == 123.0

    def test_unspecified_length_falls_back_to_reference_reeved_length(self):
        doc_dict = _synthetic_doc_dict(rope_length_m=None, max_hook_travel_m=15.0)
        expected = compute_reference_reeved_length_m(doc_dict, "hoist_a")
        assert resolve_total_rope_length_m(doc_dict, "hoist_a") == pytest.approx(expected)


class TestRopeOnWinch:
    def test_length_and_mass_scale_with_linear_mass(self):
        doc_dict = _synthetic_doc_dict(rope_length_m=1000.0)
        kin = KinematicsAdapter(doc_dict)
        positions = dict(kin.compute_all_node_positions(0.0))
        positions["hook"] = {"x": positions["sheave"]["x"], "z": positions["sheave"]["z"] - 5.0}

        length_m, mass_kg = compute_rope_on_winch(doc_dict, "hoist_a", positions)
        reeved = compute_reeved_length_m(doc_dict, "hoist_a", positions)

        assert reeved is not None
        assert length_m == pytest.approx(1000.0 - reeved)
        assert mass_kg == pytest.approx(length_m * 5.0)

    def test_insufficient_specified_length_clamps_to_zero(self):
        doc_dict = _synthetic_doc_dict(rope_length_m=1.0)
        kin = KinematicsAdapter(doc_dict)
        positions = dict(kin.compute_all_node_positions(0.0))
        positions["hook"] = {"x": positions["sheave"]["x"], "z": positions["sheave"]["z"] - 5.0}

        length_m, mass_kg = compute_rope_on_winch(doc_dict, "hoist_a", positions)

        assert length_m == 0.0
        assert mass_kg == 0.0

    def test_multiple_winch_nodes_split_mass_equally(self):
        doc_dict = _synthetic_doc_dict(rope_length_m=1000.0, winch_node_ids=("winch_a", "winch_b"))
        kin = KinematicsAdapter(doc_dict)
        positions = dict(kin.compute_all_node_positions(0.0))
        positions["hook"] = {"x": positions["sheave"]["x"], "z": positions["sheave"]["z"] - 5.0}

        _, total_mass_kg = compute_rope_on_winch(doc_dict, "hoist_a", positions)
        per_node = compute_winch_marker_masses_kg(doc_dict, "hoist_a", positions)

        assert set(per_node) == {"winch_a", "winch_b"}
        assert per_node["winch_a"] == pytest.approx(total_mass_kg / 2)
        assert per_node["winch_b"] == pytest.approx(total_mass_kg / 2)
        assert sum(per_node.values()) == pytest.approx(total_mass_kg)

    def test_no_winch_node_returns_empty_marker_dict(self):
        doc_dict = _synthetic_doc_dict(rope_length_m=1000.0, winch_node_ids=("drum_a",))
        kin = KinematicsAdapter(doc_dict)
        positions = dict(kin.compute_all_node_positions(0.0))

        assert compute_winch_marker_masses_kg(doc_dict, "hoist_a", positions) == {}


def _example_effective_mult(rope_id, seg, authored_mult, *, split_active, doc_dict, hoist_id):
    """Mirror scene_renderer._effective_segment_mult: substitute split_falls on the
    managed hook segment."""
    hoist = next(h for h in doc_dict["hoists"] if h["id"] == hoist_id)
    if rope_id != hoist["rope_id"]:
        return authored_mult
    support = hoist.get("support_node_id")
    load = hoist.get("load_node_id")
    from_node = seg.get("from_node_id")
    to_node = seg.get("to_node_id")
    is_managed_hook_segment = {from_node, to_node} == {support, load}
    if not is_managed_hook_segment:
        return authored_mult
    if split_active and hoist.get("split_falls"):
        return int(hoist["split_falls"])
    return int(hoist.get("falls") or authored_mult)


class TestSplitModeRopeOnWinch:
    def test_normal_mode_uses_normal_falls(self):
        doc_dict = _synthetic_doc_dict(
            rope_length_m=1000.0, max_hook_travel_m=10.0, falls=20, split_falls=12
        )
        kin = KinematicsAdapter(doc_dict)
        positions = dict(kin.compute_all_node_positions(0.0))
        positions["hook"] = {"x": positions["sheave"]["x"], "z": positions["sheave"]["z"] - 10.0}

        def effective_mult(rope_id, seg, mult):
            return _example_effective_mult(
                rope_id, seg, mult, split_active=False, doc_dict=doc_dict, hoist_id="hoist_a"
            )

        length_m, _ = compute_rope_on_winch(doc_dict, "hoist_a", positions, effective_mult)

        reference = compute_reference_reeved_length_m(doc_dict, "hoist_a")
        assert reference is not None
        assert length_m == pytest.approx(1000.0 - reference)

    def test_split_mode_matches_falls_delta_times_max_travel_times_linear_mass(self):
        falls_normal, split_falls, travel_max, linear_mass_kg_m = 20, 12, 10.0, 5.0
        doc_dict = _synthetic_doc_dict(
            rope_length_m=None,  # unspecified -> total == normal-mode reference reeved length
            max_hook_travel_m=travel_max,
            falls=falls_normal,
            split_falls=split_falls,
        )
        doc_dict["hoists"][0]["linear_mass_kg_m"] = linear_mass_kg_m
        kin = KinematicsAdapter(doc_dict)
        positions = dict(kin.compute_all_node_positions(0.0))
        positions["hook"] = {
            "x": positions["sheave"]["x"],
            "z": positions["sheave"]["z"] - travel_max,
        }

        def effective_mult(rope_id, seg, mult):
            return _example_effective_mult(
                rope_id, seg, mult, split_active=True, doc_dict=doc_dict, hoist_id="hoist_a"
            )

        length_m, mass_kg = compute_rope_on_winch(doc_dict, "hoist_a", positions, effective_mult)

        expected_length_m = (falls_normal - split_falls) * travel_max
        assert length_m == pytest.approx(expected_length_m)
        assert mass_kg == pytest.approx(expected_length_m * linear_mass_kg_m)

    def test_switching_to_split_mode_increases_mass_on_winch(self):
        doc_dict = _synthetic_doc_dict(
            rope_length_m=1000.0, max_hook_travel_m=10.0, falls=20, split_falls=12
        )
        kin = KinematicsAdapter(doc_dict)
        positions = dict(kin.compute_all_node_positions(0.0))
        positions["hook"] = {"x": positions["sheave"]["x"], "z": positions["sheave"]["z"] - 10.0}

        def normal_mult(rope_id, seg, mult):
            return _example_effective_mult(
                rope_id, seg, mult, split_active=False, doc_dict=doc_dict, hoist_id="hoist_a"
            )

        def split_mult(rope_id, seg, mult):
            return _example_effective_mult(
                rope_id, seg, mult, split_active=True, doc_dict=doc_dict, hoist_id="hoist_a"
            )

        _, normal_mass_kg = compute_rope_on_winch(doc_dict, "hoist_a", positions, normal_mult)
        _, split_mass_kg = compute_rope_on_winch(doc_dict, "hoist_a", positions, split_mult)

        assert split_mass_kg > normal_mass_kg


class TestExampleDocument:
    def test_boom_hoist_has_explicit_rope_length_and_winch_node(self, example_doc_dict):
        boom_hoist = next(h for h in example_doc_dict["hoists"] if h.get("rope_length_m") == 4500.0)
        assert resolve_total_rope_length_m(example_doc_dict, boom_hoist["id"]) == pytest.approx(
            4500.0
        )
        assert find_winch_node_ids(example_doc_dict, boom_hoist["id"])

    def test_mh_hoist_has_explicit_rope_length_and_winch_node(self, example_doc_dict):
        mh_hoist = next(h for h in example_doc_dict["hoists"] if h.get("rope_length_m") == 4300.0)
        assert find_winch_node_ids(example_doc_dict, mh_hoist["id"])

        kin = KinematicsAdapter(example_doc_dict)
        positions = kin.compute_all_node_positions(45.0)
        length_m, mass_kg = compute_rope_on_winch(example_doc_dict, mh_hoist["id"], positions)

        assert length_m >= 0.0
        assert mass_kg == pytest.approx(length_m * mh_hoist["linear_mass_kg_m"])
