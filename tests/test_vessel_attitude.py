"""Vessel attitude geometry: gravity seen from the slewing crane frame.

Vessel frame x forward, y port, z up. Heel + is starboard down, trim + is bow
down, slew is measured from the bow, + clockwise seen from above. The crane
frame is X along the boom (outreach), Y to its left, Z up.
"""

import math

import pytest

from crane_statics.calculation.vessel_attitude import (
    CraneFrameGravity,
    VesselAttitude,
    crane_frame_gravity,
    envelope_slew_angles,
    normalize_slew_deg,
    worst_in_plane_slew_deg,
)


def _sin(deg: float) -> float:
    return math.sin(math.radians(deg))


def _cos(deg: float) -> float:
    return math.cos(math.radians(deg))


class TestLevelVessel:
    def test_gravity_is_exactly_plumb_at_every_slew(self):
        level = VesselAttitude()
        assert level.is_level
        for slew in (0.0, 37.0, 90.0, 271.5):
            gravity = crane_frame_gravity(level, slew)
            assert (gravity.lateral_x, gravity.lateral_y, gravity.vertical) == (0.0, 0.0, 1.0)

    def test_envelope_collapses_to_a_single_slew(self):
        assert envelope_slew_angles(VesselAttitude()) == (0.0,)


class TestCardinalCases:
    def test_bow_down_trim_tips_gravity_toward_a_boom_over_the_bow(self):
        gravity = crane_frame_gravity(VesselAttitude(trim_deg=3.0), 0.0)
        assert gravity.lateral_x == pytest.approx(_sin(3.0))
        assert gravity.lateral_y == pytest.approx(0.0, abs=1e-15)
        assert gravity.vertical == pytest.approx(_cos(3.0))

    def test_starboard_down_heel_tips_gravity_toward_a_boom_over_starboard(self):
        gravity = crane_frame_gravity(VesselAttitude(heel_deg=4.0), 90.0)
        assert gravity.lateral_x == pytest.approx(_sin(4.0))
        assert gravity.lateral_y == pytest.approx(0.0, abs=1e-15)

    def test_starboard_down_heel_pulls_a_bow_boom_to_its_right(self):
        gravity = crane_frame_gravity(VesselAttitude(heel_deg=4.0), 0.0)
        assert gravity.lateral_x == pytest.approx(0.0, abs=1e-15)
        assert gravity.lateral_y == pytest.approx(-_sin(4.0))

    def test_bow_down_trim_pulls_a_starboard_boom_to_its_left(self):
        # Boom over starboard: the crane's left (+Y) points to the bow.
        gravity = crane_frame_gravity(VesselAttitude(trim_deg=3.0), 90.0)
        assert gravity.lateral_x == pytest.approx(0.0, abs=1e-15)
        assert gravity.lateral_y == pytest.approx(_sin(3.0))

    def test_combined_attitude_matches_the_rotation_formula(self):
        heel, trim, slew = 3.0, -2.0, 130.0
        gravity = crane_frame_gravity(VesselAttitude(heel_deg=heel, trim_deg=trim), slew)
        assert gravity.lateral_x == pytest.approx(
            _sin(trim) * _cos(slew) + _sin(heel) * _cos(trim) * _sin(slew)
        )
        assert gravity.lateral_y == pytest.approx(
            _sin(trim) * _sin(slew) - _sin(heel) * _cos(trim) * _cos(slew)
        )
        assert gravity.vertical == pytest.approx(_cos(heel) * _cos(trim))


class TestInvariants:
    @pytest.mark.parametrize("heel, trim", [(5.0, 0.0), (0.0, -4.0), (3.0, 2.0), (-7.0, 1.5)])
    def test_gravity_is_a_unit_vector_whose_vertical_ignores_slew(self, heel, trim):
        attitude = VesselAttitude(heel_deg=heel, trim_deg=trim)
        verticals = set()
        for slew in range(0, 360, 15):
            g = crane_frame_gravity(attitude, float(slew))
            assert g.lateral_x**2 + g.lateral_y**2 + g.vertical**2 == pytest.approx(1.0)
            verticals.add(round(g.vertical, 14))
        assert len(verticals) == 1

    def test_tilt_angles_describe_the_gravity_direction(self):
        gravity = crane_frame_gravity(VesselAttitude(heel_deg=3.0, trim_deg=2.0), 40.0)
        assert gravity.in_plane_tilt_deg == pytest.approx(
            math.degrees(math.atan2(gravity.lateral_x, gravity.vertical))
        )
        assert gravity.out_of_plane_tilt_deg == pytest.approx(
            math.degrees(math.atan2(gravity.lateral_y, gravity.vertical))
        )
        assert gravity.total_tilt_deg == pytest.approx(math.degrees(math.acos(_cos(3) * _cos(2))))

    def test_plumb_gravity_reports_zero_tilt(self):
        plumb = CraneFrameGravity()
        assert plumb.is_plumb
        assert plumb.total_tilt_deg == 0.0


class TestWorstSlew:
    def test_worst_in_plane_slew_maximises_the_outward_tilt(self):
        attitude = VesselAttitude(heel_deg=3.0, trim_deg=1.0)
        worst = worst_in_plane_slew_deg(attitude)
        peak = crane_frame_gravity(attitude, worst).lateral_x
        assert peak == pytest.approx(math.hypot(_sin(1.0), _sin(3.0) * _cos(1.0)))
        for tenth in range(0, 3600):
            assert crane_frame_gravity(attitude, tenth / 10.0).lateral_x <= peak + 1e-15

    def test_envelope_grid_is_anchored_on_the_worst_slew(self):
        attitude = VesselAttitude(heel_deg=3.0, trim_deg=1.0)
        worst = worst_in_plane_slew_deg(attitude)
        angles = envelope_slew_angles(attitude)
        assert len(angles) == 24
        assert all(0.0 <= a < 360.0 for a in angles)
        for quarter in (0.0, 90.0, 180.0, 270.0):
            target = normalize_slew_deg(worst + quarter)
            assert min(abs(a - target) for a in angles) == pytest.approx(0.0, abs=1e-9)

    def test_envelope_step_must_divide_a_quarter_turn(self):
        with pytest.raises(ValueError):
            envelope_slew_angles(VesselAttitude(heel_deg=1.0), step_deg=25.0)


class TestSlewNormalisation:
    @pytest.mark.parametrize(
        "raw, expected", [(-90.0, 270.0), (360.0, 0.0), (725.0, 5.0), (0.0, 0.0), (359.5, 359.5)]
    )
    def test_wraps_into_one_turn(self, raw, expected):
        assert normalize_slew_deg(raw) == pytest.approx(expected)


class TestFromEnvironment:
    def test_reads_heel_and_trim_from_vessel_motion(self):
        env = {"vessel_motion": {"heel_deg": 2.0, "trim_deg": -1.0, "accel_x_m_s2": 0.3}}
        assert VesselAttitude.from_environment(env) == VesselAttitude(2.0, -1.0)

    @pytest.mark.parametrize("env", [{}, {"vessel_motion": None}, {"vessel_motion": {}}, None])
    def test_missing_values_mean_a_level_vessel(self, env):
        assert VesselAttitude.from_environment(env).is_level
