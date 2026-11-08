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
from ..calculation.results import HookLateral
from ..calculation.rope_mass import active_hook_positions, hook_support_node_id
from ..calculation.solver.kinematics import KinematicsAdapter
from ..data.models import CraneDocument
from .analysis_cases import analysis_mode_by_name
from .chart_envelope import (
    VESSEL_INPUT_FIELDS,
    EnvelopeCase,
    ProbeSet,
    build_probes,
    envelope_capacity_case,
    lead_points,
)
from .demand_extraction import limit_responds_to_hook_load
from .lift_factor import LiftFactors, amplified_rope_hoist_id, hook_lateral
from .load_condition import LoadCondition, condition_cases, condition_document

# ``VesselInputs`` field -> ``SceneState`` field.
_SCENE_VESSEL_FIELDS = {vessel: scene for scene, vessel in VESSEL_INPUT_FIELDS.items()}


@dataclass(frozen=True)
class GoverningCase:
    """The case behind one chart point: ``scene_fields`` are ``SceneState`` field values.

    ``mode_name`` is the chart mode the point was computed in ("normal" or "split"). The
    fields reproduce the chart value only under that mode's hook configuration, so the
    Scene must set ``HoistState.split_mode_active = (mode_name == "split")`` before it
    applies ``scene_fields``.

    ``condition_name`` and ``case_name`` name the load condition and its profile case
    that governed (``LoadCondition.spec.name`` and ``.case.name``); None on a legacy
    document.
    """

    limit_id: str
    mode_name: str
    scene_fields: dict[str, Any]
    outreach_m: float
    condition_name: Optional[str] = None
    case_name: Optional[str] = None


def governing_case(
    doc: CraneDocument,
    hoist_id: str,
    mode_name: str,
    enabled_limits: dict,
    outreach_m: float,
    limit_id: Optional[str],
    condition_name: Optional[str] = None,
) -> Optional[GoverningCase]:
    """The case of ``limit_id``'s chart point at ``outreach_m``, in mode ``mode_name``.

    ``condition_name`` is the chart's load condition, as ``run_mode_sweep`` takes it; the
    case is searched over every case of that condition, each with its own dynamic factor
    (``lift_factor``), as the sweep does: the lowest payload wins, then the lowest hook
    load, then the first one. An unknown name raises ``KeyError``.

    ``limit_id`` None takes the combined curve: the limit of lowest hook load there (the
    first one on a tie). Returns None when the outreach is unreachable or does not solve,
    or the limit is unknown, unlimited or does not respond to the hook load (not plotted).
    The hook load is the chart value; for a magnitude limit, solving the case gives a
    capacity at most 0.1 % above it (see ``EnvelopeCase``).
    """
    conditions = condition_cases(doc, condition_name)
    hoist = next((h for h in doc.hoists if h.id == hoist_id), None)
    if hoist is None:
        return None
    mode = analysis_mode_by_name(hoist, mode_name)
    if mode.name != mode_name:
        return None  # split without a split block: run_mode_sweep has no curve either
    doc_dict = doc.model_dump()
    kin = KinematicsAdapter(doc_dict)
    offlead_deg = float(getattr(hoist, "offlead_deg", 0.0))
    sidelead_deg = float(getattr(hoist, "sidelead_deg", 0.0))

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

    # ((payload, hook load), envelope case, probes, condition, lateral) of the lowest limit
    # over the cases. Within a case the factor is one, so the hook load orders as the
    # payload does; it breaks payload ties, which keeps the legacy (hook load) choice exactly.
    best: Optional[
        tuple[tuple[float, float], EnvelopeCase, ProbeSet, LoadCondition, Optional[HookLateral]]
    ] = None
    lift: Optional[LiftFactors] = None
    for condition in conditions:
        calc = CraneCalculator(condition_document(doc, condition))
        if lift is None:
            lift = LiftFactors(doc, calc)
        vessel = condition.vessel_motion
        probes = build_probes(
            calc,
            hoist_id,
            angle,
            condition.wind_speed_m_s,
            mode.runtime_overrides,
            vessel=vessel,
            amplified_rope_hoist_id=amplified_rope_hoist_id(condition, hoist_id),
        )
        if probes is None:
            return None  # run_mode_sweep has no point where a case does not solve
        setup = lift.setup(condition, hoist_id, mode, angle, probes.zero)
        factor = setup.factor
        lateral = (
            None
            if condition.spec is None
            else hook_lateral(
                setup, condition.wind_speed_m_s, support_z_m=lift.support_z_m(hoist_id, angle)
            )
        )
        scales = lift.demand_scales(condition, hoist_id, mode, angle, setup)
        for lid in candidates:
            cap, case = envelope_capacity_case(
                calc,
                probes,
                {lid: enabled_limits[lid]},
                vessel=vessel,
                offlead_deg=offlead_deg,
                sidelead_deg=sidelead_deg,
                hook_daf=factor,
                hook_mass_t=mode.hook_mass_t,
                hook_lateral=lateral,
                demand_scale=scales,
            )
            rank = (float(cap.max_allowable_load_t), float(cap.max_allowable_load_kN))
            if case is not None and (best is None or rank < best[0]):
                best = (rank, case, probes, condition, lateral)
    if best is None or not math.isfinite(best[0][1]):
        return None
    (_load_t, load_kN), case, probes, condition, lateral = best
    wind_speed = condition.wind_speed_m_s
    leads = lead_points(probes, offlead_deg, sidelead_deg, lateral)
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
        condition_name=None if condition.spec is None else condition.spec.name,
        case_name=None if condition.case is None else condition.case.name,
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
