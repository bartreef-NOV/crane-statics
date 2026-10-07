"""Hooks are drawn hanging plumb below their sheave, along the Scene's gravity.

Only the drawing moves: a free-hanging hook loads its sheave along gravity
wherever it sits on the plumb line, so the solver keeps its hook directly below
the sheave and every result stays as it was.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from crane_statics.calculation.engine import CraneCalculator
from crane_statics.calculation.rope_mass import hook_support_node_id
from crane_statics.calculation.vessel_attitude import (
    CraneFrameGravity,
    VesselAttitude,
    crane_frame_gravity,
)
from crane_statics.core import drawn_loads as dl
from crane_statics.core.io import load_document
from crane_statics.core.scene_build import build_scene_frame, plumb_hook_positions
from tests.test_acceptance import scene_inputs

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"
HEEL, TRIM, SLEW = 3.0, 1.0, 75.0
TACKLE_M = 40.0


@pytest.fixture
def document():
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    return load_document(EXAMPLE)


def _tilted(doc, heel_deg: float = HEEL, trim_deg: float = TRIM):
    tilted = doc.model_copy(deep=True)
    tilted.environment.vessel_motion.heel_deg = heel_deg
    tilted.environment.vessel_motion.trim_deg = trim_deg
    return tilted


def _inputs(doc, *, hook_load_kN: float = 0.0, offlead_deg: float = 0.0, slew_deg: float = SLEW):
    point = CraneCalculator(doc).compute_analysis_point(
        45.0, 0.0, "MH", tackle_length_m=TACKLE_M, slew_deg=slew_deg, offlead_deg=offlead_deg
    )
    assert point is not None
    return scene_inputs(
        doc,
        "MH",
        angle=45.0,
        analysis_point=point,
        tackle_length_m=TACKLE_M,
        hook_load_kN=hook_load_kN,
        offlead_deg=offlead_deg,
        slew_deg=slew_deg,
    )


def _hooks(doc_dict) -> dict[str, str]:
    """Payload hook node -> the sheave it hangs from."""
    nodes = {node["id"]: node for node in doc_dict["nodes"]}
    return {
        hoist["load_node_id"]: hook_support_node_id(doc_dict, hoist["id"])
        for hoist in doc_dict["hoists"]
        if nodes[hoist["load_node_id"]].get("below_node_id")
        and nodes[hoist["load_node_id"]].get("local_x_m") is None
    }


class TestPlumbHookPositions:
    def test_a_level_vessel_hangs_hooks_straight_down(self):
        positions = {"sheave": {"x": 10.0, "z": 30.0}, "hook": {"x": 10.0, "z": 29.0}}

        result = plumb_hook_positions(positions, {"hook": ("sheave", 12.0)}, CraneFrameGravity())

        assert result["hook"] == {"x": 10.0, "z": 18.0}

    def test_a_tilt_hangs_the_hook_along_gravity_without_mutating_inputs(self):
        positions = {"sheave": {"x": 10.0, "z": 30.0}, "hook": {"x": 10.0, "z": 29.0}}
        gravity = crane_frame_gravity(VesselAttitude(HEEL, TRIM), SLEW)

        result = plumb_hook_positions(positions, {"hook": ("sheave", 12.0)}, gravity)

        assert result["hook"]["x"] == pytest.approx(10.0 + 12.0 * gravity.lateral_x)
        assert result["hook"]["z"] == pytest.approx(30.0 - 12.0 * gravity.vertical)
        assert positions["hook"] == {"x": 10.0, "z": 29.0}

    def test_an_unknown_sheave_leaves_the_hook_where_it_was(self):
        positions = {"hook": {"x": 10.0, "z": 29.0}}

        result = plumb_hook_positions(positions, {"hook": ("missing", 12.0)}, CraneFrameGravity())

        assert result["hook"] == {"x": 10.0, "z": 29.0}


class TestSceneHooksHangPlumb:
    def test_level_positions_are_unchanged(self, document):
        inputs = _inputs(document)
        base = inputs.base_node_positions()
        drawn = inputs.node_positions()
        active = inputs.hoist["load_node_id"]
        sheave = hook_support_node_id(inputs.document_dict, "MH")

        assert drawn[active] == {"x": base[sheave]["x"], "z": base[sheave]["z"] - TACKLE_M}
        for node_id, point in base.items():
            if node_id != active:
                assert drawn[node_id] == point, node_id

    def test_every_hook_leans_along_gravity_on_a_tilted_vessel(self, document):
        inputs = _inputs(_tilted(document))
        gravity = inputs.crane_gravity()
        base = inputs.base_node_positions()
        drawn = inputs.node_positions()
        hooks = _hooks(inputs.document_dict)
        active = inputs.hoist["load_node_id"]
        assert active in hooks and len(hooks) > 1
        assert gravity.lateral_x != 0.0

        for hook_id, sheave_id in hooks.items():
            sheave = base[sheave_id]
            drop = TACKLE_M if hook_id == active else sheave["z"] - base[hook_id]["z"]
            assert drawn[hook_id]["x"] == pytest.approx(sheave["x"] + drop * gravity.lateral_x)
            assert drawn[hook_id]["z"] == pytest.approx(sheave["z"] - drop * gravity.vertical)

    def test_nodes_other_than_hooks_stay_where_the_kinematics_put_them(self, document):
        inputs = _inputs(_tilted(document))
        base = inputs.base_node_positions()
        drawn = inputs.node_positions()
        hooks = _hooks(inputs.document_dict)

        for node_id, point in base.items():
            if node_id not in hooks:
                assert drawn[node_id] == point, node_id


class TestGuidesOnATiltedVessel:
    @staticmethod
    def _world(frame, scene_x: float, scene_y: float) -> tuple[float, float]:
        assert frame.mapping is not None
        world_x, world_z = frame.mapping.to_world(scene_x, scene_y)
        return float(world_x), float(world_z)

    def test_outreach_stays_the_sheave_x_while_the_hook_leans(self, document):
        level = build_scene_frame(_inputs(document))
        inputs = _inputs(_tilted(document))
        frame = build_scene_frame(inputs)
        sheave = inputs.base_node_positions()[hook_support_node_id(inputs.document_dict, "MH")]
        hook = inputs.node_positions()[inputs.hoist["load_node_id"]]

        guides = {guide.kind: guide for guide in frame.guides}
        level_guides = {guide.kind: guide for guide in level.guides}
        outreach_x, outreach_z = self._world(
            frame, guides["outreach"].scene_x, guides["outreach"].scene_y
        )
        height_x, height_z = self._world(
            frame, guides["hook_height"].scene_x, guides["hook_height"].scene_y
        )

        assert guides["outreach"].label == level_guides["outreach"].label
        assert guides["outreach"].label == f"R = {sheave['x']:.1f} m"
        assert outreach_x == pytest.approx(sheave["x"])
        assert outreach_z == pytest.approx(hook["z"])
        assert (height_x, height_z) == pytest.approx((hook["x"], hook["z"]))
        assert guides["hook_height"].label == f"Z = {hook['z']:.1f} m"

    def test_hit_targets_follow_their_guides(self, document):
        frame = build_scene_frame(_inputs(_tilted(document)))
        guides = {guide.kind: guide for guide in frame.guides}
        targets = {target.kind: target for target in frame.hit_targets}

        assert targets["outreach"].start_x == pytest.approx(guides["outreach"].scene_x)
        assert targets["outreach"].end_x == pytest.approx(guides["outreach"].scene_x)
        assert targets["tackle_length"].start_x == pytest.approx(guides["hook_height"].scene_x)
        assert targets["tackle_length"].start_y == pytest.approx(guides["hook_height"].scene_y)


class TestDrawnHookLoadsOnThePlumbLine:
    def test_the_hook_load_acts_at_the_hook_along_gravity(self, document):
        inputs = _inputs(_tilted(document), hook_load_kN=5000.0)
        gravity = inputs.crane_gravity()
        positions = inputs.node_positions()
        hook = positions[inputs.hoist["load_node_id"]]

        hook_loads = inputs.body_loads(positions).category(dl.HOOK_LOAD)

        assert len(hook_loads) == 1
        (load,) = hook_loads
        assert (load.world_x, load.world_z) == pytest.approx((hook["x"], hook["z"]))
        assert load.fx_kN == pytest.approx(5000.0 * gravity.lateral_x)
        assert load.fz_kN == pytest.approx(-5000.0 * gravity.vertical)

    def test_offlead_still_enters_at_the_sheave(self, document):
        inputs = _inputs(_tilted(document), hook_load_kN=5000.0, offlead_deg=2.0)
        positions = inputs.node_positions()
        sheave = positions[hook_support_node_id(inputs.document_dict, "MH")]

        offlead = [
            load
            for load in inputs.body_loads(positions).category(dl.HOOK_LOAD)
            if load.label.startswith("Offlead")
        ]

        assert len(offlead) == 1
        assert (offlead[0].world_x, offlead[0].world_z) == pytest.approx((sheave["x"], sheave["z"]))
        assert offlead[0].fz_kN == 0.0

    def test_idle_hook_weights_act_at_the_idle_hooks(self, document):
        inputs = _inputs(_tilted(document))
        positions = inputs.node_positions()
        hooks = _hooks(inputs.document_dict)
        idle = set(hooks) - {inputs.hoist["load_node_id"]}

        idle_loads = inputs.body_loads(positions).category(dl.IDLE_HOOK_MASS)

        assert idle_loads
        hook_points = {(positions[h]["x"], positions[h]["z"]) for h in idle}
        for load in idle_loads:
            assert (load.world_x, load.world_z) in hook_points
            assert load.fx_kN != 0.0


class TestRopeIsWeighedUpright:
    """A plumb hook's drawn falls are a projection; rope is weighed at true length."""

    def test_upright_positions_undo_the_plumb_drawing(self, document):
        inputs = _inputs(_tilted(document))
        base = inputs.base_node_positions()
        hooks = _hooks(inputs.document_dict)
        active = inputs.hoist["load_node_id"]

        upright = dl.upright_hook_positions(
            inputs.document_dict, inputs.node_positions(), inputs.crane_gravity()
        )

        for node_id, point in base.items():
            if node_id == active:
                sheave = base[hooks[active]]
                expected = {"x": sheave["x"], "z": sheave["z"] - TACKLE_M}
                assert upright[node_id] == pytest.approx(expected)
            else:
                assert upright[node_id] == pytest.approx(point), node_id

    def test_hook_sheaves_name_every_payload_hook_and_no_boom_sheave(self, document):
        doc_dict = document.model_dump()

        sheaves = dl.hook_sheaves(doc_dict)

        assert sheaves == _hooks(doc_dict)
        boom_hoist = next(h for h in doc_dict["hoists"] if h["id"] == "BH")
        assert boom_hoist["load_node_id"] not in sheaves

    def test_rope_weights_do_not_shift_when_gravity_leans_across_the_plane(self, document):
        # Heel over the bow leans gravity across the luffing plane: the drawn falls
        # are foreshortened, but the rope on them and on the drum must not change.
        level = _inputs(document, slew_deg=0.0)
        heeled = _inputs(_tilted(document, heel_deg=10.0, trim_deg=0.0), slew_deg=0.0)
        vertical = heeled.crane_gravity().vertical
        assert abs(heeled.crane_gravity().lateral_y) > 0.15

        def masses(inputs, vertical_fraction: float) -> dict[str, float]:
            """Rope mass per node, by its "Rope weight @ <node>" label."""
            loads = inputs.body_loads(inputs.node_positions()).category(dl.ROPE_WEIGHT)
            return {load.label.split(":")[0]: -load.fz_kN / vertical_fraction for load in loads}

        assert masses(heeled, vertical) == pytest.approx(masses(level, 1.0), rel=1e-12)

    def test_the_winch_readout_does_not_shift_either(self, document):
        level = build_scene_frame(_inputs(document, slew_deg=0.0))
        heeled = build_scene_frame(
            _inputs(_tilted(document, heel_deg=10.0, trim_deg=0.0), slew_deg=0.0)
        )

        assert heeled.winch_spools == level.winch_spools
