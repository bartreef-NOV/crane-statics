"""Canonical identifiers for rope and connection design-limit components."""

from __future__ import annotations

from enum import StrEnum


class LimitComponent(StrEnum):
    """Supported design-limit component identifiers."""

    T = "T"
    FX = "Fx"
    FY = "Fy"
    FZ = "Fz"
    M = "M"
    MX = "Mx"
    MY = "My"
    FRADIAL = "fradial"
    MRADIAL = "mradial"
    RESULTANT = "resultant"
    BOOM_AXIAL = "boom_axial"
    BOOM_NORMAL = "boom_normal"
    LEG_AXIAL = "leg_axial"
    LEG_NORMAL = "leg_normal"
    MAX_BEARING_LINE_LOAD = "max_bearing_line_load"


KNOWN_LIMIT_COMPONENTS = frozenset(component.value for component in LimitComponent)


def validate_limit_component(component: str) -> str:
    """Validate and normalize a design-limit component identifier."""
    normalized = str(component or "").strip()
    if normalized not in KNOWN_LIMIT_COMPONENTS:
        supported = ", ".join(sorted(KNOWN_LIMIT_COMPONENTS))
        raise ValueError(
            f"Unsupported design-limit component {normalized!r}; supported: {supported}"
        )
    return normalized
