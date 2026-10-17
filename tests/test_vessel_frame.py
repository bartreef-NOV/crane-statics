import math

import pytest

from crane_statics.calculation.vessel_frame import (
    VesselInputs,
    crane_frame_motion,
    gravity_in_vessel_frame,
)

G = 9.81


def test_level_vessel_gravity_is_straight_down():
    gx, gy, gz = gravity_in_vessel_frame(G, 0.0, 0.0)
    assert (gx, gy, gz) == pytest.approx((0.0, 0.0, -G))


def test_pitch_bow_down_gives_forward_gravity_component():
    gx, gy, gz = gravity_in_vessel_frame(G, 0.0, 10.0)
    assert gx == pytest.approx(G * math.sin(math.radians(10.0)))
    assert gy == pytest.approx(0.0)
    assert gz == pytest.approx(-G * math.cos(math.radians(10.0)))


def test_roll_to_starboard_gives_gravity_toward_starboard_negative_y():
    gx, gy, gz = gravity_in_vessel_frame(G, 10.0, 0.0)
    assert gx == pytest.approx(0.0)
    assert gy == pytest.approx(-G * math.sin(math.radians(10.0)))
    assert gz == pytest.approx(-G * math.cos(math.radians(10.0)))


def test_gravity_magnitude_is_preserved_for_combined_angles():
    gx, gy, gz = gravity_in_vessel_frame(G, 7.0, -12.0)
    assert math.sqrt(gx**2 + gy**2 + gz**2) == pytest.approx(G)


def test_zero_inputs_give_zero_equivalent_motion():
    m = crane_frame_motion(G, VesselInputs())
    assert m.load_accel == pytest.approx((0.0, 0.0, -G))
    assert (m.accel_x_m_s2, m.accel_y_m_s2, m.accel_z_m_s2) == pytest.approx((0.0, 0.0, 0.0))
    assert m.pitch_accel_rad_s2 == pytest.approx(0.0)
    assert m.roll_accel_rad_s2 == pytest.approx(0.0)


def test_level_acceleration_matches_legacy_convention():
    # Legacy: Fx = -m*ax, Fz = -m*(g + az)
    m = crane_frame_motion(G, VesselInputs(accel_x_m_s2=1.5, accel_z_m_s2=0.4))
    assert m.load_accel == pytest.approx((-1.5, 0.0, -(G + 0.4)))
    assert (m.accel_x_m_s2, m.accel_z_m_s2) == pytest.approx((1.5, 0.4))


def test_slew_90_maps_vessel_x_acceleration_to_negative_crane_y():
    m = crane_frame_motion(G, VesselInputs(accel_x_m_s2=1.0, slew_deg=90.0))
    assert m.accel_x_m_s2 == pytest.approx(0.0, abs=1e-12)
    assert m.accel_y_m_s2 == pytest.approx(-1.0)


def test_slew_90_maps_vessel_pitch_tilt_to_crane_y_gravity():
    m = crane_frame_motion(G, VesselInputs(pitch_deg=10.0, slew_deg=90.0))
    s = math.sin(math.radians(10.0))
    # vessel-frame g_x = G*s; crane y = -vessel x
    assert m.load_accel[0] == pytest.approx(0.0, abs=1e-12)
    assert m.load_accel[1] == pytest.approx(-G * s)


def test_slew_180_negates_horizontal_components():
    a = crane_frame_motion(G, VesselInputs(accel_x_m_s2=1.0, accel_y_m_s2=2.0))
    b = crane_frame_motion(G, VesselInputs(accel_x_m_s2=1.0, accel_y_m_s2=2.0, slew_deg=180.0))
    assert b.accel_x_m_s2 == pytest.approx(-a.accel_x_m_s2)
    assert b.accel_y_m_s2 == pytest.approx(-a.accel_y_m_s2)
    assert b.accel_z_m_s2 == pytest.approx(a.accel_z_m_s2)


def test_angular_accelerations_rotate_with_slew():
    m0 = crane_frame_motion(G, VesselInputs(roll_accel_rad_s2=0.1, pitch_accel_rad_s2=0.2))
    assert (m0.roll_accel_rad_s2, m0.pitch_accel_rad_s2) == pytest.approx((0.1, 0.2))
    m90 = crane_frame_motion(
        G, VesselInputs(roll_accel_rad_s2=0.1, pitch_accel_rad_s2=0.2, slew_deg=90.0)
    )
    assert m90.roll_accel_rad_s2 == pytest.approx(0.2)
    assert m90.pitch_accel_rad_s2 == pytest.approx(-0.1)


def test_angular_accelerations_rotate_at_intermediate_slew():
    roll, pitch, slew = 0.1, 0.2, 30.0
    m = crane_frame_motion(
        G, VesselInputs(roll_accel_rad_s2=roll, pitch_accel_rad_s2=pitch, slew_deg=slew)
    )
    c, s = math.cos(math.radians(slew)), math.sin(math.radians(slew))
    assert m.roll_accel_rad_s2 == pytest.approx(c * roll + s * pitch)
    assert m.pitch_accel_rad_s2 == pytest.approx(-s * roll + c * pitch)


def test_level_unslewed_crane_gravity_and_accel_are_the_vessel_values():
    m = crane_frame_motion(G, VesselInputs(accel_x_m_s2=0.4, accel_y_m_s2=-0.2, accel_z_m_s2=0.3))
    assert m.gravity_crane == (0.0, 0.0, -G)
    assert m.accel_crane == pytest.approx((0.4, -0.2, 0.3), rel=1e-15)


def test_slew_90_maps_vessel_x_to_negative_crane_y_for_gravity_and_accel():
    m = crane_frame_motion(G, VesselInputs(pitch_deg=10.0, accel_x_m_s2=1.0, slew_deg=90.0))
    beta = math.radians(10.0)
    assert m.gravity_crane == pytest.approx(
        (0.0, -G * math.sin(beta), -G * math.cos(beta)), abs=1e-12
    )
    assert m.accel_crane == pytest.approx((0.0, -1.0, 0.0), abs=1e-12)


def test_crane_gravity_keeps_magnitude_g():
    m = crane_frame_motion(G, VesselInputs(roll_deg=7.0, pitch_deg=-12.0, slew_deg=33.0))
    assert math.sqrt(sum(c * c for c in m.gravity_crane)) == pytest.approx(G, rel=1e-12)


def test_crane_gravity_minus_crane_accel_is_the_load_accel():
    m = crane_frame_motion(
        G,
        VesselInputs(
            roll_deg=5.0, pitch_deg=8.0, slew_deg=30.0, accel_x_m_s2=0.4, accel_z_m_s2=0.3
        ),
    )
    k = tuple(g - a for g, a in zip(m.gravity_crane, m.accel_crane))
    assert k == pytest.approx(m.load_accel, abs=1e-12)
