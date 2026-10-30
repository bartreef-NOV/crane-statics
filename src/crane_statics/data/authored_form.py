"""Convert a runtime CraneDocument back to authored form for saving."""

from typing import Any, Optional

from .authored_models import (
    AUTHORED_SCHEMA_NAME,
    AUTHORED_SCHEMA_VERSION,
    BOOM_HOIST_ID,
    DEFAULT_AIR_DENSITY_KG_M3,
    DEFAULT_GRAVITY_M_S2,
    hoist_node_prefix,
)
from .models import (
    CANONICAL_BODIES,
    CraneDocument,
    DEFAULT_VESSEL_MOTION,
    PRIMARY_NODE_DEFAULTS,
    PRIMARY_NODE_IDS,
    _is_managed_hook_node_id,
)
from .normalize.components import _runtime_centroid_position, _runtime_mass_position


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
