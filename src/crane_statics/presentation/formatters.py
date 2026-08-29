"""Formatters: domain/analysis entities → QML-consumable display dicts.

This module consolidates display logic that was previously scattered across
display_names.py, report_rows.py, and document_models.py. Each formatter
is pure (no side effects, no Qt dependencies) and fully testable without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Optional

from crane_statics.core.results import ResultRow
from crane_statics.data import CraneDocument

_MANAGED_HOOK_PREFIX = "__hook__"


def _entity_field(entity: Any, name: str) -> str:
    """Read one field from an authored entity or its serialized form.

    Callers working from ``model_dump()`` output must resolve the same display
    names as callers holding the document, so entity lookups go through here
    rather than assuming attributes.
    """
    value = entity.get(name) if isinstance(entity, Mapping) else getattr(entity, name, "")
    return str(value or "").strip()


@dataclass(frozen=True)
class Column:
    """Column specification for table display."""

    name: str
    accessor: Any  # Callable[[object], Any] but avoid import for circular dep
    decimals: Optional[int] = None

    def format(self, record: Any) -> str:
        value = self.accessor(record)
        if value is None:
            return ""
        if isinstance(value, bool):
            return str(value)
        if isinstance(value, (int, float)):
            decimals = self.decimals if self.decimals is not None else 1
            return f"{float(value):.{decimals}f}"
        return str(value)


# ============================================================================
# ROPE FORMATTING
# ============================================================================


class RopeFormatter:
    """Formats rope entities and components for display."""

    @staticmethod
    def display_name(rope_id: str) -> str:
        """Human-readable rope identifier."""
        rid = str(rope_id or "").strip()
        if rid.endswith("__rope"):
            return rid[:-6]
        if rid.endswith("_rope"):
            return rid[:-5]
        return rid

    @staticmethod
    def component_unit(component: str = "T") -> str:
        """Unit for rope component (always kN)."""
        return "kN"


def node_display_name(node_id: str) -> str:
    """Return a display label for a scene node or managed hook node."""
    normalized_id = str(node_id or "").strip()
    if not normalized_id:
        return normalized_id
    if normalized_id.startswith(_MANAGED_HOOK_PREFIX):
        hoist_id = normalized_id[len(_MANAGED_HOOK_PREFIX) :].strip()
        return f"Hook ({hoist_id})" if hoist_id else "Hook"
    return normalized_id


# ============================================================================
# CONNECTION FORMATTING
# ============================================================================


class ConnectionFormatter:
    """Formats connection points and components for display."""

    _ENTITY_LABELS = {
        "heel_point": "Heel Point",
        "heel_left": "Heel Left",
        "heel_right": "Heel Right",
        "upper_hinge": "Upper Hinge",
        "rear_hinge": "Rear Hinge",
        "front_hinge": "Front Hinge",
        "platform_base": "Platform Base",
    }

    _COMPONENT_LABELS = {
        "Fx": "Fx",
        "Fy": "Fy",
        "Fz": "Fz",
        "M": "M",
        "Mx": "Mx",
        "My": "My",
        "fradial": "Fradial",
        "mradial": "Mradial",
        "resultant": "Resultant",
        "boom_axial": "Boom Axial",
        "boom_normal": "Boom Normal",
        "leg_axial": "Leg Axial",
        "leg_normal": "Leg Normal",
        "max_bearing_line_load": "Bearing Line Load",
    }

    _COMPONENT_UNITS = {
        "Fx": "kN",
        "Fy": "kN",
        "Fz": "kN",
        "M": "kNm",
        "Mx": "kNm",
        "My": "kNm",
        "fradial": "kN",
        "mradial": "kNm",
        "resultant": "kN",
        "boom_axial": "kN",
        "boom_normal": "kN",
        "leg_axial": "kN",
        "leg_normal": "kN",
        "max_bearing_line_load": "kN/m",
    }

    _TOP_LEVEL_ORDER = (
        "platform_base",
        "heel_point",
        "front_hinge",
        "rear_hinge",
        "upper_hinge",
    )

    _CHILDREN_BY_PARENT = {
        "heel_point": ("heel_left", "heel_right"),
    }

    _CHILD_LABELS = {
        "heel_left": "Left",
        "heel_right": "Right",
    }

    @staticmethod
    def display_name(entity_id: str) -> str:
        """Human-readable connection entity label."""
        return ConnectionFormatter._ENTITY_LABELS.get(str(entity_id or ""), str(entity_id or ""))

    @staticmethod
    def component_display_name(component: str) -> str:
        """Human-readable component label (e.g., Fx → "Fx")."""
        return ConnectionFormatter._COMPONENT_LABELS.get(str(component or ""), str(component or ""))

    @staticmethod
    def component_unit(component: str) -> str:
        """Unit for connection component (kN, kNm, etc.)."""
        return ConnectionFormatter._COMPONENT_UNITS.get(str(component or ""), "kN")

    @staticmethod
    def format_label(entity_id: str, component: str) -> str:
        """Format as 'Entity / Component' for display."""
        return (
            f"{ConnectionFormatter.display_name(entity_id)} / "
            f"{ConnectionFormatter.component_display_name(component)}"
        )

    @staticmethod
    def child_display_name(entity_id: str) -> str:
        """Compact child label (e.g., 'Left' for heel_left)."""
        eid = str(entity_id or "")
        return ConnectionFormatter._CHILD_LABELS.get(eid, ConnectionFormatter.display_name(eid))

    @staticmethod
    def top_level_entities(entity_ids: list[str] | set[str] | tuple[str, ...]) -> list[str]:
        """Return connection top-level entities in canonical display order."""
        present = {str(e or "") for e in entity_ids}
        return [eid for eid in ConnectionFormatter._TOP_LEVEL_ORDER if eid in present]

    @staticmethod
    def child_entities(
        parent_entity_id: str, entity_ids: list[str] | set[str] | tuple[str, ...]
    ) -> list[str]:
        """Return child entities for a parent, filtered by currently present IDs."""
        present = {str(e or "") for e in entity_ids}
        children = ConnectionFormatter._CHILDREN_BY_PARENT.get(str(parent_entity_id or ""), ())
        return [eid for eid in children if eid in present]

    @staticmethod
    def formula_tooltip(component: str) -> str:
        """Formula/computation explanation for result rows."""
        tooltips = {
            "resultant": "Resultant = sqrt(Fx^2 + Fz^2)",
            "fradial": "Fradial = sqrt(Fx^2 + Fy^2)",
            "mradial": "Mradial = sqrt(Mx^2 + My^2)",
            "max_bearing_line_load": (
                "Bearing Line Load = Fz/(pi*D) + 4*sqrt(Mx^2 + My^2)/(pi*D^2), "
                "where D is slewing bearing diameter"
            ),
        }
        return tooltips.get(str(component or ""), "")


# ============================================================================
# HOIST FORMATTING
# ============================================================================


class HoistFormatter:
    """Formats hoist entities and table columns."""

    @staticmethod
    def display_name(
        hoist_id: str,
        doc: Optional[CraneDocument] = None,
        *,
        hoists: Optional[Iterable[Any]] = None,
    ) -> str:
        """Return a human-readable hoist identifier, resolving rope IDs when possible.

        Resolves against ``doc``, or against ``hoists`` when the caller only holds a
        serialized document. Either route gives the same name; without one, the
        suffix heuristics below are the fallback.
        """
        hid = str(hoist_id or "").strip()
        if not hid:
            return hid

        candidates = getattr(doc, "hoists", ()) if doc is not None else (hoists or ())
        for hoist in candidates:
            if _entity_field(hoist, "rope_id") == hid:
                resolved_id = _entity_field(hoist, "id")
                if resolved_id:
                    return resolved_id

        if hid.endswith("__rope"):
            return hid[:-6]
        if hid.endswith("_rope"):
            return hid[:-5]
        if hid == "boom_hoist":
            return "BH"
        return hid

    @staticmethod
    def runtime_rope_channel_to_rope_id(rope_channel_id: str, doc: Optional[CraneDocument]) -> str:
        """Map an internal rope channel to its canonical runtime rope ID."""
        rope_id = str(rope_channel_id or "").strip()
        if rope_id != "boom_hoist" or doc is None:
            return rope_id

        for rope in getattr(doc, "ropes", []):
            if str(getattr(rope, "tension_mode", "") or "") == "solve":
                solved_rope_id = str(getattr(rope, "id", "") or "").strip()
                if solved_rope_id:
                    return solved_rope_id
        return rope_id

    @staticmethod
    def display_name_for_rope_channel(rope_channel_id: str, doc: Optional[CraneDocument]) -> str:
        """Return the display name for an internal rope channel."""
        return HoistFormatter.display_name(
            HoistFormatter.runtime_rope_channel_to_rope_id(rope_channel_id, doc),
            doc,
        )

    @staticmethod
    def display_name_for_limit_id(limit_id: str, doc: Optional[CraneDocument]) -> str:
        """Return the display name for a rope or connection limit ID."""
        normalized_id = str(limit_id or "").strip()
        rope_id = normalized_id[:-2] if normalized_id.endswith("_T") else normalized_id
        return HoistFormatter.display_name(rope_id, doc)

    @staticmethod
    def mode_label(mode: str) -> str:
        """Display label for chart/hook mode."""
        normalized = str(mode or "").lower()
        return "Split" if normalized == "split" else "Normal"

    @staticmethod
    def table_columns(
        is_boom_hoist: Optional[Callable[[Any], bool]] = None,
    ) -> list[Column]:
        """Column definitions for hoist table."""

        def payload_value(getter: Callable[[Any], Any]) -> Callable[[Any], Any]:
            return lambda hoist: None if is_boom_hoist and is_boom_hoist(hoist) else getter(hoist)

        return [
            Column("ID", lambda h: h.id),
            Column("Support Node", payload_value(lambda h: h.support_node_id)),
            Column("Falls", payload_value(lambda h: h.falls), decimals=1),
            Column(
                "Hook Mass (t)",
                payload_value(lambda h: h.hook_mass_t),
                decimals=3,
            ),
            Column("Linear Mass (kg/m)", lambda h: h.linear_mass_kg_m, decimals=3),
            Column("Rope Length (m)", lambda h: h.rope_length_m, decimals=3),
            Column(
                "Splittable",
                payload_value(lambda h: h.splitable_block),
            ),
            Column("Split Falls", payload_value(lambda h: h.split_falls), decimals=1),
            Column(
                "Split Hook Mass (t)",
                payload_value(lambda h: h.split_hook_mass_t),
                decimals=3,
            ),
            Column(
                "DAF",
                payload_value(lambda h: h.hook_daf),
                decimals=3,
            ),
            Column(
                "Off Lead (deg)",
                payload_value(lambda h: h.offlead_deg),
                decimals=3,
            ),
            Column(
                "Side Lead (deg)",
                payload_value(lambda h: h.side_lead_deg),
                decimals=3,
            ),
            Column(
                "Min Hook Travel (m)",
                payload_value(lambda h: h.min_hook_travel_m),
                decimals=3,
            ),
            Column(
                "Max Hook Travel (m)",
                payload_value(lambda h: h.max_hook_travel_m),
                decimals=3,
            ),
        ]


# ============================================================================
# ENVIRONMENT FORMATTING
# ============================================================================


class EnvironmentFormatter:
    """Formats environment and vessel motion properties."""

    _PROPERTY_LABELS = {
        "gravity_m_s2": "Gravity (m/s²)",
        "max_wind_speed_m_s": "Max Wind Speed (m/s)",
        "wind_reference_height_m_asl": "Wind Ref Height (m ASL)",
        "air_density_kg_m3": "Air Density (kg/m³)",
        "wind_profile_exponent": "Wind Profile Exponent",
        "mean_sealevel_z_m": "Mean Sea Level Z (m)",
        "accel_x_m_s2": "Accel X (m/s²)",
        "accel_y_m_s2": "Accel Y (m/s²)",
        "accel_z_m_s2": "Accel Z (m/s²)",
        "roll_angular_accel_rad_s2": "Roll Accel (rad/s²)",
        "pitch_angular_accel_rad_s2": "Pitch Accel (rad/s²)",
        "reference_x_m": "Reference X (m)",
        "reference_z_m": "Reference Z (m)",
        "boom_width_m": "Boom Width (m)",
        "slewing_bearing_diameter_m": "Slewing Bearing Diameter (m)",
    }

    @staticmethod
    def property_label(key: str) -> str:
        """Human-readable property label."""
        return EnvironmentFormatter._PROPERTY_LABELS.get(str(key or ""), str(key or ""))

    @staticmethod
    def property_value_display(key: str, value: float) -> str:
        """Formatted property value for display."""
        if value is None:
            return ""
        return f"{float(value):.3f}"


# ============================================================================
# RESULT ROW FORMATTING
# ============================================================================


class ResultRowFormatter:
    """Formats analysis result rows for display tables."""

    @staticmethod
    def utilization_state(utilization_pct: Optional[float]) -> str:
        """Semantic state for utilization display (none, pass, warn, fail)."""
        if utilization_pct is None:
            return "none"
        if utilization_pct > 100.0:
            return "fail"
        if utilization_pct >= 90.0:
            return "warn"
        return "pass"

    @staticmethod
    def is_clickable(row: ResultRow) -> bool:
        """Determine if a result row should be clickable (selectable)."""
        return (
            row.limit_kN is not None
            and not row.is_group_header
            and row.kind in {"rope", "connection"}
            and bool(row.entity_id)
        )

    @staticmethod
    def result_row_payload(row: ResultRow) -> dict[str, Any]:
        """Extract result row data for event payloads."""
        return {
            "kind": row.kind,
            "entity_id": row.entity_id,
            "component": row.component,
            "runtime_id": row.runtime_id,
            "row_name": row.name,
            "unit": row.unit,
            "demand_kN": float(row.demand_kN),
            "limit_kN": None if row.limit_kN is None else float(row.limit_kN),
            "utilization_pct": (
                None if row.utilization_pct is None else float(row.utilization_pct)
            ),
        }

    @staticmethod
    def result_rows_to_dicts(rows: list[ResultRow]) -> list[dict[str, Any]]:
        """Transform analysis ResultRows into QML-consumable dicts."""
        out: list[dict[str, Any]] = []
        for row in rows:
            if row.is_group_header:
                out.append(
                    {
                        "name": row.name.strip(),
                        "unit": "",
                        "demand": "",
                        "limit": "",
                        "utilization": "",
                        "utilizationValue": 0.0,
                        "utilState": "none",
                        "isGroupHeader": True,
                        "nested": row.name.startswith("  "),
                        "clickable": False,
                        "tooltip": "",
                    }
                )
                continue

            util = row.utilization_pct if row.limit_kN is not None else None
            out.append(
                {
                    "name": row.name,
                    "unit": str(row.unit or ""),
                    "demand": f"{row.demand_kN:.1f}",
                    "limit": ("-" if row.limit_kN is None else f"{row.limit_kN:.1f}"),
                    "utilization": "-" if util is None else f"{util:.0f}%",
                    "utilizationValue": (
                        0.0 if util is None else max(0.0, min(100.0, float(util)))
                    ),
                    "utilState": ResultRowFormatter.utilization_state(util),
                    "isGroupHeader": False,
                    "nested": False,
                    "clickable": ResultRowFormatter.is_clickable(row),
                    "tooltip": ConnectionFormatter.formula_tooltip(str(row.component or "")),
                }
            )
        return out

    @staticmethod
    def report_rows_to_dicts(report: dict) -> list[dict[str, Any]]:
        """Transform equilibrium/load-summary report into displayable rows."""
        if not report.get("available"):
            return [
                {
                    "label": report.get("message", "Unavailable"),
                    "kind": "message",
                    "passed": False,
                    "fx": "",
                    "fz": "",
                    "magnitude": "",
                    "posX": "",
                    "posZ": "",
                    "moment": "",
                }
            ]

        rows: list[dict[str, Any]] = []
        for section in report.get("sections", []):
            rows.append(
                {
                    "label": section["name"],
                    "kind": "section",
                    "passed": bool(section.get("passed")),
                    "fx": ResultRowFormatter._format_number(section.get("sum_fx")),
                    "fz": ResultRowFormatter._format_number(section.get("sum_fz")),
                    "moment": ResultRowFormatter._format_number(section.get("sum_m")),
                    "magnitude": "",
                    "posX": "",
                    "posZ": "",
                }
            )
            for category in section.get("categories", []):
                rows.append(
                    {
                        "label": f"  {category['name']}",
                        "kind": "category",
                        "passed": True,
                        "fx": ResultRowFormatter._format_number(category.get("sum_fx")),
                        "fz": ResultRowFormatter._format_number(category.get("sum_fz")),
                        "moment": ResultRowFormatter._format_number(category.get("sum_m")),
                        "magnitude": "",
                        "posX": "",
                        "posZ": "",
                    }
                )
                for entry in category.get("rows", []):
                    rows.append(
                        {
                            "label": f"    {entry['label']}",
                            "kind": "row",
                            "passed": True,
                            "fx": ResultRowFormatter._format_number(entry.get("fx")),
                            "fz": ResultRowFormatter._format_number(entry.get("fz")),
                            "magnitude": ResultRowFormatter._format_number(entry.get("magnitude")),
                            "posX": ResultRowFormatter._format_number(entry.get("x")),
                            "posZ": ResultRowFormatter._format_number(entry.get("z")),
                            "moment": ResultRowFormatter._format_number(entry.get("moment")),
                        }
                    )
        return rows

    @staticmethod
    def _format_number(value: Any) -> str:
        """Format a numeric value for display (or empty string if None)."""
        return "" if value is None else f"{float(value):.1f}"


# ============================================================================
# COMPONENT TABLE COLUMNS
# ============================================================================


class ComponentTableFormatter:
    """Formats component table columns (nodes, mass points, wind areas, segments)."""

    _BOOM_BODY_ID = "boom"

    @staticmethod
    def node_columns(body_id: str) -> list[Column]:
        """Column definitions for node table.

        Args:
            body_id: Body identifier (determines coordinate system)
        """
        if body_id == ComponentTableFormatter._BOOM_BODY_ID:
            # Boom uses boom-local U/W coordinates
            return [
                Column("ID", lambda n: n.id),
                Column("U (m)", lambda n: n.local_x_m, decimals=3),
                Column("W (m)", lambda n: n.local_z_m, decimals=3),
            ]
        # Other bodies use global X/Z coordinates
        return [
            Column("ID", lambda n: n.id),
            Column("X (m)", lambda n: n.x_m, decimals=3),
            Column("Z (m)", lambda n: n.z_m, decimals=3),
        ]

    @staticmethod
    def mass_point_columns(body_id: str) -> list[Column]:
        """Column definitions for mass point table."""
        if body_id == ComponentTableFormatter._BOOM_BODY_ID:
            return [
                Column("ID", lambda m: m.id),
                Column("Mass (t)", lambda m: m.mass_t, decimals=3),
                Column("U (m)", lambda m: m.local_x_m, decimals=3),
                Column("V (m)", lambda m: m.local_y_m, decimals=3),
                Column("W (m)", lambda m: m.local_z_m, decimals=3),
            ]
        return [
            Column("ID", lambda m: m.id),
            Column("Mass (t)", lambda m: m.mass_t, decimals=3),
            Column("X (m)", lambda m: m.x_m, decimals=3),
            Column("Y (m)", lambda m: m.y_m, decimals=3),
            Column("Z (m)", lambda m: m.z_m, decimals=3),
        ]

    @staticmethod
    def wind_area_columns(body_id: str) -> list[Column]:
        """Column definitions for wind area table."""
        if body_id == ComponentTableFormatter._BOOM_BODY_ID:
            return [
                Column("ID", lambda w: w.id),
                Column("Area X (m²)", lambda w: w.area_w_m2, decimals=3),
                Column("Area Y (m²)", lambda w: w.area_v_m2, decimals=3),
                Column("U (m)", lambda w: w.local_x_m, decimals=3),
                Column("W (m)", lambda w: w.local_z_m, decimals=3),
                Column("Cd", lambda w: w.cd, decimals=3),
            ]
        return [
            Column("ID", lambda w: w.id),
            Column("Area X (m²)", lambda w: w.area_w_m2, decimals=3),
            Column("Area Y (m²)", lambda w: w.area_v_m2, decimals=3),
            Column("X (m)", lambda w: w.x_m, decimals=3),
            Column("Z (m)", lambda w: w.z_m, decimals=3),
            Column("Cd", lambda w: w.cd, decimals=3),
        ]

    @staticmethod
    def rope_segment_columns() -> list[Column]:
        """Column definitions for rope segment table."""
        return [
            Column("From Node", lambda s: s.from_node_id),
            Column("To Node", lambda s: s.to_node_id),
            Column("Mult", lambda s: s.mult, decimals=1),
        ]

    @staticmethod
    def contractual_columns() -> list[Column]:
        """Column definitions for contractual point table."""
        return [
            Column("Outreach (m)", lambda c: c.outreach_m, decimals=3),
            Column("Load (t)", lambda c: c.load_t, decimals=3),
        ]
