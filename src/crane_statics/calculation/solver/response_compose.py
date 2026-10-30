"""Directional response basis type and the composition of a response point from it."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Tuple


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
