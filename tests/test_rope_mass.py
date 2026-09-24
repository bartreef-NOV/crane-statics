"""Unit tests for rope reeving length, rope-on-winch, and the hook-height derivation."""

from pathlib import Path

import math

import pytest

from crane_statics.calculation.rope_mass import (
    compute_reeved_length_m,
    compute_rope_on_winch,
    derive_hook_geometry,
    find_winch_node_ids,
    hook_positions_at_height,
    reeved_length_at_angle_m,
    resolve_total_rope_length_m,
)
from crane_statics.calculation.solver.kinematics import KinematicsAdapter
from crane_statics.core.io import load_document

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"


@pytest.fixture
def example_doc():
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    return load_document(EXAMPLE)


@pytest.fixture
def example_doc_dict(example_doc):
    return example_doc.model_dump()


def _synthetic_doc_dict(
    *,
    rope_length_m=None,
    max_hook_travel_m=10.0,
    winch_node_ids=("winch_a",),
    falls=2,
    split_falls=None,
    outreach_min_m=15.0,
    drum_dead_turns=0,
    drum_diameter_m=None,
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
                "outreach_min_m": outreach_min_m,
                "linear_mass_kg_m": 5.0,
                "rope_length_m": rope_length_m,
                "falls": falls,
                "split_falls": split_falls,
                "drum_dead_turns": drum_dead_turns,
                "drum_diameter_m": drum_diameter_m,
            }
        ],
    }


def _positions_with_hook_dropped(doc_dict, drop_m, angle_deg=0.0):
    kin = KinematicsAdapter(doc_dict)
    positions = dict(kin.compute_all_node_positions(angle_deg))
    positions["hook"] = {
        "x": positions["sheave"]["x"],
        "z": positions["sheave"]["z"] - drop_m,
    }
    return positions


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
        short_len = compute_reeved_length_m(
            doc_dict, "hoist_a", _positions_with_hook_dropped(doc_dict, 5.0)
        )
        long_len = compute_reeved_length_m(
            doc_dict, "hoist_a", _positions_with_hook_dropped(doc_dict, 20.0)
        )

        assert short_len is not None and long_len is not None
        assert long_len > short_len

    def test_length_at_angle_uses_kinematic_positions(self):
        doc_dict = _synthetic_doc_dict()
        kin = KinematicsAdapter(doc_dict)
        expected = compute_reeved_length_m(
            doc_dict, "hoist_a", kin.compute_all_node_positions(12.0)
        )
        assert reeved_length_at_angle_m(doc_dict, "hoist_a", 12.0) == pytest.approx(expected)

    def test_unknown_hoist_returns_none(self):
        doc_dict = _synthetic_doc_dict()
        assert compute_reeved_length_m(doc_dict, "no_such_hoist", {}) is None


class TestHookGeometryDerivation:
    def test_travel_is_support_elevation_above_the_design_height(self):
        doc_dict = _synthetic_doc_dict()
        kin = KinematicsAdapter(doc_dict)
        angle = kin.outreach_to_angle(15.0, "hoist_a")
        support_z = kin.compute_all_node_positions(angle)["sheave"]["z"]

        travel_m, _rope_m = derive_hook_geometry(doc_dict, "hoist_a", -30.0)

        assert travel_m == pytest.approx(support_z + 30.0)

    def test_rope_length_is_the_reeved_length_at_that_state(self):
        doc_dict = _synthetic_doc_dict()
        kin = KinematicsAdapter(doc_dict)
        angle = kin.outreach_to_angle(15.0, "hoist_a")
        positions = kin.compute_all_node_positions(angle)
        expected = compute_reeved_length_m(
            doc_dict,
            "hoist_a",
            hook_positions_at_height(doc_dict, "hoist_a", positions, -30.0),
        )

        _travel_m, rope_m = derive_hook_geometry(doc_dict, "hoist_a", -30.0)

        assert rope_m == pytest.approx(expected)

    def test_dead_turns_add_their_wrapped_length(self):
        doc_dict = _synthetic_doc_dict()
        _travel_m, bare_rope_m = derive_hook_geometry(doc_dict, "hoist_a", -30.0)
        _travel_m, with_dead_m = derive_hook_geometry(doc_dict, "hoist_a", -30.0, 4 * math.pi * 1.5)

        assert with_dead_m - bare_rope_m == pytest.approx(4 * math.pi * 1.5)

    def test_design_height_above_the_sheave_is_an_error(self):
        doc_dict = _synthetic_doc_dict()
        with pytest.raises(ValueError, match="hook travel is negative"):
            derive_hook_geometry(doc_dict, "hoist_a", 1000.0)

    def test_unknown_hoist_returns_none(self):
        doc_dict = _synthetic_doc_dict()
        assert derive_hook_geometry(doc_dict, "no_such_hoist", -30.0) is None

    def test_missing_min_outreach_returns_none(self):
        doc_dict = _synthetic_doc_dict(outreach_min_m=None)
        assert derive_hook_geometry(doc_dict, "hoist_a", -30.0) is None


class TestTotalRopeLength:
    def test_stored_length_is_used_verbatim(self):
        doc_dict = _synthetic_doc_dict(rope_length_m=123.0)
        assert resolve_total_rope_length_m(doc_dict, "hoist_a") == 123.0

    def test_absent_length_is_unknown_rather_than_guessed(self):
        doc_dict = _synthetic_doc_dict(rope_length_m=None)
        assert resolve_total_rope_length_m(doc_dict, "hoist_a") is None


