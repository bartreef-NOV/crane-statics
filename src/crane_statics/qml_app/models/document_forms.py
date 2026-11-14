"""Qt-free conversions between document records and the dicts the model forms use.

``*_fields`` read a record into the form dict QML shows; ``*_kwargs`` read a submitted
form dict into the arguments of the matching ``core.document_edit.build_*`` function.
The environment helpers read and write the scalar settings on a ``CraneDocument``.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import ValidationError

from crane_statics.core.document_edit import TaggedChartPoint
from crane_statics.core.hoist_daf import daf_is_derived, shown_daf
from crane_statics.data import CraneDocument, payload_hoist_ids
from crane_statics.data.models import ConditionSpec
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
]
# The crane's pitch/roll reference point (``doc.motion_reference``); not a condition value.
MOTION_REFERENCE_KEYS = ["reference_x_m", "reference_z_m"]
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
        {key: float(getattr(doc.motion_reference, key)) for key in MOTION_REFERENCE_KEYS}
    )
    env_dict.update(
        {
            key: (float(raw) if (raw := getattr(doc.support_widths, key)) is not None else None)
            for key in SUPPORT_WIDTH_KEYS
        }
    )
    return EnvironmentSettings.from_dict(env_dict).to_dict()


# The environment values a document takes from itself. The wind speed and vessel motion
# it takes from its load conditions (``doc.conditions``): its environment carries runtime
# placeholders for them, which no analysis reads and nothing edits.
EDITABLE_ENVIRONMENT_KEYS = ("gravity_m_s2", "air_density_kg_m3")


def environment_from_conditions(doc: Optional[CraneDocument]) -> bool:
    """Whether wind speed and vessel motion come from the load conditions: for every
    document (with or without rules)."""
    return doc is not None


def set_environment_value(doc: CraneDocument, key: str, value: float) -> bool:
    """Set one scalar setting (gravity, air density, a support width, the motion reference
    point); False when the key is not one (the per-condition wind speed and vessel motion
    included) or the value is unchanged."""
    target: Any
    if key in EDITABLE_ENVIRONMENT_KEYS:
        target = doc.environment
    elif key in SUPPORT_WIDTH_KEYS:
        target = doc.support_widths
    elif key in MOTION_REFERENCE_KEYS:
        target = doc.motion_reference
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


# ----------------------------------------------------------------------
# Load conditions
# ----------------------------------------------------------------------

CONDITION_SCALAR_KEYS: tuple[str, ...] = (
    "wind_speed_m_s",
    "load_wind_area_m2",
    "load_drag_coefficient",
)
CONDITION_OPTIONAL_KEYS: tuple[str, ...] = (
    "significant_wave_height_m",
    "v_in_m_s",
    "v_t_m_s",
    "hook_height_override_m",
)
NEW_CONDITION_PREFIX = "condition_"


def editable_conditions(doc: Optional[CraneDocument]) -> dict[str, ConditionSpec]:
    """The load conditions of the document, in order (with or without rules)."""
    if doc is None:
        return {}
    return dict(doc.conditions)


def condition_fields(spec: ConditionSpec) -> dict:
    """One condition as a flat form dict; unset optional values stay ``None``."""
    fields: dict[str, Any] = {"name": spec.name, "lift": spec.lift}
    fields.update({key: float(getattr(spec, key)) for key in CONDITION_SCALAR_KEYS})
    fields.update({key: float(getattr(spec.vessel_motion, key)) for key in VESSEL_MOTION_KEYS})
    fields.update(
        {
            key: (None if (raw := getattr(spec, key)) is None else float(raw))
            for key in CONDITION_OPTIONAL_KEYS
        }
    )
    return fields


def _revalidated(spec: ConditionSpec, **changes: Any) -> ConditionSpec:
    """A copy of ``spec`` with ``changes``, validated as a new ``ConditionSpec``.

    A rejected value raises a ``ValueError`` of one short line (``field: message``), not
    pydantic's multi-line report, because the message is shown to the user as is.
    """
    try:
        return ConditionSpec.model_validate({**spec.model_dump(), **changes})
    except ValidationError as exc:
        first = exc.errors()[0]
        field = first["loc"][-1] if first["loc"] else ""
        raise ValueError(f"{field}: {first['msg']}" if field else first["msg"]) from None


def with_condition_value(spec: ConditionSpec, key: str, value: Optional[float]) -> ConditionSpec:
    """A re-validated copy of ``spec`` with one value replaced.

    ``value=None`` clears an optional key; any other key needs a number. Raises
    ``ValueError`` for an unknown key or a bad value.
    """
    if value is None and key not in CONDITION_OPTIONAL_KEYS:
        raise ValueError(f"{key} needs a value")
    number = None if value is None else float(value)
    if key in CONDITION_SCALAR_KEYS or key in CONDITION_OPTIONAL_KEYS:
        return _revalidated(spec, **{key: number})
    if key in VESSEL_MOTION_KEYS:
        motion = {**spec.vessel_motion.model_dump(), key: number}
        return _revalidated(spec, vessel_motion=motion)
    raise ValueError(f"Unknown condition field {key!r}")


def with_condition_lift(spec: ConditionSpec, lift: str) -> ConditionSpec:
    """A re-validated copy of ``spec`` with ``lift``; hidden offboard values are kept."""
    return _revalidated(spec, lift=str(lift))


def with_condition_name(spec: ConditionSpec, name: str) -> ConditionSpec:
    """A copy of ``spec`` named ``name`` (the editor checks the name)."""
    return _revalidated(spec, name=str(name))


def new_condition(existing: list[str], wind_speed_m_s: float) -> ConditionSpec:
    """An onboard condition named ``condition_<n>`` (first unused n), defaults elsewhere."""
    n = 1
    while f"{NEW_CONDITION_PREFIX}{n}" in existing:
        n += 1
    return ConditionSpec(name=f"{NEW_CONDITION_PREFIX}{n}", wind_speed_m_s=wind_speed_m_s)


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
    """One hoist as a flat form dict (its DAF and lead limits are per condition:
    ``condition_hoist_rows``)."""
    fields = {
        "id": hoist.id,
        "is_boom_hoist": is_boom_hoist,
        "support_node_id": hoist.support_node_id or hoist.load_node_id,
        "falls": int(hoist.falls or 1),
        "lower_block_mass_t": float(hoist.lower_block_mass_t),
        "linear_mass_kg_m": float(hoist.linear_mass_kg_m),
        "rope_length_m": None if hoist.rope_length_m is None else float(hoist.rope_length_m),
        "lowest_hook_height_m": float(hoist.lowest_hook_height_m or 0.0),
        "splitable_block": bool(hoist.splitable_block),
        "split_falls": int(hoist.split_falls or hoist.falls or 1),
        "split_lower_block_mass_t": float(
            hoist.split_lower_block_mass_t
            if hoist.split_lower_block_mass_t is not None
            else hoist.lower_block_mass_t
        ),
    }
    return fields


def rope_segment_fields(segment: Any) -> dict[str, Any]:
    return {
        "from_node_id": segment.from_node_id,
        "to_node_id": segment.to_node_id,
        "mult": int(segment.mult),
    }


def chart_point_fields(point: TaggedChartPoint) -> dict[str, Any]:
    """One load-chart point as the chart-point form dict, with the conditions it names."""
    return {
        "outreach_m": float(point.outreach_m),
        "load_t": float(point.load_t),
        "conditions": list(point.conditions),
    }


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
        "lower_block_mass_t": float(fields.get("lower_block_mass_t", 0.0)),
        "linear_mass_kg_m": max(0.0, float(fields.get("linear_mass_kg_m", 0.0))),
        "lowest_hook_height_m": float(fields.get("lowest_hook_height_m", 0.0)),
        "splitable_block": splitable,
        "split_falls": int(fields.get("split_falls", 1)) if splitable else None,
        "split_lower_block_mass_t": (
            float(fields.get("split_lower_block_mass_t", 0.0)) if splitable else None
        ),
    }


def chart_point_conditions(fields: dict) -> Optional[list[str]]:
    """The condition names a submitted chart-point form carries; None when it carries
    none (the editor's default applies)."""
    names = fields.get("conditions")
    if names is None:
        return None
    return [str(name) for name in names]


# ----------------------------------------------------------------------
# Per-condition hoist table and the tagged load chart
# ----------------------------------------------------------------------


def condition_hoist_rows(doc: Optional[CraneDocument], spec: Optional[ConditionSpec]) -> list:
    """One row per payload hoist (document order) for the hoist table of condition ``spec``.

    ``usable``: the condition lists the hoist; then ``offleadDeg``/``sideleadDeg`` are its
    lead limits there and ``daf`` the authored factor (None: no override). ``dafDerived``
    is True under rules when the factor is derived from the standard (``dafShown`` None,
    the view shows a placeholder); otherwise ``dafShown`` is the factor that applies. A
    row of a hoist the condition does not list carries None for the values.
    """
    if doc is None or spec is None:
        return []
    rows = []
    for hoist_id in payload_hoist_ids(doc):
        entry = spec.hoists.get(hoist_id)
        if entry is None:
            rows.append(
                {
                    "hoistId": hoist_id,
                    "usable": False,
                    "offleadDeg": None,
                    "sideleadDeg": None,
                    "daf": None,
                    "dafShown": None,
                    "dafDerived": False,
                }
            )
            continue
        derived = daf_is_derived(doc, entry.daf)
        rows.append(
            {
                "hoistId": hoist_id,
                "usable": True,
                "offleadDeg": float(entry.offlead_deg),
                "sideleadDeg": float(entry.sidelead_deg),
                "daf": None if entry.daf is None else float(entry.daf),
                "dafShown": None if derived else shown_daf(entry.daf),
                "dafDerived": derived,
            }
        )
    return rows


def entered_daf_value(value: Any) -> Optional[float]:
    """A DAF entered in the per-condition hoist table as a number; None, "" or an
    undefined QML value clear the override (the editor stores it: ``enter_condition_hoist``)."""
    if value is None or value == "":
        return None
    return float(value)


def chart_point_rows(points: list[TaggedChartPoint]) -> list[dict[str, Any]]:
    """One row per authored load-chart point: its index, outreach, load and the names of
    the conditions it applies to (``DocumentEditor.tagged_chart``)."""
    return [
        {
            "index": index,
            "outreachM": float(point.outreach_m),
            "loadT": float(point.load_t),
            "conditions": list(point.conditions),
        }
        for index, point in enumerate(points)
    ]


def segment_kwargs(fields: dict) -> dict:
    return {
        "from_node_id": str(fields.get("from_node_id", "")),
        "to_node_id": str(fields.get("to_node_id", "")),
        "mult": int(fields.get("mult", 1)),
    }
