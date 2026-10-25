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

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

AUTHORED_SCHEMA_NAME = "crane-statics"
AUTHORED_SCHEMA_MAJOR_VERSION = 11
AUTHORED_SCHEMA_VERSION = "11.0.0"
"""Current minor.patch written on save; informational provenance only — the
major-only pattern below is what's actually enforced on load."""

IdName = Annotated[str, Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")]

DEFAULT_GRAVITY_M_S2 = 9.81
DEFAULT_AIR_DENSITY_KG_M3 = 1.225

BOOM_HOIST_ID = "BH"
"""Runtime hoist ID of the boom hoist; its local node IDs are prefixed ``bh_``."""


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
    """Optional vessel motion limits: surge, sway, heave (accelerations, gravity excluded),
    roll and pitch (angular accelerations), roll angle and pitch angle. Each motion value is
    a ± limit (its sign is ignored); the load chart takes the worst case over ±. The crane
    is fully revolving, so there is no slewing angle in the Model. Omitted values are zero."""

    model_config = ConfigDict(extra="forbid")

    accel_x_m_s2: float = 0.0
    accel_y_m_s2: float = 0.0
    accel_z_m_s2: float = 0.0
    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    pitch_angular_accel_rad_s2: float = 0.0
    roll_angular_accel_rad_s2: float = 0.0
    reference_x_m: float = 0.0
    reference_z_m: float = 0.0


class AuthoredEnvironment(BaseModel):
    """Environmental constants. Gravity and air density have defaults; the maximum
    wind speed (constant over height) is required."""

    model_config = ConfigDict(extra="forbid")

    gravity_m_s2: float = Field(
        default=DEFAULT_GRAVITY_M_S2,
        gt=0,
        description="Gravity magnitude in m/s²; the runtime uses it as negative Z gravity.",
    )
    max_wind_speed_m_s: float = Field(gt=0, description="Positive maximum wind speed in m/s.")
    air_density_kg_m3: float = Field(default=DEFAULT_AIR_DENSITY_KG_M3, gt=0)


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


def hoist_node_prefix(hoist_id: str) -> str:
    """Prefix that turns a hoist-local node name into its global runtime node ID."""
    return f"{hoist_id.lower()}_"


class AuthoredReevingEntry(BaseModel):
    """One stop on a hoist's rope path, listed in order from the winch outwards.

    An entry carrying ``body`` and coordinates defines a node owned by this hoist;
    its global ID is the lowercased hoist ID, an underscore, and ``node``. An entry
    without coordinates passes through a node by name: another node of this hoist
    if one is so named, otherwise a global node (a primary node such as
    ``boom_heel`` or a shared node listed under a body's ``nodes``)."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {"node": "winch", "body": "platform", "x_m": 1.81, "z_m": 3.99},
                {
                    "node": "boom_sheave_4",
                    "body": "boom",
                    "u_m": 109.0,
                    "w_m": -4.25,
                    "parts": 2,
                },
            ]
        },
    )

    node: IdName = Field(description="Node name, local to this hoist unless it reuses a node.")
    body: Optional[Literal["boom", "rear_leg", "front_leg", "platform"]] = Field(
        default=None,
        description="Body the node moves with. Boom nodes use u_m/w_m; the others use x_m/z_m. "
        "Omit (with all coordinates) to pass through an existing node.",
    )
    u_m: Optional[float] = Field(default=None, description="Boom-local longitudinal coordinate.")
    w_m: Optional[float] = Field(default=None, description="Boom-local vertical coordinate.")
    x_m: Optional[float] = Field(default=None, description="Global horizontal coordinate.")
    z_m: Optional[float] = Field(default=None, description="Global vertical coordinate.")
    parts: Optional[int] = Field(
        default=None,
        ge=1,
        description="Rope parts in the span arriving at this node (default 1). Not allowed on "
        "the first entry.",
    )
    from_: Optional[IdName] = Field(
        default=None,
        alias="from",
        description="Node the span arriving here starts from, when it is not the previous "
        "entry. Not allowed on the first entry.",
    )

    @model_validator(mode="after")
    def _check_body_coordinates(self) -> "AuthoredReevingEntry":
        coords = {k for k in ("u_m", "w_m", "x_m", "z_m") if getattr(self, k) is not None}
        if self.body is None:
            if coords:
                raise ValueError(f"node {self.node!r} has coordinates but no body")
        elif self.body == "boom":
            if coords != {"u_m", "w_m"}:
                raise ValueError(f"boom node {self.node!r} must use exactly u_m and w_m")
        elif coords != {"x_m", "z_m"}:
            raise ValueError(f"{self.body} node {self.node!r} must use exactly x_m and z_m")
        return self


def _check_reeving(reeving: list[AuthoredReevingEntry]) -> None:
    first = reeving[0]
    if first.parts is not None or first.from_ is not None:
        raise ValueError("the first reeving entry cannot have parts or from")
    defined: set[str] = set()
    for entry in reeving:
        if entry.body is not None:
            if entry.node in defined:
                raise ValueError(
                    f"reeving node {entry.node!r} is defined twice; omit body and coordinates "
                    "to pass through it again"
                )
            defined.add(entry.node)


class AuthoredLoadChartPoint(BaseModel):
    """A rated operating point on the hoist capacity curve."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"outreach_m": 50.0, "load_t": 1433.0}]},
    )

    outreach_m: float = Field(ge=0, description="Horizontal outreach in metres.")
    load_t: float = Field(ge=0, description="Permitted payload in tonnes.")


