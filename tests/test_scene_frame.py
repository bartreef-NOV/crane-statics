"""Toolkit-neutral scene frame assembly."""

import pytest

from crane_statics.core.scene_frame import SceneFrameBuilder, SceneMapping, SceneNode, SceneStatus


def test_builder_emits_immutable_monotonic_frame_revisions():
    builder = SceneFrameBuilder()
    builder.add_node("node", 10.0, 20.0, "node tooltip")
    builder.add_segment(
        kind="rope",
        source_id="node",
        target_id="tip",
        start_x=10.0,
        start_y=20.0,
        end_x=30.0,
        end_y=40.0,
        color="#000000",
        width=2.0,
        tooltip="rope tooltip",
    )
    builder.add_marker(
        kind="center_of_gravity",
        scene_x=15.0,
        scene_y=25.0,
        radius=6.0,
        tooltip="CG tooltip",
    )
    builder.add_axis(
        label="X",
        start_x=10.0,
        start_y=20.0,
        end_x=30.0,
        end_y=20.0,
        color="#ff0000",
    )
    builder.add_force_arrow(
        origin_x=10.0,
        origin_y=20.0,
        tip_x=30.0,
        tip_y=40.0,
        color="#00ff00",
        dashed=False,
        label="force",
        tooltip="force tooltip",
    )
    builder.add_moment(
        origin_x=10.0,
        origin_y=20.0,
        moment_kNm=12.0,
        radius=14.0,
        start_degrees=-50.0,
        span_degrees=280.0,
        arrow_tip_x=30.0,
        arrow_tip_y=40.0,
        color="#0000ff",
        label="moment",
        tooltip="moment tooltip",
    )
    builder.add_label(kind="force", scene_x=30.0, scene_y=40.0, color="#00ff00", text="force")
    builder.add_guide(kind="outreach", scene_x=30.0, scene_y=40.0, label="R = 30.0 m")
    builder.set_waterline(scene_y=100.0, elevation_z=0.0, label="MSL  z = 0.0 m")
    builder.add_hit_target(
        kind="outreach",
        start_x=30.0,
        start_y=40.0,
        end_x=30.0,
        end_y=700.0,
        radius=10.0,
        extends_to_canvas_edge=True,
    )

    first = builder.build(fit_rect=(1.0, 2.0, 3.0, 4.0))
    builder.reset()
    second = builder.build(fit_rect=(0.0, 0.0, 0.0, 0.0))

    assert first.revision == 1
    assert first.nodes == (SceneNode("node", 10.0, 20.0, "node tooltip"),)
    assert first.rope_segments[0].tooltip == "rope tooltip"
    assert first.markers[0].tooltip == "CG tooltip"
    assert first.boom_axes[0].label == "X"
    assert first.force_arrows[0].tooltip == "force tooltip"
    assert first.moments[0].tooltip == "moment tooltip"
    assert first.labels[0].text == "force"
    assert first.guides[0].label == "R = 30.0 m"
    assert first.waterline is not None
    assert first.hit_targets[0].kind == "outreach"
    assert second.revision == 2
    assert second.nodes == ()


def test_builder_carries_toolkit_neutral_status_text():
    builder = SceneFrameBuilder()
    builder.status = SceneStatus("Load a document to view geometry", "#7A7A7A")

    frame = builder.build(fit_rect=(0.0, 0.0, 0.0, 0.0))

    assert frame.status == SceneStatus("Load a document to view geometry", "#7A7A7A")


def test_mapping_round_trips_world_coordinates_and_derives_fit_bounds():
    mapping = SceneMapping.from_positions(
        {"left": {"x": 10.0, "z": -5.0}, "right": {"x": 30.0, "z": 15.0}}
    )

    scene_point = mapping.to_scene(20.0, 5.0)
    assert mapping.to_world(*scene_point) == pytest.approx((20.0, 5.0))
    assert mapping.fit_rect(
        [mapping.to_scene(10.0, -5.0), mapping.to_scene(30.0, 15.0)]
    ) == pytest.approx((32.0, 32.0, 696.0, 696.0))


