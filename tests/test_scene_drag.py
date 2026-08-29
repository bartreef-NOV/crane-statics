"""The scene drag gesture: what a pointer position asks the scene to become.

Every test here goes through the gesture's own interface -- ``begin``, ``edit``,
``target_at`` -- against a stub canvas and plain numbers. No view model, no
session, no renderer, so clamping, alt-snap and the heel-relative angle are
asserted where they can actually be wrong.
"""

import pytest

from crane_statics.qml_app.scene.scene_drag import DragEdit, DragLimits, SceneDrag


class StubCanvas:
    """A canvas as a drag gesture sees it: a mapping, a scale and a heel.

    Scene pixels run down-positive at ``scale`` pixels per metre with the world
    origin at scene (0, 0), so world x is scene x over the scale and world z is
    its negation -- the same flip the real ``SceneMapping`` applies.
    """

    def __init__(self, *, scale: float = 10.0, heel=(0.0, 0.0)):
        self._scale = float(scale)
        self._heel = heel

    @property
    def scene_to_world(self):
        return lambda scene_x, scene_y: (scene_x / self._scale, -scene_y / self._scale)

    @property
    def map_scale(self) -> float:
        return self._scale

    @property
    def heel_world(self):
        return self._heel


class TestBeginning:
    @pytest.mark.parametrize("kind", ["boom_angle", "outreach", "tackle_length"])
    def test_every_drawn_quantity_can_be_grabbed(self, kind):
        assert SceneDrag.begin(kind, 0.0, 0.0).kind == kind

    @pytest.mark.parametrize("kind", ["invalid", "", "BOOM_ANGLE"])
    def test_nothing_else_starts_a_gesture(self, kind):
        assert SceneDrag.begin(kind, 0.0, 0.0) is None


class TestOutreachDrag:
    def test_asks_for_the_world_x_under_the_pointer(self):
        drag = SceneDrag.begin("outreach", 0.0, 0.0)

        assert drag.edit(StubCanvas(), 425.0, 700.0) == DragEdit("outreach_m", 42.5)

    def test_alt_snaps_to_half_a_metre(self):
        drag = SceneDrag.begin("outreach", 0.0, 0.0)

        edit = drag.edit(StubCanvas(), 123.0, 700.0, alt_snap=True)

        assert edit.value == pytest.approx(12.5)


class TestTackleDrag:
    def test_pixels_dragged_down_become_metres_paid_out(self):
        drag = SceneDrag.begin("tackle_length", 200.0, 10.0)

        edit = drag.edit(StubCanvas(scale=10.0), 0.0, 220.0)

        assert edit.field == "tackle_m"
        assert edit.value == pytest.approx(12.0)

    def test_dragging_up_hauls_rope_back_in(self):
        drag = SceneDrag.begin("tackle_length", 200.0, 10.0)

        edit = drag.edit(StubCanvas(scale=10.0), 0.0, 150.0)

        assert edit.value == pytest.approx(5.0)

    def test_is_clamped_to_the_hoist_travel_limits(self):
        drag = SceneDrag.begin("tackle_length", 200.0, 10.0)
        limits = DragLimits(tackle_m=(5.0, 12.0))

        paid_out = drag.edit(StubCanvas(), 0.0, 9000.0, limits=limits)
        hauled_in = drag.edit(StubCanvas(), 0.0, -9000.0, limits=limits)

        assert paid_out.value == pytest.approx(12.0)
        assert hauled_in.value == pytest.approx(5.0)

    def test_alt_snaps_to_half_a_metre(self):
        drag = SceneDrag.begin("tackle_length", 200.0, 10.0)

        edit = drag.edit(StubCanvas(scale=10.0), 0.0, 226.0, alt_snap=True)

        assert edit.value == pytest.approx(12.5)

    def test_a_scaleless_canvas_does_not_divide_by_zero(self):
        drag = SceneDrag.begin("tackle_length", 200.0, 10.0)

        edit = drag.edit(StubCanvas(scale=0.0), 0.0, 200.0)

        assert edit.value == pytest.approx(10.0)


