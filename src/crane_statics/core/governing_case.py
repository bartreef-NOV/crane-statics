"""The governing case of one load-chart point, as Scene inputs.

A chart point is the worst case over vessel motion sign cases, slew, wind direction and
lead signs (``chart_envelope``). ``governing_case`` re-evaluates one point the way
``sweep.run_mode_sweep`` does and returns the case that produced it, so the Scene can
show it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

from ..calculation.engine import CraneCalculator
from ..calculation.rope_mass import active_hook_positions, hook_support_node_id
from ..calculation.solver.kinematics import KinematicsAdapter
from ..data.models import CraneDocument
from .analysis_cases import analysis_mode_by_name
from .chart_envelope import (
    _VESSEL_INPUT_FIELDS,
    EnvelopeCase,
    build_probes,
    envelope_capacity_case,
    lead_points,
)
from .demand_extraction import limit_responds_to_hook_load

# ``VesselInputs`` field -> ``SceneState`` field.
_SCENE_VESSEL_FIELDS = {vessel: scene for scene, vessel in _VESSEL_INPUT_FIELDS.items()}


@dataclass(frozen=True)
class GoverningCase:
    """The case behind one chart point: ``scene_fields`` are ``SceneState`` field values.

    ``mode_name`` is the chart mode the point was computed in ("normal" or "split"). The
    fields reproduce the chart value only under that mode's hook configuration, so the
    Scene must set ``HoistState.split_mode_active = (mode_name == "split")`` before it
    applies ``scene_fields``.
    """

    limit_id: str
    mode_name: str
    scene_fields: dict[str, Any]
    outreach_m: float


def governing_case(
    doc: CraneDocument,
    hoist_id: str,
    mode_name: str,
    enabled_limits: dict,
    outreach_m: float,
    limit_id: Optional[str],
) -> Optional[GoverningCase]:
    """The case of ``limit_id``'s chart point at ``outreach_m``, in mode ``mode_name``.

    ``limit_id`` None takes the combined curve: the limit of lowest hook load there (the
    first one on a tie). Returns None when the outreach is unreachable or does not solve,
    or the limit is unknown, unlimited or does not respond to the hook load (not plotted).
    The hook load is the chart value; for a magnitude limit, solving the case gives a
    capacity at most 0.1 % above it (see ``EnvelopeCase``).
    """
    hoist = next((h for h in doc.hoists if h.id == hoist_id), None)
    if hoist is None:
        return None
    mode = analysis_mode_by_name(hoist, mode_name)
    if mode.name != mode_name:
        return None  # split without a split block: run_mode_sweep has no curve either
    calc = CraneCalculator(doc)
    doc_dict = doc.model_dump()
    kin = KinematicsAdapter(doc_dict)
    wind_speed = float(doc.environment.max_wind_speed_m_s)
    vessel = doc.environment.vessel_motion
    offlead_deg = float(getattr(hoist, "offlead_deg", 0.0))
    sidelead_deg = float(getattr(hoist, "sidelead_deg", offlead_deg))

    candidates = [
        lid
        for lid, comps in enabled_limits.items()
        if any(comps.values()) and (limit_id is None or lid == limit_id)
    ]
    if not candidates:
        return None
    angle = kin.outreach_to_angle(outreach_m, hoist_id)
    if angle is None:
        return None
    probes = build_probes(calc, hoist_id, angle, wind_speed, mode.runtime_overrides, vessel=vessel)
    if probes is None:
        return None

    best: Optional[tuple[float, EnvelopeCase]] = None
    for lid in candidates:
        cap, case = envelope_capacity_case(
            calc,
            probes,
            {lid: enabled_limits[lid]},
            vessel=vessel,
            offlead_deg=offlead_deg,
            sidelead_deg=sidelead_deg,
            hook_daf=hoist.hook_daf,
            hook_mass_t=mode.hook_mass_t,
        )
        load_kN = float(cap.max_allowable_load_kN)
        if case is not None and (best is None or load_kN < best[0]):
            best = (load_kN, case)
    if best is None or not math.isfinite(best[0]):
        return None
    load_kN, case = best
    leads = lead_points(probes, offlead_deg, sidelead_deg)
    comps = enabled_limits[case.limit_id]
    if not any(limit_responds_to_hook_load(doc, pt, case.limit_id, comps) for pt in leads):
        return None
    tackle_m = _design_tackle_length_m(doc_dict, kin, hoist_id, angle)
    if tackle_m is None:
        return None

    fields: dict[str, Any] = {
        "boom_angle_deg": float(angle),
        # Hook force, as Auto-Set stores it (SceneViewModel, compute_auto_load).
        "hook_load_kN": load_kN,
        "hook_load_auto": False,
        "tackle_length_m": tackle_m,
        "offlead_deg": case.offlead_deg,
        "sidelead_deg": case.sidelead_deg,
        "wind_speed_m_s": wind_speed,
        # No wind axis: the limit does not respond to wind, any direction holds.
        "wind_direction": case.wind_axis or "+X",
        "crane_slewing_angle_deg": case.slew_deg,
    }
    fields.update(
        {_SCENE_VESSEL_FIELDS[name]: float(value) for name, value in case.vessel_inputs.items()}
    )
    return GoverningCase(
        limit_id=case.limit_id,
        mode_name=mode.name,
        scene_fields=fields,
        outreach_m=float(outreach_m),
    )


def _design_tackle_length_m(
    doc_dict: dict[str, Any], kin: KinematicsAdapter, hoist_id: str, angle: float
) -> Optional[float]:
    """The payout below the sheave at the sweep's hook position (``tackle_length_m=None``)."""
    hoist: dict[str, Any] = next(
        (h for h in doc_dict.get("hoists", []) if h.get("id") == hoist_id), {}
    )
    positions = active_hook_positions(
        doc_dict, hoist_id, kin.compute_all_node_positions(angle), None
    )
    hook = positions.get(str(hoist.get("load_node_id") or ""))
    support = positions.get(hook_support_node_id(doc_dict, hoist_id))
    if hook is None or support is None:
        return None
    return max(0.0, float(support["z"]) - float(hook["z"]))
