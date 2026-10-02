"""Pydantic models for the authored (user-written) crane document shape.

This is the single source of truth for the authored-document contract. The
JSON Schema published at src/crane_statics/schemas/ is generated from these
models by generate_schema.py, not hand-authored — regenerate it after any
change here.

Schema versioning policy: AUTHORED_SCHEMA_MAJOR_VERSION identifies the
published file (schemas/crane-statics-v<major>.schema.json) and gates
acceptance; any "<major>.x.y" document validates against it.
  - Non-breaking (new optional field, widened bound, new allowed value):
    bump AUTHORED_SCHEMA_VERSION's minor/patch and regenerate the same file.
  - Breaking (removed/renamed/required-ified field, narrowed bound, stricter
    extra): bump AUTHORED_SCHEMA_MAJOR_VERSION and ship a new file.
Enforcing that distinction automatically (diffing generated schemas across
versions) is not built; treat it as a review discipline for now.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

AUTHORED_SCHEMA_NAME = "crane-statics"
AUTHORED_SCHEMA_MAJOR_VERSION = 5
AUTHORED_SCHEMA_VERSION = "5.13.0"
"""Current minor.patch written on save; informational provenance only — the
major-only pattern below is what's actually enforced on load."""

IdName = Annotated[str, Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")]


def authored_schema_major(version: Any) -> Optional[int]:
    """Parse the leading major-version digits from an authored schema.version string."""
    head = str(version).split(".", 1)[0]
    return int(head) if head.isdigit() else None


def format_authored_validation_error(error: ValidationError) -> str:
    """Render a pydantic ValidationError as a single-line, field-located message."""
    first = error.errors()[0]
    location = "/".join(str(p) for p in first["loc"])
    location_msg = f" at {location}" if location else ""
    return f"Schema validation failed{location_msg}: {first['msg']}"


class AuthoredSchemaBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["crane-statics"]
    version: str = Field(pattern=rf"^{AUTHORED_SCHEMA_MAJOR_VERSION}\.\d+\.\d+$")


class AuthoredMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: Optional[str] = None


class AuthoredVesselMotion(BaseModel):
    """Optional vessel accelerations and rotation reference. Omitted values default to zero."""

    model_config = ConfigDict(extra="forbid")

    accel_x_m_s2: float = Field(default=0.0, ge=0)
    accel_y_m_s2: float = Field(default=0.0, ge=0)
    accel_z_m_s2: float = Field(default=0.0, ge=0)
    pitch_angular_accel_rad_s2: float = Field(default=0.0, ge=0)
    roll_angular_accel_rad_s2: float = Field(default=0.0, ge=0)
    reference_x_m: float = 0.0
    reference_z_m: float = 0.0


class AuthoredEnvironment(BaseModel):
    """Environmental constants. Gravity and air density have defaults; wind
    profile and sea-level reference values are required."""

    model_config = ConfigDict(extra="forbid")

    gravity_m_s2: float = Field(
        default=9.81,
        gt=0,
        description="Gravity magnitude in m/s²; the runtime uses it as negative Z gravity.",
    )
    max_wind_speed_m_s: float = Field(gt=0, description="Positive maximum wind speed in m/s.")
    air_density_kg_m3: float = Field(default=1.225, gt=0)
    wind_profile_exponent: float = Field(gt=0, description="Power-law wind profile exponent.")
    wind_reference_height_m_asl: float = Field(
        gt=0, description="Reference height above mean sea level in metres."
    )
    mean_sealevel_z_m: float = Field(description="Mean sea-level elevation in global Z metres.")


class AuthoredGlobalPosition2D(BaseModel):
    """Global X/Z position in metres."""

    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"x_m": 0.0, "z_m": 7.7}]}
    )

    x_m: float = Field(description="Global horizontal coordinate in metres.")
    z_m: float = Field(description="Global vertical coordinate in metres.")


class AuthoredGlobalPosition3D(BaseModel):
    """Global X/Y/Z position in metres."""

    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"x_m": 0.0, "y_m": 0.0, "z_m": 4.0}]}
    )

    x_m: float = Field(description="Global horizontal coordinate in metres.")
    y_m: float = Field(description="Global transverse coordinate in metres.")
    z_m: float = Field(description="Global vertical coordinate in metres.")