class TestRopeOnWinch:
    def test_length_and_mass_scale_with_linear_mass(self):
        doc_dict = _synthetic_doc_dict(rope_length_m=1000.0)
        positions = _positions_with_hook_dropped(doc_dict, 5.0)

        length_m, mass_kg = compute_rope_on_winch(doc_dict, "hoist_a", positions)
        reeved = compute_reeved_length_m(doc_dict, "hoist_a", positions)

        assert reeved is not None
        assert length_m == pytest.approx(1000.0 - reeved)
        assert mass_kg == pytest.approx(length_m * 5.0)

    def test_insufficient_specified_length_clamps_to_zero(self):
        doc_dict = _synthetic_doc_dict(rope_length_m=1.0)
        positions = _positions_with_hook_dropped(doc_dict, 5.0)

        length_m, mass_kg = compute_rope_on_winch(doc_dict, "hoist_a", positions)

        assert length_m == 0.0
        assert mass_kg == 0.0

    def test_unknown_total_length_reports_nothing_on_the_drum(self):
        doc_dict = _synthetic_doc_dict(rope_length_m=None)
        positions = _positions_with_hook_dropped(doc_dict, 5.0)

        assert compute_rope_on_winch(doc_dict, "hoist_a", positions) == (0.0, 0.0)


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
        positions = _positions_with_hook_dropped(doc_dict, 10.0)

        def effective_mult(rope_id, seg, mult):
            return _example_effective_mult(
                rope_id, seg, mult, split_active=False, doc_dict=doc_dict, hoist_id="hoist_a"
            )

        length_m, _ = compute_rope_on_winch(doc_dict, "hoist_a", positions, effective_mult)

        reeved = compute_reeved_length_m(doc_dict, "hoist_a", positions)
        assert reeved is not None
        assert length_m == pytest.approx(1000.0 - reeved)

    def test_split_mode_matches_falls_delta_times_travel_times_linear_mass(self):
        falls_normal, split_falls, drop_m, linear_mass_kg_m = 20, 12, 10.0, 5.0
        doc_dict = _synthetic_doc_dict(
            max_hook_travel_m=drop_m, falls=falls_normal, split_falls=split_falls
        )
        doc_dict["hoists"][0]["linear_mass_kg_m"] = linear_mass_kg_m
        positions = _positions_with_hook_dropped(doc_dict, drop_m)
        # Total rope is exactly what normal-mode reeving needs at this state, so the
        # only rope left on the drum in split mode is the falls it no longer carries.
        doc_dict["hoists"][0]["rope_length_m"] = compute_reeved_length_m(
            doc_dict, "hoist_a", positions
        )

        def effective_mult(rope_id, seg, mult):
            return _example_effective_mult(
                rope_id, seg, mult, split_active=True, doc_dict=doc_dict, hoist_id="hoist_a"
            )

        length_m, mass_kg = compute_rope_on_winch(doc_dict, "hoist_a", positions, effective_mult)

        expected_length_m = (falls_normal - split_falls) * drop_m
        assert length_m == pytest.approx(expected_length_m)
        assert mass_kg == pytest.approx(expected_length_m * linear_mass_kg_m)

    def test_switching_to_split_mode_increases_mass_on_winch(self):
        doc_dict = _synthetic_doc_dict(
            rope_length_m=1000.0, max_hook_travel_m=10.0, falls=20, split_falls=12
        )
        positions = _positions_with_hook_dropped(doc_dict, 10.0)

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
    def test_boom_hoist_keeps_its_authored_rope_length(self, example_doc_dict):
        boom_hoist = next(h for h in example_doc_dict["hoists"] if h["id"] == "BH")
        assert resolve_total_rope_length_m(example_doc_dict, "BH") == pytest.approx(4500.0)
        assert find_winch_node_ids(example_doc_dict, boom_hoist["id"])

    def test_payload_hoist_rope_length_is_derived_from_the_design_hook_height(self, example_doc):
        hook_height_m = example_doc.hook_height_at_min_outreach_m
        assert hook_height_m == pytest.approx(-53.0)

        doc_dict = example_doc.model_dump()
        for hoist in example_doc.hoists:
            if hoist.id == "BH":
                continue
            travel_m, rope_m = derive_hook_geometry(doc_dict, hoist.id, hook_height_m)
            assert hoist.max_hook_travel_m == pytest.approx(travel_m)
            assert hoist.rope_length_m == pytest.approx(rope_m)

    def test_derived_rope_covers_the_reeving_at_minimum_outreach(self, example_doc):
        doc_dict = example_doc.model_dump()
        kin = KinematicsAdapter(doc_dict)
        for hoist in example_doc.hoists:
            if hoist.id == "BH":
                continue
            angle = kin.outreach_to_angle(float(hoist.outreach_min_m), hoist.id)
            positions = hook_positions_at_height(
                doc_dict,
                hoist.id,
                kin.compute_all_node_positions(angle),
                float(example_doc.hook_height_at_min_outreach_m),
            )
            reeved = compute_reeved_length_m(doc_dict, hoist.id, positions)
            assert reeved is not None
            assert float(hoist.rope_length_m) >= reeved - 1e-6

    def test_rope_on_winch_is_consistent_with_linear_mass(self, example_doc_dict):
        mh_hoist = next(h for h in example_doc_dict["hoists"] if h["id"] == "MH")
        kin = KinematicsAdapter(example_doc_dict)
        positions = kin.compute_all_node_positions(45.0)
        length_m, mass_kg = compute_rope_on_winch(example_doc_dict, "MH", positions)

        assert length_m >= 0.0
        assert mass_kg == pytest.approx(length_m * mh_hoist["linear_mass_kg_m"])
