"""Static solver context: body, hoist, rope and load-entry tables built once per document."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def build_solver_static_context(doc_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Build metadata reused across many statics solves.

    Accepts a CraneDocument.model_dump() compatible dict.
    Field names use the rewrite convention: x_m, z_m, local_x_m, local_z_m,
    area_w_m2, area_v_m2, cd, from_node_id, to_node_id.
    """
    body_ids = [str(b["id"]) for b in doc_dict.get("bodies", []) if b.get("id")]
    body_index = {bid: i for i, bid in enumerate(body_ids)}
    hoists = [h for h in doc_dict.get("hoists", []) if h.get("id")]
    hoist_by_id = {str(h["id"]): h for h in hoists}
    rope_to_hoist = {str(h["rope_id"]): h for h in hoists if h.get("rope_id")}
    hook_node_ids = [str(h["load_node_id"]) for h in hoists if h.get("load_node_id")]

    ropes_meta: List[Dict[str, Any]] = []
    parts_count_map: Dict[Tuple[str, str], int] = {}
    for rope in doc_dict.get("ropes", []):
        rope_id = str(rope.get("id", ""))
        # Segments use from_node_id / to_node_id in the rewrite
        segs = [
            (str(s["from_node_id"]), str(s["to_node_id"]), float(s.get("mult", 1)))
            for s in rope.get("segments", [])
            if s.get("from_node_id") and s.get("to_node_id")
        ]
        n_parts_by_hook: Dict[str, int] = {}
        for hook_id in hook_node_ids:
            n = max(1, int(sum(m for f, t, m in segs if hook_id in (f, t))))
            n_parts_by_hook[hook_id] = n
            parts_count_map[(rope_id, hook_id)] = n
        ropes_meta.append(
            {
                "id": rope_id,
                "is_solve": rope.get("tension_mode") == "solve",
                "segments": segs,
                "n_parts_by_hook": n_parts_by_hook,
            }
        )

    mass_entries_global: List[Tuple[int, float, float, float]] = []
    mass_entries_local: List[Tuple[int, float, float, float]] = []
    wind_entries_global: List[Tuple[int, float, float, float, float, float]] = []
    wind_entries_local: List[Tuple[int, float, float, float, float, float]] = []

    for body in doc_dict.get("bodies", []):
        bid = str(body.get("id", ""))
        if bid not in body_index:
            continue
        bidx = body_index[bid]

        for mp in body.get("mass_points", []):
            mass_t = float(mp.get("mass_t", 0.0))
            if mp.get("local_x_m") is not None:
                # boom-local coordinates
                mass_entries_local.append(
                    (bidx, mass_t, float(mp["local_x_m"]), float(mp.get("local_z_m") or 0.0))
                )
            else:
                # global coordinates
                mass_entries_global.append(
                    (bidx, mass_t, float(mp.get("x_m", 0.0)), float(mp.get("z_m", 0.0)))
                )

        for wa in body.get("wind_areas", []):
            area_w = float(wa.get("area_w_m2", 0.0))
            area_v = float(wa.get("area_v_m2", 0.0))
            cd = float(wa.get("cd", 1.2))
            if wa.get("local_x_m") is not None:
                wind_entries_local.append(
                    (
                        bidx,
                        area_w,
                        area_v,
                        cd,
                        float(wa["local_x_m"]),
                        float(wa.get("local_z_m") or 0.0),
                    )
                )
            else:
                wind_entries_global.append(
                    (bidx, area_w, area_v, cd, float(wa.get("x_m", 0.0)), float(wa.get("z_m", 0.0)))
                )

    return {
        "body_ids": body_ids,
        "body_index": body_index,
        "hoists": hoists,
        "hoist_by_id": hoist_by_id,
        "rope_to_hoist": rope_to_hoist,
        "ropes_meta": ropes_meta,
        "parts_count_map": parts_count_map,
        "mass_entries_global": mass_entries_global,
        "mass_entries_local": mass_entries_local,
        "wind_entries_global": wind_entries_global,
        "wind_entries_local": wind_entries_local,
    }