class AuthoredBoomHoistRope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    linear_mass_kg_m: float = Field(default=0.0, ge=0)
    length_m: Optional[float] = Field(
        default=None,
        ge=0,
        description="Total rope length in metres. Omit to leave the length on the drum "
        "unknown, in which case no spooled rope mass is reported for this hoist.",
    )


class AuthoredBoomHoist(BaseModel):
    """The rope system that luffs the boom. Its hoist-local node IDs are prefixed ``bh_``."""

    model_config = ConfigDict(extra="forbid")

    rope: AuthoredBoomHoistRope = Field(default_factory=AuthoredBoomHoistRope)
    reeving: list[AuthoredReevingEntry] = Field(min_length=2)

    @model_validator(mode="after")
    def _check_reeving(self) -> "AuthoredBoomHoist":
        _check_reeving(self.reeving)
        return self


class AuthoredPayloadHoistRope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    linear_mass_kg_m: float = Field(default=0.0, ge=0)


class AuthoredSplitMode(BaseModel):
    """Optional split-block operating mode with its own hook mass, falls and load chart."""

    model_config = ConfigDict(extra="forbid")

    hook_mass_t: float = Field(ge=0, description="Hook block mass in split mode.")
    falls: int = Field(ge=1, description="Rope falls between the support sheave and the hook.")
    load_chart: list[AuthoredLoadChartPoint] = Field(min_length=1)


