import pytest
from pydantic import ValidationError

from crane_statics.data.authored_models import (
    AUTHORED_SCHEMA_MAJOR_VERSION,
    AuthoredEnvironment,
    AuthoredVesselMotion,
)
from crane_statics.data.models import Environment, VesselMotion


def test_schema_major_is_7():
    assert AUTHORED_SCHEMA_MAJOR_VERSION == 7


def test_authored_vessel_motion_accepts_signed_values_and_angles():
    vm = AuthoredVesselMotion(
        accel_x_m_s2=-1.2, roll_deg=-4.0, pitch_deg=3.0, crane_slewing_angle_deg=-90.0
    )
    assert vm.accel_x_m_s2 == -1.2
    assert vm.crane_slewing_angle_deg == -90.0


def test_authored_environment_rejects_removed_wind_fields():
    with pytest.raises(ValidationError):
        AuthoredEnvironment(max_wind_speed_m_s=20.0, wind_profile_exponent=0.143)
    with pytest.raises(ValidationError):
        AuthoredEnvironment(max_wind_speed_m_s=20.0, mean_sealevel_z_m=-35.0)


def test_runtime_models_have_signed_motion_and_no_wind_profile():
    vm = VesselMotion(accel_z_m_s2=-0.5, roll_deg=2.0)
    assert vm.accel_z_m_s2 == -0.5
    env = Environment()
    for removed in ("wind_profile_exponent", "wind_reference_height_m_asl", "mean_sealevel_z_m"):
        assert not hasattr(env, removed)