class AuthoredBoomPosition3D(BaseModel):
    """Boom-local U/V/W position in metres."""

    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"u_m": 87.0, "v_m": 0.0, "w_m": -0.4}]}
    )

    u_m: float = Field(description="Boom-local longitudinal coordinate in metres.")
    v_m: float = Field(description="Boom-local transverse coordinate in metres.")
    w_m: float = Field(description="Boom-local vertical coordinate in metres.")


class AuthoredBoomPosition2D(BaseModel):
    """Boom-local U/W position in metres."""

    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"u_m": 155.0, "w_m": -6.05}]}
    )

    u_m: float = Field(description="Boom-local longitudinal coordinate in metres.")
    w_m: float = Field(description="Boom-local vertical coordinate in metres.")


class AuthoredMassPointBoom(BaseModel):
    """Boom structural mass located in boom-local U/V/W coordinates."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "id": "boom_structure",
                    "mass_t": 759.1,
                    "position": {"u_m": 87.0, "v_m": 0.0, "w_m": -0.4},
                }
            ]
        },
    )

    id: IdName
    mass_t: float = Field(gt=0)
    position: AuthoredBoomPosition3D


class AuthoredMassPointGlobal(BaseModel):
    """Fixed-body mass located in global X/Y/Z coordinates."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "id": "platform_structure",
                    "mass_t": 615.0,
                    "position": {"x_m": -0.49, "y_m": 0.23, "z_m": 4.24},
                }
            ]
        },
    )

    id: IdName
    mass_t: float = Field(gt=0)
    position: AuthoredGlobalPosition3D


class AuthoredWindAreaBoom(BaseModel):
    """Boom wind area using boom-local U/W centroid coordinates."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "id": "boom_lattice",
                    "area_w_m2": 540.3,
                    "area_v_m2": 485.7,
                    "cd": 1.25,
                    "position": {"u_m": 82.4, "w_m": 0.0},
                }
            ]
        },
    )

    id: IdName
    area_w_m2: float = Field(ge=0)
    area_v_m2: float = Field(ge=0)
    cd: float = Field(default=1.0, gt=0)
    position: AuthoredBoomPosition2D


class AuthoredWindAreaGlobal(BaseModel):
    """Fixed-body wind area using global X/Z centroid coordinates."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "id": "platform_wind_x",
                    "area_x_m2": 156.5,
                    "area_y_m2": 0.0,
                    "cd": 1.0,
                    "position": {"x_m": 0.0, "z_m": 3.4},
                }
            ]
        },
    )

    id: IdName
    area_x_m2: float = Field(ge=0)
    area_y_m2: float = Field(ge=0)
    cd: float = Field(default=1.0, gt=0)
    position: AuthoredGlobalPosition2D


class AuthoredBoomBody(BaseModel):
    """Optional boom mass, wind, and named boom-local nodes. Rope-referenced
    node IDs must be present."""

    model_config = ConfigDict(extra="forbid")

    mass_points: list[AuthoredMassPointBoom] = Field(default_factory=list)
    wind_areas: list[AuthoredWindAreaBoom] = Field(default_factory=list)
    nodes: dict[IdName, AuthoredBoomPosition2D] = Field(default_factory=dict)


class AuthoredGlobalBody(BaseModel):
    """Optional fixed-body mass, wind, and named global nodes. Rope-referenced
    node IDs must be present."""

    model_config = ConfigDict(extra="forbid")

    mass_points: list[AuthoredMassPointGlobal] = Field(default_factory=list)
    wind_areas: list[AuthoredWindAreaGlobal] = Field(default_factory=list)
    nodes: dict[IdName, AuthoredGlobalPosition2D] = Field(default_factory=dict)