class AuthoredPayloadHoist(BaseModel):
    """Self-contained payload hoist: its rope, its reeving path with the sheaves it
    owns, its hook mass, falls, lift factors and its load chart. The hook hangs from the
    last reeving node unless support_node names another; the application creates the
    managed hook node automatically."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "rope": {"linear_mass_kg_m": 9.17},
                    "reeving": [
                        {"node": "winch", "body": "platform", "x_m": 1.81, "z_m": 3.99},
                        {
                            "node": "boom_sheave_4",
                            "body": "boom",
                            "u_m": 109.0,
                            "w_m": -4.25,
                            "parts": 2,
                        },
                    ],
                    "hook_mass_t": 50.0,
                    "falls": 20,
                    "daf": 1.1,
                    "offlead_deg": 1.0,
                    "load_chart": [{"outreach_m": 16.0, "load_t": 1000.0}],
                }
            ]
        },
    )

    rope: AuthoredPayloadHoistRope = Field(default_factory=AuthoredPayloadHoistRope)
    reeving: list[AuthoredReevingEntry] = Field(min_length=2)
    support_node: Optional[IdName] = Field(
        default=None,
        description="Reeving node the hook hangs from. Omit to use the last reeving entry.",
    )
    hook_mass_t: float = Field(ge=0, description="Hook block mass.")
    falls: int = Field(ge=1, description="Rope falls between the support sheave and the hook.")
    daf: float = Field(ge=1, description="Hook dynamic amplification factor.")
    offlead_deg: float = Field(ge=0)
    sidelead_deg: float = Field(default=0.0, ge=0)
    lowest_hook_height_m: Optional[float] = Field(
        default=None,
        description="Absolute global Z the hook must reach at this hoist's minimum outreach. "
        "The hoist's maximum hook travel and total rope length are derived from it. Omit to "
        "default to crane-frame z = 0.",
    )
    load_chart: list[AuthoredLoadChartPoint] = Field(min_length=1)
    split: Optional[AuthoredSplitMode] = None

    @model_validator(mode="after")
    def _check_reeving(self) -> "AuthoredPayloadHoist":
        _check_reeving(self.reeving)
        return self

    @model_validator(mode="after")
    def _check_split_within_normal_bounds(self) -> "AuthoredPayloadHoist":
        if self.split is not None:
            if self.split.falls > self.falls:
                raise ValueError("split.falls must be <= falls")
            if self.split.hook_mass_t > self.hook_mass_t:
                raise ValueError("split.hook_mass_t must be <= hook_mass_t")
        return self


class AuthoredStructure(BaseModel):
    """Primary structure geometry: the boom heel, the hinges and support widths."""

    model_config = ConfigDict(extra="forbid")

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


class AuthoredLimit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capacity_kN: float = Field(
        ge=0,
        description="The limit's capacity in kN (kN/m for bearing line loads, kNm for moments), "
        "as a positive magnitude.",
    )
    enabled: bool = Field(default=True, description="Whether the limit is checked.")


class AuthoredModelDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: AuthoredEnvironment
    vessel_motion: AuthoredVesselMotion = Field(default_factory=AuthoredVesselMotion)
    structure: AuthoredStructure
    boom: AuthoredBoomBody = Field(
        default_factory=AuthoredBoomBody,
        description="The boom body: its structural mass, wind areas, and shared boom-local "
        "nodes. Hoist sheaves belong in each hoist's reeving.",
    )
    rear_leg: AuthoredGlobalBody = Field(
        default_factory=AuthoredGlobalBody,
        description="The rear leg body supporting the upper structure, in global coordinates.",
    )
    front_leg: AuthoredGlobalBody = Field(
        default_factory=AuthoredGlobalBody,
        description="The front leg body supporting the upper structure, in global coordinates.",
    )
    platform: AuthoredGlobalBody = Field(
        default_factory=AuthoredGlobalBody,
        description="The fixed platform/base body, in global coordinates.",
    )
    hoists: dict[IdName, Union[AuthoredBoomHoist, AuthoredPayloadHoist]] = Field(
        min_length=2,
        description=f"Named hoists. The required '{BOOM_HOIST_ID}' entry is the rope system that "
        "raises and lowers the boom; every other entry is a payload hoist. Each is "
        "self-contained: deleting its block removes the hoist together with the sheaves it owns.",
    )
    limits: dict[IdName, AuthoredLimit] = Field(
        default_factory=dict,
        description="Design limits whose value or enabled state differs from the default the "
        "app derives from the hoists' contractual points. Keyed by limit id: a rope limit is "
        "'<rope id>_T' (for example 'MH__rope_T'), a connection limit '<connection>_<component>' "
        "(for example 'rear_hinge_Fx'). Limits not listed keep their default.",
    )

    @field_validator("hoists", mode="before")
    @classmethod
    def _parse_hoists_by_kind(cls, value: Any) -> Any:
        """Validate each entry against its own model so errors name the real problem: the
        ``BH`` entry is the boom hoist, every other entry a payload hoist."""
        if not isinstance(value, dict):
            return value
        if BOOM_HOIST_ID not in value:
            raise ValueError(f"hoists must include the boom hoist '{BOOM_HOIST_ID}'")
        parsed: dict[Any, Any] = {}
        for hoist_id, hoist in value.items():
            if isinstance(hoist, dict):
                try:
                    if hoist_id == BOOM_HOIST_ID:
                        hoist = AuthoredBoomHoist.model_validate(hoist)
                    else:
                        hoist = AuthoredPayloadHoist.model_validate(hoist)
                except ValidationError as error:
                    raise ValueError(f"{hoist_id}: {format_authored_validation_error(error)}")
            parsed[hoist_id] = hoist
        return parsed

    @model_validator(mode="after")
    def _check_hoist_prefixes_unique(self) -> "AuthoredModelDefinition":
        seen: dict[str, str] = {}
        for hoist_id in self.hoists:
            prefix = hoist_node_prefix(hoist_id)
            if prefix in seen:
                raise ValueError(
                    f"hoist {hoist_id!r} clashes with {seen[prefix]!r}: hoist IDs must "
                    "differ ignoring case"
                )
            seen[prefix] = hoist_id
        return self


EXAMPLE_DOCUMENT: dict = {
    "schema": {"name": "crane-statics", "version": AUTHORED_SCHEMA_VERSION},
    "metadata": {"name": "New Crane Model"},
    "model_definition": {
        "environment": {
            "gravity_m_s2": DEFAULT_GRAVITY_M_S2,
            "air_density_kg_m3": DEFAULT_AIR_DENSITY_KG_M3,
            "max_wind_speed_m_s": 20.0,
        },
        "structure": {
            "boom_width_m": 1.0,
            "slewing_bearing_diameter_m": 1.0,
            "boom_heel": {"x_m": 0.0, "z_m": 0.0},
            "upper_hinge": {"x_m": 0.0, "z_m": 0.0},
            "rear_hinge": {"x_m": 0.0, "z_m": 0.0},
            "front_hinge": {"x_m": 0.0, "z_m": 0.0},
        },
        "hoists": {
            "BH": {
                "reeving": [{"node": "boom_heel"}, {"node": "rear_top", "parts": 2}],
            },
            "MH": {
                "reeving": [
                    {"node": "boom_heel"},
                    {"node": "hook", "body": "boom", "u_m": 0.0, "w_m": 0.0},
                ],
                "hook_mass_t": 0.0,
                "falls": 1,
                "daf": 1.0,
                "offlead_deg": 0.0,
                "load_chart": [{"outreach_m": 0.0, "load_t": 0.0}],
            },
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
