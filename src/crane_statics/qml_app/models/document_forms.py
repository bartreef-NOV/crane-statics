"""Qt-free conversions between document records and the dicts the model forms use.

``*_fields`` read a record into the form dict QML shows; ``*_kwargs`` read a submitted
form dict into the arguments of the matching ``core.document_edit.build_*`` function.
The environment helpers read and write the scalar settings on a ``CraneDocument``.
"""

from __future__ import annotations

from typing import Any, Optional

from crane_statics.data import CraneDocument
from crane_statics.qml_app.contracts import EnvironmentSettings

ENVIRONMENT_KEYS = [
    "gravity_m_s2",
    "max_wind_speed_m_s",
    "air_density_kg_m3",
]
VESSEL_MOTION_KEYS = [
    "roll_deg",
    "pitch_deg",
    "accel_x_m_s2",
    "accel_y_m_s2",
    "accel_z_m_s2",
    "roll_angular_accel_rad_s2",
    "pitch_angular_accel_rad_s2",
    "reference_x_m",
    "reference_z_m",
]
SUPPORT_WIDTH_KEYS = ["boom_width_m", "slewing_bearing_diameter_m"]
# Support-width keys that may be cleared back to "unset" via clearEnvironmentValue.
NULLABLE_SUPPORT_WIDTH_KEYS = {"slewing_bearing_diameter_m"}

# Authored primary-structure points and the runtime nodes they map to.
PRIMARY_STRUCTURE_BINDINGS = [
    ("boom_heel", "Heel Point"),
    ("rear_top", "Upper Hinge"),
    ("rear_base", "Rear Hinge"),
    ("front_base", "Front Hinge"),
]


# ----------------------------------------------------------------------
# Environment, support widths and primary structure
# ----------------------------------------------------------------------


def environment_settings(doc: Optional[CraneDocument]) -> dict:
    if doc is None:
        return EnvironmentSettings.defaults().to_dict()
    env_dict: dict[str, Optional[float]] = {
        key: float(getattr(doc.environment, key)) for key in ENVIRONMENT_KEYS
    }
    env_dict.update(
        {key: float(getattr(doc.environment.vessel_motion, key)) for key in VESSEL_MOTION_KEYS}
    )
    env_dict.update(
        {
            key: (float(raw) if (raw := getattr(doc.support_widths, key)) is not None else None)
            for key in SUPPORT_WIDTH_KEYS
        }
    )
    return EnvironmentSettings.from_dict(env_dict).to_dict()


def set_environment_value(doc: CraneDocument, key: str, value: float) -> bool:
    """Set one scalar setting; False when the key is unknown or the value is unchanged."""
    target: Any
    if key in ENVIRONMENT_KEYS:
        target = doc.environment
    elif key in VESSEL_MOTION_KEYS:
        target = doc.environment.vessel_motion
    elif key in SUPPORT_WIDTH_KEYS:
        target = doc.support_widths
    else:
        return False
    previous = getattr(target, key)
    if float(previous or 0.0) == float(value):
        return False
    setattr(target, key, float(value))
    return True


def clear_support_width(doc: CraneDocument, key: str) -> bool:
    """Reset a nullable support width to unset; False when it cannot or need not change."""
    if key not in NULLABLE_SUPPORT_WIDTH_KEYS or getattr(doc.support_widths, key) is None:
        return False
    setattr(doc.support_widths, key, None)
    return True


def primary_structure_rows(doc: Optional[CraneDocument]) -> list[dict[str, Any]]:
    by_id = {} if doc is None else {n.id: n for n in doc.nodes}
    rows = []
    for node_id, label in PRIMARY_STRUCTURE_BINDINGS:
        node = by_id.get(node_id)
        if node is None:
            continue
        rows.append(
            {
                "nodeId": node_id,
                "label": label,
                "posX": float(node.x_m),
                "posZ": float(node.z_m),
            }
        )
    return rows


# ----------------------------------------------------------------------
# Record -> form dict
# ----------------------------------------------------------------------


def node_fields(node: Any) -> dict[str, Any]:
    return {
        "id": node.id,
        "hanging": bool(node.below_node_id),
        "below_node_id": node.below_node_id or "",
        "x_m": float(node.x_m),
        "z_m": float(node.z_m),
        "local_x_m": float(node.local_x_m or 0.0),
        "local_z_m": float(node.local_z_m or 0.0),
    }


def mass_point_fields(point: Any) -> dict[str, Any]:
    return {
        "id": point.id,
        "mass_t": float(point.mass_t),
        "x_m": float(point.x_m),
        "y_m": float(point.y_m),
        "z_m": float(point.z_m),
        "local_x_m": float(point.local_x_m or 0.0),
        "local_y_m": float(point.local_y_m or 0.0),
        "local_z_m": float(point.local_z_m or 0.0),
    }


