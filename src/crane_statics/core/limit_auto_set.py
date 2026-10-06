"""Shared design-limit auto-set helpers.

This module centralizes rope-cap auto-set behavior so load-time bootstrap
and chart-row Auto-Set use identical semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional, Callable, Any

from ..data.models import CraneDocument
from ..calculation.engine import CraneCalculator, get_calculator
from ..calculation.point_composition import compose_lateral_channels
from ..calculation.solver.kinematics import KinematicsAdapter
from .analysis_cases import (
    iter_wind_lead_directional_cases,
    iter_hoist_analysis_modes,
    DirectionalAnalysisCase,
)
from .demand_extraction import extract_rope_tension_demand, extract_connection_component_demand


@dataclass
class ContractualPointResult:
    """Result from evaluating a single contractual point across all directional cases."""

    hoist_id: str
    mode_name: str
    cp_index: int
    cp_outreach_m: float
    angle_deg: float
    best_demand: float
    best_case: DirectionalAnalysisCase


@dataclass
class RopeAutoSetResult:
    """Outcome of required rope-cap computation from contractual points."""

    required_kN: Optional[float]
    evaluated_points: int
    evaluated_hoists: int
    message: str
    governing_hoist_id: Optional[str] = None
    governing_cp_index: Optional[int] = None
    governing_outreach_m: Optional[float] = None
    governing_angle_deg: Optional[float] = None
    governing_offlead_deg: Optional[float] = None
    governing_sidelead_deg: Optional[float] = None
    governing_wind_direction: Optional[str] = None
    governing_mode: Optional[str] = None
    used_system_rope_fallback: bool = False


@dataclass
class ConnectionAutoSetResult:
    """Outcome of required connection-cap computation from contractual points."""

    required_kN: Optional[float]
    evaluated_points: int
    evaluated_hoists: int
    message: str
    governing_hoist_id: Optional[str] = None
    governing_cp_index: Optional[int] = None
    governing_outreach_m: Optional[float] = None
    governing_angle_deg: Optional[float] = None
    governing_offlead_deg: Optional[float] = None
    governing_sidelead_deg: Optional[float] = None
    governing_wind_direction: Optional[str] = None
    governing_mode: Optional[str] = None


def _required_hook_force_kN(
    load_t: float, hook_mass_t: float, hook_daf: float, gravity_m_s2: float
) -> float:
    """Required hook force at contractual point, including hook mass and DAF."""
    return (float(load_t) + float(hook_mass_t)) * abs(float(gravity_m_s2)) * float(hook_daf)


def _compose_lead_channel_point(pt: Any, case: DirectionalAnalysisCase) -> Any:
    """Compose one lead-sign case from a zero-lead analysis point."""
    return compose_lateral_channels(
        pt,
        hook_x=math.sin(math.radians(float(case.offlead_deg or 0.0))),
        hook_y=math.sin(math.radians(float(case.sidelead_deg or 0.0))),
    )


def _evaluate_contractual_points(
    hoists: list[Any],
    doc: CraneDocument,
    calc: CraneCalculator,
    kin: KinematicsAdapter,
    gravity: float,
    demand_extractor: Callable[[Any, float, DirectionalAnalysisCase], Optional[float]],
    use_lead_channel_composition: bool = False,
) -> list[ContractualPointResult]:
    """Evaluate all contractual points across hoists/modes/cases using a custom demand extractor.

    Args:
        hoists: List of hoist objects to evaluate
        doc: Crane document for wind speed
        calc: Calculator for analysis points
        kin: Kinematics adapter for angle conversion
        gravity: Gravity magnitude
        demand_extractor: Callable(analysis_point, hook_kN, case) -> demand_value or None
        use_lead_channel_composition: Compose lead cases from one zero-lead
            point per wind direction instead of rerunning the solver per case.

    Returns:
        List of ContractualPointResult with best demand per contractual point.
    """
    results = []
    wind_speed = float(doc.environment.max_wind_speed_m_s)

    for hoist in hoists:
        for mode in iter_hoist_analysis_modes(hoist):
            for cp_index, cp in enumerate(mode.contractual_points):
                try:
                    angle = kin.outreach_to_angle(float(cp.outreach_m), hoist.id)
                except Exception:
                    angle = None
                if angle is None:
                    continue

                best_demand = float("-inf")
                best_case = None

                hook_kN = _required_hook_force_kN(
                    cp.load_t,
                    mode.hook_mass_t,
                    hoist.hook_daf,
                    gravity,
                )
                points_by_wind: dict[str, Any] = {}
                if use_lead_channel_composition:
                    for case in iter_wind_lead_directional_cases(hoist, wind_speed):
                        if case.wind_direction in points_by_wind:
                            continue
                        points_by_wind[case.wind_direction] = calc.compute_analysis_point(
                            float(angle),
                            0.0,
                            hoist.id,
                            wind_speed_m_s=wind_speed,
                            wind_direction=case.wind_direction,
                            offlead_deg=0.0,
                            sidelead_deg=0.0,
                            hoist_runtime_overrides=mode.runtime_overrides,
                        )

                for case in iter_wind_lead_directional_cases(hoist, wind_speed):
                    if not use_lead_channel_composition:
                        pt = calc.compute_analysis_point(
                            float(angle),
                            0.0,
                            hoist.id,
                            wind_speed_m_s=wind_speed,
                            wind_direction=case.wind_direction,
                            offlead_deg=case.offlead_deg,
                            sidelead_deg=case.sidelead_deg,
                            hoist_runtime_overrides=mode.runtime_overrides,
                        )
                    else:
                        pt = points_by_wind.get(case.wind_direction)
                    if pt is None:
                        continue

                    demand_point = (
                        _compose_lead_channel_point(pt, case)
                        if use_lead_channel_composition
                        else pt
                    )
                    demand = demand_extractor(demand_point, hook_kN, case)
                    if demand is None or not math.isfinite(demand):
                        continue

                    if demand > best_demand:
                        best_demand = demand
                        best_case = case

                if math.isfinite(best_demand) and best_demand > 0.0 and best_case is not None:
                    results.append(
                        ContractualPointResult(
                            hoist_id=hoist.id,
                            mode_name=mode.name,
                            cp_index=cp_index,
                            cp_outreach_m=float(cp.outreach_m),
                            angle_deg=float(angle),
                            best_demand=best_demand,
                            best_case=best_case,
                        )
                    )

    return results


def compute_required_rope_capacity_kN(doc: CraneDocument, rope_id: str) -> RopeAutoSetResult:
    """Compute required rope tension capacity from relevant contractual points.

    Rules:
    - Only hoists using this rope are considered.
    - Contractual points are evaluated on-demand by outreach inversion.
    - Worst-case offlead direction governs per contractual point.
    """

    requested_rope_id = str(rope_id)
    rope_obj = next((r for r in doc.ropes if r.id == requested_rope_id), None)
    relevant_hoists = [h for h in doc.hoists if h.rope_id == requested_rope_id]
    using_fallback = False
    sensitivity_key = requested_rope_id

    # Solve-mode ropes are system ropes: evaluate across all hoists using the
    # solver's boom-hoist key rather than the authored rope id.
    if rope_obj and rope_obj.tension_mode == "solve":
        relevant_hoists = list(doc.hoists)
        sensitivity_key = "boom_hoist"
        using_fallback = True

    if not relevant_hoists:
        # Preserve system-rope behavior (e.g., boom_hoist) when a rope exists but
        # has no directly attached hoist: evaluate all hoists.
        if rope_obj is not None:
            relevant_hoists = list(doc.hoists)
            using_fallback = True
    if not relevant_hoists:
        return RopeAutoSetResult(
            required_kN=None,
            evaluated_points=0,
            evaluated_hoists=0,
            message=f"No hoists use rope '{requested_rope_id}'",
        )

    calc = get_calculator(doc)
    kin = KinematicsAdapter(doc.model_dump())
    gravity = abs(float(doc.environment.gravity_m_s2))

    def rope_demand_extractor(
        pt: Any, hook_kN: float, case: DirectionalAnalysisCase
    ) -> Optional[float]:
        """Extract rope tension from analysis point."""
        return extract_rope_tension_demand(pt, hook_kN, sensitivity_key)

    def _evaluate(
        hoists: list[Any],
    ) -> tuple[
        float,
        int,
        Optional[str],
        Optional[int],
        Optional[float],
        Optional[float],
        Optional[float],
        Optional[float],
        Optional[str],
        Optional[str],
    ]:
        results = _evaluate_contractual_points(
            hoists,
            doc,
            calc,
            kin,
            gravity,
            rope_demand_extractor,
            use_lead_channel_composition=True,
        )

        if not results:
            return float("-inf"), 0, None, None, None, None, None, None, None, None

        best = max(results, key=lambda r: r.best_demand)
        return (
            best.best_demand,
            len(results),
            best.hoist_id,
            best.cp_index,
            best.cp_outreach_m,
            best.angle_deg,
            best.best_case.offlead_deg,
            best.best_case.sidelead_deg,
            best.best_case.wind_direction,
            best.mode_name,
        )

    (
        required_kN,
        evaluated_points,
        governing_hoist_id,
        governing_cp_index,
        governing_outreach_m,
        governing_angle_deg,
        governing_offlead_deg,
        governing_sidelead_deg,
        governing_wind_direction,
        governing_mode,
    ) = _evaluate(relevant_hoists)

    # For non-solve ropes, retry across all hoists if direct-owner points could
    # not be evaluated and the rope exists in the model.
    if (
        evaluated_points == 0
        and not using_fallback
        and rope_obj
        and rope_obj.tension_mode != "solve"
    ):
        (
            required_kN,
            evaluated_points,
            governing_hoist_id,
            governing_cp_index,
            governing_outreach_m,
            governing_angle_deg,
            governing_offlead_deg,
            governing_sidelead_deg,
            governing_wind_direction,
            governing_mode,
        ) = _evaluate(list(doc.hoists))
        if evaluated_points > 0:
            using_fallback = True

    if evaluated_points == 0 or not math.isfinite(required_kN):
        return RopeAutoSetResult(
            required_kN=None,
            evaluated_points=0,
            evaluated_hoists=len(relevant_hoists),
            message=f"No contractual points could be evaluated for rope '{requested_rope_id}'",
        )

    return RopeAutoSetResult(
        required_kN=float(required_kN),
        evaluated_points=evaluated_points,
        evaluated_hoists=len(relevant_hoists),
        message="ok",
        governing_hoist_id=governing_hoist_id,
        governing_cp_index=governing_cp_index,
        governing_outreach_m=governing_outreach_m,
        governing_angle_deg=governing_angle_deg,
        governing_offlead_deg=governing_offlead_deg,
        governing_sidelead_deg=governing_sidelead_deg,
        governing_wind_direction=governing_wind_direction,
        governing_mode=governing_mode,
        used_system_rope_fallback=using_fallback,
    )


def compute_required_connection_capacity_kN(
    doc: CraneDocument,
    connection_id: str,
    component: str,
) -> ConnectionAutoSetResult:
    """Compute required connection component capacity from contractual points.

    Connection rows are evaluated across all hoists and contractual points.
    """

    calc = get_calculator(doc)
    kin = KinematicsAdapter(doc.model_dump())
    gravity = abs(float(doc.environment.gravity_m_s2))

    def connection_demand_extractor(
        pt: Any, hook_kN: float, case: DirectionalAnalysisCase
    ) -> Optional[float]:
        """Extract connection component demand from analysis point."""
        diameter = doc.support_widths.slewing_bearing_diameter_m
        return extract_connection_component_demand(
            pt, hook_kN, connection_id, component, support_widths_diameter_m=diameter
        )

    results = _evaluate_contractual_points(
        doc.hoists,
        doc,
        calc,
        kin,
        gravity,
        connection_demand_extractor,
    )

    if not results:
        return ConnectionAutoSetResult(
            required_kN=None,
            evaluated_points=0,
            evaluated_hoists=len(doc.hoists),
            message=(
                f"No contractual points could be evaluated for connection "
                f"'{connection_id}' component '{component}'"
            ),
        )

    best = max(results, key=lambda r: r.best_demand)
    return ConnectionAutoSetResult(
        required_kN=float(best.best_demand),
        evaluated_points=len(results),
        evaluated_hoists=len(doc.hoists),
        message="ok",
        governing_hoist_id=best.hoist_id,
        governing_cp_index=best.cp_index,
        governing_outreach_m=best.cp_outreach_m,
        governing_angle_deg=best.angle_deg,
        governing_offlead_deg=best.best_case.offlead_deg,
        governing_sidelead_deg=best.best_case.sidelead_deg,
        governing_wind_direction=best.best_case.wind_direction,
        governing_mode=best.mode_name,
    )