class TestBoomAngleDrag:
    def test_is_measured_from_the_heel_not_the_world_origin(self):
        drag = SceneDrag.begin("boom_angle", 0.0, 0.0)
        # Heel at world (10, 0); pointer at world (20, 10) -- 45 degrees above it.
        canvas = StubCanvas(scale=10.0, heel=(10.0, 0.0))

        edit = drag.edit(canvas, 200.0, -100.0)

        assert edit.field == "angle_deg"
        assert edit.value == pytest.approx(45.0)

    def test_is_clamped_to_the_reachable_range(self):
        drag = SceneDrag.begin("boom_angle", 0.0, 0.0)

        edit = drag.edit(StubCanvas(), 100.0, -100.0, limits=DragLimits(angle_deg=(0.0, 30.0)))

        assert edit.value == pytest.approx(30.0)

    def test_alt_snaps_to_half_a_degree(self):
        drag = SceneDrag.begin("boom_angle", 0.0, 0.0)

        # World (10, 9.9) off the heel is 44.71 degrees.
        edit = drag.edit(StubCanvas(scale=10.0), 100.0, -99.0, alt_snap=True)

        assert edit.value == pytest.approx(44.5)

    def test_asks_for_nothing_when_there_is_no_heel_to_pivot_about(self):
        drag = SceneDrag.begin("boom_angle", 0.0, 0.0)

        assert drag.edit(StubCanvas(heel=None), 100.0, -100.0) is None

    def test_asks_for_nothing_when_the_pointer_is_on_the_heel(self):
        drag = SceneDrag.begin("boom_angle", 0.0, 0.0)

        assert drag.edit(StubCanvas(heel=(10.0, -20.0)), 100.0, 200.0) is None


class TestTargetAt:
    """Hit-testing: which quantity a press would grab, from the frame's targets."""

    def test_nothing_is_grabbed_where_there_are_no_targets(self):
        assert SceneDrag.target_at(0.0, 0.0, []) == ""

    @pytest.mark.parametrize(
        "radius, expected",
        [(3.0, "boom_angle"), (2.9, "")],
        ids=["within_radius", "outside_radius"],
    )
    def test_the_boom_is_grabbed_by_perpendicular_distance_to_its_segment(self, radius, expected):
        # (5, 3) is exactly 3 px off the segment (0, 0) -> (10, 0).
        targets = [
            {
                "kind": "boom_angle",
                "start_x": 0.0,
                "start_y": 0.0,
                "end_x": 10.0,
                "end_y": 0.0,
                "radius": radius,
            }
        ]

        assert SceneDrag.target_at(5.0, 3.0, targets) == expected

    @pytest.mark.parametrize(
        "radius, expected",
        [(1.0, "boom_angle"), (0.9, "")],
        ids=["within_radius", "outside_radius"],
    )
    def test_distance_past_the_boom_segment_is_measured_to_its_endpoint(self, radius, expected):
        # (2, 0) is beyond the segment's end, so the nearest point is (1, 0).
        targets = [
            {
                "kind": "boom_angle",
                "start_x": 0.0,
                "start_y": 0.0,
                "end_x": 1.0,
                "end_y": 0.0,
                "radius": radius,
            }
        ]

        assert SceneDrag.target_at(2.0, 0.0, targets) == expected

    def test_a_boom_segment_of_zero_length_is_grabbed_as_a_point(self):
        targets = [
            {
                "kind": "boom_angle",
                "start_x": 4.0,
                "start_y": 4.0,
                "end_x": 4.0,
                "end_y": 4.0,
                "radius": 5.0,
            }
        ]

        assert SceneDrag.target_at(7.0, 8.0, targets) == "boom_angle"

    def test_the_outreach_guide_is_grabbed_below_its_anchor_only(self):
        targets = [{"kind": "outreach", "start_x": 100.0, "start_y": 200.0, "radius": 10.0}]

        assert SceneDrag.target_at(105.0, 250.0, targets) == "outreach"
        assert SceneDrag.target_at(105.0, 150.0, targets) == ""
        assert SceneDrag.target_at(120.0, 250.0, targets) == ""

    def test_the_hook_height_guide_is_grabbed_right_of_its_anchor_only(self):
        targets = [{"kind": "tackle_length", "start_x": 200.0, "start_y": 100.0, "radius": 10.0}]

        assert SceneDrag.target_at(250.0, 105.0, targets) == "tackle_length"
        assert SceneDrag.target_at(150.0, 105.0, targets) == ""
        assert SceneDrag.target_at(250.0, 130.0, targets) == ""

    def test_the_frames_ordering_decides_which_of_two_overlapping_targets_wins(self):
        targets = [
            {"kind": "outreach", "start_x": 100.0, "start_y": 200.0, "radius": 10.0},
            {
                "kind": "boom_angle",
                "start_x": 100.0,
                "start_y": 200.0,
                "end_x": 100.0,
                "end_y": 300.0,
                "radius": 10.0,
            },
        ]

        assert SceneDrag.target_at(105.0, 250.0, targets) == "outreach"
        assert SceneDrag.target_at(105.0, 250.0, list(reversed(targets))) == "boom_angle"

    def test_an_unknown_target_kind_is_ignored(self):
        targets = [{"kind": "slew", "start_x": 100.0, "start_y": 200.0, "radius": 100.0}]

        assert SceneDrag.target_at(105.0, 250.0, targets) == ""
