"""Crane statics solver: load accumulation, statics kernel, response basis.

Adapted from crane_app.solver.crane_solver.  Key differences from the original:
- Reads from CraneDocument.model_dump() dicts (field names: x_m/z_m/local_x_m,
    area_w_m2/area_v_m2/cd, from_node_id/to_node_id) instead of the original authored schema.
- No file I/O dependencies; caller passes doc_dict directly.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Tuple, Any, cast

import numpy as np

if TYPE_CHECKING:
    from .kinematics import KinematicsAdapter

# ─────────────────────────────────────────────────────────────────────────────
# Numeric Tolerance Constants
# ─────────────────────────────────────────────────────────────────────────────

VECTOR_MAGNITUDE_TOLERANCE = 1e-12  # Threshold for zero magnitude (unitless direction)
LOAD_ACCUMULATION_TOLERANCE = 1e-9  # Tolerance for load/force comparisons during accumulation


# ─────────────────────────────────────────────────────────────────────────────
# Response types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DirectionalResponseBasis:
    boom_angle_deg: float
    outreach_m: float
    dead_raw: Dict[str, float]
    wind_speed_ref_m_s: float
    wind_raw: Dict[str, float]
    accel_x_ref_m_s2: float
    accel_x_raw: Dict[str, float]
    accel_z_ref_m_s2: float
    accel_z_raw: Dict[str, float]
    pitch_ref_rad_s2: float
    pitch_raw: Dict[str, float]
    hook_sensitivity_raw: Dict[str, float]
    offlead_lateral_sensitivity_raw: Dict[str, float]
    default_offlead_deg: float
    rope_ids: Tuple[str, ...]
    active_hoist_id: str
    active_rope_id: str
    active_rope_parts: int
    inactive_rope_baselines: Dict[str, float]
    pitch_sign: float
    connection_local_axes: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # Idle hook mass per fall (t) by rope: the reported idle tension is
    # mass_per_part * (g + accel_z), the same vertical load the solve applies.
    inactive_rope_mass_per_part_t: Dict[str, float] = field(default_factory=dict)
    # Hook block and rope self-weight masses lumped at nodes, as (mass_t, x, z): the
    # out-of-plane pass applies them exactly as the X-Z solve does.
    lumped_point_masses: Tuple[Tuple[float, float, float], ...] = ()


# ---------------------------------------------------------------------------
# Static context builder  (precomputed once per document)
# ---------------------------------------------------------------------------


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
            sf = sum(m for f, t, m in segs if f == hook_id)
            st = sum(m for f, t, m in segs if t == hook_id)
            n = max(1, int(sf + st))
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_unit_vector(dx: float, dz: float) -> Tuple[float, float] | None:
    mag = math.hypot(float(dx), float(dz))
    if mag <= VECTOR_MAGNITUDE_TOLERANCE:
        return None
    return float(dx) / mag, float(dz) / mag


def _connection_local_axes_for_nodes(
    node_pos: Dict[str, Tuple[float, float]],
) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    rb, rt = node_pos.get("rear_base"), node_pos.get("rear_top")
    if rb and rt:
        v = _safe_unit_vector(rt[0] - rb[0], rt[1] - rb[1])
        if v:
            out["rear_hinge"] = {"ux": v[0], "uz": v[1]}
    fb, ft = node_pos.get("front_base"), node_pos.get("front_top")
    if fb and ft:
        v = _safe_unit_vector(ft[0] - fb[0], ft[1] - fb[1])
        if v:
            out["front_hinge"] = {"ux": v[0], "uz": v[1]}

    bh = node_pos.get("boom_heel")
    if bh:
        for ref_id in (
            "mh_boom_sheave_3",
            "bh_sheave_3",
            "mh_boom_sheave_4",
            "ah_boom_sheave_3",
            "ah_boom_sheave_4",
            "sh_boom_sheave_3",
            "sh_boom_sheave_4",
            "mh_hook",
            "ah_hook",
            "sh_hook",
        ):
            ref = node_pos.get(ref_id)
            if not ref:
                continue
            v = _safe_unit_vector(ref[0] - bh[0], ref[1] - bh[1])
            if v:
                out["heel_point"] = {"ux": v[0], "uz": v[1]}
                out["heel_left"] = {"ux": v[0], "uz": v[1]}
                out["heel_right"] = {"ux": v[0], "uz": v[1]}
                break
    return out


def rotate_boom_local_point(
    local_x: float,
    local_z: float,
    node_pos: Dict[str, Tuple[float, float]],
    boom_angle_deg: float,
) -> Tuple[float, float]:
    """World position of a boom-local point: rotate it about the boom heel by the boom angle.

    The same transform as ``kinematics._resolve_nodes`` and ``drawn_loads._body_point``, so
    the solver loads every boom mass and wind area where the scene draws it. (It used to
    infer the angle from a hard-coded sheave list with one crane's local coordinates.)
    """
    heel = node_pos.get("boom_heel")
    if heel is None:
        return local_x, local_z
    heel_x, heel_z = heel
    theta = math.radians(boom_angle_deg)
    gx = heel_x + local_x * math.cos(theta) - local_z * math.sin(theta)
    gz = heel_z + local_x * math.sin(theta) + local_z * math.cos(theta)
    return gx, gz


def boom_wind_projection_scale(boom_angle_deg: float) -> float:
    """Return |sin(boom angle)|: the boom's projected wind area on a vertical surface."""
    return abs(math.sin(math.radians(boom_angle_deg)))


def inertia_force(
    mass_t: float,
    x: float,
    z: float,
    ax: float,
    az: float,
    pitch: float,
    ref_x: float,
    ref_z: float,
    gravity: float,
) -> Tuple[float, float]:
    """Return (Fx, Fz) inertia + gravity load for a mass point."""
    dx, dz = x - ref_x, z - ref_z
    ax_pt = ax + pitch * dz
    az_pt = az - pitch * dx
    return -mass_t * ax_pt, -mass_t * (gravity + az_pt)


# ---------------------------------------------------------------------------
# Active rope metadata
# ---------------------------------------------------------------------------


def _active_rope_metadata(
    doc_dict: Dict[str, Any],
    hoist_id: str,
    solver_ctx: Dict[str, Any],
    hoist_runtime_overrides: Dict[str, Dict[str, Any]] | None = None,
) -> Tuple[Tuple[str, ...], str, int]:
    rope_ids = tuple(str(r["id"]) for r in doc_dict.get("ropes", []) if r.get("id"))
    hoist = solver_ctx["hoist_by_id"].get(hoist_id)
    if hoist is None:
        return rope_ids, "", 1
    active_rope_id = str(hoist.get("rope_id", ""))
    load_node_id = str(hoist.get("load_node_id", ""))
    n = solver_ctx["parts_count_map"].get((active_rope_id, load_node_id), 1)
    override = (hoist_runtime_overrides or {}).get(hoist_id, {})
    override_falls = override.get("falls")
    if override_falls is not None:
        try:
            n = max(1, int(override_falls))
        except (TypeError, ValueError):
            pass
    return rope_ids, active_rope_id, max(1, n)


def _inactive_rope_mass_per_part(
    active_hoist_id: str,
    solver_ctx: Dict[str, Any],
    hoist_runtime_overrides: Dict[str, Dict[str, Any]] | None = None,
) -> Dict[str, float]:
    """Idle hook mass per fall (t) by rope; the idle tension is this times (g + accel_z)."""
    baseline_by_rope: Dict[str, float] = {}
    for hoist in solver_ctx.get("hoists", []):
        hoist_runtime_id = str(hoist.get("id", "") or "")
        rope_id = str(hoist.get("rope_id", "") or "")
        if not rope_id or rope_id == "boom_hoist" or hoist_runtime_id == active_hoist_id:
            continue
        override = (hoist_runtime_overrides or {}).get(hoist_runtime_id, {})
        hook_mass_t = float(override.get("hook_mass_t", hoist.get("hook_mass_t", 0.0)) or 0.0)
        load_node_id = str(hoist.get("load_node_id", "") or "")
        parts = solver_ctx.get("parts_count_map", {}).get((rope_id, load_node_id), 1)
        override_falls = override.get("falls")
        if override_falls is not None:
            try:
                parts = max(1, int(override_falls))
            except (TypeError, ValueError):
                pass
        baseline_by_rope[rope_id] = hook_mass_t / max(1, int(parts))
    return baseline_by_rope


def _build_rope_response_maps(
    rope_ids: Tuple[str, ...],
    active_rope_id: str,
    active_rope_parts: int,
    boom_baseline_kN: float,
    boom_sensitivity_per_kN: float,
    inactive_rope_baselines: Dict[str, float],
) -> Tuple[Dict[str, float], Dict[str, float]]:
    ids = list(rope_ids)
    for rid in ("boom_hoist", active_rope_id):
        if rid and rid not in ids:
            ids.append(rid)
    baseline = {rid: 0.0 for rid in ids}
    sensitivity = {rid: 0.0 for rid in ids}
    baseline["boom_hoist"] = float(boom_baseline_kN)
    sensitivity["boom_hoist"] = float(boom_sensitivity_per_kN)
    for rope_id, baseline_kN in inactive_rope_baselines.items():
        if rope_id not in baseline:
            baseline[rope_id] = 0.0
            sensitivity[rope_id] = 0.0
        baseline[rope_id] = float(baseline_kN)
    if active_rope_id:
        sensitivity[active_rope_id] = 1.0 / max(1, active_rope_parts)
    return baseline, sensitivity


def _build_rope_channel_map(rope_ids: Tuple[str, ...], bh_val: float) -> Dict[str, float]:
    ids = list(rope_ids)
    if "boom_hoist" not in ids:
        ids.append("boom_hoist")
    ch = {rid: 0.0 for rid in ids}
    ch["boom_hoist"] = float(bh_val)
    return ch


def _subtract_raw(a: Dict[str, float], b: Dict[str, float]) -> Dict[str, float]:
    return {k: float(a.get(k, 0.0)) - float(b.get(k, 0.0)) for k in set(a) | set(b)}


def _add_scaled_raw(base: Dict[str, float], delta: Dict[str, float], s: float) -> Dict[str, float]:
    return {
        k: float(base.get(k, 0.0)) + s * float(delta.get(k, 0.0)) for k in set(base) | set(delta)
    }


def _normalize_channel_raw(raw: Dict[str, float], ref: float) -> Dict[str, float]:
    if abs(ref) <= VECTOR_MAGNITUDE_TOLERANCE:
        return {k: 0.0 for k in raw}
    return {k: float(v) / ref for k, v in raw.items()}


def _reactions_from_raw(raw: Dict[str, float], s: float = 1.0) -> Dict[str, Dict[str, float]]:
    return {
        "heel_point": {"Fx": raw.get("h_x", 0.0) * s, "Fz": raw.get("h_z", 0.0) * s},
        "rear_hinge": {"Fx": raw.get("r_rb_x", 0.0) * s, "Fz": raw.get("r_rb_z", 0.0) * s},
        "front_hinge": {"Fx": raw.get("r_fb_x", 0.0) * s, "Fz": raw.get("r_fb_z", 0.0) * s},
        "upper_hinge": {"Fx": raw.get("r_top_x", 0.0) * s, "Fz": raw.get("r_top_z", 0.0) * s},
        "platform_base": {
            "Fx": raw.get("r_g_x", 0.0) * s,
            "Fz": raw.get("r_g_z", 0.0) * s,
            "M": raw.get("m_g", 0.0) * s,
            "My": raw.get("m_g", 0.0) * s,
            "Mx": raw.get("m_g_x", 0.0) * s,
        },
    }


# ---------------------------------------------------------------------------
# Load accumulation
# ---------------------------------------------------------------------------


def lumped_point_masses(
    doc_dict: Dict[str, Any],
    ctx: Dict[str, Any],
    active_hoist_id: str,
    node_pos: Dict[str, Tuple[float, float]],
    node_body_map: Dict[str, str],
    hoist_runtime_overrides: Dict[str, Dict[str, Any]] | None = None,
    rope_mass_t_by_node: Dict[str, float] | None = None,
) -> List[Tuple[int, float, float, float]]:
    """Masses lumped at nodes, as ``(body_index, mass_t, x, z)``.

    - Idle hoists' hook blocks at their hook nodes. The active hoist's hook block is not
      here: it is part of the hook load, carried through the rope.
    - Rope self-weight from ``rope_mass.rope_mass_at_nodes``. It is dead load: no wind area,
      no hook DAF, and it only ever lands on the right-hand side -- the boom-hoist
      coefficients (bh_*) are the unknown's, and rope weight is not proportional to it.

    The X-Z solve and the out-of-plane (Y) pass in the engine both apply exactly this list.
    """
    body_index: Dict[str, int] = ctx["body_index"]
    overrides = hoist_runtime_overrides or {}
    out: List[Tuple[int, float, float, float]] = []
    for hoist_item in ctx.get("hoists", []):
        if hoist_item.get("id") == active_hoist_id:
            continue
        node_id = str(hoist_item.get("load_node_id", ""))
        if not node_id or node_id not in node_pos:
            continue
        hbody = body_index.get(node_body_map.get(node_id, "boom"), -1)
        if hbody < 0:
            continue
        idle_override = overrides.get(str(hoist_item.get("id", "") or ""), {})
        idle_mass_t = float(
            idle_override.get("hook_mass_t", hoist_item.get("hook_mass_t", 0.0)) or 0.0
        )
        if idle_mass_t > 0:
            hx, hz = node_pos[node_id]
            out.append((hbody, idle_mass_t, float(hx), float(hz)))
    for node_id, rope_mass_t in (rope_mass_t_by_node or {}).items():
        position = node_pos.get(node_id)
        if position is None or rope_mass_t <= 0.0:
            continue
        rbody = body_index.get(node_body_map.get(node_id, ""), -1)
        if rbody < 0:
            continue
        out.append((rbody, float(rope_mass_t), float(position[0]), float(position[1])))
    return out


def _accumulate_loads(
    doc_dict: Dict[str, Any],
    node_pos: Dict[str, Tuple[float, float]],
    node_body_map: Dict[str, str],
    hoist_id: str,
    hook_load_kN: float,
    wind_speed_m_s: float,
    accel_x_m_s2: float,
    accel_z_m_s2: float,
    pitch_rad_s2: float = 0.0,
    offlead_lateral_force_kN: float = 0.0,
    solver_ctx: Dict[str, Any] | None = None,
    hoist_runtime_overrides: Dict[str, Dict[str, Any]] | None = None,
    rope_mass_t_by_node: Dict[str, float] | None = None,
    *,
    boom_angle_deg: float,
) -> Tuple[Dict[str, dict], Dict[str, dict]]:
    ctx = solver_ctx or build_solver_static_context(doc_dict)
    body_ids: List[str] = ctx["body_ids"]
    body_index: Dict[str, int] = ctx["body_index"]
    n = len(body_ids)

    ld_fx = [0.0] * n
    ld_fz = [0.0] * n
    ld_m = [0.0] * n
    bh_fx = [0.0] * n
    bh_fz = [0.0] * n
    bh_m = [0.0] * n

    env = doc_dict.get("environment", {})
    gravity = abs(env.get("gravity_m_s2", 9.81))
    air_density = env.get("air_density_kg_m3", 1.225)
    vm = env.get("vessel_motion") or {}
    ref_x = float(vm.get("reference_x_m", 0.0))
    ref_z = float(vm.get("reference_z_m", 0.0))

    # Mass / inertia loads
    for bidx, mass_t, cx, cz in ctx["mass_entries_global"]:
        fx, fz = inertia_force(
            mass_t, cx, cz, accel_x_m_s2, accel_z_m_s2, pitch_rad_s2, ref_x, ref_z, gravity
        )
        ld_fx[bidx] += fx
        ld_fz[bidx] += fz
        ld_m[bidx] += cx * fz - cz * fx

    for bidx, mass_t, lx, lz in ctx["mass_entries_local"]:
        cx, cz = rotate_boom_local_point(lx, lz, node_pos, boom_angle_deg)
        fx, fz = inertia_force(
            mass_t, cx, cz, accel_x_m_s2, accel_z_m_s2, pitch_rad_s2, ref_x, ref_z, gravity
        )
        ld_fx[bidx] += fx
        ld_fz[bidx] += fz
        ld_m[bidx] += cx * fz - cz * fx

    # Wind loads (constant over height, horizontal force only)
    wind_sign: float = math.copysign(1.0, wind_speed_m_s) if wind_speed_m_s != 0 else 0.0
    v_mag = abs(wind_speed_m_s)
    boom_scale = boom_wind_projection_scale(boom_angle_deg)

    def _wind_fx(area: float, cd: float, is_boom_body: bool) -> float:
        eff_area = area * boom_scale if is_boom_body else area
        return float(wind_sign * 0.5 * air_density * v_mag**2 * cd * eff_area / 1000.0)

    # This basis composes X-axis wind effects only; Y-axis wind is handled by
    # the explicit directional scene-analysis path in engine.py.
    for bidx, area_w, area_v, cd, wcx, wcz in ctx["wind_entries_global"]:
        _ = area_v
        fx = _wind_fx(area_w, cd, body_ids[bidx] == "boom")
        ld_fx[bidx] += fx
        ld_m[bidx] += -wcz * fx

    for bidx, area_w, area_v, cd, lx, lz in ctx["wind_entries_local"]:
        _ = area_v
        wcx, wcz = rotate_boom_local_point(lx, lz, node_pos, boom_angle_deg)
        fx = _wind_fx(area_w, cd, body_ids[bidx] == "boom")
        ld_fx[bidx] += fx
        ld_m[bidx] += -wcz * fx

    # Rope loads
    hoist_data = ctx["hoist_by_id"].get(hoist_id)
    if hoist_data is None:
        raise ValueError(f"Hoist {hoist_id!r} not found")
    overrides = hoist_runtime_overrides or {}
    active_override = overrides.get(hoist_id, {})

    active_rope_id = str(hoist_data.get("rope_id", ""))
    gravity_abs = gravity
    node_body_cache: Dict[str, int] = {}
    rope_to_hoist: Dict[str, Any] = ctx.get("rope_to_hoist", {})

    for rope in ctx["ropes_meta"]:
        rope_id = rope["id"]
        is_solve = rope["is_solve"]
        segs = rope["segments"]

        if is_solve:
            # Boom-hoist: accumulate unit direction coefficients.
            # Convention matches original: at na (+ux*w), at nb (-ux*w).
            for na, nb, mult in segs:
                if na not in node_pos or nb not in node_pos:
                    continue
                xa, za = node_pos[na]
                xb, zb = node_pos[nb]
                length = math.hypot(xb - xa, zb - za)
                if length < 1e-9:
                    continue
                ux, uz = (xb - xa) / length, (zb - za) / length
                w = mult
                ba = node_body_cache.get(na)
                if ba is None:
                    ba = body_index.get(node_body_map.get(na, ""), -1)
                    node_body_cache[na] = ba
                bb = node_body_cache.get(nb)
                if bb is None:
                    bb = body_index.get(node_body_map.get(nb, ""), -1)
                    node_body_cache[nb] = bb
                if ba >= 0:
                    bh_fx[ba] += ux * w
                    bh_fz[ba] += uz * w
                    bh_m[ba] += (xa * uz - za * ux) * w
                if bb >= 0:
                    bh_fx[bb] -= ux * w
                    bh_fz[bb] -= uz * w
                    bh_m[bb] += (xb * (-uz) - zb * (-ux)) * w
        else:
            # Known tension rope: compute tension and distribute through all segments.
            if rope_id == active_rope_id:
                load_node_id = str(hoist_data.get("load_node_id", ""))
                n_parts = rope["n_parts_by_hook"].get(load_node_id, 1)
                override_falls = active_override.get("falls")
                if override_falls is not None:
                    try:
                        n_parts = max(1, int(override_falls))
                    except (TypeError, ValueError):
                        pass
                tension_kN = hook_load_kN / max(1, n_parts)
            elif rope_id in rope_to_hoist:
                idle_hoist = rope_to_hoist[rope_id]
                idle_id = str(idle_hoist.get("id", "") or "")
                idle_override = overrides.get(idle_id, {})
                idle_hook_mass_t = float(
                    idle_override.get("hook_mass_t", idle_hoist.get("hook_mass_t", 0.0)) or 0.0
                )
                idle_hook_node = str(idle_hoist.get("load_node_id", ""))
                n_parts_idle = rope["n_parts_by_hook"].get(idle_hook_node, 1)
                override_falls_idle = idle_override.get("falls")
                if override_falls_idle is not None:
                    try:
                        n_parts_idle = max(1, int(override_falls_idle))
                    except (TypeError, ValueError):
                        pass
                # Idle-hoist rope tension uses only the vertical heave component
                # m*(g + accel_z)/n (accel_z is the crane-frame value); it does not
                # include the pitch-lever term at the hook node.
                tension_kN = idle_hook_mass_t * (gravity_abs + accel_z_m_s2) / max(1, n_parts_idle)
            else:
                tension_kN = 0.0

            for na, nb, mult in segs:
                if na not in node_pos or nb not in node_pos:
                    continue
                xa, za = node_pos[na]
                xb, zb = node_pos[nb]
                length = math.hypot(xb - xa, zb - za)
                if length < 1e-9:
                    continue
                ux, uz = (xb - xa) / length, (zb - za) / length
                w = mult
                fx = tension_kN * ux * w
                fz = tension_kN * uz * w
                ba = node_body_cache.get(na)
                if ba is None:
                    ba = body_index.get(node_body_map.get(na, ""), -1)
                    node_body_cache[na] = ba
                bb = node_body_cache.get(nb)
                if bb is None:
                    bb = body_index.get(node_body_map.get(nb, ""), -1)
                    node_body_cache[nb] = bb
                if ba >= 0:
                    ld_fx[ba] += fx
                    ld_fz[ba] += fz
                    ld_m[ba] += xa * fz - za * fx
                if bb >= 0:
                    ld_fx[bb] -= fx
                    ld_fz[bb] -= fz
                    ld_m[bb] += xb * (-fz) - zb * (-fx)

    # Hook loads: active hoist (cargo load) + idle hoist hook masses
    node_lookup = {n["id"]: n for n in doc_dict.get("nodes", []) if n.get("id")}
    for hoist_item in ctx.get("hoists", []):
        node_id = str(hoist_item.get("load_node_id", ""))
        if not node_id or node_id not in node_pos:
            continue
        hx, hz = node_pos[node_id]
        hbody = node_body_cache.get(node_id)
        if hbody is None:
            hbody = body_index.get(node_body_map.get(node_id, "boom"), -1)
            node_body_cache[node_id] = hbody
        if hbody < 0:
            continue

        if hoist_item.get("id") == hoist_id:
            # Active hoist: apply hook load downward
            ld_fz[hbody] -= hook_load_kN
            ld_m[hbody] += hx * (-hook_load_kN)
            # Offlead force enters at the rope reference (sheave) above the hook.
            support_node_id = node_id
            load_node = node_lookup.get(node_id, {})
            below_id = str(load_node.get("below_node_id") or "")
            if below_id and below_id in node_pos:
                support_node_id = below_id
            sx, sz = node_pos.get(support_node_id, (hx, hz))
            sbody = node_body_cache.get(support_node_id)
            if sbody is None:
                sbody = body_index.get(node_body_map.get(support_node_id, "boom"), -1)
                node_body_cache[support_node_id] = sbody
            if sbody >= 0 and abs(offlead_lateral_force_kN) > VECTOR_MAGNITUDE_TOLERANCE:
                ld_fx[sbody] += offlead_lateral_force_kN
                ld_m[sbody] += -sz * offlead_lateral_force_kN

            normal_hook_mass_t = float(hoist_data.get("hook_mass_t", 0.0) or 0.0)
            effective_hook_mass_t = float(
                active_override.get("hook_mass_t", normal_hook_mass_t) or 0.0
            )
            comp_mass_t = active_override.get("support_comp_mass_t")
            if comp_mass_t is None:
                comp_mass_t = max(0.0, normal_hook_mass_t - effective_hook_mass_t)
            try:
                comp_mass_t = max(0.0, float(comp_mass_t))
            except (TypeError, ValueError):
                comp_mass_t = 0.0
            if comp_mass_t > VECTOR_MAGNITUDE_TOLERANCE:
                support_node_id = str(
                    active_override.get("support_node_id")
                    or hoist_data.get("support_node_id")
                    or support_node_id
                )
                if support_node_id in node_pos:
                    sx_comp, sz_comp = node_pos[support_node_id]
                    sbody_comp = node_body_cache.get(support_node_id)
                    if sbody_comp is None:
                        sbody_comp = body_index.get(node_body_map.get(support_node_id, "boom"), -1)
                        node_body_cache[support_node_id] = sbody_comp
                    if sbody_comp >= 0:
                        fx_comp, fz_comp = inertia_force(
                            comp_mass_t,
                            sx_comp,
                            sz_comp,
                            accel_x_m_s2,
                            accel_z_m_s2,
                            pitch_rad_s2,
                            ref_x,
                            ref_z,
                            gravity,
                        )
                        ld_fx[sbody_comp] += fx_comp
                        ld_fz[sbody_comp] += fz_comp
                        ld_m[sbody_comp] += sx_comp * fz_comp - sz_comp * fx_comp

    # Idle hook blocks and rope self-weight: masses lumped at nodes that feel gravity
    # and the vessel motion like any other mass point (see ``lumped_point_masses``).
    for lbody, lmass_t, lx, lz in lumped_point_masses(
        doc_dict,
        ctx,
        hoist_id,
        node_pos,
        node_body_map,
        hoist_runtime_overrides,
        rope_mass_t_by_node,
    ):
        fx, fz = inertia_force(
            lmass_t, lx, lz, accel_x_m_s2, accel_z_m_s2, pitch_rad_s2, ref_x, ref_z, gravity
        )
        ld_fx[lbody] += fx
        ld_fz[lbody] += fz
        ld_m[lbody] += lx * fz - lz * fx

    ld = {bid: {"Fx": ld_fx[i], "Fz": ld_fz[i], "M": ld_m[i]} for i, bid in enumerate(body_ids)}
    bh = {bid: {"Fx": bh_fx[i], "Fz": bh_fz[i], "M": bh_m[i]} for i, bid in enumerate(body_ids)}
    return ld, bh


# ---------------------------------------------------------------------------
# Statics kernel
# ---------------------------------------------------------------------------


#: Smallest ``abs(det) / prod(row norms)`` (Hadamard ratio, 1 for orthogonal rows) a
#: statics matrix may have before its solution is treated as meaningless.
SINGULAR_RATIO = 1e-12

#: ``solver_ctx`` key under which ``_run_statics`` leaves the reason it returned ``{}``.
UNAVAILABLE_REASON_KEY = "_unavailable_reason"


def _record_unavailable(solver_ctx: Dict[str, Any] | None, reason: str) -> None:
    if solver_ctx is not None:
        solver_ctx[UNAVAILABLE_REASON_KEY] = reason


def is_ill_conditioned(matrix: np.ndarray) -> bool:
    """True when ``matrix`` is singular or so close to it that a solve is unreliable.

    The test is scale-free: ``abs(det) / prod(row norms) <= SINGULAR_RATIO``. A zero row
    (zero product of norms) counts as ill-conditioned.
    """
    norms = np.linalg.norm(matrix, axis=1)
    scale = float(np.prod(norms))
    if not np.isfinite(scale) or scale <= 0.0:
        return True
    return bool(abs(float(np.linalg.det(matrix))) / scale <= SINGULAR_RATIO)


def _singular_reason(matrix_name: str) -> str:
    return (
        f"The {matrix_name} statics are singular for this geometry "
        "(its supports do not restrain the structure); check the hinge and heel positions."
    )


def _run_statics(
    doc_dict: Dict[str, Any],
    node_pos: Dict[str, Tuple[float, float]],
    node_body_map: Dict[str, str],
    hoist_id: str,
    hook_load_kN: float,
    wind_speed_m_s: float,
    accel_x_m_s2: float,
    accel_z_m_s2: float,
    pitch_rad_s2: float = 0.0,
    offlead_lateral_force_kN: float = 0.0,
    solver_ctx: Dict[str, Any] | None = None,
    hoist_runtime_overrides: Dict[str, Dict[str, Any]] | None = None,
    rope_mass_t_by_node: Dict[str, float] | None = None,
    *,
    boom_angle_deg: float,
) -> Dict[str, float]:
    """Solve 3-body statics sequentially: boom → rear/front leg frame → platform."""
    ld, bh = _accumulate_loads(
        doc_dict,
        node_pos,
        node_body_map,
        hoist_id,
        hook_load_kN,
        wind_speed_m_s,
        accel_x_m_s2,
        accel_z_m_s2,
        pitch_rad_s2,
        offlead_lateral_force_kN,
        solver_ctx,
        hoist_runtime_overrides,
        rope_mass_t_by_node,
        boom_angle_deg=boom_angle_deg,
    )

    heel_x, heel_z = node_pos["boom_heel"]
    bm, bm_bh = ld["boom"], bh["boom"]

    # Boom: solve for [H_x, H_z, T_bh]
    A_boom = np.array(
        [
            [1.0, 0.0, bm_bh["Fx"]],
            [0.0, 1.0, bm_bh["Fz"]],
            [-heel_z, heel_x, bm_bh["M"]],
        ],
        dtype=float,
    )
    b_boom = np.array([-bm["Fx"], -bm["Fz"], -bm["M"]], dtype=float)
    if is_ill_conditioned(A_boom):
        _record_unavailable(solver_ctx, _singular_reason("boom"))
        return {}
    try:
        h_x, h_z, t_bh = np.linalg.solve(A_boom, b_boom)
    except np.linalg.LinAlgError:
        _record_unavailable(solver_ctx, _singular_reason("boom"))
        return {}

    rb_x, rb_z = node_pos["rear_base"]
    rt_x, rt_z = node_pos["rear_top"]
    fb_x, fb_z = node_pos["front_base"]
    ft_x, ft_z = node_pos["front_top"]

    rl, fl = ld["rear_leg"], ld["front_leg"]
    rl_bh, fl_bh = bh["rear_leg"], bh["front_leg"]

    rear_fx = rl["Fx"] + t_bh * rl_bh["Fx"]
    rear_fz = rl["Fz"] + t_bh * rl_bh["Fz"]
    rear_m = rl["M"] + t_bh * rl_bh["M"]
    front_fx = fl["Fx"] + t_bh * fl_bh["Fx"]
    front_fz = fl["Fz"] + t_bh * fl_bh["Fz"]
    front_m = fl["M"] + t_bh * fl_bh["M"]

    # Rear/front leg frame: solve for [R_rb_x, R_rb_z, R_fb_x, R_fb_z, R_top_x, R_top_z]
    A_af = np.array(
        [
            [1, 0, 0, 0, -1, 0],
            [0, 1, 0, 0, 0, -1],
            [-rb_z, rb_x, 0, 0, rt_z, -rt_x],
            [0, 0, 1, 0, 1, 0],
            [0, 0, 0, 1, 0, 1],
            [0, 0, -fb_z, fb_x, -ft_z, ft_x],
        ],
        dtype=float,
    )
    b_af = np.array(
        [
            -rear_fx,
            -rear_fz,
            -rear_m,
            -front_fx,
            -front_fz,
            -front_m,
        ],
        dtype=float,
    )
    if is_ill_conditioned(A_af):
        _record_unavailable(solver_ctx, _singular_reason("leg frame"))
        return {}
    try:
        r_rb_x, r_rb_z, r_fb_x, r_fb_z, r_top_x, r_top_z = np.linalg.solve(A_af, b_af)
    except np.linalg.LinAlgError:
        _record_unavailable(solver_ctx, _singular_reason("leg frame"))
        return {}

    # Platform: resultant at ground pin
    pl, pl_bh = ld["platform"], bh["platform"]
    plat_fx = pl["Fx"] + t_bh * pl_bh["Fx"] - h_x - r_rb_x - r_fb_x
    plat_fz = pl["Fz"] + t_bh * pl_bh["Fz"] - h_z - r_rb_z - r_fb_z

    ph_x, ph_z = node_pos["platform_heel"]
    pr_x, pr_z = node_pos["platform_rear"]
    pf_x, pf_z = node_pos["platform_front"]
    plat_m = (
        pl["M"]
        + t_bh * pl_bh["M"]
        + ph_x * (-h_z)
        - ph_z * (-h_x)
        + pr_x * (-r_rb_z)
        - pr_z * (-r_rb_x)
        + pf_x * (-r_fb_z)
        - pf_z * (-r_fb_x)
    )

    return {
        "t_bh": float(t_bh),
        "h_x": float(h_x),
        "h_z": float(h_z),
        "r_rb_x": float(r_rb_x),
        "r_rb_z": float(r_rb_z),
        "r_fb_x": float(r_fb_x),
        "r_fb_z": float(r_fb_z),
        "r_top_x": float(r_top_x),
        "r_top_z": float(r_top_z),
        "r_g_x": float(-plat_fx),
        "r_g_z": float(-plat_fz),
        "m_g": float(-plat_m),
    }


# ---------------------------------------------------------------------------
# Public API: build directional response basis
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _AngleInvariants:
    """What ``build_directional_response_basis`` solves at one boom angle, whatever the channels."""

    node_pos: Dict[str, Tuple[float, float]]
    node_body_map: Dict[str, str]
    outreach_m: float
    rope_mass_t_by_node: Dict[str, float]
    dead_raw: Dict[str, float]
    hook_sensitivity_raw: Dict[str, float]
    offlead_lateral_sensitivity_raw: Dict[str, float]


# (cache key, invariants, bases by channel references) of the last angle built.
_InvariantsEntry = Tuple[
    Tuple[Any, ...],
    "_AngleInvariants | None",
    Dict[Tuple[float, ...], "DirectionalResponseBasis | None"],
]


def _angle_invariants(
    doc_dict: Dict[str, Any],
    kinematics: "KinematicsAdapter",
    hoist_id: str,
    boom_angle_deg: float,
    ctx: Dict[str, Any],
    hoist_runtime_overrides: Dict[str, Dict[str, Any]] | None,
    tackle_length_m: float | None,
) -> _AngleInvariants | None:
    # ``rope_mass`` reaches back into this package for kinematics, so importing it
    # at module level would close the cycle.
    from ..rope_mass import active_hook_positions, falls_override_effective_mult, rope_mass_at_nodes

    hoist_data = next(h for h in doc_dict.get("hoists", []) if h["id"] == hoist_id)
    node_positions_dicts = active_hook_positions(
        doc_dict,
        hoist_id,
        kinematics.compute_all_node_positions(boom_angle_deg),
        tackle_length_m,
    )
    node_pos: Dict[str, Tuple[float, float]] = {
        nid: (float(d["x"]), float(d["z"])) for nid, d in node_positions_dicts.items()
    }
    node_body_map: Dict[str, str] = {n["id"]: n.get("body", "") for n in doc_dict.get("nodes", [])}

    load_node_id = str(hoist_data.get("load_node_id", ""))
    outreach_m = node_pos.get(load_node_id, (0.0, 0.0))[0]

    falls_by_hoist_id: Dict[str, int] = {}
    for runtime_hoist_id, override in (hoist_runtime_overrides or {}).items():
        try:
            falls_by_hoist_id[str(runtime_hoist_id)] = int(override["falls"])
        except (KeyError, TypeError, ValueError):
            continue
    rope_mass_t_by_node = {
        node_id: entry.mass_t
        for node_id, entry in rope_mass_at_nodes(
            doc_dict,
            node_positions_dicts,
            effective_mult=falls_override_effective_mult(doc_dict, falls_by_hoist_id),
        ).items()
    }

    dead_raw = _run_statics(
        doc_dict,
        node_pos,
        node_body_map,
        hoist_id,
        hook_load_kN=0.0,
        wind_speed_m_s=0.0,
        accel_x_m_s2=0.0,
        accel_z_m_s2=0.0,
        pitch_rad_s2=0.0,
        offlead_lateral_force_kN=0.0,
        solver_ctx=ctx,
        hoist_runtime_overrides=hoist_runtime_overrides,
        rope_mass_t_by_node=rope_mass_t_by_node,
        boom_angle_deg=boom_angle_deg,
    )
    if not dead_raw:
        return None

    raw_hook_unit = _run_statics(
        doc_dict,
        node_pos,
        node_body_map,
        hoist_id,
        hook_load_kN=1.0,
        wind_speed_m_s=0.0,
        accel_x_m_s2=0.0,
        accel_z_m_s2=0.0,
        pitch_rad_s2=0.0,
        offlead_lateral_force_kN=0.0,
        solver_ctx=ctx,
        hoist_runtime_overrides=hoist_runtime_overrides,
        rope_mass_t_by_node=rope_mass_t_by_node,
        boom_angle_deg=boom_angle_deg,
    )
    if not raw_hook_unit:
        return None
    raw_offlead_lateral_unit = _run_statics(
        doc_dict,
        node_pos,
        node_body_map,
        hoist_id,
        hook_load_kN=0.0,
        wind_speed_m_s=0.0,
        accel_x_m_s2=0.0,
        accel_z_m_s2=0.0,
        pitch_rad_s2=0.0,
        offlead_lateral_force_kN=1.0,
        solver_ctx=ctx,
        hoist_runtime_overrides=hoist_runtime_overrides,
        rope_mass_t_by_node=rope_mass_t_by_node,
        boom_angle_deg=boom_angle_deg,
    )
    if not raw_offlead_lateral_unit:
        return None
    hook_sensitivity_raw = _subtract_raw(raw_hook_unit, dead_raw)
    offlead_lateral_sensitivity_raw = _subtract_raw(raw_offlead_lateral_unit, dead_raw)

    return _AngleInvariants(
        node_pos=node_pos,
        node_body_map=node_body_map,
        outreach_m=outreach_m,
        rope_mass_t_by_node=rope_mass_t_by_node,
        dead_raw=dead_raw,
        hook_sensitivity_raw=hook_sensitivity_raw,
        offlead_lateral_sensitivity_raw=offlead_lateral_sensitivity_raw,
    )


def build_directional_response_basis(
    doc_dict: Dict[str, Any],
    kinematics: "KinematicsAdapter",
    hoist_id: str,
    boom_angle_deg: float,
    wind_speed_m_s: float = 0.0,
    accel_x_m_s2: float = 0.0,
    accel_z_m_s2: float = 0.0,
    pitch_rad_s2: float = 0.0,
    solver_ctx: Dict[str, Any] | None = None,
    hoist_runtime_overrides: Dict[str, Dict[str, Any]] | None = None,
    tackle_length_m: float | None = None,
) -> DirectionalResponseBasis | None:
    hoist_data = next((h for h in doc_dict.get("hoists", []) if h["id"] == hoist_id), None)
    if hoist_data is None:
        return None

    ctx = solver_ctx or build_solver_static_context(doc_dict)
    # A sweep builds several bases at one angle that differ only in their channel references,
    # and the probes that load no in-plane channel share one. The invariants and the bases
    # are kept (last angle only) in the static context.
    cache_key = (
        hoist_id,
        boom_angle_deg,
        tackle_length_m,
        json.dumps(hoist_runtime_overrides, sort_keys=True, default=repr),
    )
    last: _InvariantsEntry | None = ctx.get("_angle_invariants")
    if last is None or last[0] != cache_key:
        ctx.pop(UNAVAILABLE_REASON_KEY, None)
        last = (
            cache_key,
            _angle_invariants(
                doc_dict,
                kinematics,
                hoist_id,
                boom_angle_deg,
                ctx,
                hoist_runtime_overrides,
                tackle_length_m,
            ),
            {},
        )
        ctx["_angle_invariants"] = last
    _, invariants, bases = last
    if invariants is None:
        return None
    refs = (
        abs(float(wind_speed_m_s)),
        abs(float(accel_x_m_s2)),
        abs(float(accel_z_m_s2)),
        abs(float(pitch_rad_s2)),
        1.0 if pitch_rad_s2 > 0 else (-1.0 if pitch_rad_s2 < 0 else 0.0),
    )
    if refs not in bases:
        bases[refs] = _basis_from_invariants(
            doc_dict, hoist_data, boom_angle_deg, refs, ctx, hoist_runtime_overrides, invariants
        )
    basis: DirectionalResponseBasis | None = bases[refs]
    return basis


def _basis_from_invariants(
    doc_dict: Dict[str, Any],
    hoist_data: Dict[str, Any],
    boom_angle_deg: float,
    refs: Tuple[float, float, float, float, float],
    ctx: Dict[str, Any],
    hoist_runtime_overrides: Dict[str, Dict[str, Any]] | None,
    invariants: _AngleInvariants,
) -> DirectionalResponseBasis | None:
    """The basis for channel references ``refs`` (wind, accel x, accel z, pitch, pitch sign)."""
    hoist_id = str(hoist_data["id"])
    node_pos = invariants.node_pos
    node_body_map = invariants.node_body_map
    outreach_m = invariants.outreach_m
    rope_mass_t_by_node = invariants.rope_mass_t_by_node
    dead_raw = invariants.dead_raw
    hook_sensitivity_raw = invariants.hook_sensitivity_raw
    offlead_lateral_sensitivity_raw = invariants.offlead_lateral_sensitivity_raw

    def _channel(
        *, wind: float = 0.0, ax: float = 0.0, az: float = 0.0, pitch: float = 0.0
    ) -> Dict[str, float] | None:
        r = _run_statics(
            doc_dict,
            node_pos,
            node_body_map,
            hoist_id,
            hook_load_kN=0.0,
            wind_speed_m_s=wind,
            accel_x_m_s2=ax,
            accel_z_m_s2=az,
            pitch_rad_s2=pitch,
            offlead_lateral_force_kN=0.0,
            solver_ctx=ctx,
            hoist_runtime_overrides=hoist_runtime_overrides,
            rope_mass_t_by_node=rope_mass_t_by_node,
            boom_angle_deg=boom_angle_deg,
        )
        return _subtract_raw(r, dead_raw) if r else None

    wind_ref, ax_ref, az_ref, pt_ref, pitch_sign = refs

    wind_raw: Dict[str, float] | None = (
        _channel(wind=wind_ref) if wind_ref > 0 else {k: 0.0 for k in dead_raw}
    )
    ax_raw: Dict[str, float] | None = (
        _channel(ax=ax_ref) if ax_ref > 0 else {k: 0.0 for k in dead_raw}
    )
    az_raw: Dict[str, float] | None = (
        _channel(az=az_ref) if az_ref > 0 else {k: 0.0 for k in dead_raw}
    )
    pt_raw: Dict[str, float] | None = (
        _channel(pitch=pt_ref) if pt_ref > 0 else {k: 0.0 for k in dead_raw}
    )
    if any(v is None for v in (wind_raw, ax_raw, az_raw, pt_raw)):
        return None
    wind_raw = cast(Dict[str, float], wind_raw)
    ax_raw = cast(Dict[str, float], ax_raw)
    az_raw = cast(Dict[str, float], az_raw)
    pt_raw = cast(Dict[str, float], pt_raw)

    rope_ids, active_rope_id, active_rope_parts = _active_rope_metadata(
        doc_dict,
        hoist_id,
        ctx,
        hoist_runtime_overrides,
    )
    gravity_abs = abs(float((doc_dict.get("environment") or {}).get("gravity_m_s2", 9.81)))
    inactive_rope_mass_per_part_t = _inactive_rope_mass_per_part(
        hoist_id, ctx, hoist_runtime_overrides
    )
    inactive_rope_baselines = {
        rope_id: mass_per_part_t * gravity_abs
        for rope_id, mass_per_part_t in inactive_rope_mass_per_part_t.items()
    }
    lumped = tuple(
        (mass_t, x, z)
        for _body, mass_t, x, z in lumped_point_masses(
            doc_dict,
            ctx,
            hoist_id,
            node_pos,
            node_body_map,
            hoist_runtime_overrides,
            rope_mass_t_by_node,
        )
    )

    return DirectionalResponseBasis(
        boom_angle_deg=boom_angle_deg,
        outreach_m=outreach_m,
        dead_raw=dead_raw,
        wind_speed_ref_m_s=wind_ref,
        wind_raw=_normalize_channel_raw(wind_raw, wind_ref),
        accel_x_ref_m_s2=ax_ref,
        accel_x_raw=_normalize_channel_raw(ax_raw, ax_ref),
        accel_z_ref_m_s2=az_ref,
        accel_z_raw=_normalize_channel_raw(az_raw, az_ref),
        pitch_ref_rad_s2=pt_ref,
        pitch_raw=_normalize_channel_raw(pt_raw, pt_ref),
        hook_sensitivity_raw=hook_sensitivity_raw,
        offlead_lateral_sensitivity_raw=offlead_lateral_sensitivity_raw,
        default_offlead_deg=float(hoist_data.get("offlead_deg", 0.0)),
        rope_ids=rope_ids,
        active_hoist_id=hoist_id,
        active_rope_id=active_rope_id,
        active_rope_parts=active_rope_parts,
        inactive_rope_baselines=inactive_rope_baselines,
        pitch_sign=pitch_sign,
        connection_local_axes=_connection_local_axes_for_nodes(node_pos),
        inactive_rope_mass_per_part_t=inactive_rope_mass_per_part_t,
        lumped_point_masses=lumped,
    )


def compose_unit_basis_point(
    basis: DirectionalResponseBasis,
    wind_sign: float = 0.0,
    accel_x_sign: float = 0.0,
    accel_z_sign: float = 0.0,
    pitch_sign: float = 0.0,
    offlead_deg: float | None = None,
) -> Dict:
    """Compose a response point from a pre-computed directional basis."""
    raw = dict(basis.dead_raw)
    raw = _add_scaled_raw(raw, basis.wind_raw, wind_sign * basis.wind_speed_ref_m_s)
    raw = _add_scaled_raw(raw, basis.accel_x_raw, accel_x_sign * basis.accel_x_ref_m_s2)
    raw = _add_scaled_raw(raw, basis.accel_z_raw, accel_z_sign * basis.accel_z_ref_m_s2)
    raw = _add_scaled_raw(raw, basis.pitch_raw, pitch_sign * basis.pitch_ref_rad_s2)

    active_offlead_deg = basis.default_offlead_deg if offlead_deg is None else float(offlead_deg)
    offlead_scale = math.sin(math.radians(active_offlead_deg))
    sensitivity_raw = _add_scaled_raw(
        basis.hook_sensitivity_raw,
        basis.offlead_lateral_sensitivity_raw,
        offlead_scale,
    )

    # Idle ropes carry the vertical hook load, m/parts * (g + accel_z), as in the solve.
    accel_z_signed = accel_z_sign * basis.accel_z_ref_m_s2
    inactive_ropes = {
        rope_id: float(baseline_kN)
        + accel_z_signed * float(basis.inactive_rope_mass_per_part_t.get(rope_id, 0.0))
        for rope_id, baseline_kN in basis.inactive_rope_baselines.items()
    }
    baseline_ropes, sensitivity_ropes = _build_rope_response_maps(
        basis.rope_ids,
        basis.active_rope_id,
        basis.active_rope_parts,
        raw["t_bh"],
        sensitivity_raw["t_bh"],
        inactive_ropes,
    )
    return {
        "boom_angle_deg": basis.boom_angle_deg,
        "outreach_m": basis.outreach_m,
        "baseline_rope_tensions": baseline_ropes,
        "baseline_reactions": _reactions_from_raw(raw),
        "sensitivity_rope_tensions": sensitivity_ropes,
        "sensitivity_reactions": _reactions_from_raw(sensitivity_raw),
        "offlead_lateral_unit_rope_tensions": _build_rope_channel_map(
            basis.rope_ids, basis.offlead_lateral_sensitivity_raw.get("t_bh", 0.0)
        ),
        "offlead_lateral_unit_reactions": _reactions_from_raw(
            basis.offlead_lateral_sensitivity_raw
        ),
        "governing_signs": {
            "wind_speed": wind_sign,
            "accel_x": accel_x_sign,
            "accel_z": accel_z_sign,
            "pitch": pitch_sign,
        },
        "connection_local_axes": dict(basis.connection_local_axes),
    }
