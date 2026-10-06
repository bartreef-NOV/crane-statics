"""Static vessel attitude (heel, trim) and crane slew as a gravity direction.

Frames and signs:

- Vessel frame: x forward, y to port, z up.
- Heel + is starboard down; trim + is bow down (rotation order ZYX).
- Slew is measured from the bow, + clockwise seen from above (toward starboard).
- Crane frame: X along the boom (outreach), Y to the boom's left, Z up -- the
  frame the solver works in.

Gravity seen from the slewing crane frame, as a unit vector pointing down:

    lateral_x = sin(trim)·cos(slew) + sin(heel)·cos(trim)·sin(slew)   (in-plane)
    lateral_y = sin(trim)·sin(slew) - sin(heel)·cos(trim)·cos(slew)   (out-of-plane)
    vertical  = cos(heel)·cos(trim)                                   (slew-independent)

The lateral parts are what tilting adds: a level vessel gives exactly
(0, 0, 1) and an unchanged model. The hook hangs plumb, so its load direction
is the same vector.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Optional

ENVELOPE_SLEW_STEP_DEG = 15.0
"""Default spacing of the slew samples a load-chart envelope is taken over."""

ATTITUDE_FIELDS = ("heel_deg", "trim_deg")
"""The ``environment.vessel_motion`` fields that make up the static attitude."""


@dataclass(frozen=True)
class VesselAttitude:
    """Static heel and trim of the vessel the crane is mounted on, in degrees."""

    heel_deg: float = 0.0
    trim_deg: float = 0.0

    @property
    def is_level(self) -> bool:
        return self.heel_deg == 0.0 and self.trim_deg == 0.0

    @classmethod
    def from_environment(cls, environment: Optional[Mapping[str, Any]]) -> "VesselAttitude":
        """Read heel and trim from a document's ``environment`` mapping."""
        motion = (environment or {}).get("vessel_motion") or {}
        return cls(
            heel_deg=float(motion.get("heel_deg", 0.0) or 0.0),
            trim_deg=float(motion.get("trim_deg", 0.0) or 0.0),
        )


@dataclass(frozen=True)
class CraneFrameGravity:
    """Unit gravity direction in the crane frame (see the module docstring)."""

    lateral_x: float = 0.0
    lateral_y: float = 0.0
    vertical: float = 1.0

    @property
    def is_plumb(self) -> bool:
        return self.lateral_x == 0.0 and self.lateral_y == 0.0

    @property
    def in_plane_tilt_deg(self) -> float:
        """Tilt of gravity in the luffing plane; + leans toward the boom tip."""
        return math.degrees(math.atan2(self.lateral_x, self.vertical))

    @property
    def out_of_plane_tilt_deg(self) -> float:
        """Tilt of gravity across the luffing plane; + leans to the boom's left."""
        return math.degrees(math.atan2(self.lateral_y, self.vertical))

    @property
    def total_tilt_deg(self) -> float:
        if self.is_plumb:
            return 0.0
        return math.degrees(math.acos(max(-1.0, min(1.0, self.vertical))))


PLUMB = CraneFrameGravity()


def normalize_slew_deg(slew_deg: float) -> float:
    """Wrap a slew angle into [0, 360)."""
    wrapped = float(slew_deg) % 360.0
    return 0.0 if wrapped >= 360.0 else wrapped


def crane_frame_gravity(attitude: VesselAttitude, slew_deg: float) -> CraneFrameGravity:
    """Gravity direction seen by a crane slewed to ``slew_deg`` on a tilted vessel."""
    if attitude.is_level:
        return PLUMB
    heel = math.radians(attitude.heel_deg)
    trim = math.radians(attitude.trim_deg)
    slew = math.radians(slew_deg)
    sin_trim, cos_trim = math.sin(trim), math.cos(trim)
    sin_heel_cos_trim = math.sin(heel) * cos_trim
    return CraneFrameGravity(
        lateral_x=sin_trim * math.cos(slew) + sin_heel_cos_trim * math.sin(slew),
        lateral_y=sin_trim * math.sin(slew) - sin_heel_cos_trim * math.cos(slew),
        vertical=math.cos(heel) * cos_trim,
    )


def worst_in_plane_slew_deg(attitude: VesselAttitude) -> float:
    """Slew at which gravity leans furthest toward the boom tip (0 when level)."""
    if attitude.is_level:
        return 0.0
    heel = math.radians(attitude.heel_deg)
    trim = math.radians(attitude.trim_deg)
    return normalize_slew_deg(
        math.degrees(math.atan2(math.sin(heel) * math.cos(trim), math.sin(trim)))
    )


def envelope_slew_angles(
    attitude: VesselAttitude, step_deg: float = ENVELOPE_SLEW_STEP_DEG
) -> tuple[float, ...]:
    """Slew samples for a worst-case-over-slew envelope.

    The grid is anchored on the worst in-plane slew, so the peak in-plane and
    out-of-plane tilts (a quarter turn apart) are sampled exactly. Between
    samples a response linear in the tilt is under-estimated by at most
    R·(1 - cos(step/2)) of its tilt sensitivity, R being the tilt's sine. A
    level vessel needs one sample.
    """
    step = float(step_deg)
    if step <= 0.0 or not math.isclose(90.0 / step, round(90.0 / step)):
        raise ValueError(f"slew envelope step must divide 90 degrees, got {step_deg}")
    if attitude.is_level:
        return (0.0,)
    anchor = worst_in_plane_slew_deg(attitude)
    count = int(round(360.0 / step))
    return tuple(normalize_slew_deg(anchor + k * step) for k in range(count))
