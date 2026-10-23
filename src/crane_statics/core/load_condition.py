"""The environmental inputs one analysis runs under.

Today a document carries a single set of them (its ``environment``), so every analysis
runs under that one condition. Analyses read their wind speed and vessel-motion limits
through ``LoadCondition`` rather than from the document, so a document with several
conditions only has to say which one to use.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..data.models import CraneDocument, VesselMotion

DEFAULT_CONDITION_NAME = "default"


@dataclass(frozen=True)
class LoadCondition:
    """Wind speed and vessel-motion limits (± values) of one analysis condition."""

    name: str
    wind_speed_m_s: float
    vessel_motion: VesselMotion


def default_load_condition(doc: CraneDocument) -> LoadCondition:
    """The condition of the document's environment: what every analysis uses today."""
    return LoadCondition(
        name=DEFAULT_CONDITION_NAME,
        wind_speed_m_s=float(doc.environment.max_wind_speed_m_s),
        vessel_motion=doc.environment.vessel_motion,
    )
