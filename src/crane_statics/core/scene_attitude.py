"""A document as the Scene sees it: the same model at a heel and trim of its own.

The Scene may try a static attitude other than the document's design condition.
These copies carry it into the Scene's own solve and drawing, and nowhere else:
both are shallow, replacing only ``environment.vessel_motion``'s heel and trim, so
the saved document and every cached serialization of it stay untouched.
"""

from __future__ import annotations

from typing import Any, Mapping

from crane_statics.data import CraneDocument

from ..calculation.vessel_attitude import VesselAttitude


def document_with_attitude(document: CraneDocument, attitude: VesselAttitude) -> CraneDocument:
    """``document`` at ``attitude``, sharing everything else with the original."""
    environment = document.environment
    vessel_motion = environment.vessel_motion.model_copy(
        update={"heel_deg": float(attitude.heel_deg), "trim_deg": float(attitude.trim_deg)}
    )
    return document.model_copy(
        update={"environment": environment.model_copy(update={"vessel_motion": vessel_motion})}
    )


def document_dict_with_attitude(
    document_dict: Mapping[str, Any], attitude: VesselAttitude
) -> dict[str, Any]:
    """A serialized document at ``attitude``, sharing everything else with the original."""
    environment = dict(document_dict.get("environment") or {})
    vessel_motion = dict(environment.get("vessel_motion") or {})
    vessel_motion["heel_deg"] = float(attitude.heel_deg)
    vessel_motion["trim_deg"] = float(attitude.trim_deg)
    environment["vessel_motion"] = vessel_motion
    return {**document_dict, "environment": environment}
