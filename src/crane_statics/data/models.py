"""Data contract models for Crane Statics.

This module defines all the Pydantic models that enforce strict validation
and normalization according to the handoff data contract.
"""

from typing import Any, Optional
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from copy import deepcopy


CANONICAL_BODIES = ["boom", "rear_leg", "front_leg", "platform"]
AUTHORED_SCHEMA_NAME = "crane-statics"
AUTHORED_SCHEMA_VERSION = "5.12.0"
DEFAULT_GRAVITY_M_S2 = 9.81
DEFAULT_AIR_DENSITY_KG_M3 = 1.225
DEFAULT_VESSEL_MOTION = {
    "accel_x_m_s2": 0.0,
    "accel_y_m_s2": 0.0,
    "accel_z_m_s2": 0.0,
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


class ModelType(str, Enum):
    """Supported model types."""

    FIXED_TOPOLOGY_CRANE_2D = "fixed_topology_crane_2d"


class Metadata(BaseModel):
    """Metadata fields for the crane model."""

    name: str = Field(default="New Crane Model", description="User-facing model name")
    units: str = Field(default="m,kN", description="Units descriptor")
    chart_show_scrubber: bool = Field(
        default=True,
        description="Whether the load-chart scrubber is visible",
    )


class VesselMotion(BaseModel):
    """Vessel motion definition under environment."""

    accel_x_m_s2: float = Field(default=0.0, description="Translational X acceleration")
    accel_y_m_s2: float = Field(default=0.0, description="Translational Y acceleration")
    accel_z_m_s2: float = Field(default=0.0, description="Translational Z acceleration")
    reference_x_m: float = Field(default=0.0, description="Pitch rotation reference X")
    reference_z_m: float = Field(default=0.0, description="Pitch rotation reference Z")
    pitch_angular_accel_rad_s2: float = Field(default=0.0, description="Pitch angular acceleration")
    roll_angular_accel_rad_s2: float = Field(default=0.0, description="Roll angular acceleration")

    @field_validator(
        "accel_x_m_s2",
        "accel_y_m_s2",
        "accel_z_m_s2",
        "pitch_angular_accel_rad_s2",
        "roll_angular_accel_rad_s2",
    )
    @classmethod
    def validate_non_negative(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError("Value must be >= 0")
        return v


class Environment(BaseModel):
    """Environment definition."""

    gravity_m_s2: float = Field(default=-9.81, description="Gravity acceleration")
    max_wind_speed_m_s: float = Field(default=20.0, description="Maximum wind speed")
    wind_reference_height_m_asl: float = Field(
        default=10.0, description="Wind reference height ASL"
    )
    air_density_kg_m3: float = Field(default=1.225, description="Air density")
    wind_profile_exponent: float = Field(
        default=0.143, description="Wind profile power-law exponent"
    )
    mean_sealevel_z_m: float = Field(default=-35.0, description="Mean sea level Z coordinate")
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

    @field_validator("wind_reference_height_m_asl", "air_density_kg_m3", "wind_profile_exponent")
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
    static_hook_load_t: float = Field(default=0.0, description="Static hook load")
    boom_angle_step_deg: float = Field(default=0.5, description="Boom angle step for charts")
    outreach_min_m: Optional[float] = Field(default=None, description="Minimum outreach")
    outreach_max_m: Optional[float] = Field(default=None, description="Maximum outreach")
    offlead_deg: float = Field(default=0.0, description="Offlead angle limit")
    side_lead_deg: float = Field(default=0.0, description="Side lead angle limit")
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
    min_hook_travel_m: Optional[float] = Field(default=None, description="Minimum hook travel")
    max_hook_travel_m: Optional[float] = Field(default=None, description="Maximum hook travel")
    contractual_points: list[ContractualPoint] = Field(default_factory=list)
    linear_mass_kg_m: float = Field(default=0.0, ge=0.0, description="Rope linear mass in kg/m")
    rope_length_m: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Total rope length in metres; None means reeved length at max hook travel "
        "and 0 deg boom angle",
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
        if self.min_hook_travel_m is not None and self.max_hook_travel_m is not None:
            if self.min_hook_travel_m > self.max_hook_travel_m:
                raise ValueError("min_hook_travel_m must be <= max_hook_travel_m")

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
    slewing_bearing_diameter_m: float = Field(default=1.0, description="Slewing bearing diameter")

    @field_validator("boom_width_m", "slewing_bearing_diameter_m")
    @classmethod
    def validate_positive_width(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError("Support width must be > 0")
        return v


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


def _require_object_keys(
    obj: dict[str, Any], required: set[str], optional: set[str], ctx: str
) -> None:
    """Validate required and unknown keys for strict authored object shapes."""
    missing = [k for k in required if k not in obj]
    if missing:
        raise ValueError(f"{ctx} missing required keys: {sorted(missing)}")
    allowed = required | optional
    unknown = [k for k in obj.keys() if k not in allowed]
    if unknown:
        raise ValueError(f"{ctx} has unknown keys: {sorted(unknown)}")


def _is_authored_document(doc_data: dict[str, Any]) -> bool:
    schema = doc_data.get("schema")
    if not isinstance(schema, dict):
        return False
    return (
        schema.get("name") == AUTHORED_SCHEMA_NAME
        and schema.get("version") == AUTHORED_SCHEMA_VERSION
    )


def _convert_authored_segments(segments_src: Any, ctx: str) -> list[dict[str, Any]]:
    if not isinstance(segments_src, list):
        raise ValueError(f"{ctx} must be an array")
    segments: list[dict[str, Any]] = []
    for idx, seg in enumerate(segments_src):
        if not isinstance(seg, dict):
            raise ValueError(f"{ctx}[{idx}] must be an object")
        from_id = seg.get("from")
        to_id = seg.get("to")
        if from_id is None or to_id is None:
            raise ValueError(f"{ctx}[{idx}] must include from and to")
        parts = int(seg.get("parts", 1))
        if parts < 1:
            raise ValueError(f"{ctx}[{idx}].parts must be >= 1")
        segments.append(
            {
                "from": str(from_id),
                "to": str(to_id),
                **({"parts": parts} if parts != 1 else {}),
            }
        )
    return segments


def _infer_solve_load_node_id(segments: list[dict[str, Any]], ctx: str) -> str:
    """Infer runtime load-node placeholder for solve hoists from final segment endpoint."""
    if not segments:
        raise ValueError(f"{ctx}.rope_segments must contain at least one segment")
    last = segments[-1]
    return str(last["to"])


def _normalize_authored_document(doc_data: dict[str, Any]) -> dict[str, Any]:
    """Convert authored JSON into the normalized runtime document shape."""
    # Structural key presence/unknown-key checks are owned by the JSON schema.
    # Keep Python-side validation focused on semantic and cross-reference rules.
    schema = doc_data.get("schema")
    if not isinstance(schema, dict):
        raise ValueError("schema must be an object")
    if (
        schema.get("name") != AUTHORED_SCHEMA_NAME
        or schema.get("version") != AUTHORED_SCHEMA_VERSION
    ):
        raise ValueError("unsupported authored schema identifier")

    md = doc_data.get("model_definition")
    if not isinstance(md, dict):
        raise ValueError("model_definition must be an object")

    topology = md.get("topology")
    if topology is None:
        topology = "fixed_topology_crane_2d"
    if topology != "fixed_topology_crane_2d":
        raise ValueError("model_definition.topology must be fixed_topology_crane_2d")

    def _convert_load_container(section: Any, body_id: str, section_ctx: str) -> dict[str, Any]:
        if not isinstance(section, dict):
            raise ValueError(f"{section_ctx} must be an object")

        mass_points_out: list[dict[str, Any]] = []
        mass_points_src = section.get("mass_points", [])
        if not isinstance(mass_points_src, list):
            raise ValueError(f"{section_ctx}.mass_points must be an array")
        for idx, mp in enumerate(mass_points_src):
            if not isinstance(mp, dict):
                raise ValueError(f"{section_ctx}.mass_points[{idx}] must be an object")
            mass_points_out.append(
                {
                    "id": str(mp["id"]),
                    "mass_t": float(mp["mass_t"]),
                    "position": dict(mp["position"]),
                }
            )

        wind_areas_out: list[dict[str, Any]] = []
        wind_areas_src = section.get("wind_areas", [])
        if not isinstance(wind_areas_src, list):
            raise ValueError(f"{section_ctx}.wind_areas must be an array")
        for idx, wa in enumerate(wind_areas_src):
            if not isinstance(wa, dict):
                raise ValueError(f"{section_ctx}.wind_areas[{idx}] must be an object")
            if body_id == "boom":
                area_w = float(wa["area_w_m2"])
                area_v = float(wa["area_v_m2"])
            else:
                area_w = float(wa["area_x_m2"])
                area_v = float(wa["area_y_m2"])
            wind_areas_out.append(
                {
                    "id": str(wa["id"]),
                    "area_w_m2": area_w,
                    "area_v_m2": area_v,
                    "cd": float(wa["cd"]),
                    "position": dict(wa["position"]),
                }
            )

        nodes_src = section.get("nodes", {})
        if not isinstance(nodes_src, dict):
            raise ValueError(f"{section_ctx}.nodes must be an object")
        nodes_out: dict[str, Any] = {}
        for node_id, node_val in nodes_src.items():
            node_key = str(node_id)
            if not isinstance(node_val, dict):
                raise ValueError(f"{section_ctx}.nodes[{node_key}] must be an object")
            nodes_out[node_key] = dict(node_val)

        return {
            "mass_points": mass_points_out,
            "wind_areas": wind_areas_out,
            "nodes": nodes_out,
        }

    primary_out = {
        "boom_heel": dict(md["boom_heel"]),
        "upper_hinge": dict(md["upper_hinge"]),
        "rear_hinge": dict(md["rear_hinge"]),
        "front_hinge": dict(md["front_hinge"]),
    }

    components = {
        "boom": _convert_load_container(md.get("boom"), "boom", "model_definition.boom"),
        "rear_leg": _convert_load_container(
            md.get("rear_leg"), "rear_leg", "model_definition.rear_leg"
        ),
        "front_leg": _convert_load_container(
            md.get("front_leg"), "front_leg", "model_definition.front_leg"
        ),
        "platform": _convert_load_container(
            md.get("platform"), "platform", "model_definition.platform"
        ),
    }
    _validate_compact_component_positions(components, "model_definition")

    body_loads = _build_body_loads_from_components(
        components,
        require_nodes=True,
        path_prefix="model_definition",
    )
    nodes_src = _extract_component_nodes_from_components(
        components,
        path_prefix="model_definition",
        forbidden_node_ids=RESERVED_TOPOLOGY_NODE_IDS,
    )
    primary_nodes = _extract_primary_structure_nodes(primary_out)

    nodes_with_inferred_body: dict[str, Any] = {}
    for node_id, node in nodes_src.items():
        if not isinstance(node, dict):
            raise ValueError(f"model_definition.nodes[{node_id}] must be an object")
        node_copy = dict(node)
        if node_copy.get("body"):
            nodes_with_inferred_body[node_id] = node_copy
            continue
        if node_copy.get("u_m") is not None or node_copy.get("w_m") is not None:
            node_copy["body"] = "boom"
        else:
            raise ValueError(
                f"model_definition.nodes[{node_id}] is ambiguous: global x_m/z_m nodes must "
                "declare body explicitly (rear_leg|front_leg|platform), or use boom u_m/w_m"
            )
        nodes_with_inferred_body[node_id] = node_copy

    nodes_with_inferred_body.update(primary_nodes)
    nodes_with_primary = _synthesize_primary_nodes_into_nodes_map(nodes_with_inferred_body)

    payload_hoists_src = md.get("payload_hoists")
    if not isinstance(payload_hoists_src, dict):
        raise ValueError("model_definition.payload_hoists must be an object")
    if not payload_hoists_src:
        raise ValueError("model_definition.payload_hoists must contain at least one payload hoist")

    boom_hoist_src = md.get("boom_hoist")
    if not isinstance(boom_hoist_src, dict):
        raise ValueError("model_definition.boom_hoist must be an object")

    boom_id = "BH"

    boom_segments = _convert_authored_segments(
        boom_hoist_src.get("rope_segments"),
        "model_definition.boom_hoist.rope_segments",
    )

    metadata_src = doc_data.get("metadata")
    if not isinstance(metadata_src, dict):
        raise ValueError("metadata must be an object")

    ropes_norm: dict[str, Any] = {}
    hoists_norm: dict[str, Any] = {}

    for hoist_id, hoist in payload_hoists_src.items():
        hoist_key = str(hoist_id)
        if hoist_key == boom_id:
            raise ValueError("model_definition.payload_hoists cannot include the boom hoist id")
        if not isinstance(hoist, dict):
            raise ValueError(f"model_definition.payload_hoists[{hoist_key}] must be an object")

        support_node_id = str(hoist.get("support_node_id") or "").strip()
        if not support_node_id:
            raise ValueError(
                f"model_definition.payload_hoists[{hoist_key}].support_node_id must be "
                "a non-empty string"
            )
        if support_node_id not in nodes_with_primary:
            raise ValueError(
                f"model_definition.payload_hoists[{hoist_key}].support_node_id references "
                f"unknown node {support_node_id!r}"
            )
        normal_mode_obj = hoist
        split_mode_obj = hoist.get("split")
        if split_mode_obj is not None and not isinstance(split_mode_obj, dict):
            raise ValueError(
                f"model_definition.payload_hoists[{hoist_key}].split must be an object"
            )

        normal_falls_raw = normal_mode_obj.get("falls")
        normal_hook_mass_raw = normal_mode_obj.get("hook_mass_t")
        if normal_falls_raw is None or normal_hook_mass_raw is None:
            raise ValueError(
                f"model_definition.payload_hoists[{hoist_key}] is missing falls or hook_mass_t"
            )
        normal_falls = int(normal_falls_raw)
        if normal_falls < 1:
            raise ValueError(f"model_definition.payload_hoists[{hoist_key}].falls must be >= 1")
        split_falls = normal_falls
        if split_mode_obj is not None:
            split_falls_raw = split_mode_obj.get("falls")
            split_hook_mass_raw = split_mode_obj.get("hook_mass_t")
            if split_falls_raw is None or split_hook_mass_raw is None:
                raise ValueError(
                    f"model_definition.payload_hoists[{hoist_key}].split is missing falls "
                    "or hook_mass_t"
                )
            split_falls = int(split_falls_raw)
            if split_falls < 1:
                raise ValueError(
                    f"model_definition.payload_hoists[{hoist_key}].split.falls must be >= 1"
                )
            if split_falls > normal_falls:
                raise ValueError(
                    f"model_definition.payload_hoists[{hoist_key}].split.falls must be <= falls"
                )
            if float(split_hook_mass_raw) > float(normal_hook_mass_raw):
                raise ValueError(
                    f"model_definition.payload_hoists[{hoist_key}].split.hook_mass_t must be "
                    "<= hook_mass_t"
                )

        managed_hook_node_id = _managed_hook_node_id(hoist_key)
        if managed_hook_node_id in nodes_with_primary and not _is_managed_hook_node_id(
            managed_hook_node_id
        ):
            raise ValueError(
                f"model_definition.payload_hoists[{hoist_key}] conflicts with reserved "
                f"managed hook node id {managed_hook_node_id!r}"
            )

        support_node = nodes_with_primary[support_node_id]
        if not isinstance(support_node, dict):
            raise ValueError(
                f"model_definition.payload_hoists[{hoist_key}].support_node_id references "
                f"invalid node record {support_node_id!r}"
            )
        support_body = str(support_node.get("body") or "boom")
        nodes_with_primary[managed_hook_node_id] = {
            "body": support_body,
            "hang_from_node_id": support_node_id,
            "drop_m": MANAGED_HOOK_FALLBACK_DROP_M,
        }

        segs = _convert_authored_segments(
            hoist.get("rope_segments"),
            f"model_definition.payload_hoists[{hoist_key}].rope_segments",
        )
        if not any(support_node_id in (str(seg.get("from")), str(seg.get("to"))) for seg in segs):
            raise ValueError(
                f"model_definition.payload_hoists[{hoist_key}].rope_segments must include "
                f"support node {support_node_id!r}"
            )
        segs.append(
            {
                "from": support_node_id,
                "to": managed_hook_node_id,
                "parts": normal_falls,
            }
        )

        runtime_rope_id = _runtime_rope_id_for_hoist(hoist_key)
        ropes_norm[runtime_rope_id] = {
            "tension_mode": "fixed",
            "segments": segs,
            "linear_mass_kg_m": float(hoist.get("linear_mass_kg_m", 0.0)),
        }

        normal_curve_src = normal_mode_obj.get("contractual_points")
        if not isinstance(normal_curve_src, list):
            raise ValueError(
                f"model_definition.payload_hoists[{hoist_key}].contractual_points must be an array"
            )
        normal_curve = _normalize_contractual_curve_points(
            normal_curve_src,
            f"model_definition.payload_hoists[{hoist_key}].contractual_points",
        )

        split_curve: list[dict[str, Any]] = []
        if split_mode_obj is not None:
            split_curve_src = split_mode_obj.get("contractual_points")
            if not isinstance(split_curve_src, list):
                raise ValueError(
                    f"model_definition.payload_hoists[{hoist_key}].split.contractual_points "
                    "must be an array"
                )
            split_curve = _normalize_contractual_curve_points(
                split_curve_src,
                f"model_definition.payload_hoists[{hoist_key}].split.contractual_points",
            )

        normal_min_outreach, normal_max_outreach = _hoist_curve_outreach_bounds(normal_curve)
        split_min_outreach = normal_min_outreach
        split_max_outreach = normal_max_outreach
        if split_curve:
            split_min_outreach, split_max_outreach = _hoist_curve_outreach_bounds(split_curve)
        min_outreach = min(normal_min_outreach, split_min_outreach)
        max_outreach = max(normal_max_outreach, split_max_outreach)

        hoists_norm[hoist_key] = {
            "rope_id": runtime_rope_id,
            "load_node_id": managed_hook_node_id,
            "support_node_id": support_node_id,
            "falls": normal_falls,
            "splitable_block": split_mode_obj is not None,
            "split_falls": split_falls,
            "split_hook_mass_t": float(
                split_mode_obj["hook_mass_t"]
                if split_mode_obj is not None
                else normal_mode_obj["hook_mass_t"]
            ),
            "hook": {
                "mass_t": float(normal_mode_obj["hook_mass_t"]),
                "daf": float(hoist["hook_daf"]),
                "offlead_deg_limit": float(hoist["offlead_deg"]),
                "side_lead_deg_limit": float(hoist.get("side_lead_deg", hoist["offlead_deg"])),
            },
            "operating_envelope": {
                "outreach_min_m": float(min_outreach),
                "outreach_max_m": float(max_outreach),
            },
            "contractual_curve": normal_curve,
            "split_contractual_points": split_curve,
            "linear_mass_kg_m": float(hoist.get("linear_mass_kg_m", 0.0)),
            "rope_length_m": (
                float(hoist["rope_length_m"]) if hoist.get("rope_length_m") is not None else None
            ),
        }
        hook_travel = hoist.get("hook_travel")
        min_tackle = max_tackle = None
        if hook_travel is not None:
            if not isinstance(hook_travel, dict):
                raise ValueError(
                    f"model_definition.payload_hoists[{hoist_key}].hook_travel must be an object"
                )
            min_tackle = float(hook_travel["min_m"])
            max_tackle = float(hook_travel["max_m"])
            if min_tackle > max_tackle:
                raise ValueError(
                    f"model_definition.payload_hoists[{hoist_key}].hook_travel.min_m must "
                    "be <= max_m"
                )
        if min_tackle is not None and max_tackle is not None:
            hoists_norm[hoist_key]["hook_travel"] = {
                "min_m": min_tackle,
                "max_m": max_tackle,
            }

    if boom_id in hoists_norm:
        raise ValueError("model_definition.payload_hoists cannot include the boom hoist id")

    boom_runtime_rope_id = _runtime_rope_id_for_hoist(boom_id)
    ropes_norm[boom_runtime_rope_id] = {
        "tension_mode": "solve",
        "segments": boom_segments,
        "linear_mass_kg_m": float(boom_hoist_src.get("linear_mass_kg_m", 0.0)),
    }
    hoists_norm[boom_id] = {
        "rope_id": boom_runtime_rope_id,
        "load_node_id": _infer_solve_load_node_id(boom_segments, "model_definition.boom_hoist"),
        "linear_mass_kg_m": float(boom_hoist_src.get("linear_mass_kg_m", 0.0)),
        "hook": {
            "mass_t": 0.0,
            "daf": 1.0,
            "offlead_deg_limit": 0.0,
            "side_lead_deg_limit": 0.0,
        },
        "operating_envelope": {
            "outreach_min_m": 0.0,
            "outreach_max_m": 200.0,
        },
        "contractual_curve": [],
        "rope_length_m": (
            float(boom_hoist_src["rope_length_m"])
            if boom_hoist_src.get("rope_length_m") is not None
            else None
        ),
    }
    environment_src = md.get("environment")
    if not isinstance(environment_src, dict):
        raise ValueError("model_definition.environment must be an object")
    vessel_motion_src = md.get("vessel_motion", {})
    if not isinstance(vessel_motion_src, dict):
        raise ValueError("model_definition.vessel_motion must be an object")

    boom_width_m = float(md["boom_width_m"])
    slewing_bearing_diameter_m = float(md["slewing_bearing_diameter_m"])

    bodies: list[dict[str, Any]] = []
    for body_id in CANONICAL_BODIES:
        body_item = body_loads.get(body_id)
        if not isinstance(body_item, dict):
            raise ValueError(f"model_definition.body_loads.{body_id} must be an object")
        _require_object_keys(
            body_item,
            {"mass_points", "wind_areas"},
            set(),
            f"model_definition.body_loads.{body_id}",
        )
        mass_points_src = body_item["mass_points"]
        wind_areas_src = body_item["wind_areas"]
        if not isinstance(mass_points_src, list) or not isinstance(wind_areas_src, list):
            raise ValueError(
                f"model_definition.body_loads.{body_id} mass_points/wind_areas must be arrays"
            )

        mass_points: list[dict[str, Any]] = []
        for idx, mp in enumerate(mass_points_src):
            if not isinstance(mp, dict):
                raise ValueError(f"mass point at {body_id}[{idx}] must be an object")
            _require_object_keys(
                mp, {"id", "mass_t", "position"}, set(), f"mass_point[{body_id}][{idx}]"
            )
            if not isinstance(mp.get("position"), dict):
                raise ValueError(f"mass_point[{body_id}][{idx}].position must be an object")
            pos = _position_to_runtime_fields(
                mp["position"],
                f"mass_point[{body_id}][{idx}]",
                allow_hanging=False,
                body_id=body_id,
                allow_inferred_type=True,
            )
            mass_points.append(
                {
                    "id": str(mp["id"]),
                    "mass_t": float(mp["mass_t"]),
                    **pos,
                }
            )

        wind_areas: list[dict[str, Any]] = []
        for idx, wa in enumerate(wind_areas_src):
            if not isinstance(wa, dict):
                raise ValueError(f"wind area at {body_id}[{idx}] must be an object")
            _require_object_keys(
                wa,
                {"id", "area_w_m2", "area_v_m2", "cd", "position"},
                set(),
                f"wind_area[{body_id}][{idx}]",
            )
            area_w = float(wa["area_w_m2"])
            area_v = float(wa["area_v_m2"])
            if not isinstance(wa.get("position"), dict):
                raise ValueError(f"wind_area[{body_id}][{idx}].position must be an object")
            pos = _position_to_runtime_fields(
                wa["position"],
                f"wind_area[{body_id}][{idx}]",
                allow_hanging=False,
                body_id=body_id,
                allow_inferred_type=True,
            )
            wind_areas.append(
                {
                    "id": str(wa["id"]),
                    "area_w_m2": area_w,
                    "area_v_m2": area_v,
                    "cd": float(wa["cd"]),
                    **pos,
                }
            )

        bodies.append({"id": body_id, "mass_points": mass_points, "wind_areas": wind_areas})

    node_ids = set(nodes_with_primary.keys())
    nodes: list[dict[str, Any]] = []
    for node_id, node in nodes_with_primary.items():
        if not isinstance(node, dict):
            raise ValueError(f"node {node_id} must be an object")
        allowed_node_keys = {"position", "x_m", "z_m", "u_m", "w_m"}
        if _is_managed_hook_node_id(str(node_id)):
            allowed_node_keys.update({"hang_from_node_id", "drop_m"})
        _require_object_keys(node, {"body"}, allowed_node_keys, f"node[{node_id}]")
        if node["body"] not in CANONICAL_BODIES:
            raise ValueError(f"node[{node_id}].body must be one of {CANONICAL_BODIES}")
        if "position" in node:
            if not isinstance(node.get("position"), dict):
                raise ValueError(f"node[{node_id}].position must be an object")
            pos = _position_to_runtime_fields(
                node["position"], f"node[{node_id}]", allow_hanging=True
            )
        else:
            if _is_managed_hook_node_id(str(node_id)) and node.get("hang_from_node_id") is not None:
                if any(k in node for k in ("x_m", "z_m", "u_m", "w_m")):
                    raise ValueError(
                        f"node[{node_id}] hanging nodes cannot also define x_m/z_m/u_m/w_m"
                    )
                drop_m_raw = node.get("drop_m")
                drop_m = float(drop_m_raw) if drop_m_raw is not None else None
                if drop_m is not None and drop_m < 0.0:
                    raise ValueError(f"node[{node_id}].drop_m must be >= 0")
                pos = {
                    "x_m": 0.0,
                    "z_m": 0.0,
                    "below_node_id": str(node["hang_from_node_id"]),
                    "hanging_drop_m": drop_m,
                }
            elif node["body"] == "boom" and ("u_m" in node or "w_m" in node):
                if "u_m" not in node or "w_m" not in node:
                    raise ValueError(f"node[{node_id}] boom-local nodes require both u_m and w_m")
                if "x_m" in node or "z_m" in node:
                    raise ValueError(
                        f"node[{node_id}] cannot define both local and global coordinates"
                    )
                pos = {
                    "x_m": 0.0,
                    "z_m": 0.0,
                    "local_x_m": float(node["u_m"]),
                    "local_z_m": float(node["w_m"]),
                }
            else:
                if "x_m" not in node or "z_m" not in node:
                    raise ValueError(
                        f"node[{node_id}] global nodes require x_m and z_m, "
                        "or provide local u_m/w_m for boom nodes"
                    )
                if "u_m" in node or "w_m" in node:
                    raise ValueError(
                        f"node[{node_id}] cannot define both local and global coordinates"
                    )
                pos = {
                    "x_m": float(node["x_m"]),
                    "z_m": float(node["z_m"]),
                }
        nodes.append(
            {
                "id": str(node_id),
                "body": str(node["body"]),
                **pos,
            }
        )

    for node in nodes:
        ref_id = node.get("below_node_id")
        if not ref_id:
            continue
        if ref_id not in node_ids:
            raise ValueError(
                f"node[{node['id']}].position.from_node_id references unknown node {ref_id!r}"
            )
        if ref_id == node.get("id"):
            raise ValueError(f"node[{node['id']}] cannot hang from itself")

    rope_ids = set(ropes_norm.keys())
    ropes: list[dict[str, Any]] = []
    for rope_id, rope in ropes_norm.items():
        if not isinstance(rope, dict):
            raise ValueError(f"rope {rope_id} must be an object")
        _require_object_keys(
            rope, {"tension_mode", "segments"}, {"linear_mass_kg_m"}, f"rope[{rope_id}]"
        )
        segs = rope["segments"]
        if not isinstance(segs, list):
            raise ValueError(f"rope[{rope_id}].segments must be an array")
        segments: list[dict[str, Any]] = []
        for idx, seg in enumerate(segs):
            if not isinstance(seg, dict):
                raise ValueError(f"rope[{rope_id}].segments[{idx}] must be an object")
            _require_object_keys(seg, {"from", "to"}, {"parts"}, f"rope[{rope_id}].segments[{idx}]")
            from_node_id = str(seg["from"])
            to_node_id = str(seg["to"])
            if from_node_id not in node_ids:
                raise ValueError(
                    f"rope[{rope_id}].segments[{idx}].from references unknown node {from_node_id!r}"
                )
            if to_node_id not in node_ids:
                raise ValueError(
                    f"rope[{rope_id}].segments[{idx}].to references unknown node {to_node_id!r}"
                )
            segments.append(
                {
                    "from_node_id": from_node_id,
                    "to_node_id": to_node_id,
                    "mult": int(seg.get("parts", 1)),
                }
            )
        tension_mode = str(rope["tension_mode"])
        if tension_mode not in {"fixed", "solve"}:
            raise ValueError(f"rope[{rope_id}].tension_mode must be fixed|solve")
        ropes.append(
            {
                "id": str(rope_id),
                "segments": segments,
                "tension_mode": "solve" if tension_mode == "solve" else None,
                "linear_mass_kg_m": float(rope.get("linear_mass_kg_m", 0.0)),
            }
        )

    hoists: list[dict[str, Any]] = []
    for hoist_id, hoist in hoists_norm.items():
        if not isinstance(hoist, dict):
            raise ValueError(f"hoist {hoist_id} must be an object")
        _require_object_keys(
            hoist,
            {"rope_id", "load_node_id", "hook", "operating_envelope", "contractual_curve"},
            {
                "hook_travel",
                "support_node_id",
                "falls",
                "splitable_block",
                "split_falls",
                "split_hook_mass_t",
                "split_contractual_points",
                "linear_mass_kg_m",
                "rope_length_m",
            },
            f"hoist[{hoist_id}]",
        )
        hook = hoist["hook"]
        envl = hoist["operating_envelope"]
        curve = hoist["contractual_curve"]
        hook_travel = hoist.get("hook_travel")
        if not isinstance(hook, dict) or not isinstance(envl, dict) or not isinstance(curve, list):
            raise ValueError(f"hoist[{hoist_id}] hook/envelope/curve have invalid types")
        _require_object_keys(
            hook,
            {"mass_t", "daf", "offlead_deg_limit"},
            {"side_lead_deg_limit"},
            f"hoist[{hoist_id}].hook",
        )
        _require_object_keys(
            envl,
            {"outreach_min_m", "outreach_max_m"},
            set(),
            f"hoist[{hoist_id}].operating_envelope",
        )
        min_hook_travel_m = None
        max_hook_travel_m = None
        if hook_travel is not None:
            if not isinstance(hook_travel, dict):
                raise ValueError(f"hoist[{hoist_id}].hook_travel must be an object")
            _require_object_keys(
                hook_travel, {"min_m", "max_m"}, set(), f"hoist[{hoist_id}].hook_travel"
            )
            min_hook_travel_m = float(hook_travel["min_m"])
            max_hook_travel_m = float(hook_travel["max_m"])
        rope_id = str(hoist["rope_id"])
        load_node_id = str(hoist["load_node_id"])
        if rope_id not in rope_ids:
            raise ValueError(f"hoist[{hoist_id}].rope_id references unknown rope {rope_id!r}")
        if load_node_id not in node_ids:
            raise ValueError(
                f"hoist[{hoist_id}].load_node_id references unknown node {load_node_id!r}"
            )
        cps: list[dict[str, Any]] = []
        for idx, cp in enumerate(curve):
            if not isinstance(cp, dict):
                raise ValueError(f"hoist[{hoist_id}].contractual_curve[{idx}] must be an object")
            _require_object_keys(
                cp,
                {"outreach_m", "load_t"},
                {"label"},
                f"hoist[{hoist_id}].contractual_curve[{idx}]",
            )
            cp_runtime = {
                "outreach_m": float(cp["outreach_m"]),
                "load_t": float(cp["load_t"]),
            }
            if "label" in cp:
                cp_runtime["label"] = str(cp["label"])
            cps.append(cp_runtime)
        split_cps: list[dict[str, Any]] = []
        split_curve = hoist.get("split_contractual_points") or []
        if not isinstance(split_curve, list):
            raise ValueError(f"hoist[{hoist_id}].split_contractual_points must be an array")
        for idx, cp in enumerate(split_curve):
            if not isinstance(cp, dict):
                raise ValueError(
                    f"hoist[{hoist_id}].split_contractual_points[{idx}] must be an object"
                )
            _require_object_keys(
                cp,
                {"outreach_m", "load_t"},
                {"label"},
                f"hoist[{hoist_id}].split_contractual_points[{idx}]",
            )
            cp_runtime = {
                "outreach_m": float(cp["outreach_m"]),
                "load_t": float(cp["load_t"]),
            }
            if "label" in cp:
                cp_runtime["label"] = str(cp["label"])
            split_cps.append(cp_runtime)
        hoists.append(
            {
                "id": str(hoist_id),
                "rope_id": rope_id,
                "load_node_id": load_node_id,
                "support_node_id": hoist.get("support_node_id"),
                "falls": hoist.get("falls"),
                "splitable_block": bool(hoist.get("splitable_block", False)),
                "split_falls": hoist.get("split_falls"),
                "split_hook_mass_t": hoist.get("split_hook_mass_t"),
                "split_contractual_points": split_cps,
                "hook_mass_t": float(hook["mass_t"]),
                "hook_daf": float(hook["daf"]),
                "offlead_deg": float(hook["offlead_deg_limit"]),
                "side_lead_deg": float(hook.get("side_lead_deg_limit", hook["offlead_deg_limit"])),
                "outreach_min_m": float(envl["outreach_min_m"]),
                "outreach_max_m": float(envl["outreach_max_m"]),
                "min_hook_travel_m": min_hook_travel_m,
                "max_hook_travel_m": max_hook_travel_m,
                "contractual_points": cps,
                "linear_mass_kg_m": float(hoist.get("linear_mass_kg_m", 0.0)),
                "rope_length_m": (
                    float(hoist["rope_length_m"])
                    if hoist.get("rope_length_m") is not None
                    else None
                ),
            }
        )

    return {
        "schema_version": "1.0.0",
        "model_type": "fixed_topology_crane_2d",
        "metadata": {
            "name": str(metadata_src["name"]),
            "units": "m,kN",
        },
        "environment": {
            "gravity_m_s2": -abs(float(environment_src.get("gravity_m_s2", DEFAULT_GRAVITY_M_S2))),
            "max_wind_speed_m_s": abs(float(environment_src["max_wind_speed_m_s"])),
            "wind_reference_height_m_asl": float(environment_src["wind_reference_height_m_asl"]),
            "air_density_kg_m3": float(
                environment_src.get("air_density_kg_m3", DEFAULT_AIR_DENSITY_KG_M3)
            ),
            "wind_profile_exponent": float(environment_src["wind_profile_exponent"]),
            "mean_sealevel_z_m": float(environment_src["mean_sealevel_z_m"]),
            "vessel_motion": {
                "accel_x_m_s2": abs(
                    float(
                        vessel_motion_src.get("accel_x_m_s2", DEFAULT_VESSEL_MOTION["accel_x_m_s2"])
                    )
                ),
                "accel_y_m_s2": abs(
                    float(
                        vessel_motion_src.get("accel_y_m_s2", DEFAULT_VESSEL_MOTION["accel_y_m_s2"])
                    )
                ),
                "accel_z_m_s2": abs(
                    float(
                        vessel_motion_src.get("accel_z_m_s2", DEFAULT_VESSEL_MOTION["accel_z_m_s2"])
                    )
                ),
                "reference_x_m": float(
                    vessel_motion_src.get("reference_x_m", DEFAULT_VESSEL_MOTION["reference_x_m"])
                ),
                "reference_z_m": float(
                    vessel_motion_src.get("reference_z_m", DEFAULT_VESSEL_MOTION["reference_z_m"])
                ),
                "pitch_angular_accel_rad_s2": abs(
                    float(
                        vessel_motion_src.get(
                            "pitch_angular_accel_rad_s2",
                            DEFAULT_VESSEL_MOTION["pitch_angular_accel_rad_s2"],
                        )
                    )
                ),
                "roll_angular_accel_rad_s2": abs(
                    float(
                        vessel_motion_src.get(
                            "roll_angular_accel_rad_s2",
                            DEFAULT_VESSEL_MOTION["roll_angular_accel_rad_s2"],
                        )
                    )
                ),
            },
        },
        "support_widths": {
            "boom_width_m": boom_width_m,
            "slewing_bearing_diameter_m": slewing_bearing_diameter_m,
        },
        "bodies": bodies,
        "nodes": nodes,
        "ropes": ropes,
        "hoists": hoists,
    }


def _infer_falls_from_segments(
    segments: list[list[Any]], support_node_id: str, load_node_id: str
) -> int:
    for seg in segments:
        if not isinstance(seg, list) or len(seg) < 3:
            continue
        from_id = str(seg[0])
        to_id = str(seg[1])
        if (from_id == support_node_id and to_id == load_node_id) or (
            to_id == support_node_id and from_id == load_node_id
        ):
            return max(1, int(seg[2]))
    return 1


def _runtime_rope_id_for_hoist(hoist_id: str) -> str:
    return f"{hoist_id}__rope"


def _hoist_curve_outreach_bounds(curve: list[Any]) -> tuple[float, float]:
    if not curve:
        return (0.0, 200.0)
    outreaches: list[float] = []
    for cp in curve:
        if isinstance(cp, dict):
            outreaches.append(float(cp.get("outreach_m", 0.0)))
        elif isinstance(cp, (list, tuple)) and len(cp) >= 1:
            outreaches.append(float(cp[0]))
        else:
            raise ValueError("contractual_curve points must be objects or [outreach_m, load_t]")
    return (min(outreaches), max(outreaches))


def _normalize_contractual_curve_points(
    curve_src: list[Any],
    ctx: str,
) -> list[dict[str, Any]]:
    """Normalize contractual points from authored form."""
    curve_norm: list[dict[str, Any]] = []
    for idx, cp in enumerate(curve_src):
        if isinstance(cp, dict):
            _require_object_keys(cp, {"outreach_m", "load_t"}, {"label"}, f"{ctx}[{idx}]")
            curve_norm.append(
                {
                    "outreach_m": float(cp["outreach_m"]),
                    "load_t": float(cp["load_t"]),
                    **({"label": str(cp["label"])} if cp.get("label") else {}),
                }
            )
            continue
        raise ValueError(f"{ctx}[{idx}] must be an object with outreach_m and load_t")
    return curve_norm


def _validate_compact_component_positions(components: dict[str, Any], path_prefix: str) -> None:
    """Enforce compact authored position shape for mass points and wind areas.

    - boom: position must use u_m/w_m (no type)
    - rear_leg/front_leg/platform: position must use x_m/z_m (no type)
    """

    sections = {
        "boom": components.get("boom"),
        "rear_leg": components.get("rear_leg"),
        "front_leg": components.get("front_leg"),
        "platform": components.get("platform"),
    }

    for body_id, section in sections.items():
        if not isinstance(section, dict):
            continue
        for key in ("mass_points", "wind_areas"):
            entries = section.get(key) or []
            if not isinstance(entries, list):
                continue
            for idx, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                pos = entry.get("position")
                if not isinstance(pos, dict):
                    continue
                if "type" in pos:
                    raise ValueError(
                        f"{path_prefix}.{body_id}.{key}[{idx}].position must omit type "
                        "in compact format"
                    )
                if body_id == "boom":
                    if "u_m" not in pos or "w_m" not in pos:
                        raise ValueError(
                            f"{path_prefix}.{body_id}.{key}[{idx}].position must use u_m and w_m"
                        )
                    if "x_m" in pos or "z_m" in pos:
                        raise ValueError(
                            f"{path_prefix}.{body_id}.{key}[{idx}].position cannot include x_m/z_m"
                        )
                else:
                    if "x_m" not in pos or "z_m" not in pos:
                        raise ValueError(
                            f"{path_prefix}.{body_id}.{key}[{idx}].position must use x_m and z_m"
                        )
                    if "u_m" in pos or "w_m" in pos:
                        raise ValueError(
                            f"{path_prefix}.{body_id}.{key}[{idx}].position cannot include u_m/w_m"
                        )


def _is_default_analysis_defaults(scene: dict[str, Any]) -> bool:
    vm = scene.get("accelerations") or {}
    return (
        abs(float(scene.get("wind_speed_m_s", 20.0)) - 20.0) <= 1e-9
        and abs(float(vm.get("accel_x_m_s2", 0.0))) <= 1e-9
        and abs(float(vm.get("accel_y_m_s2", 0.0))) <= 1e-9
        and abs(float(vm.get("accel_z_m_s2", 0.0))) <= 1e-9
        and abs(float(vm.get("pitch_angular_accel_rad_s2", 0.0))) <= 1e-9
        and abs(float(vm.get("roll_angular_accel_rad_s2", 0.0))) <= 1e-9
        and abs(float(vm.get("reference_x_m", 0.0))) <= 1e-9
        and abs(float(vm.get("reference_z_m", 0.0))) <= 1e-9
    )


def _build_body_loads_from_components(
    components: dict[str, Any],
    *,
    require_nodes: bool = False,
    path_prefix: str = "model_definition.components",
) -> dict[str, Any]:
    """Map compact authored component sections to canonical body_loads."""
    _require_object_keys(
        components, {"boom", "rear_leg", "front_leg", "platform"}, set(), path_prefix
    )

    container_required: set[str] = {"nodes"} if require_nodes else set()
    container_optional = {"nodes", "mass_points", "wind_areas"}

    for comp_id, comp_obj in {
        "boom": components.get("boom"),
        "rear_leg": components.get("rear_leg"),
        "front_leg": components.get("front_leg"),
        "platform": components.get("platform"),
    }.items():
        if not isinstance(comp_obj, dict):
            raise ValueError(f"{path_prefix}.{comp_id} must be an object")
        _require_object_keys(
            comp_obj, container_required, container_optional, f"{path_prefix}.{comp_id}"
        )

    def _loads_only(section: dict[str, Any]) -> dict[str, Any]:
        return {
            "mass_points": section.get("mass_points", []),
            "wind_areas": section.get("wind_areas", []),
        }

    return {
        "boom": _loads_only(components.get("boom", {})),
        "rear_leg": _loads_only(components.get("rear_leg", {})),
        "front_leg": _loads_only(components.get("front_leg", {})),
        "platform": _loads_only(components.get("platform", {})),
    }


def _extract_component_nodes_from_components(
    components: dict[str, Any],
    *,
    path_prefix: str = "model_definition.components",
    forbidden_node_ids: Optional[set[str]] = None,
) -> dict[str, Any]:
    """Flatten component-scoped nodes into a single node map with inferred body."""
    sections = [
        ("boom", components.get("boom")),
        ("rear_leg", components.get("rear_leg")),
        ("front_leg", components.get("front_leg")),
        ("platform", components.get("platform")),
    ]

    nodes_out: dict[str, Any] = {}
    for body_id, container in sections:
        if not isinstance(container, dict):
            raise ValueError(f"{path_prefix}.{body_id} must be an object")
        raw_nodes = container.get("nodes") or {}
        if isinstance(raw_nodes, dict):
            for node_id, node in raw_nodes.items():
                if not isinstance(node, dict):
                    raise ValueError(f"{path_prefix}.{body_id}.nodes[{node_id}] must be an object")
                _require_object_keys(
                    node,
                    set(),
                    {"x_m", "z_m", "u_m", "w_m"},
                    f"{path_prefix}.{body_id}.nodes[{node_id}]",
                )
                node_id_str = str(node_id)
                if node_id_str in nodes_out:
                    raise ValueError(f"duplicate node id across components: {node_id_str!r}")
                if forbidden_node_ids and node_id_str in forbidden_node_ids:
                    raise ValueError(
                        f"{path_prefix}.{body_id}.nodes[{node_id}] is reserved topology input; "
                        "define it under model_definition.primary_structure"
                    )
                node_copy = dict(node)
                node_copy["body"] = body_id
                nodes_out[node_id_str] = node_copy
            continue
        raise ValueError(f"{path_prefix}.{body_id}.nodes must be an object keyed by node id")
    return nodes_out


def _extract_primary_structure_nodes(primary_structure: Any) -> dict[str, Any]:
    """Convert authored primary_structure coordinates into runtime primary nodes."""
    if not isinstance(primary_structure, dict):
        raise ValueError("model_definition.primary_structure must be an object")
    _require_object_keys(
        primary_structure,
        set(PRIMARY_STRUCTURE_TO_RUNTIME_NODE.keys()),
        set(),
        "model_definition.primary_structure",
    )

    nodes: dict[str, Any] = {}
    for authored_key, (runtime_node_id, body_id) in PRIMARY_STRUCTURE_TO_RUNTIME_NODE.items():
        val = primary_structure.get(authored_key)
        if not isinstance(val, dict):
            raise ValueError(f"model_definition.primary_structure.{authored_key} must be an object")
        _require_object_keys(
            val,
            {"x_m", "z_m"},
            set(),
            f"model_definition.primary_structure.{authored_key}",
        )
        nodes[runtime_node_id] = {
            "body": body_id,
            "x_m": float(val["x_m"]),
            "z_m": float(val["z_m"]),
        }
    return nodes


def _synthesize_primary_nodes_into_nodes_map(nodes_src: dict[str, Any]) -> dict[str, Any]:
    """Ensure internal canonical primary topology is present even when omitted by authored JSON."""
    merged = dict(nodes_src)
    for node_id, node_def in PRIMARY_NODE_DEFAULTS.items():
        merged.setdefault(node_id, dict(node_def))
    return merged


def _position_to_runtime_fields(
    position: dict[str, Any],
    ctx: str,
    allow_hanging: bool,
    *,
    body_id: Optional[str] = None,
    allow_inferred_type: bool = False,
) -> dict[str, Any]:
    """Convert authored position object to runtime coordinate fields."""
    ptype = position.get("type")
    if ptype is None and allow_inferred_type:
        _require_object_keys(
            position, set(), {"x_m", "y_m", "z_m", "u_m", "v_m", "w_m"}, f"{ctx}.position"
        )
        if body_id == "boom":
            if "u_m" not in position or "w_m" not in position:
                raise ValueError(
                    f"{ctx}.position for boom must provide u_m and w_m when type is omitted"
                )
            if "x_m" in position or "y_m" in position or "z_m" in position:
                raise ValueError(f"{ctx}.position cannot mix x_m/y_m/z_m with u_m/v_m/w_m")
            return {
                "x_m": 0.0,
                "y_m": 0.0,
                "z_m": 0.0,
                "local_x_m": float(position["u_m"]),
                "local_y_m": float(position.get("v_m", 0.0)),
                "local_z_m": float(position["w_m"]),
            }
        if body_id in {"rear_leg", "front_leg", "platform"}:
            if "x_m" not in position or "z_m" not in position:
                raise ValueError(
                    f"{ctx}.position for {body_id} must provide x_m and z_m when type is omitted"
                )
            if "u_m" in position or "v_m" in position or "w_m" in position:
                raise ValueError(f"{ctx}.position cannot mix x_m/y_m/z_m with u_m/v_m/w_m")
            return {
                "x_m": float(position["x_m"]),
                "y_m": float(position.get("y_m", 0.0)),
                "z_m": float(position["z_m"]),
            }
        raise ValueError(f"{ctx}.position cannot infer coordinate system without a valid body")

    _require_object_keys(
        position,
        {"type"},
        {"x_m", "y_m", "z_m", "u_m", "v_m", "w_m", "from_node_id", "drop_m"},
        f"{ctx}.position",
    )
    if ptype == "global":
        if body_id in {"boom", "rear_leg", "front_leg", "platform"}:
            if "x_m" not in position or "z_m" not in position:
                raise ValueError(f"{ctx}.position type=global requires x_m and z_m")
            return {
                "x_m": float(position["x_m"]),
                "y_m": float(position.get("y_m", 0.0)),
                "z_m": float(position["z_m"]),
            }
        if "x_m" not in position or "z_m" not in position:
            raise ValueError(f"{ctx}.position type=global requires x_m and z_m")
        return {
            "x_m": float(position["x_m"]),
            "z_m": float(position["z_m"]),
        }
    if ptype == "boom_local":
        if body_id in {"boom", "rear_leg", "front_leg", "platform"}:
            if "u_m" not in position or "w_m" not in position:
                raise ValueError(f"{ctx}.position type=boom_local requires u_m and w_m")
            return {
                "x_m": 0.0,
                "y_m": 0.0,
                "z_m": 0.0,
                "local_x_m": float(position["u_m"]),
                "local_y_m": float(position.get("v_m", 0.0)),
                "local_z_m": float(position["w_m"]),
            }
        if "u_m" not in position or "w_m" not in position:
            raise ValueError(f"{ctx}.position type=boom_local requires u_m and w_m")
        return {
            "x_m": 0.0,
            "z_m": 0.0,
            "local_x_m": float(position["u_m"]),
            "local_z_m": float(position["w_m"]),
        }
    if ptype == "hanging":
        if not allow_hanging:
            raise ValueError(f"{ctx}.position type=hanging not allowed here")
        if "from_node_id" not in position:
            raise ValueError(f"{ctx}.position type=hanging requires from_node_id")
        drop_m = float(position.get("drop_m", 1.0))
        if drop_m < 0.0:
            raise ValueError(f"{ctx}.position drop_m must be >= 0")
        return {
            "x_m": 0.0,
            "z_m": 0.0,
            "below_node_id": str(position["from_node_id"]),
            "hanging_drop_m": drop_m,
        }
    raise ValueError(f"{ctx}.position type must be one of global|boom_local|hanging")


def _runtime_centroid_position(entity: dict[str, Any], *, body_id: str) -> dict[str, float]:
    """Convert runtime wind-area coordinates to the v5.12 authored position object."""
    if body_id == "boom" and entity.get("local_x_m") is not None:
        return {
            "u_m": float(entity.get("local_x_m", 0.0)),
            "w_m": float(entity.get("local_z_m", 0.0)),
        }
    return {"x_m": float(entity.get("x_m", 0.0)), "z_m": float(entity.get("z_m", 0.0))}


def _runtime_mass_position(entity: dict[str, Any], *, body_id: str) -> dict[str, float]:
    """Convert runtime mass-point coordinates to the v5.12 authored position object."""
    if body_id == "boom" and entity.get("local_x_m") is not None:
        return {
            "u_m": float(entity.get("local_x_m", 0.0)),
            "v_m": float(entity.get("local_y_m", 0.0)),
            "w_m": float(entity.get("local_z_m", 0.0)),
        }
    return {
        "x_m": float(entity.get("x_m", 0.0)),
        "y_m": float(entity.get("y_m", 0.0)),
        "z_m": float(entity.get("z_m", 0.0)),
    }


# ============================================================================
# Normalization and Round-Trip Functions
# ============================================================================


def normalize_document(doc_data: dict[str, Any]) -> CraneDocument:
    """
    Normalize an authored document into runtime form.

    This function:
    1. Fills in missing required fields with defaults
    2. Generates derived nodes
    3. Generates canonical connections
    4. Ensures canonical fixed-body order

    Args:
        doc_data: Raw JSON data from file

    Returns:
        Normalized CraneDocument ready for analysis
    """
    doc_data = deepcopy(doc_data)

    if "schema" in doc_data:
        if _is_authored_document(doc_data):
            doc_data = _normalize_authored_document(doc_data)
        else:
            schema = doc_data.get("schema") if isinstance(doc_data.get("schema"), dict) else {}
            found_name = schema.get("name")
            found_version = schema.get("version")
            raise ValueError(
                "Only crane-statics schema version 5.12.0 is supported for authored input; "
                f"found name={found_name!r}, version={found_version!r}"
            )

    # Ensure required root fields exist
    if "schema_version" not in doc_data:
        doc_data["schema_version"] = "1.0.0"
    if "model_type" not in doc_data:
        doc_data["model_type"] = "fixed_topology_crane_2d"
    if "metadata" not in doc_data:
        doc_data["metadata"] = {}
    if "environment" not in doc_data:
        doc_data["environment"] = {}
    if "bodies" not in doc_data:
        doc_data["bodies"] = []
    if "nodes" not in doc_data:
        doc_data["nodes"] = []
    if "ropes" not in doc_data:
        doc_data["ropes"] = []
    if "hoists" not in doc_data:
        doc_data["hoists"] = []

    # Normalize body order: canonical fixed bodies first
    canonical_bodies = CANONICAL_BODIES
    existing_ids = {b.get("id"): b for b in doc_data["bodies"]}
    normalized_bodies = []

    for body_id in canonical_bodies:
        if body_id in existing_ids:
            normalized_bodies.append(existing_ids[body_id])
        else:
            # Insert default empty body
            normalized_bodies.append({"id": body_id, "mass_points": [], "wind_areas": []})

    # Add non-canonical bodies
    for body in doc_data["bodies"]:
        if body.get("id") not in canonical_bodies:
            normalized_bodies.append(body)

    doc_data["bodies"] = normalized_bodies

    # Ensure canonical primary topology nodes exist (internal topology synthesis).
    node_ids = {n.get("id") for n in doc_data["nodes"]}
    for node_id, node_def in PRIMARY_NODE_DEFAULTS.items():
        if node_id in node_ids:
            continue
        doc_data["nodes"].append(
            {
                "id": node_id,
                "body": node_def["body"],
                "x_m": float(node_def["x_m"]),
                "z_m": float(node_def["z_m"]),
            }
        )

    # Normalize structural nodes - set body if missing for known topology nodes
    structural_nodes = {
        "boom_heel": "boom",
        "rear_base": "rear_leg",
        "rear_top": "rear_leg",
        "front_base": "front_leg",
        "front_top": "front_leg",
    }

    for node in doc_data["nodes"]:
        node_id = node.get("id")
        if node_id in structural_nodes and "body" not in node:
            node["body"] = structural_nodes[node_id]

    # Create derived nodes if missing
    derived_node_mappings = {
        "front_top": ("rear_top", "front_leg"),
        "platform_rear": ("rear_base", "platform"),
        "platform_front": ("front_base", "platform"),
        "platform_heel": ("boom_heel", "platform"),
    }

    node_ids = {n.get("id") for n in doc_data["nodes"]}
    node_by_id = {n.get("id"): n for n in doc_data["nodes"]}

    for derived_id, (source_id, target_body) in derived_node_mappings.items():
        if derived_id not in node_ids and source_id in node_by_id:
            source_node = node_by_id[source_id]
            doc_data["nodes"].append(
                {
                    "id": derived_id,
                    "body": target_body,
                    "x_m": source_node.get("x_m", 0.0),
                    "z_m": source_node.get("z_m", 0.0),
                    "local_x_m": source_node.get("local_x_m"),
                    "local_z_m": source_node.get("local_z_m"),
                }
            )

    # Parse and validate
    doc = CraneDocument(**doc_data)

    # Generate canonical connections (runtime only)
    doc.connections = generate_canonical_connections()

    return doc


def generate_canonical_connections() -> list[dict[str, Any]]:
    """Generate the canonical fixed-topology connections."""
    return [
        {"id": "platform_base", "type": "ground_fixed"},
        {"id": "rear_hinge", "type": "body_pin"},
        {"id": "front_hinge", "type": "body_pin"},
        {"id": "upper_hinge", "type": "body_pin"},
        {"id": "heel_point", "type": "body_pin"},
    ]


def document_to_authored_form(doc: CraneDocument) -> dict[str, Any]:
    """
    Convert a normalized runtime document back to authored form for saving.

    This removes:
    - Derived nodes
    - Canonical connections
    - Topology-controlled body fields on structural nodes
    - Internal segment IDs
    """
    data = doc.model_dump(exclude={"connections"})

    # Remove derived nodes
    derived_node_ids = {"front_top", "platform_rear", "platform_front", "platform_heel"}
    data["nodes"] = [n for n in data["nodes"] if n.get("id") not in derived_node_ids]

    # Remove topology-controlled body fields
    structural_nodes = {
        "boom_heel": "boom",
        "rear_base": "rear_leg",
        "rear_top": "rear_leg",
        "front_base": "front_leg",
        "platform_base": "platform",
    }

    for node in data["nodes"]:
        node_id = node.get("id")
        if node_id in structural_nodes:
            # Keep body for clarity in authored form, but note it's implicit
            pass

    body_loads: dict[str, dict[str, list[dict[str, Any]]]] = {
        body_id: {"mass_points": [], "wind_areas": []} for body_id in CANONICAL_BODIES
    }
    for body in data.get("bodies", []):
        body_id = body.get("id")
        if body_id not in body_loads:
            continue
        mass_points = []
        for mp in body.get("mass_points", []):
            mass_points.append(
                {
                    "id": mp.get("id"),
                    "mass_t": float(mp.get("mass_t", 0.0)),
                    "position": _runtime_mass_position(mp, body_id=body_id),
                }
            )
        wind_areas = []
        for wa in body.get("wind_areas", []):
            item = {
                "id": wa.get("id"),
                "cd": float(wa.get("cd", 1.0)),
                "position": _runtime_centroid_position(wa, body_id=body_id),
            }
            if body_id == "boom":
                item["area_w_m2"] = float(wa.get("area_w_m2", 0.0))
                item["area_v_m2"] = float(wa.get("area_v_m2", 0.0))
            else:
                item["area_x_m2"] = float(wa.get("area_w_m2", 0.0))
                item["area_y_m2"] = float(wa.get("area_v_m2", 0.0))
            wind_areas.append(item)
        body_loads[body_id] = {
            "mass_points": mass_points,
            "wind_areas": wind_areas,
        }

    nodes_by_body_authored: dict[str, dict[str, Any]] = {
        "boom": {},
        "rear_leg": {},
        "front_leg": {},
        "platform": {},
    }
    for node in data.get("nodes", []):
        node_id = node.get("id")
        if node_id in {"front_top", "platform_rear", "platform_front", "platform_heel"}:
            continue
        if _is_managed_hook_node_id(str(node_id)):
            continue
        if node_id in PRIMARY_NODE_IDS:
            continue
        node_out: Any
        if node.get("below_node_id"):
            if not _is_managed_hook_node_id(str(node_id)):
                raise ValueError(
                    f"Cannot export arbitrary hanging node {node_id!r}; use a payload hoist "
                    "support_node_id"
                )
            node_out = {"hang_from_node_id": str(node.get("below_node_id"))}
            drop_val = node.get("hanging_drop_m")
            if drop_val is not None:
                node_out["drop_m"] = float(drop_val)
        elif node.get("body") == "boom" and node.get("local_x_m") is not None:
            node_out = {
                "u_m": float(node.get("local_x_m", 0.0)),
                "w_m": float(node.get("local_z_m", 0.0)),
            }
        else:
            node_out = {
                "x_m": float(node.get("x_m", 0.0)),
                "z_m": float(node.get("z_m", 0.0)),
            }
        body_id = str(node.get("body") or "")
        if body_id not in nodes_by_body_authored:
            continue
        nodes_by_body_authored[body_id][str(node_id)] = node_out

    authored_ropes: dict[str, dict[str, Any]] = {}
    for rope in data.get("ropes", []):
        rid = str(rope.get("id"))
        segments = []
        for seg in rope.get("segments", []):
            parts = int(seg.get("mult", 1))
            segments.append(
                {
                    "from": str(seg.get("from_node_id")),
                    "to": str(seg.get("to_node_id")),
                    **({"parts": parts} if parts != 1 else {}),
                }
            )
        authored_ropes[rid] = {
            "tension_mode": "solve" if rope.get("tension_mode") == "solve" else "fixed",
            "segments": segments,
            "linear_mass_kg_m": float(rope.get("linear_mass_kg_m", 0.0)),
        }

    ropes_by_id = dict(authored_ropes)
    nodes_by_id = {str(n.get("id")): n for n in data.get("nodes", []) if isinstance(n, dict)}
    authored_payload_hoists: dict[str, dict[str, Any]] = {}
    authored_boom_hoist: dict[str, Any] | None = None
    rope_owner_by_id: dict[str, str] = {}
    solve_hoist_ids: list[str] = []
    for hoist in data.get("hoists", []):
        hid = str(hoist.get("id"))
        rope_id = str(hoist.get("rope_id") or "")
        if not rope_id or rope_id not in ropes_by_id:
            raise ValueError(
                f"Cannot export hoist-owned ropes: hoist {hid!r} references missing rope "
                f"{rope_id!r}"
            )
        if rope_id in rope_owner_by_id:
            raise ValueError(
                f"Cannot export hoist-owned ropes: runtime rope {rope_id!r} is shared by hoists "
                f"{rope_owner_by_id[rope_id]!r} and {hid!r}"
            )
        rope_owner_by_id[rope_id] = hid

        if ropes_by_id[rope_id].get("tension_mode") == "solve":
            solve_hoist_ids.append(hid)
            authored_boom_hoist = {
                "rope_segments": ropes_by_id[rope_id]["segments"],
            }
            rope_length = hoist.get("rope_length_m")
            if rope_length is not None:
                authored_boom_hoist["rope_length_m"] = float(rope_length)
            linear_mass = float(ropes_by_id[rope_id].get("linear_mass_kg_m", 0.0))
            if linear_mass > 0.0:
                authored_boom_hoist["linear_mass_kg_m"] = linear_mass
            continue

        cps = []
        for cp in hoist.get("contractual_points", []):
            outreach = float(cp.get("outreach_m", 0.0))
            load = float(cp.get("load_t", 0.0))
            cps.append({"outreach_m": outreach, "load_t": load})
        hook_mass = float(hoist.get("hook_mass_t", 0.0))
        hook_daf = float(hoist.get("hook_daf", 1.0))
        hook_offlead = float(hoist.get("offlead_deg", 0.0))
        hook_side_lead = float(hoist.get("side_lead_deg", hook_offlead))
        splitable_block = bool(hoist.get("splitable_block", False))

        load_node_id = str(hoist.get("load_node_id") or "")
        support_node_id = str(hoist.get("support_node_id") or "")
        if not support_node_id and load_node_id:
            load_node = nodes_by_id.get(load_node_id, {})
            if isinstance(load_node, dict):
                support_node_id = str(load_node.get("below_node_id") or "")
        if not support_node_id:
            support_node_id = load_node_id

        rope_segments_out = []
        for seg in ropes_by_id[rope_id]["segments"]:
            if _is_managed_hook_node_id(load_node_id):
                if load_node_id in {
                    str(seg.get("from")),
                    str(seg.get("to")),
                }:
                    continue
            rope_segments_out.append(seg)

        falls = hoist.get("falls")
        if falls is None:
            falls = _infer_falls_from_segments(
                ropes_by_id[rope_id]["segments"], support_node_id, load_node_id
            )
        split_falls = hoist.get("split_falls")
        if split_falls is None:
            split_falls = falls
        split_hook_mass_t = hoist.get("split_hook_mass_t")
        if split_hook_mass_t is None:
            split_hook_mass_t = hook_mass

        normal_points: list[dict[str, float]] = cps
        split_points: list[dict[str, float]] = []
        for cp in hoist.get("split_contractual_points", []):
            split_points.append(
                {
                    "outreach_m": float(cp.get("outreach_m", 0.0)),
                    "load_t": float(cp.get("load_t", 0.0)),
                }
            )

        authored_hoist: dict[str, Any] = {
            "falls": int(falls),
            "hook_mass_t": hook_mass,
            "contractual_points": normal_points,
        }
        if splitable_block:
            authored_hoist["split"] = {
                "falls": int(split_falls),
                "hook_mass_t": float(split_hook_mass_t),
                "contractual_points": split_points,
            }

        authored_payload_hoists[hid] = {
            "support_node_id": support_node_id,
            "hook_daf": hook_daf,
            "offlead_deg": hook_offlead,
            "side_lead_deg": hook_side_lead,
            **authored_hoist,
            "rope_segments": rope_segments_out,
        }
        rope_length = hoist.get("rope_length_m")
        if rope_length is not None:
            authored_payload_hoists[hid]["rope_length_m"] = float(rope_length)
        linear_mass = float(ropes_by_id[rope_id].get("linear_mass_kg_m", 0.0))
        if linear_mass > 0.0:
            authored_payload_hoists[hid]["linear_mass_kg_m"] = linear_mass
        min_travel = hoist.get("min_hook_travel_m")
        max_travel = hoist.get("max_hook_travel_m")
        if min_travel is not None and max_travel is not None:
            authored_payload_hoists[hid]["hook_travel"] = {
                "min_m": float(min_travel),
                "max_m": float(max_travel),
            }

    unowned_rope_ids = sorted(set(ropes_by_id.keys()) - set(rope_owner_by_id.keys()))
    if unowned_rope_ids:
        raise ValueError(
            "Cannot export hoist-owned ropes: runtime ropes without hoist owner: "
            + ", ".join(unowned_rope_ids)
        )

    if len(solve_hoist_ids) != 1:
        raise ValueError(
            "Cannot export v5 authored form: expected exactly one solve-mode boom hoist, "
            f"found {len(solve_hoist_ids)} "
            f"({', '.join(solve_hoist_ids) if solve_hoist_ids else 'none'})"
        )
    if authored_boom_hoist is None:
        raise ValueError("Cannot export v5 authored form: boom hoist data could not be assembled")

    env = data.get("environment", {})
    vm = env.get("vessel_motion", {})
    metadata = data.get("metadata", {})

    component_sections = {
        "boom": {
            **body_loads["boom"],
            "nodes": nodes_by_body_authored["boom"],
        },
        "rear_leg": {
            **body_loads["rear_leg"],
            "nodes": nodes_by_body_authored["rear_leg"],
        },
        "front_leg": {
            **body_loads["front_leg"],
            "nodes": nodes_by_body_authored["front_leg"],
        },
        "platform": {
            **body_loads["platform"],
            "nodes": nodes_by_body_authored["platform"],
        },
    }

    def _primary_xy(node_id: str) -> dict[str, float]:
        node = nodes_by_id.get(node_id) or PRIMARY_NODE_DEFAULTS.get(node_id, {})
        return {"x_m": float(node.get("x_m", 0.0)), "z_m": float(node.get("z_m", 0.0))}

    primary_structure_out = {
        "boom_heel": _primary_xy("boom_heel"),
        "upper_hinge": _primary_xy("rear_top"),
        "rear_hinge": _primary_xy("rear_base"),
        "front_hinge": _primary_xy("front_base"),
    }

    authored_out = {
        "schema": {
            "name": AUTHORED_SCHEMA_NAME,
            "version": AUTHORED_SCHEMA_VERSION,
        },
        "metadata": {
            "name": metadata.get("name", "New Crane Model"),
        },
        "model_definition": {
            "environment": {
                "gravity_m_s2": abs(float(env.get("gravity_m_s2", -9.81))),
                "air_density_kg_m3": float(env.get("air_density_kg_m3", 1.225)),
                "wind_profile_exponent": float(env.get("wind_profile_exponent", 0.143)),
                "wind_reference_height_m_asl": float(env.get("wind_reference_height_m_asl", 10.0)),
                "mean_sealevel_z_m": float(env.get("mean_sealevel_z_m", -35.0)),
                "max_wind_speed_m_s": float(env.get("max_wind_speed_m_s", 20.0)),
            },
            "boom_width_m": float((data.get("support_widths") or {}).get("boom_width_m", 1.0)),
            "slewing_bearing_diameter_m": float(
                (data.get("support_widths") or {}).get("slewing_bearing_diameter_m", 1.0)
            ),
            **primary_structure_out,
            "vessel_motion": {
                "accel_x_m_s2": float(vm.get("accel_x_m_s2", 0.0)),
                "accel_y_m_s2": float(vm.get("accel_y_m_s2", 0.0)),
                "accel_z_m_s2": float(vm.get("accel_z_m_s2", 0.0)),
                "pitch_angular_accel_rad_s2": float(vm.get("pitch_angular_accel_rad_s2", 0.0)),
                "roll_angular_accel_rad_s2": float(vm.get("roll_angular_accel_rad_s2", 0.0)),
                "reference_x_m": float(vm.get("reference_x_m", 0.0)),
                "reference_z_m": float(vm.get("reference_z_m", 0.0)),
            },
            "boom": component_sections["boom"],
            "rear_leg": component_sections["rear_leg"],
            "front_leg": component_sections["front_leg"],
            "platform": component_sections["platform"],
            "boom_hoist": authored_boom_hoist,
            "payload_hoists": authored_payload_hoists,
        },
    }

    return authored_out
