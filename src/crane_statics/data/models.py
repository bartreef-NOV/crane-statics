"""Data contract models for Crane Statics.

This module defines the Pydantic runtime models that enforce strict validation
according to the handoff data contract. Normalization lives in ``data.normalize``
and the runtime-to-authored conversion in ``data.authored_form``.
"""

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .authored_models import DEFAULT_AIR_DENSITY_KG_M3, DEFAULT_GRAVITY_M_S2

CANONICAL_BODIES = ["boom", "rear_leg", "front_leg", "platform"]
DEFAULT_VESSEL_MOTION = {
    "accel_x_m_s2": 0.0,
    "accel_y_m_s2": 0.0,
    "accel_z_m_s2": 0.0,
    "roll_deg": 0.0,
    "pitch_deg": 0.0,
    "pitch_angular_accel_rad_s2": 0.0,
    "roll_angular_accel_rad_s2": 0.0,
    "reference_x_m": 0.0,
    "reference_z_m": 0.0,
}
PRIMARY_NODE_DEFAULTS: dict[str, dict[str, Any]] = {
    "platform_base": {"body": "platform", "x_m": 0.0, "z_m": 0.0},
    "boom_heel": {"body": "boom", "x_m": 8.5, "z_m": 8.0},
    "rear_base": {"body": "rear_leg", "x_m": -11.0, "z_m": 7.7},
    "rear_top": {"body": "rear_leg", "x_m": -11.0, "z_m": 52.3},
    "front_base": {"body": "front_leg", "x_m": 6.87, "z_m": 7.7},
}
PRIMARY_NODE_IDS = set(PRIMARY_NODE_DEFAULTS.keys())
PRIMARY_STRUCTURE_TO_RUNTIME_NODE = {
    "boom_heel": ("boom_heel", "boom"),
    "upper_hinge": ("rear_top", "rear_leg"),
    "rear_hinge": ("rear_base", "rear_leg"),
    "front_hinge": ("front_base", "front_leg"),
}
RESERVED_TOPOLOGY_NODE_IDS = PRIMARY_NODE_IDS | {
    "front_top",
    "platform_rear",
    "platform_front",
    "platform_heel",
}
MANAGED_HOOK_NODE_PREFIX = "__hook__"
MANAGED_HOOK_FALLBACK_DROP_M = 1.0


def _managed_hook_node_id(hoist_id: str) -> str:
    return f"{MANAGED_HOOK_NODE_PREFIX}{hoist_id}"


def _is_managed_hook_node_id(node_id: str) -> bool:
    return str(node_id).startswith(MANAGED_HOOK_NODE_PREFIX)


class Metadata(BaseModel):
    """Metadata fields for the crane model."""

    name: str = Field(default="New Crane Model", description="User-facing model name")


class VesselMotion(BaseModel):
    """Vessel motion limits under environment (vessel-frame, gravity excluded).

    Each value is a ± limit: the load chart ignores its sign and takes the worst case over
    both signs. The reference point fields are positions, not limits.
    """

    accel_x_m_s2: float = Field(default=0.0, description="Vessel-frame X acceleration")
    accel_y_m_s2: float = Field(default=0.0, description="Vessel-frame Y acceleration")
    accel_z_m_s2: float = Field(default=0.0, description="Vessel-frame Z acceleration")
    roll_deg: float = Field(default=0.0, description="Vessel roll angle (gravity tilt)")
    pitch_deg: float = Field(default=0.0, description="Vessel pitch angle (gravity tilt)")
    reference_x_m: float = Field(default=0.0, description="Pitch rotation reference X")
    reference_z_m: float = Field(default=0.0, description="Pitch rotation reference Z")
    pitch_angular_accel_rad_s2: float = Field(default=0.0, description="Pitch angular acceleration")
    roll_angular_accel_rad_s2: float = Field(default=0.0, description="Roll angular acceleration")


