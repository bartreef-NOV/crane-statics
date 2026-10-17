"""Vessel-frame motion → crane-frame load acceleration (pure, Qt-free).

Vessel axes: x forward, y port, z up. Pitch is positive bow-down, roll positive to
starboard. R = Rz(yaw)·Ry(pitch)·Rx(roll) (intrinsic z-y-x) maps vessel → world, so
gravity in the vessel frame is Rᵀ·(0, 0, -g); yaw drops out. The crane frame is the vessel
frame rotated about z by the slewing angle.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class VesselInputs:
    accel_x_m_s2: float = 0.0
    accel_y_m_s2: float = 0.0
    accel_z_m_s2: float = 0.0
    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    slew_deg: float = 0.0
    roll_accel_rad_s2: float = 0.0
    pitch_accel_rad_s2: float = 0.0


@dataclass(frozen=True)
class CraneFrameMotion:
    load_accel: tuple[float, float, float]
    accel_x_m_s2: float
    accel_y_m_s2: float
    accel_z_m_s2: float
    pitch_accel_rad_s2: float
    roll_accel_rad_s2: float
    # Gravity and the vessel's own linear acceleration, each rotated into the crane frame;
    # gravity_crane - accel_crane == load_accel. Drawn loads use this split.
    gravity_crane: tuple[float, float, float]
    accel_crane: tuple[float, float, float]


def gravity_in_vessel_frame(
    g: float, roll_deg: float, pitch_deg: float
) -> tuple[float, float, float]:
    """Return gravity (m/s²) in the vessel frame for a positive magnitude ``g``."""
    roll = math.radians(roll_deg)
    pitch = math.radians(pitch_deg)
    return (
        g * math.sin(pitch),
        -g * math.sin(roll) * math.cos(pitch),
        -g * math.cos(roll) * math.cos(pitch),
    )


def _vessel_to_crane(x: float, y: float, slew_deg: float) -> tuple[float, float]:
    """Rotate a horizontal vessel-frame vector by -slew about z."""
    s = math.radians(slew_deg)
    return (
        math.cos(s) * x + math.sin(s) * y,
        -math.sin(s) * x + math.cos(s) * y,
    )


def crane_frame_motion(g: float, inputs: VesselInputs) -> CraneFrameMotion:
    """Resolve vessel inputs into the crane-frame load acceleration and equivalent motion."""
    gx, gy, gz = gravity_in_vessel_frame(g, inputs.roll_deg, inputs.pitch_deg)
    kx_v = gx - inputs.accel_x_m_s2
    ky_v = gy - inputs.accel_y_m_s2
    kz = gz - inputs.accel_z_m_s2
    kx, ky = _vessel_to_crane(kx_v, ky_v, inputs.slew_deg)
    gx_c, gy_c = _vessel_to_crane(gx, gy, inputs.slew_deg)
    ax_c, ay_c = _vessel_to_crane(inputs.accel_x_m_s2, inputs.accel_y_m_s2, inputs.slew_deg)
    roll_c, pitch_c = _vessel_to_crane(
        inputs.roll_accel_rad_s2, inputs.pitch_accel_rad_s2, inputs.slew_deg
    )
    return CraneFrameMotion(
        load_accel=(kx, ky, kz),
        accel_x_m_s2=-kx,
        accel_y_m_s2=-ky,
        accel_z_m_s2=-g - kz,
        pitch_accel_rad_s2=pitch_c,
        roll_accel_rad_s2=roll_c,
        gravity_crane=(gx_c, gy_c, gz),
        accel_crane=(ax_c, ay_c, float(inputs.accel_z_m_s2)),
    )