def test_builder_generates_filtered_nodes_and_suppresses_cg_overlap():
    builder = SceneFrameBuilder()
    builder.add_marker(
        kind="center_of_gravity",
        scene_x=10.0,
        scene_y=10.0,
        radius=6.0,
        tooltip="CG",
    )

    nodes = builder.add_nodes_from_positions(
        {"overlap": {"x": 10.0, "z": 10.0}, "shown": {"x": 30.0, "z": 40.0}},
        project=lambda x, z: (x, z),
        tooltip_for=lambda node_id, _position: node_id,
    )

    assert nodes == (SceneNode("shown", 30.0, 40.0, "shown"),)


def test_builder_generates_structural_members_for_the_selected_freebody():
    positions = {
        "rear_base": {"x": 0.0, "z": 0.0},
        "rear_top": {"x": 1.0, "z": 2.0},
        "front_base": {"x": 4.0, "z": 0.0},
        "front_top": {"x": 3.0, "z": 2.0},
    }
    builder = SceneFrameBuilder()

    rear_only = builder.add_structural_members(
        positions,
        project=lambda x, z: (x, z),
        selected_freebody="rear_leg",
        color="#7A7A7A",
        width=2.0,
    )

    assert [segment.tooltip for segment in rear_only] == [
        "Rear leg\nFrom: rear_base\nTo: rear_top\nLength: 2.24 m"
    ]


def test_builder_generates_rope_segments_from_projected_positions():
    builder = SceneFrameBuilder()
    segments = builder.add_rope_segments(
        [{"id": "rope", "segments": [{"from_node_id": "a", "to_node_id": "b", "mult": 2}]}],
        {"a": {"x": 1.0, "z": 2.0}, "b": {"x": 3.0, "z": 4.0}},
        project=lambda x, z: (x * 10.0, z * 10.0),
        effective_multiplier=lambda _rope_id, _segment, authored: authored,
        style_for=lambda _rope_id, _multiplier: ("#000000", 2.0),
        tooltip_for=lambda *_args: "rope tooltip",
    )

    assert len(segments) == 1
    assert segments[0].start_x == 10.0
    assert segments[0].end_y == 40.0
    assert segments[0].tooltip == "rope tooltip"


def test_builder_generates_rotated_boom_cg_markers():
    builder = SceneFrameBuilder()
    markers = builder.add_cg_markers(
        [{"id": "boom", "mass_points": [{"id": "cg", "mass_t": 1.0, "local_x_m": 10.0}]}],
        heel={"x": 0.0, "z": 0.0},
        boom_angle_degrees=90.0,
        project=lambda x, z: (x, z),
        include_body=lambda _body_id: True,
        tooltip_for=lambda mass_point: mass_point["id"],
    )

    assert markers[0].scene_x == pytest.approx(0.0)
    assert markers[0].scene_y == pytest.approx(10.0)
    assert markers[0].tooltip == (
        "Center of gravity\n" "Mass point: cg\n" "Mass: 1.00 t\n" "Position: (0.00, 10.00) m"
    )


def test_builder_lowers_the_hook_from_its_support_node_without_mutating_inputs():
    positions = {"support": {"x": 10.0, "z": 30.0}, "hook": {"x": 10.0, "z": 28.0}}

    result = SceneFrameBuilder.with_hook_tackle(
        positions,
        {"hook": {"below_node_id": "support"}},
        "hook",
        12.0,
    )

    assert result["hook"] == {"x": 10.0, "z": 18.0}
    assert positions["hook"] == {"x": 10.0, "z": 28.0}


def test_builder_generates_split_support_cg_marker():
    builder = SceneFrameBuilder()

    marker = builder.add_split_support_cg_marker(
        {"support": {"x": 12.0, "z": 25.0}},
        support_node_id="support",
        support_mass_t=4.5,
        include_node=lambda _node_id: True,
        project=lambda x, z: (x, z),
        hoist_label="MH",
    )

    assert marker is not None
    assert marker.tooltip == "MH split block CG: 4.5 t  (12.0 m, 25.0 m)"