class AuthoredRopeSegment(BaseModel):
    """One connected rope path segment. Node IDs must refer to nodes in the model."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"from": "winch", "to": "sheave", "parts": 2}]},
    )

    from_: IdName = Field(alias="from", description="Starting node ID.")
    to: IdName = Field(description="Ending node ID.")
    parts: int = Field(default=1, ge=1)


class AuthoredContractualPoint(BaseModel):
    """A rated operating point on the hoist capacity curve."""

    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"outreach_m": 50.0, "load_t": 1433.0}]}
    )

    outreach_m: float = Field(ge=0, description="Horizontal outreach in metres.")
    load_t: float = Field(ge=0, description="Permitted payload in tonnes.")


class AuthoredBoomHoist(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rope_segments: list[AuthoredRopeSegment] = Field(min_length=1)
    linear_mass_kg_m: float = Field(default=0.0, ge=0)
    rope_length_m: Optional[float] = Field(
        default=None,
        ge=0,
        description="Total rope length in metres. Omit to leave the length on the drum "
        "unknown, in which case no spooled rope mass is reported for this hoist.",
    )


class AuthoredPayloadHoistMode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    falls: int = Field(ge=1)
    hook_mass_t: float = Field(ge=0)
    contractual_points: list[AuthoredContractualPoint] = Field(min_length=1)


class AuthoredPayloadHoist(BaseModel):
    """Payload hoist attached to a named support node. The application creates
    the managed hook node automatically."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "support_node_id": "mh_boom_sheave_4",
                    "hook_daf": 1.1,
                    "offlead_deg": 1.0,
                    "falls": 20,
                    "hook_mass_t": 102.0,
                    "contractual_points": [{"outreach_m": 50.0, "load_t": 1433.0}],
                    "rope_segments": [{"from": "winch", "to": "sheave", "parts": 2}],
                }
            ]
        },
    )

    rope_segments: list[AuthoredRopeSegment] = Field(min_length=1)
    linear_mass_kg_m: float = Field(default=0.0, ge=0)
    support_node_id: IdName
    hook_daf: float = Field(ge=1)
    offlead_deg: float = Field(ge=0)
    sidelead_deg: float = Field(default=0.0, ge=0)
    drum_dead_turns: int = Field(
        default=0,
        ge=0,
        description="Turns of rope that must remain on the drum when the hook is at its "
        "lowest point. Requires drum_diameter_m.",
    )
    drum_diameter_m: Optional[float] = Field(
        default=None,
        gt=0,
        description="Mean wrap diameter of the dead turns in metres. Dead rope length is "
        "drum_dead_turns * pi * drum_diameter_m and is added to the derived total rope length.",
    )
    falls: int = Field(ge=1)
    hook_mass_t: float = Field(ge=0)
    contractual_points: list[AuthoredContractualPoint] = Field(min_length=1)
    split: Optional[AuthoredPayloadHoistMode] = None

    @model_validator(mode="after")
    def _check_dead_turns_require_diameter(self) -> "AuthoredPayloadHoist":
        if "drum_dead_turns" in self.model_fields_set and "drum_diameter_m" not in (
            self.model_fields_set
        ):
            raise ValueError("drum_dead_turns requires drum_diameter_m")
        return self

    @model_validator(mode="after")
    def _check_split_within_normal_bounds(self) -> "AuthoredPayloadHoist":
        if self.split is not None:
            if self.split.falls > self.falls:
                raise ValueError("split.falls must be <= falls")
            if self.split.hook_mass_t > self.hook_mass_t:
                raise ValueError("split.hook_mass_t must be <= hook_mass_t")
        return self


class AuthoredModelDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: AuthoredEnvironment
    vessel_motion: AuthoredVesselMotion = Field(default_factory=AuthoredVesselMotion)
    hook_height_at_min_outreach_m: Optional[float] = Field(
        default=None,
        description="Absolute global Z the hook must reach at each payload hoist's minimum "
        "outreach. Every payload hoist's maximum hook travel and total rope length are "
        "derived from it. Omit to default to environment.mean_sealevel_z_m.",
    )
    boom_width_m: float = Field(
        gt=0,
        description="Boom structural width in metres, used for platform-base bearing "
        "line load checks.",
    )
    slewing_bearing_diameter_m: Optional[float] = Field(
        default=None,
        gt=0,
        description="Slewing bearing diameter. Omit to skip platform-base bearing line "
        "load checks.",
    )
    boom_heel: AuthoredGlobalPosition2D = Field(
        description="Global position of the boom's heel (foot) pivot."
    )
    upper_hinge: AuthoredGlobalPosition2D = Field(
        description="Global position of the upper structure hinge the boom is suspended from."
    )
    rear_hinge: AuthoredGlobalPosition2D = Field(
        description="Global position of the rear leg's upper hinge."
    )
    front_hinge: AuthoredGlobalPosition2D = Field(
        description="Global position of the front leg's upper hinge."
    )
    boom: AuthoredBoomBody = Field(
        description="The boom body: its structural mass, wind areas, and boom-local nodes."
    )
    rear_leg: AuthoredGlobalBody = Field(
        description="The rear leg body supporting the upper structure, in global coordinates."
    )
    front_leg: AuthoredGlobalBody = Field(
        description="The front leg body supporting the upper structure, in global coordinates."
    )
    platform: AuthoredGlobalBody = Field(
        description="The fixed platform/base body, in global coordinates."
    )
    boom_hoist: AuthoredBoomHoist = Field(
        description="The rope system that raises and lowers the boom."
    )
    payload_hoists: dict[IdName, AuthoredPayloadHoist] = Field(
        min_length=1,
        description="Named payload hoists, each attached to a support node on the boom.",
    )


EXAMPLE_DOCUMENT: dict = {
    "schema": {"name": "crane-statics", "version": "5.13.0"},
    "metadata": {"name": "New Crane Model"},
    "model_definition": {
        "environment": {
            "gravity_m_s2": 9.81,
            "air_density_kg_m3": 1.225,
            "wind_profile_exponent": 0.143,
            "wind_reference_height_m_asl": 10.0,
            "mean_sealevel_z_m": -35.0,
            "max_wind_speed_m_s": 20.0,
        },
        "vessel_motion": {
            "accel_x_m_s2": 0.0,
            "accel_y_m_s2": 0.0,
            "accel_z_m_s2": 0.0,
            "pitch_angular_accel_rad_s2": 0.0,
            "roll_angular_accel_rad_s2": 0.0,
            "reference_x_m": 0.0,
            "reference_z_m": 0.0,
        },
        "boom_width_m": 1.0,
        "slewing_bearing_diameter_m": 1.0,
        "boom_heel": {"x_m": 0.0, "z_m": 0.0},
        "upper_hinge": {"x_m": 0.0, "z_m": 0.0},
        "rear_hinge": {"x_m": 0.0, "z_m": 0.0},
        "front_hinge": {"x_m": 0.0, "z_m": 0.0},
        "boom": {
            "mass_points": [],
            "wind_areas": [],
            "nodes": {"mh_hook": {"u_m": 0.0, "w_m": 0.0}},
        },
        "rear_leg": {"mass_points": [], "wind_areas": [], "nodes": {}},
        "front_leg": {"mass_points": [], "wind_areas": [], "nodes": {}},
        "platform": {"mass_points": [], "wind_areas": [], "nodes": {}},
        "payload_hoists": {
            "MH": {
                "rope_segments": [{"from": "boom_heel", "to": "mh_hook"}],
                "support_node_id": "mh_hook",
                "hook_daf": 1.0,
                "offlead_deg": 0.0,
                "sidelead_deg": 0.0,
                "falls": 1,
                "hook_mass_t": 0.0,
                "contractual_points": [{"outreach_m": 0.0, "load_t": 0.0}],
            }
        },
        "boom_hoist": {
            "rope_segments": [{"from": "boom_heel", "to": "rear_top", "parts": 2}],
        },
    },
}


class AuthoredDocument(BaseModel):
    """Minimal authored input for a fixed-topology 2D crane. Coordinates are
    named objects; lengths are metres, masses are tonnes, and angles are
    degrees unless noted."""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [EXAMPLE_DOCUMENT]})

    schema_: AuthoredSchemaBlock = Field(alias="schema")
    metadata: AuthoredMetadata
    model_definition: AuthoredModelDefinition