class Environment(BaseModel):
    """Environment definition."""

    gravity_m_s2: float = Field(default=-DEFAULT_GRAVITY_M_S2, description="Gravity acceleration")
    max_wind_speed_m_s: float = Field(default=20.0, description="Maximum wind speed")
    air_density_kg_m3: float = Field(default=DEFAULT_AIR_DENSITY_KG_M3, description="Air density")
    vessel_motion: VesselMotion = Field(default_factory=VesselMotion)

    @field_validator("gravity_m_s2")
    @classmethod
    def validate_gravity(cls, v: float) -> float:
        if v == 0.0:
            raise ValueError("gravity_m_s2 must be non-zero")
        return v

    @field_validator("max_wind_speed_m_s")
    @classmethod
    def validate_max_wind(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError("max_wind_speed_m_s must be > 0")
        return v

    @field_validator("air_density_kg_m3")
    @classmethod
    def validate_positive(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError("Value must be > 0")
        return v


class MassPoint(BaseModel):
    """Mass point definition for a body."""

    id: str = Field(description="Mass point identifier")
    mass_t: float = Field(description="Mass in tonnes")
    x_m: float = Field(description="Global X coordinate")
    y_m: float = Field(default=0.0, description="Global Y coordinate")
    z_m: float = Field(description="Global Z coordinate")
    local_x_m: Optional[float] = Field(default=None, description="Boom-local X if applicable")
    local_y_m: Optional[float] = Field(default=None, description="Boom-local Y (V) if applicable")
    local_z_m: Optional[float] = Field(default=None, description="Boom-local Z if applicable")
    below_node_id: Optional[str] = Field(default=None, description="Node this mass hangs from")


class WindArea(BaseModel):
    """Wind area definition for a body."""

    id: str = Field(description="Wind area identifier")
    area_w_m2: float = Field(description="Wind area in m² for X-directed wind")
    area_v_m2: float = Field(description="Wind area in m² for Y-directed wind")
    x_m: float = Field(description="Global X coordinate of centroid")
    z_m: float = Field(description="Global Z coordinate of centroid")
    local_x_m: Optional[float] = Field(default=None, description="Boom-local X if applicable")
    local_z_m: Optional[float] = Field(default=None, description="Boom-local Z if applicable")
    cd: float = Field(default=1.0, description="Drag coefficient")


class Body(BaseModel):
    """Structural body definition."""

    id: str = Field(description="Body identifier")
    mass_points: list[MassPoint] = Field(default_factory=list)
    wind_areas: list[WindArea] = Field(default_factory=list)


class Node(BaseModel):
    """Named reference point or hoist geometry point."""

    id: str = Field(description="Node identifier")
    body: str = Field(description="Body this node belongs to")
    x_m: float = Field(description="Global X coordinate")
    z_m: float = Field(description="Global Z coordinate")
    local_x_m: Optional[float] = Field(default=None, description="Boom-local X if applicable")
    local_z_m: Optional[float] = Field(default=None, description="Boom-local Z if applicable")
    below_node_id: Optional[str] = Field(default=None, description="Node this hangs below")
    hanging_drop_m: Optional[float] = Field(
        default=None, description="Vertical hanging drop from reference node"
    )


class Segment(BaseModel):
    """Rope segment definition."""

    from_node_id: str = Field(description="Segment start node")
    to_node_id: str = Field(description="Segment end node")
    mult: int = Field(default=1, description="Segment multiplicity (parts)")


class Rope(BaseModel):
    """Rope definition."""

    id: str = Field(description="Rope identifier")
    segments: list[Segment] = Field(description="Rope path segments")
    tension_mode: Optional[str] = Field(
        default=None, description="'solve' for boom-hoist solve mode"
    )
    linear_mass_kg_m: float = Field(default=0.0, ge=0.0, description="Rope linear mass in kg/m")


class ContractualPoint(BaseModel):
    """Contractual operating point."""

    load_t: float = Field(description="Payload in tonnes")
    outreach_m: float = Field(description="Outreach in meters")
    label: Optional[str] = Field(default=None, description="Optional label")


class Hoist(BaseModel):
    """Hoist definition."""

    id: str = Field(description="Hoist identifier")
    rope_id: str = Field(description="Rope this hoist operates")
    load_node_id: str = Field(description="Node where load attaches")
    support_node_id: Optional[str] = Field(
        default=None, description="Support node used to synthesize managed hook node"
    )
    falls: Optional[int] = Field(
        default=None, description="Hook falls count for managed hook synthesis"
    )
    hook_mass_t: float = Field(default=0.0, description="Hook block mass in tonnes")
    hook_daf: float = Field(default=1.0, description="Dynamic amplification factor")
    outreach_min_m: Optional[float] = Field(default=None, description="Minimum outreach")
    outreach_max_m: Optional[float] = Field(default=None, description="Maximum outreach")
    offlead_deg: float = Field(default=0.0, description="Offlead angle limit")
    sidelead_deg: float = Field(default=0.0, description="Sidelead angle limit")
    splitable_block: bool = Field(
        default=False, description="Whether the payload hook block can be split"
    )
    split_falls: Optional[int] = Field(
        default=None, description="Hook falls count when block is split"
    )
    split_hook_mass_t: Optional[float] = Field(
        default=None, description="Hook block mass in tonnes when split"
    )
    split_contractual_points: list[ContractualPoint] = Field(default_factory=list)
    max_hook_travel_m: Optional[float] = Field(
        default=None,
        description="Maximum hook travel. Derived for payload hoists from "
        "lowest_hook_height_m; the minimum is always 0.0",
    )
    lowest_hook_height_m: Optional[float] = Field(
        default=None,
        description="Absolute global Z the hook must reach at this hoist's minimum outreach. "
        "max_hook_travel_m and rope_length_m derive from it. Payload hoists carry crane-frame "
        "z = 0 when unauthored",
    )
    contractual_points: list[ContractualPoint] = Field(default_factory=list)
    linear_mass_kg_m: float = Field(default=0.0, ge=0.0, description="Rope linear mass in kg/m")
    rope_length_m: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Total rope length in metres. Authored for the boom hoist; for payload hoists "
        "derived as the reeved length at min outreach with the hook at the lowest hook height",
    )

    @field_validator("hook_daf")
    @classmethod
    def validate_daf(cls, v: float) -> float:
        if v < 1.0:
            raise ValueError("hook_daf must be >= 1.0")
        return v

    @field_validator("falls")
    @classmethod
    def validate_falls(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and int(v) < 1:
            raise ValueError("falls must be >= 1")
        return v

    @field_validator("split_falls")
    @classmethod
    def validate_split_falls(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and int(v) < 1:
            raise ValueError("split_falls must be >= 1")
        return v

    @model_validator(mode="after")
    def apply_contractual_defaults(self) -> "Hoist":
        """Apply defaults from contractual points if bounds are missing."""
        if self.contractual_points:
            outreaches = [p.outreach_m for p in self.contractual_points]
            if self.outreach_min_m is None and outreaches:
                self.outreach_min_m = min(outreaches)
            if self.outreach_max_m is None and outreaches:
                self.outreach_max_m = max(outreaches)

        # Fallback defaults if still None
        if self.outreach_min_m is None:
            self.outreach_min_m = 0.0
        if self.outreach_max_m is None:
            self.outreach_max_m = 200.0

        if self.outreach_min_m > self.outreach_max_m:
            raise ValueError("outreach_min_m must be <= outreach_max_m")

        if self.split_hook_mass_t is not None and float(self.split_hook_mass_t) < 0.0:
            raise ValueError("split_hook_mass_t must be >= 0")

        if self.splitable_block:
            if self.falls is None:
                raise ValueError("splitable_block requires falls")
            if self.split_falls is None:
                raise ValueError("splitable_block requires split_falls")
            if self.split_hook_mass_t is None:
                raise ValueError("splitable_block requires split_hook_mass_t")
            if int(self.split_falls) > int(self.falls):
                raise ValueError("split_falls must be <= falls")
            if float(self.split_hook_mass_t) > float(self.hook_mass_t):
                raise ValueError("split_hook_mass_t must be <= hook_mass_t")
            if not self.split_contractual_points:
                raise ValueError("splitable_block requires split_contractual_points")

        return self


class SupportWidths(BaseModel):
    """Support widths used for left/right reaction splitting."""

    boom_width_m: float = Field(default=1.0, description="Boom support width")
    slewing_bearing_diameter_m: Optional[float] = Field(
        default=None, description="Slewing bearing diameter; omit to skip bearing line load checks"
    )

    @field_validator("boom_width_m", "slewing_bearing_diameter_m")
    @classmethod
    def validate_positive_width(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0.0:
            raise ValueError("Support width must be > 0")
        return v


class SavedLimit(BaseModel):
    """An authored design-limit value: the capacity in kN and whether the limit is checked."""

    capacity_kN: float = Field(ge=0.0)
    enabled: bool = True


class CraneDocument(BaseModel):
    """Root crane model document."""

    schema_version: str = Field(default="1.0.0")
    model_type: str = Field(default="fixed_topology_crane_2d")
    metadata: Metadata = Field(default_factory=Metadata)
    environment: Environment = Field(default_factory=Environment)
    bodies: list[Body] = Field(default_factory=list)
    nodes: list[Node] = Field(default_factory=list)
    ropes: list[Rope] = Field(default_factory=list)
    hoists: list[Hoist] = Field(default_factory=list)
    support_widths: SupportWidths = Field(default_factory=SupportWidths)
    saved_limits: dict[str, SavedLimit] = Field(
        default_factory=dict,
        description="Design limits as authored: those differing from the default catalog. "
        "Read once when a session starts; the session's own limits are what is analysed",
    )
    connections: Optional[list[dict[str, Any]]] = Field(
        default=None, description="Runtime-generated only"
    )

    model_config = ConfigDict(
        validate_assignment=True,
        json_encoders={
            float: lambda v: round(v, 10) if v is not None else None,
        },
    )


def is_solve_hoist(doc: CraneDocument, hoist_id: str) -> bool:
    """Return whether a hoist is the solve-mode (boom) hoist."""
    hoist = next((h for h in doc.hoists if h.id == hoist_id), None)
    if hoist is None:
        return False
    rope = next((r for r in doc.ropes if r.id == hoist.rope_id), None)
    return bool(rope and rope.tension_mode == "solve")


def payload_hoist_ids(doc: CraneDocument) -> list[str]:
    """Return hoist ids that represent payload hoists (non-solve ropes)."""
    ids: list[str] = []
    for hoist in doc.hoists:
        rope = next((r for r in doc.ropes if r.id == hoist.rope_id), None)
        if rope is None or rope.tension_mode != "solve":
            ids.append(hoist.id)
    return ids


# ============================================================================
# Normalization and Round-Trip Functions
# ============================================================================
