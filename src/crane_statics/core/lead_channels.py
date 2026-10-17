"""Compose off-lead/side-lead cases from a zero-lead analysis point."""

from __future__ import annotations

from dataclasses import replace
import math

from ..calculation.engine import AnalysisPoint


def compose_lead_channel_point(
    pt: AnalysisPoint, offlead_deg: float, sidelead_deg: float
) -> AnalysisPoint:
    """Compose one lead-sign case from a zero-lead analysis point."""
    offlead_scale = math.sin(math.radians(float(offlead_deg)))
    sidelead_scale = math.sin(math.radians(float(sidelead_deg)))
    offlead_rope_channels = pt.offlead_lateral_unit_rope_tensions or {}
    offlead_reaction_channels = pt.offlead_lateral_unit_reactions or {}
    sidelead_reaction_channels = pt.sidelead_lateral_unit_reactions or {}

    sensitivity_ropes = {
        rope_id: float(sensitivity) + offlead_scale * float(offlead_rope_channels.get(rope_id, 0.0))
        for rope_id, sensitivity in pt.sensitivity_rope_tensions.items()
    }
    sensitivity_reactions: dict[str, dict[str, float]] = {}
    entity_ids = (
        set(pt.sensitivity_reactions)
        | set(offlead_reaction_channels)
        | set(sidelead_reaction_channels)
    )
    for entity_id in entity_ids:
        base_components = pt.sensitivity_reactions.get(entity_id, {})
        offlead_components = offlead_reaction_channels.get(entity_id, {})
        sidelead_components = sidelead_reaction_channels.get(entity_id, {})
        component_ids = set(base_components) | set(offlead_components) | set(sidelead_components)
        sensitivity_reactions[entity_id] = {
            component: float(base_components.get(component, 0.0))
            + offlead_scale * float(offlead_components.get(component, 0.0))
            + sidelead_scale * float(sidelead_components.get(component, 0.0))
            for component in component_ids
        }

    return replace(
        pt,
        sensitivity_rope_tensions=sensitivity_ropes,
        sensitivity_reactions=sensitivity_reactions,
    )