def wind_area_fields(area: Any) -> dict[str, Any]:
    return {
        "id": area.id,
        "area_w_m2": float(area.area_w_m2),
        "area_v_m2": float(area.area_v_m2),
        "x_m": float(area.x_m),
        "z_m": float(area.z_m),
        "local_x_m": float(area.local_x_m or 0.0),
        "local_z_m": float(area.local_z_m or 0.0),
        "cd": float(area.cd),
    }


def hoist_fields(hoist: Any, *, is_boom_hoist: bool) -> dict[str, Any]:
    return {
        "id": hoist.id,
        "is_boom_hoist": is_boom_hoist,
        "support_node_id": hoist.support_node_id or hoist.load_node_id,
        "falls": int(hoist.falls or 1),
        "hook_mass_t": float(hoist.hook_mass_t),
        "linear_mass_kg_m": float(hoist.linear_mass_kg_m),
        "rope_length_m": None if hoist.rope_length_m is None else float(hoist.rope_length_m),
        "lowest_hook_height_m": float(hoist.lowest_hook_height_m or 0.0),
        "splitable_block": bool(hoist.splitable_block),
        "split_falls": int(hoist.split_falls or hoist.falls or 1),
        "split_hook_mass_t": float(
            hoist.split_hook_mass_t if hoist.split_hook_mass_t is not None else hoist.hook_mass_t
        ),
        "hook_daf": float(hoist.hook_daf),
        "offlead_deg": float(hoist.offlead_deg),
        "sidelead_deg": float(hoist.sidelead_deg),
    }


def rope_segment_fields(segment: Any) -> dict[str, Any]:
    return {
        "from_node_id": segment.from_node_id,
        "to_node_id": segment.to_node_id,
        "mult": int(segment.mult),
    }


def contractual_fields(point: Any) -> dict[str, Any]:
    return {"outreach_m": float(point.outreach_m), "load_t": float(point.load_t)}


# ----------------------------------------------------------------------
# Form dict -> build_* arguments
# ----------------------------------------------------------------------


def node_kwargs(fields: dict) -> dict:
    return {
        "node_id": str(fields.get("id", "")),
        "hanging": bool(fields.get("hanging", False)),
        "below_node_id": str(fields.get("below_node_id", "") or ""),
        "x_m": float(fields.get("x_m", 0.0)),
        "z_m": float(fields.get("z_m", 0.0)),
        "local_x_m": float(fields.get("local_x_m", 0.0)),
        "local_z_m": float(fields.get("local_z_m", 0.0)),
    }


def mass_kwargs(fields: dict) -> dict:
    return {
        "mass_point_id": str(fields.get("id", "")),
        "mass_t": float(fields.get("mass_t", 0.0)),
        "x_m": float(fields.get("x_m", 0.0)),
        "y_m": float(fields.get("y_m", 0.0)),
        "z_m": float(fields.get("z_m", 0.0)),
        "local_x_m": float(fields.get("local_x_m", 0.0)),
        "local_y_m": float(fields.get("local_y_m", 0.0)),
        "local_z_m": float(fields.get("local_z_m", 0.0)),
    }


def wind_kwargs(fields: dict) -> dict:
    return {
        "wind_area_id": str(fields.get("id", "")),
        "area_w_m2": float(fields.get("area_w_m2", 0.0)),
        "area_v_m2": float(fields.get("area_v_m2", 0.0)),
        "x_m": float(fields.get("x_m", 0.0)),
        "z_m": float(fields.get("z_m", 0.0)),
        "local_x_m": float(fields.get("local_x_m", 0.0)),
        "local_z_m": float(fields.get("local_z_m", 0.0)),
        "cd": float(fields.get("cd", 1.0)),
    }


def hoist_kwargs(fields: dict) -> dict:
    splitable = bool(fields.get("splitable_block", False))
    return {
        "hoist_id": str(fields.get("id", "")),
        "support_node_id": str(fields.get("support_node_id", "")),
        "falls": int(fields.get("falls", 1)),
        "hook_mass_t": float(fields.get("hook_mass_t", 0.0)),
        "linear_mass_kg_m": max(0.0, float(fields.get("linear_mass_kg_m", 0.0))),
        "lowest_hook_height_m": float(fields.get("lowest_hook_height_m", 0.0)),
        "splitable_block": splitable,
        "split_falls": int(fields.get("split_falls", 1)) if splitable else None,
        "split_hook_mass_t": float(fields.get("split_hook_mass_t", 0.0)) if splitable else None,
        "hook_daf": float(fields.get("hook_daf", 1.0)),
        "offlead_deg": float(fields.get("offlead_deg", 0.0)),
        "sidelead_deg": float(fields.get("sidelead_deg", 0.0)),
    }


def segment_kwargs(fields: dict) -> dict:
    return {
        "from_node_id": str(fields.get("from_node_id", "")),
        "to_node_id": str(fields.get("to_node_id", "")),
        "mult": int(fields.get("mult", 1)),
    }
