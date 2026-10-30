"""Qt-free grouping and row building for the Load Chart design-limits table."""

from __future__ import annotations

from typing import Any, Optional

from crane_statics.core.session_model import DesignLimit
from crane_statics.data.models import CraneDocument
from crane_statics.presentation.formatters import (
    ConnectionFormatter,
    HoistFormatter,
    RopeFormatter,
)

_ROPES_GROUP_ID = "ropes"
_ROPES_GROUP_NAME = "Ropes"
_GROUP_OPEN = "▾ "
_GROUP_CLOSED = "▸ "
_UNCHECKED, _PARTLY_CHECKED, _CHECKED = 0, 1, 2

LimitMember = tuple[DesignLimit, str, str]
LimitGroup = tuple[str, str, list[LimitMember]]


def limit_groups(
    doc: Optional[CraneDocument], design_limits: list[DesignLimit]
) -> list[LimitGroup]:
    """Every limit as (group id, group name, [(limit, row name, unit)]), ropes first.

    Connection groups follow the canonical entity order, so the table reads the way
    the crane is built; entities the formatter does not know come last.
    """
    ropes: list[LimitMember] = []
    by_entity: dict[str, list[LimitMember]] = {}
    for dl in design_limits:
        if dl.kind == "rope":
            name = HoistFormatter.display_name_for_limit_id(dl.id, doc)
            ropes.append((dl, name, RopeFormatter.component_unit(dl.component)))
        else:
            name = ConnectionFormatter.component_display_name(dl.component)
            unit = ConnectionFormatter.component_unit(dl.component)
            by_entity.setdefault(dl.entity_id, []).append((dl, name, unit))

    ordered: list[str] = []
    for top in ConnectionFormatter.top_level_entities(list(by_entity)):
        ordered.append(top)
        ordered.extend(ConnectionFormatter.child_entities(top, list(by_entity)))
    ordered.extend(entity for entity in by_entity if entity not in ordered)

    groups: list[LimitGroup] = [(_ROPES_GROUP_ID, _ROPES_GROUP_NAME, ropes)] if ropes else []
    groups.extend(
        (f"connection:{entity}", ConnectionFormatter.display_name(entity), by_entity[entity])
        for entity in ordered
    )
    return groups


def limit_rows(
    groups: list[LimitGroup], filter_text: str, collapsed_groups: set[str]
) -> list[dict[str, Any]]:
    """The table's records: a header row per group, then its limits unless collapsed.

    A filter shows only the matching groups, open, and within a group whose name does
    not match, only the matching limits.
    """
    needle = filter_text.strip().casefold()
    rows: list[dict[str, Any]] = []
    for group_id, group_name, members in groups:
        if needle and needle not in group_name.casefold():
            members = [m for m in members if needle in f"{group_name} {m[1]}".casefold()]
        if not members:
            continue
        enabled = sum(1 for dl, _, _ in members if dl.enabled)
        if enabled == 0:
            state = _UNCHECKED
        elif enabled == len(members):
            state = _CHECKED
        else:
            state = _PARTLY_CHECKED
        expanded = bool(needle) or group_id not in collapsed_groups
        rows.append(
            {
                "isGroup": True,
                "groupId": group_id,
                "groupName": group_name,
                "limitId": "",
                "limitIds": [dl.id for dl, _, _ in members],
                "name": (_GROUP_OPEN if expanded else _GROUP_CLOSED) + group_name,
                "unit": "",
                "maxValue": "",
                "checkState": state,
                "tooltip": "",
            }
        )
        if not expanded:
            continue
        for dl, name, unit in members:
            rows.append(
                {
                    "isGroup": False,
                    "groupId": group_id,
                    "groupName": group_name,
                    "limitId": dl.id,
                    "limitIds": [dl.id],
                    "name": name,
                    "unit": unit,
                    "maxValue": "" if dl.max_kN is None else f"{float(dl.max_kN):.1f}",
                    "checkState": _CHECKED if dl.enabled else _UNCHECKED,
                    "tooltip": "",
                }
            )
    return rows
