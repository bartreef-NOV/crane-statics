"""Typed contracts for data crossing UI/service boundaries.

This module consolidates dict-heavy payloads into explicit TypedDict and dataclass
contracts, reducing implicit coupling and improving maintainability. These are used
for data flowing between:
- QML view layer and Qt view models
- View models and domain services
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, TypedDict

# =====================================================================
# Model Edit Payloads
# =====================================================================


class NodeFieldsDict(TypedDict, total=False):
    """Typed dict for node field data crossing QML boundary.

    Returned by ModelViewModel.nodeFields() for QML display and editing.
    """

    id: str
    hanging: bool
    below_node_id: str
    x_m: float
    z_m: float
    local_x_m: float
    local_z_m: float


class MassPointFieldsDict(TypedDict, total=False):
    """Typed dict for mass point field data crossing QML boundary."""

    id: str
    mass_t: float
    x_m: float
    y_m: float
    z_m: float
    local_x_m: float
    local_y_m: float
    local_z_m: float


class WindAreaFieldsDict(TypedDict, total=False):
    """Typed dict for wind area field data crossing QML boundary."""

    id: str
    area_w_m2: float
    area_v_m2: float
    x_m: float
    z_m: float
    local_x_m: float
    local_z_m: float
    cd: float


class HoistFieldsDict(TypedDict, total=False):
    """Typed dict for hoist field data crossing QML boundary."""

    id: str
    tackle_length_m: float


class RopeSegmentFieldsDict(TypedDict, total=False):
    """Typed dict for rope segment field data crossing QML boundary."""

    id: str
    hoist_id: str
    from_node_id: str
    to_node_id: str
    tension_mode: str


class ContractualPointFieldsDict(TypedDict, total=False):
    """Typed dict for contractual point field data crossing QML boundary."""

    outreach_m: float
    load_t: float


# =====================================================================
# Environment Settings
# =====================================================================


@dataclass
class EnvironmentSettings:
    """Environmental and vessel parameters.

    Consolidates environment, vessel motion, and support width settings
    that are frequently edited in the model view.

    Used by ModelViewModel to expose and edit crane environment parameters.
    """

    # Environment
    gravity_m_s2: float = 9.81
    max_wind_speed_m_s: float = 20.0
    wind_reference_height_m_asl: float = 10.0
    air_density_kg_m3: float = 1.225
    wind_profile_exponent: float = 0.2
    mean_sealevel_z_m: float = 0.0

    # Vessel Motion
    heel_deg: float = 0.0
    trim_deg: float = 0.0
    accel_x_m_s2: float = 0.0
    accel_y_m_s2: float = 0.0
    accel_z_m_s2: float = 0.0
    roll_angular_accel_rad_s2: float = 0.0
    pitch_angular_accel_rad_s2: float = 0.0
    reference_x_m: float = 0.0
    reference_z_m: float = 0.0

    # Support Widths
    boom_width_m: float = 0.0
    slewing_bearing_diameter_m: Optional[float] = None

    # Design duty
    hook_height_at_min_outreach_m: float = 0.0

    def to_dict(self) -> dict[str, Optional[float]]:
        """Convert to flat dict for QML or storage."""
        return {
            "gravity_m_s2": self.gravity_m_s2,
            "max_wind_speed_m_s": self.max_wind_speed_m_s,
            "wind_reference_height_m_asl": self.wind_reference_height_m_asl,
            "air_density_kg_m3": self.air_density_kg_m3,
            "wind_profile_exponent": self.wind_profile_exponent,
            "mean_sealevel_z_m": self.mean_sealevel_z_m,
            "heel_deg": self.heel_deg,
            "trim_deg": self.trim_deg,
            "accel_x_m_s2": self.accel_x_m_s2,
            "accel_y_m_s2": self.accel_y_m_s2,
            "accel_z_m_s2": self.accel_z_m_s2,
            "roll_angular_accel_rad_s2": self.roll_angular_accel_rad_s2,
            "pitch_angular_accel_rad_s2": self.pitch_angular_accel_rad_s2,
            "reference_x_m": self.reference_x_m,
            "reference_z_m": self.reference_z_m,
            "boom_width_m": self.boom_width_m,
            "slewing_bearing_diameter_m": self.slewing_bearing_diameter_m,
            "hook_height_at_min_outreach_m": self.hook_height_at_min_outreach_m,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EnvironmentSettings:
        """Construct from flat dict (e.g., from QML or document)."""
        return cls(
            gravity_m_s2=float(data.get("gravity_m_s2", 9.81)),
            max_wind_speed_m_s=float(data.get("max_wind_speed_m_s", 20.0)),
            wind_reference_height_m_asl=float(data.get("wind_reference_height_m_asl", 10.0)),
            air_density_kg_m3=float(data.get("air_density_kg_m3", 1.225)),
            wind_profile_exponent=float(data.get("wind_profile_exponent", 0.2)),
            mean_sealevel_z_m=float(data.get("mean_sealevel_z_m", 0.0)),
            heel_deg=float(data.get("heel_deg", 0.0)),
            trim_deg=float(data.get("trim_deg", 0.0)),
            accel_x_m_s2=float(data.get("accel_x_m_s2", 0.0)),
            accel_y_m_s2=float(data.get("accel_y_m_s2", 0.0)),
            accel_z_m_s2=float(data.get("accel_z_m_s2", 0.0)),
            roll_angular_accel_rad_s2=float(data.get("roll_angular_accel_rad_s2", 0.0)),
            pitch_angular_accel_rad_s2=float(data.get("pitch_angular_accel_rad_s2", 0.0)),
            reference_x_m=float(data.get("reference_x_m", 0.0)),
            reference_z_m=float(data.get("reference_z_m", 0.0)),
            boom_width_m=float(data.get("boom_width_m", 0.0)),
            slewing_bearing_diameter_m=(
                float(v) if (v := data.get("slewing_bearing_diameter_m")) is not None else None
            ),
            hook_height_at_min_outreach_m=float(data.get("hook_height_at_min_outreach_m", 0.0)),
        )

    @classmethod
    def defaults(cls) -> EnvironmentSettings:
        """Return default environment settings."""
        return cls()
