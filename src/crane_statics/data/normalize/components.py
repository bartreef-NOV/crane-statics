"""Authored-form component and position helpers shared by the normalizers."""

from typing import Any, Optional

from ..models import PRIMARY_NODE_DEFAULTS, PRIMARY_STRUCTURE_TO_RUNTIME_NODE


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
