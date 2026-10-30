"""Convert an authored document into the normalized runtime dict shape."""

from typing import Any
from pydantic import ValidationError

from ..authored_models import (
    AuthoredDocument,
    BOOM_HOIST_ID,
    DEFAULT_AIR_DENSITY_KG_M3,
    DEFAULT_GRAVITY_M_S2,
    format_authored_validation_error,
    hoist_node_prefix,
)
from ..models import (
    CANONICAL_BODIES,
    DEFAULT_VESSEL_MOTION,
    MANAGED_HOOK_FALLBACK_DROP_M,
    RESERVED_TOPOLOGY_NODE_IDS,
    _is_managed_hook_node_id,
    _managed_hook_node_id,
)
from .components import (
    _build_body_loads_from_components,
    _extract_component_nodes_from_components,
    _extract_primary_structure_nodes,
    _position_to_runtime_fields,
    _require_object_keys,
    _synthesize_primary_nodes_into_nodes_map,
    _validate_compact_component_positions,
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
