"""Data contract models for Crane Statics.

This module defines all the Pydantic models that enforce strict validation
and normalization according to the handoff data contract.
"""

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from copy import deepcopy

from .authored_models import (
    AuthoredDocument,
    AUTHORED_SCHEMA_MAJOR_VERSION,
    AUTHORED_SCHEMA_NAME,
    AUTHORED_SCHEMA_VERSION,
    BOOM_HOIST_ID,
    DEFAULT_AIR_DENSITY_KG_M3,
    DEFAULT_GRAVITY_M_S2,
    authored_schema_major,
    format_authored_validation_error,
    hoist_node_prefix,
)

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
        and authored_schema_major(schema.get("version")) == AUTHORED_SCHEMA_MAJOR_VERSION
    )


def _expand_reeving(
    hoist_id: str, reeving: list[dict[str, Any]], ctx: str
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Expand an authored reeving path into owned runtime nodes and rope segments.

    Returns (nodes, segments, path) where nodes maps global node ID to a runtime
    node record, segments are chained from/to/parts dicts, and path lists the
    global node ID of each reeving entry in order."""
    prefix = hoist_node_prefix(hoist_id)
    owned = {e["node"] for e in reeving if e.get("body")}
    nodes: dict[str, dict[str, Any]] = {}
    path: list[str] = []
    segments: list[dict[str, Any]] = []
    for idx, entry in enumerate(reeving):
        name = str(entry["node"])
        global_id = f"{prefix}{name}" if name in owned else name
        if entry.get("body"):
            if entry["body"] == "boom":
                coords = {"u_m": float(entry["u_m"]), "w_m": float(entry["w_m"])}
            else:
                coords = {"x_m": float(entry["x_m"]), "z_m": float(entry["z_m"])}
            nodes[global_id] = {"body": entry["body"], **coords}
        if idx > 0:
            start = str(entry["from"]) if entry.get("from") else path[-1]
            if start in owned:
                start = f"{prefix}{start}"
            parts = int(entry.get("parts") or 1)
            segments.append(
                {"from": start, "to": global_id, **({"parts": parts} if parts != 1 else {})}
            )
        path.append(global_id)
    return nodes, segments, path


def _infer_solve_load_node_id(segments: list[dict[str, Any]], ctx: str) -> str:
    """Infer runtime load-node placeholder for solve hoists from final segment endpoint."""
    if not segments:
        raise ValueError(f"{ctx}.reeving must contain at least one segment")
    last = segments[-1]
    return str(last["to"])


def _convert_load_container(section: Any, body_id: str, section_ctx: str) -> dict[str, Any]:
    """Convert one authored body section into mass points, wind areas and nodes."""
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


def _expand_hoist_reeving_nodes(
    hoists: list[tuple[str, dict[str, Any]]], nodes_src: dict[str, Any]
) -> dict[str, tuple[list[dict[str, Any]], list[str]]]:
    """Expand each hoist's reeving, adding its owned nodes to nodes_src.

    Returns hoist key -> (segments, path)."""
    expanded: dict[str, tuple[list[dict[str, Any]], list[str]]] = {}
    for hoist_key, hoist_src in hoists:
        ctx = f"model_definition.hoists[{hoist_key}]"
        hoist_nodes, hoist_segments, hoist_path = _expand_reeving(
            str(hoist_key), hoist_src["reeving"], f"{ctx}.reeving"
        )
        for node_id, node_rec in hoist_nodes.items():
            if node_id in nodes_src or node_id in RESERVED_TOPOLOGY_NODE_IDS:
                raise ValueError(
                    f"{ctx}.reeving node {node_id!r} collides with an existing node id"
                )
            nodes_src[node_id] = node_rec
        expanded[str(hoist_key)] = (hoist_segments, hoist_path)
    return expanded


def _infer_node_bodies(nodes_src: dict[str, Any]) -> dict[str, Any]:
    """Copy nodes, defaulting boom-local (u_m/w_m) nodes to the boom body."""
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
    return nodes_with_inferred_body


def _resolve_support_node_id(hoist: dict[str, Any], hoist_key: str, hoist_path: list[str]) -> str:
    support_name = hoist.get("support_node")
    if support_name is None:
        return hoist_path[-1]
    hoist_prefix = hoist_node_prefix(hoist_key)
    candidates = {f"{hoist_prefix}{support_name}", str(support_name)}
    matches = [n for n in hoist_path if n in candidates]
    if not matches:
        raise ValueError(
            f"model_definition.hoists[{hoist_key}].support_node "
            f"{support_name!r} is not a node on the reeving path"
        )
    return matches[0]


def _normalize_payload_hoist(
    hoist_key: str,
    hoist: dict[str, Any],
    hoist_segments: list[dict[str, Any]],
    hoist_path: list[str],
    nodes_with_primary: dict[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Normalize one payload hoist into (runtime rope id, rope, hoist) records.

    Registers the hoist's managed hook node in nodes_with_primary."""
    support_node_id = _resolve_support_node_id(hoist, hoist_key, hoist_path)
    split_mode_obj = hoist.get("split")
    normal_falls = int(hoist["falls"])
    # falls >= 1, split falls <= falls, and split hook mass <= hook mass are
    # enforced by AuthoredPayloadHoist's validators above; only derive here.
    split_falls = normal_falls
    if split_mode_obj is not None:
        split_falls = int(split_mode_obj["falls"])

    managed_hook_node_id = _managed_hook_node_id(hoist_key)
    if managed_hook_node_id in nodes_with_primary and not _is_managed_hook_node_id(
        managed_hook_node_id
    ):
        raise ValueError(
            f"model_definition.hoists[{hoist_key}] conflicts with reserved "
            f"managed hook node id {managed_hook_node_id!r}"
        )

    support_node = nodes_with_primary[support_node_id]
    if not isinstance(support_node, dict):
        raise ValueError(
            f"model_definition.hoists[{hoist_key}].support_node references "
            f"invalid node record {support_node_id!r}"
        )
    support_body = str(support_node.get("body") or "boom")
    nodes_with_primary[managed_hook_node_id] = {
        "body": support_body,
        "hang_from_node_id": support_node_id,
        "drop_m": MANAGED_HOOK_FALLBACK_DROP_M,
    }

    segs = [
        *hoist_segments,
        {
            "from": support_node_id,
            "to": managed_hook_node_id,
            "parts": normal_falls,
        },
    ]

    rope_src = hoist["rope"]
    runtime_rope_id = _runtime_rope_id_for_hoist(hoist_key)
    rope_norm = {
        "tension_mode": "fixed",
        "segments": segs,
        "linear_mass_kg_m": float(rope_src["linear_mass_kg_m"]),
    }

    normal_curve = _normalize_contractual_curve_points(
        hoist["load_chart"],
        f"model_definition.hoists[{hoist_key}].load_chart",
    )

    split_curve: list[dict[str, Any]] = []
    if split_mode_obj is not None:
        split_curve = _normalize_contractual_curve_points(
            split_mode_obj["load_chart"],
            f"model_definition.hoists[{hoist_key}].split.load_chart",
        )

    normal_min_outreach, normal_max_outreach = _hoist_curve_outreach_bounds(normal_curve)
    split_min_outreach = normal_min_outreach
    split_max_outreach = normal_max_outreach
    if split_curve:
        split_min_outreach, split_max_outreach = _hoist_curve_outreach_bounds(split_curve)
    min_outreach = min(normal_min_outreach, split_min_outreach)
    max_outreach = max(normal_max_outreach, split_max_outreach)

    hoist_norm = {
        "rope_id": runtime_rope_id,
        "load_node_id": managed_hook_node_id,
        "support_node_id": support_node_id,
        "falls": normal_falls,
        "splitable_block": split_mode_obj is not None,
        "split_falls": split_falls,
        "split_hook_mass_t": float(
            split_mode_obj["hook_mass_t"] if split_mode_obj is not None else hoist["hook_mass_t"]
        ),
        "hook": {
            "mass_t": float(hoist["hook_mass_t"]),
            "daf": float(hoist["daf"]),
            "offlead_deg_limit": float(hoist["offlead_deg"]),
            "sidelead_deg_limit": float(hoist["sidelead_deg"]),
        },
        "operating_envelope": {
            "outreach_min_m": float(min_outreach),
            "outreach_max_m": float(max_outreach),
        },
        "contractual_curve": normal_curve,
        "split_contractual_points": split_curve,
        "linear_mass_kg_m": float(rope_src["linear_mass_kg_m"]),
        # Unauthored lowest hook height defaults to the crane-frame origin (z = 0).
        "lowest_hook_height_m": (
            float(hoist["lowest_hook_height_m"])
            if hoist.get("lowest_hook_height_m") is not None
            else 0.0
        ),
    }
    return runtime_rope_id, rope_norm, hoist_norm


def _normalize_boom_hoist(
    boom_hoist_src: dict[str, Any], boom_segments: list[dict[str, Any]]
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Normalize the boom (solve-mode) hoist into (runtime rope id, rope, hoist) records."""
    runtime_rope_id = _runtime_rope_id_for_hoist(BOOM_HOIST_ID)
    rope_src = boom_hoist_src["rope"]
    rope_norm = {
        "tension_mode": "solve",
        "segments": boom_segments,
        "linear_mass_kg_m": float(rope_src["linear_mass_kg_m"]),
    }
    hoist_norm = {
        "rope_id": runtime_rope_id,
        "load_node_id": _infer_solve_load_node_id(
            boom_segments, f"model_definition.hoists[{BOOM_HOIST_ID}]"
        ),
        "linear_mass_kg_m": float(rope_src["linear_mass_kg_m"]),
        "hook": {
            "mass_t": 0.0,
            "daf": 1.0,
            "offlead_deg_limit": 0.0,
            "sidelead_deg_limit": 0.0,
        },
        "operating_envelope": {
            "outreach_min_m": 0.0,
            "outreach_max_m": 200.0,
        },
        "contractual_curve": [],
        "rope_length_m": (
            float(rope_src["length_m"]) if rope_src.get("length_m") is not None else None
        ),
    }
    return runtime_rope_id, rope_norm, hoist_norm


def _runtime_bodies(body_loads: dict[str, Any]) -> list[dict[str, Any]]:
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
    return bodies


def _runtime_node_position(node_id: str, node: dict[str, Any]) -> dict[str, Any]:
    """Resolve a node's runtime position fields from its authored coordinates."""
    if "position" in node:
        if not isinstance(node.get("position"), dict):
            raise ValueError(f"node[{node_id}].position must be an object")
        return _position_to_runtime_fields(node["position"], f"node[{node_id}]", allow_hanging=True)
    if _is_managed_hook_node_id(str(node_id)) and node.get("hang_from_node_id") is not None:
        if any(k in node for k in ("x_m", "z_m", "u_m", "w_m")):
            raise ValueError(f"node[{node_id}] hanging nodes cannot also define x_m/z_m/u_m/w_m")
        drop_m_raw = node.get("drop_m")
        drop_m = float(drop_m_raw) if drop_m_raw is not None else None
        if drop_m is not None and drop_m < 0.0:
            raise ValueError(f"node[{node_id}].drop_m must be >= 0")
        return {
            "x_m": 0.0,
            "z_m": 0.0,
            "below_node_id": str(node["hang_from_node_id"]),
            "hanging_drop_m": drop_m,
        }
    if node["body"] == "boom" and ("u_m" in node or "w_m" in node):
        if "u_m" not in node or "w_m" not in node:
            raise ValueError(f"node[{node_id}] boom-local nodes require both u_m and w_m")
        if "x_m" in node or "z_m" in node:
            raise ValueError(f"node[{node_id}] cannot define both local and global coordinates")
        return {
            "x_m": 0.0,
            "z_m": 0.0,
            "local_x_m": float(node["u_m"]),
            "local_z_m": float(node["w_m"]),
        }
    if "x_m" not in node or "z_m" not in node:
        raise ValueError(
            f"node[{node_id}] global nodes require x_m and z_m, "
            "or provide local u_m/w_m for boom nodes"
        )
    if "u_m" in node or "w_m" in node:
        raise ValueError(f"node[{node_id}] cannot define both local and global coordinates")
    return {
        "x_m": float(node["x_m"]),
        "z_m": float(node["z_m"]),
    }


def _runtime_nodes(nodes_with_primary: dict[str, Any]) -> list[dict[str, Any]]:
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
        nodes.append(
            {
                "id": str(node_id),
                "body": str(node["body"]),
                **_runtime_node_position(node_id, node),
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
    return nodes


def _runtime_ropes(ropes_norm: dict[str, Any], node_ids: set[str]) -> list[dict[str, Any]]:
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
    return ropes


def _runtime_curve_points(points: list[Any], ctx: str) -> list[dict[str, Any]]:
    """Validate and convert contractual curve points; ctx names the list in errors."""
    out: list[dict[str, Any]] = []
    for idx, cp in enumerate(points):
        if not isinstance(cp, dict):
            raise ValueError(f"{ctx}[{idx}] must be an object")
        _require_object_keys(cp, {"outreach_m", "load_t"}, {"label"}, f"{ctx}[{idx}]")
        cp_runtime: dict[str, float | str] = {
            "outreach_m": float(cp["outreach_m"]),
            "load_t": float(cp["load_t"]),
        }
        if "label" in cp:
            cp_runtime["label"] = str(cp["label"])
        out.append(cp_runtime)
    return out


def _runtime_hoists(
    hoists_norm: dict[str, Any], rope_ids: set[str], node_ids: set[str]
) -> list[dict[str, Any]]:
    hoists: list[dict[str, Any]] = []
    for hoist_id, hoist in hoists_norm.items():
        if not isinstance(hoist, dict):
            raise ValueError(f"hoist {hoist_id} must be an object")
        _require_object_keys(
            hoist,
            {
                "rope_id",
                "load_node_id",
                "hook",
                "operating_envelope",
                "contractual_curve",
            },
            {
                "support_node_id",
                "falls",
                "splitable_block",
                "split_falls",
                "split_hook_mass_t",
                "split_contractual_points",
                "linear_mass_kg_m",
                "lowest_hook_height_m",
                "rope_length_m",
            },
            f"hoist[{hoist_id}]",
        )
        hook = hoist["hook"]
        envl = hoist["operating_envelope"]
        curve = hoist["contractual_curve"]
        if not isinstance(hook, dict) or not isinstance(envl, dict) or not isinstance(curve, list):
            raise ValueError(f"hoist[{hoist_id}] hook/envelope/curve have invalid types")
        _require_object_keys(
            hook,
            {"mass_t", "daf", "offlead_deg_limit"},
            {"sidelead_deg_limit"},
            f"hoist[{hoist_id}].hook",
        )
        _require_object_keys(
            envl,
            {"outreach_min_m", "outreach_max_m"},
            set(),
            f"hoist[{hoist_id}].operating_envelope",
        )
        rope_id = str(hoist["rope_id"])
        load_node_id = str(hoist["load_node_id"])
        if rope_id not in rope_ids:
            raise ValueError(f"hoist[{hoist_id}].rope_id references unknown rope {rope_id!r}")
        if load_node_id not in node_ids:
            raise ValueError(
                f"hoist[{hoist_id}].load_node_id references unknown node {load_node_id!r}"
            )
        cps = _runtime_curve_points(curve, f"hoist[{hoist_id}].contractual_curve")
        split_curve = hoist.get("split_contractual_points") or []
        if not isinstance(split_curve, list):
            raise ValueError(f"hoist[{hoist_id}].split_contractual_points must be an array")
        split_cps = _runtime_curve_points(
            split_curve, f"hoist[{hoist_id}].split_contractual_points"
        )
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
                "sidelead_deg": float(
                    hook[
                        (
                            "sidelead_deg_limit"
                            if "sidelead_deg_limit" in hook
                            else "offlead_deg_limit"
                        )
                    ]
                ),
                "outreach_min_m": float(envl["outreach_min_m"]),
                "outreach_max_m": float(envl["outreach_max_m"]),
                "contractual_points": cps,
                "linear_mass_kg_m": float(hoist.get("linear_mass_kg_m", 0.0)),
                "lowest_hook_height_m": (
                    float(hoist["lowest_hook_height_m"])
                    if hoist.get("lowest_hook_height_m") is not None
                    else None
                ),
                "rope_length_m": (
                    float(hoist["rope_length_m"])
                    if hoist.get("rope_length_m") is not None
                    else None
                ),
            }
        )
    return hoists


def _runtime_environment(
    environment_src: dict[str, Any], vessel_motion_src: dict[str, Any]
) -> dict[str, Any]:
    return {
        "gravity_m_s2": -abs(float(environment_src.get("gravity_m_s2", DEFAULT_GRAVITY_M_S2))),
        "max_wind_speed_m_s": abs(float(environment_src["max_wind_speed_m_s"])),
        "air_density_kg_m3": float(
            environment_src.get("air_density_kg_m3", DEFAULT_AIR_DENSITY_KG_M3)
        ),
        "vessel_motion": {
            key: float(vessel_motion_src.get(key, default))
            for key, default in DEFAULT_VESSEL_MOTION.items()
        },
    }


def _normalize_authored_document(doc_data: dict[str, Any]) -> dict[str, Any]:
    """Convert authored YAML into the normalized runtime document shape."""
    # Structural key presence/unknown-key checks and cross-field business rules
    # (e.g. split.falls <= falls) are owned by AuthoredDocument; this function
    # focuses on cross-reference rules that span the whole document (node ids,
    # topology synthesis) which aren't expressible as per-object validation.
    try:
        validated = AuthoredDocument.model_validate(doc_data)
    except ValidationError as e:
        raise ValueError(format_authored_validation_error(e)) from e
    doc_data = validated.model_dump(mode="json", by_alias=True)

    md = doc_data["model_definition"]

    topology = md.get("topology")
    if topology is None:
        topology = "fixed_topology_crane_2d"
    if topology != "fixed_topology_crane_2d":
        raise ValueError("model_definition.topology must be fixed_topology_crane_2d")

    structure = md["structure"]
    primary_out = {
        "boom_heel": dict(structure["boom_heel"]),
        "upper_hinge": dict(structure["upper_hinge"]),
        "rear_hinge": dict(structure["rear_hinge"]),
        "front_hinge": dict(structure["front_hinge"]),
    }

    components = {
        body_id: _convert_load_container(md.get(body_id), body_id, f"model_definition.{body_id}")
        for body_id in CANONICAL_BODIES
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

    boom_id = BOOM_HOIST_ID
    hoists_src = md.get("hoists")
    if not isinstance(hoists_src, dict):
        raise ValueError("model_definition.hoists must be an object")
    boom_hoist_src = hoists_src.get(boom_id)
    if not isinstance(boom_hoist_src, dict):
        raise ValueError(f"model_definition.hoists[{boom_id}] must be an object")
    payload_hoists_src = {k: v for k, v in hoists_src.items() if k != boom_id}
    if not payload_hoists_src:
        raise ValueError("model_definition.hoists must contain at least one payload hoist")

    expanded = _expand_hoist_reeving_nodes(
        [(boom_id, boom_hoist_src), *payload_hoists_src.items()], nodes_src
    )

    nodes_with_inferred_body = _infer_node_bodies(nodes_src)
    nodes_with_inferred_body.update(primary_nodes)
    nodes_with_primary = _synthesize_primary_nodes_into_nodes_map(nodes_with_inferred_body)

    for hoist_key, (_, hoist_path) in expanded.items():
        for node_id in hoist_path:
            if node_id not in nodes_with_primary:
                raise ValueError(f"hoist {hoist_key!r} reeving references unknown node {node_id!r}")

    metadata_src = doc_data.get("metadata")
    if not isinstance(metadata_src, dict):
        raise ValueError("metadata must be an object")

    ropes_norm: dict[str, Any] = {}
    hoists_norm: dict[str, Any] = {}

    for hoist_id, hoist in payload_hoists_src.items():
        hoist_key = str(hoist_id)
        if not isinstance(hoist, dict):
            raise ValueError(f"model_definition.hoists[{hoist_key}] must be an object")
        hoist_segments, hoist_path = expanded[hoist_key]
        rope_id, rope_norm, hoist_norm = _normalize_payload_hoist(
            hoist_key, hoist, hoist_segments, hoist_path, nodes_with_primary
        )
        ropes_norm[rope_id] = rope_norm
        hoists_norm[hoist_key] = hoist_norm

    boom_rope_id, boom_rope_norm, boom_hoist_norm = _normalize_boom_hoist(
        boom_hoist_src, expanded[boom_id][0]
    )
    ropes_norm[boom_rope_id] = boom_rope_norm
    hoists_norm[boom_id] = boom_hoist_norm

    environment_src = md.get("environment")
    if not isinstance(environment_src, dict):
        raise ValueError("model_definition.environment must be an object")
    vessel_motion_src = md.get("vessel_motion", {})
    if not isinstance(vessel_motion_src, dict):
        raise ValueError("model_definition.vessel_motion must be an object")

    boom_width_m = float(structure["boom_width_m"])
    slewing_bearing_diameter_m = (
        float(structure["slewing_bearing_diameter_m"])
        if structure.get("slewing_bearing_diameter_m") is not None
        else None
    )

    bodies = _runtime_bodies(body_loads)
    node_ids = set(nodes_with_primary.keys())
    nodes = _runtime_nodes(nodes_with_primary)
    ropes = _runtime_ropes(ropes_norm, node_ids)
    hoists = _runtime_hoists(hoists_norm, set(ropes_norm.keys()), node_ids)

    return {
        "schema_version": "1.0.0",
        "model_type": "fixed_topology_crane_2d",
        "metadata": {
            "name": str(metadata_src["name"]),
        },
        "environment": _runtime_environment(environment_src, vessel_motion_src),
        "support_widths": {
            "boom_width_m": boom_width_m,
            "slewing_bearing_diameter_m": slewing_bearing_diameter_m,
        },
        "saved_limits": {
            str(limit_id): {
                "capacity_kN": float(limit["capacity_kN"]),
                "enabled": bool(limit.get("enabled", True)),
            }
            for limit_id, limit in (md.get("limits") or {}).items()
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
    """Ensure internal canonical primary topology is present even when the document omits it."""
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
        doc_data: Raw parsed data from file

    Returns:
        Normalized CraneDocument ready for analysis
    """
    doc_data = deepcopy(doc_data)

    if "schema" in doc_data:
        if _is_authored_document(doc_data):
            doc_data = _normalize_authored_document(doc_data)
        else:
            schema_obj = doc_data.get("schema")
            schema = schema_obj if isinstance(schema_obj, dict) else {}
            found_name = schema.get("name")
            found_version = schema.get("version")
            raise ValueError(
                f"Only crane-statics schema major version {AUTHORED_SCHEMA_MAJOR_VERSION} is "
                f"supported for authored input; found name={found_name!r}, "
                f"version={found_version!r}"
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

    derive_payload_hoist_rope_geometry(doc)

    return doc


def derive_payload_hoist_rope_geometry(doc: CraneDocument) -> None:
    """Fill each payload hoist's ``max_hook_travel_m`` and ``rope_length_m`` in place.

    Both are consequences of the hoist's ``lowest_hook_height_m``, so they are
    derived here rather than authored: a normalized document always carries them,
    whether it arrived through the authored reader or straight from a dict.

    ``calculation`` is imported lazily on purpose -- ``calculation.engine``
    imports this module, so a module-level import would close the cycle.
    """
    from ..calculation.rope_mass import derive_hook_geometry

    payload_ids = set(payload_hoist_ids(doc))
    if not payload_ids:
        return
    doc_dict = doc.model_dump()
    for hoist in doc.hoists:
        if hoist.id not in payload_ids:
            continue
        if hoist.lowest_hook_height_m is None:
            hoist.lowest_hook_height_m = 0.0
        derived = derive_hook_geometry(doc_dict, hoist.id, float(hoist.lowest_hook_height_m))
        if derived is None:
            continue
        hoist.max_hook_travel_m, hoist.rope_length_m = derived


def generate_canonical_connections() -> list[dict[str, Any]]:
    """Generate the canonical fixed-topology connections."""
    return [
        {"id": "platform_base", "type": "ground_fixed"},
        {"id": "rear_hinge", "type": "body_pin"},
        {"id": "front_hinge", "type": "body_pin"},
        {"id": "upper_hinge", "type": "body_pin"},
        {"id": "heel_point", "type": "body_pin"},
    ]


def _authored_node_coords(node: dict[str, Any]) -> dict[str, float]:
    """Authored coordinates for a runtime node: boom nodes use u/w, the rest use x/z."""
    if node.get("body") == "boom" and node.get("local_x_m") is not None:
        return {
            "u_m": float(node.get("local_x_m", 0.0)),
            "w_m": float(node.get("local_z_m", 0.0)),
        }
    return {"x_m": float(node.get("x_m", 0.0)), "z_m": float(node.get("z_m", 0.0))}


def _authored_reeving(
    hoist_id: str,
    segments: list[dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
    owned_ids: set[str],
) -> list[dict[str, Any]]:
    """Convert ordered runtime rope segments into an authored reeving path.

    Nodes in owned_ids are written inline (name without the hoist prefix, with body and
    coordinates on first appearance); any other node is written by its global ID."""
    prefix = hoist_node_prefix(hoist_id)

    def _name(node_id: str) -> str:
        return node_id[len(prefix) :] if node_id in owned_ids else node_id

    reeving: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _entry(node_id: str) -> dict[str, Any]:
        entry: dict[str, Any] = {"node": _name(node_id)}
        if node_id in owned_ids and node_id not in seen:
            node = nodes_by_id[node_id]
            entry["body"] = str(node.get("body"))
            entry.update(_authored_node_coords(node))
        seen.add(node_id)
        return entry

    previous: Optional[str] = None
    for seg in segments:
        start, end = str(seg["from"]), str(seg["to"])
        if previous is None:
            reeving.append(_entry(start))
        entry = _entry(end)
        if start != (previous if previous is not None else start):
            entry["from"] = _name(start)
        parts = int(seg.get("parts", 1))
        if parts != 1:
            entry["parts"] = parts
        reeving.append(entry)
        previous = end
    return reeving


def document_to_authored_form(doc: CraneDocument) -> dict[str, Any]:
    """
    Convert a normalized runtime document back to authored form for saving.

    This removes:
    - Derived nodes
    - Canonical connections
    - Managed hook nodes and hook spans

    and folds each hoist's exclusive sheave/winch nodes into its own reeving path.
    """
    data = doc.model_dump(exclude={"connections"})

    derived_node_ids = {"front_top", "platform_rear", "platform_front", "platform_heel"}
    data["nodes"] = [n for n in data["nodes"] if n.get("id") not in derived_node_ids]

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

    # Pair every hoist with its rope, dropping the managed hook span of payload hoists.
    hoist_segments: dict[str, list[dict[str, Any]]] = {}
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
        load_node_id = str(hoist.get("load_node_id") or "")
        hoist_segments[hid] = [
            seg
            for seg in ropes_by_id[rope_id]["segments"]
            if not (
                _is_managed_hook_node_id(load_node_id)
                and load_node_id in {str(seg.get("from")), str(seg.get("to"))}
            )
        ]

    unowned_rope_ids = sorted(set(ropes_by_id.keys()) - set(rope_owner_by_id.keys()))
    if unowned_rope_ids:
        raise ValueError(
            "Cannot export hoist-owned ropes: runtime ropes without hoist owner: "
            + ", ".join(unowned_rope_ids)
        )
    if len(solve_hoist_ids) != 1:
        raise ValueError(
            "Cannot export authored form: expected exactly one solve-mode boom hoist, "
            f"found {len(solve_hoist_ids)} "
            f"({', '.join(solve_hoist_ids) if solve_hoist_ids else 'none'})"
        )

    # A node is owned by a hoist when it carries the hoist's prefix, sits on a fixed body
    # and no other hoist's rope touches it. Owned nodes are written inline in that hoist.
    users: dict[str, set[str]] = {}
    for hid, segs in hoist_segments.items():
        for seg in segs:
            for end in (str(seg["from"]), str(seg["to"])):
                users.setdefault(end, set()).add(hid)
    owned_by_hoist: dict[str, set[str]] = {}
    for hid, segs in hoist_segments.items():
        prefix = hoist_node_prefix(hid)
        path_ids = {str(seg[k]) for seg in segs for k in ("from", "to")}
        owned = {
            node_id
            for node_id in path_ids
            if node_id.startswith(prefix)
            and len(node_id) > len(prefix)
            and node_id not in PRIMARY_NODE_IDS
            and not _is_managed_hook_node_id(node_id)
            and users.get(node_id) == {hid}
            and node_id in nodes_by_id
            and not nodes_by_id[node_id].get("below_node_id")
            and nodes_by_id[node_id].get("body") in CANONICAL_BODIES
        }
        # A shared node written by its global ID must not shadow an owned local name.
        shared = path_ids - owned
        owned = {n for n in owned if n[len(prefix) :] not in shared}
        owned_by_hoist[hid] = owned
    all_owned = set().union(*owned_by_hoist.values()) if owned_by_hoist else set()

    nodes_by_body_authored: dict[str, dict[str, Any]] = {
        body_id: {} for body_id in CANONICAL_BODIES
    }
    for node in data.get("nodes", []):
        node_id = str(node.get("id"))
        if (
            node_id in derived_node_ids
            or node_id in PRIMARY_NODE_IDS
            or node_id in all_owned
            or _is_managed_hook_node_id(node_id)
        ):
            continue
        if node.get("below_node_id"):
            raise ValueError(
                f"Cannot export arbitrary hanging node {node_id!r}; use a payload hoist "
                "support node"
            )
        body_id = str(node.get("body") or "")
        if body_id not in nodes_by_body_authored:
            continue
        nodes_by_body_authored[body_id][node_id] = _authored_node_coords(node)

    authored_payload_hoists: dict[str, dict[str, Any]] = {}
    authored_boom_hoist: dict[str, Any] = {}
    for hoist in data.get("hoists", []):
        hid = str(hoist.get("id"))
        rope = ropes_by_id[str(hoist["rope_id"])]
        reeving = _authored_reeving(hid, hoist_segments[hid], nodes_by_id, owned_by_hoist[hid])

        if rope.get("tension_mode") == "solve":
            rope_out: dict[str, Any] = {}
            linear_mass = float(rope.get("linear_mass_kg_m", 0.0))
            if linear_mass > 0.0:
                rope_out["linear_mass_kg_m"] = linear_mass
            if hoist.get("rope_length_m") is not None:
                rope_out["length_m"] = float(hoist["rope_length_m"])
            authored_boom_hoist = {
                **({"rope": rope_out} if rope_out else {}),
                "reeving": reeving,
            }
            continue

        hook_mass = float(hoist.get("hook_mass_t", 0.0))
        hook_offlead = float(hoist.get("offlead_deg", 0.0))
        hook_sidelead = float(hoist.get("sidelead_deg", hook_offlead))
        load_node_id = str(hoist.get("load_node_id") or "")
        support_node_id = str(hoist.get("support_node_id") or "")
        if not support_node_id and load_node_id:
            load_node = nodes_by_id.get(load_node_id, {})
            if isinstance(load_node, dict):
                support_node_id = str(load_node.get("below_node_id") or "")
        if not support_node_id:
            support_node_id = load_node_id

        falls = hoist.get("falls")
        if falls is None:
            falls = _infer_falls_from_segments(rope["segments"], support_node_id, load_node_id)

        def _chart(points: list[dict[str, Any]]) -> list[dict[str, float]]:
            return [
                {
                    "outreach_m": float(cp.get("outreach_m", 0.0)),
                    "load_t": float(cp.get("load_t", 0.0)),
                }
                for cp in points
            ]

        hoist_out: dict[str, Any] = {}

        rope_out = {}
        linear_mass = float(rope.get("linear_mass_kg_m", 0.0))
        if linear_mass > 0.0:
            rope_out["linear_mass_kg_m"] = linear_mass
        # rope_length_m and hook_travel are derived from lowest_hook_height_m,
        # so they are deliberately not written back out.
        if rope_out:
            hoist_out["rope"] = rope_out
        hoist_out["reeving"] = reeving
        last = reeving[-1]["node"] if reeving else ""
        support_name = (
            support_node_id[len(hoist_node_prefix(hid)) :]
            if support_node_id in owned_by_hoist[hid]
            else support_node_id
        )
        if support_name != last:
            hoist_out["support_node"] = support_name
        hoist_out["hook_mass_t"] = hook_mass
        hoist_out["falls"] = int(falls)
        hoist_out["daf"] = float(hoist.get("hook_daf", 1.0))
        hoist_out["offlead_deg"] = hook_offlead
        if hook_sidelead:
            hoist_out["sidelead_deg"] = hook_sidelead
        hoist_out["lowest_hook_height_m"] = float(hoist.get("lowest_hook_height_m") or 0.0)
        hoist_out["load_chart"] = _chart(hoist.get("contractual_points", []))
        if bool(hoist.get("splitable_block", False)):
            split_falls = hoist.get("split_falls")
            split_mass = hoist.get("split_hook_mass_t")
            hoist_out["split"] = {
                "hook_mass_t": float(hook_mass if split_mass is None else split_mass),
                "falls": int(falls if split_falls is None else split_falls),
                "load_chart": _chart(hoist.get("split_contractual_points", [])),
            }
        authored_payload_hoists[hid] = hoist_out

    if not authored_boom_hoist:
        raise ValueError("Cannot export authored form: boom hoist data could not be assembled")

    env = data.get("environment", {})
    vm = env.get("vessel_motion", {})
    metadata = data.get("metadata", {})

    def _primary_xy(node_id: str) -> dict[str, float]:
        node = nodes_by_id.get(node_id) or PRIMARY_NODE_DEFAULTS.get(node_id, {})
        return {"x_m": float(node.get("x_m", 0.0)), "z_m": float(node.get("z_m", 0.0))}

    widths = data.get("support_widths") or {}
    structure_out: dict[str, Any] = {"boom_width_m": float(widths.get("boom_width_m", 1.0))}
    if widths.get("slewing_bearing_diameter_m") is not None:
        structure_out["slewing_bearing_diameter_m"] = float(widths["slewing_bearing_diameter_m"])
    structure_out.update(
        {
            "boom_heel": _primary_xy("boom_heel"),
            "upper_hinge": _primary_xy("rear_top"),
            "rear_hinge": _primary_xy("rear_base"),
            "front_hinge": _primary_xy("front_base"),
        }
    )

    model_definition: dict[str, Any] = {
        "environment": {
            "gravity_m_s2": abs(float(env.get("gravity_m_s2", -DEFAULT_GRAVITY_M_S2))),
            "air_density_kg_m3": float(env.get("air_density_kg_m3", DEFAULT_AIR_DENSITY_KG_M3)),
            "max_wind_speed_m_s": float(env.get("max_wind_speed_m_s", 20.0)),
        },
    }
    vessel_motion_out = {key: float(vm.get(key, 0.0)) for key in DEFAULT_VESSEL_MOTION}
    if any(vessel_motion_out.values()):
        model_definition["vessel_motion"] = vessel_motion_out
    model_definition["structure"] = structure_out
    for body_id in CANONICAL_BODIES:
        section = {
            **body_loads[body_id],
            "nodes": nodes_by_body_authored[body_id],
        }
        section = {key: value for key, value in section.items() if value}
        if section:
            model_definition[body_id] = section
    model_definition["hoists"] = {BOOM_HOIST_ID: authored_boom_hoist, **authored_payload_hoists}
    saved_limits = data.get("saved_limits") or {}
    if saved_limits:
        model_definition["limits"] = {
            str(limit_id): {
                "capacity_kN": float(limit["capacity_kN"]),
                "enabled": bool(limit.get("enabled", True)),
            }
            for limit_id, limit in saved_limits.items()
        }

    return {
        "schema": {
            "name": AUTHORED_SCHEMA_NAME,
            "version": AUTHORED_SCHEMA_VERSION,
        },
        "metadata": {
            "name": metadata.get("name", "New Crane Model"),
        },
        "model_definition": model_definition,
    }
