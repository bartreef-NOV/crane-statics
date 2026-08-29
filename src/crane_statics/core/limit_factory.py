"""Factory for constructing design-limit catalogs from crane documents."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .limit_auto_set import compute_required_rope_capacity_kN
from .limit_components import validate_limit_component

if TYPE_CHECKING:
    from crane_statics.data import CraneDocument
    from .session_model import DesignLimit


class DesignLimitFactory:
    """Build canonical design-limit catalogs for crane documents."""

    @staticmethod
    def create_for_document(doc: CraneDocument) -> list[DesignLimit]:
        """Generate the default design-limit catalog for a document."""
        from .session_model import DesignLimit  # Import here to avoid circular dependency

        limits: list[DesignLimit] = []

        # Rope tension limits
        for rope in doc.ropes:
            required_capacity = compute_required_rope_capacity_kN(doc, rope.id).required_kN
            limits.append(
                DesignLimit(
                    id=f"{rope.id}_T",
                    kind="rope",
                    entity_id=rope.id,
                    component="T",
                    max_kN=required_capacity,
                    enabled=required_capacity is not None,
                )
            )

        # Connection force and moment limits
        pinned = {"rear_hinge", "front_hinge", "heel_point", "upper_hinge"}
        for connection_id in [
            "rear_hinge",
            "front_hinge",
            "heel_point",
            "upper_hinge",
            "platform_base",
        ]:
            components = (
                ["Fx", "Fy", "Fz", "Mx", "My", "fradial", "mradial"]
                if connection_id == "platform_base"
                else ["Fx", "Fz", "M", "resultant"]
            )
            for component in components:
                if component == "M" and connection_id in pinned:
                    continue
                limits.append(
                    DesignLimit(
                        id=f"{connection_id}_{component}",
                        kind="connection",
                        entity_id=connection_id,
                        component=component,
                    )
                )

            # Platform-specific limits
            if connection_id == "platform_base":
                limits.append(
                    DesignLimit(
                        id=f"{connection_id}_max_bearing_line_load",
                        kind="connection",
                        entity_id=connection_id,
                        component="max_bearing_line_load",
                    )
                )

            # Heel-point boom and axial limits
            if connection_id == "heel_point":
                for component in ["boom_axial", "boom_normal"]:
                    limits.append(
                        DesignLimit(
                            id=f"{connection_id}_{component}",
                            kind="connection",
                            entity_id=connection_id,
                            component=component,
                        )
                    )

            # Leg-pin limits
            if connection_id in {"front_hinge", "rear_hinge"}:
                for component in ["leg_axial", "leg_normal"]:
                    limits.append(
                        DesignLimit(
                            id=f"{connection_id}_{component}",
                            kind="connection",
                            entity_id=connection_id,
                            component=component,
                        )
                    )

        # Heel support limits
        for connection_id in ["heel_left", "heel_right"]:
            for component in ["Fx", "Fz", "resultant", "boom_axial", "boom_normal"]:
                limits.append(
                    DesignLimit(
                        id=f"{connection_id}_{component}",
                        kind="connection",
                        entity_id=connection_id,
                        component=component,
                    )
                )

        # Normalize and deduplicate
        for limit in limits:
            limit.component = validate_limit_component(limit.component)

        return limits

    @staticmethod
    def index_by_id(limits: list[DesignLimit]) -> dict[str, DesignLimit]:
        """Create a lookup dictionary keyed by limit ID."""
        return {limit.id: limit for limit in limits}
