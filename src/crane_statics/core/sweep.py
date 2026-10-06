"""Toolkit-neutral capacity-curve sweep used by the QML front end."""

from __future__ import annotations

import logging
import math
from typing import Any, Callable, Optional

from ..calculation.engine import AllowableCapacity, AnalysisPoint, get_calculator
from ..calculation.solver.kinematics import KinematicsAdapter
from ..data.models import CraneDocument
from .analysis_cases import analysis_mode_by_name, iter_wind_directional_cases
from .demand_extraction import (
    connection_component_responds_to_hook_load,
    rope_tension_responds_to_hook_load,
)
from .limit_components import KNOWN_LIMIT_COMPONENTS

_LOG = logging.getLogger(__name__)


class SweepCancelled(Exception):
    """Raised when a capacity sweep is asked to stop cooperatively."""


def build_absolute_outreach_grid(lo_out: float, hi_out: float, outreach_step: float) -> list[float]:
    """Return absolute outreach samples in [lo_out, hi_out] plus explicit hi_out endpoint.

    For step s, base samples are k*s (k integer), clipped to hoist bounds.
    """
    step = max(0.01, float(outreach_step))
    lo = float(lo_out)
    hi = float(hi_out)
    if hi < lo:
        lo, hi = hi, lo

    eps = max(1e-9, step * 1e-6)
    start_k = math.ceil((lo - eps) / step)
    end_k = math.floor((hi + eps) / step)

    values: list[float] = []
    for k in range(start_k, end_k + 1):
        x = round(k * step, 10)
        if lo - eps <= x <= hi + eps:
            values.append(x)

    hi_rounded = round(hi, 10)
    if not values or all(abs(v - hi_rounded) > eps for v in values):
        values.append(hi_rounded)

    return sorted(set(values))


def run_capacity_sweep(
    doc: CraneDocument,
    hoist_id: str,
    enabled_limits: dict,
    outreach_step: float,
    limit_display_names: dict,
    progress: Optional[Callable[[str], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> dict:
    """Compute capacity curves, contractual verdicts and per-limit series for a hoist."""
    report = progress if progress is not None else (lambda _msg: None)
    cancel_requested = should_cancel if should_cancel is not None else (lambda: False)

    def check_cancelled() -> None:
        if cancel_requested():
            raise SweepCancelled()

    hoist = next(h for h in doc.hoists if h.id == hoist_id)
    calc = get_calculator(doc)
    kin = KinematicsAdapter(doc.model_dump())
    wind_speed = float(doc.environment.max_wind_speed_m_s)

    solve_rope_ids = {
        str(r.id).strip()
        for r in doc.ropes
        if str(getattr(r, "tension_mode", "") or "").strip().lower() == "solve"
    }
    payload_hoists = [h for h in doc.hoists if str(h.rope_id).strip() not in solve_rope_ids]
    solve_hoists = [h for h in doc.hoists if str(h.rope_id).strip() in solve_rope_ids]
    ordered_hoists = solve_hoists + payload_hoists
    hoist_order_by_rope = {
        str(h.rope_id).strip(): idx
        for idx, h in enumerate(ordered_hoists)
        if str(h.rope_id).strip()
    }

    def _wind_points(angle: float, hoist_runtime_overrides: dict[str, dict[str, Any]]) -> list:
        """Every case a chart point is the worst of: wind directions x vessel slews."""
        points = []
        for case in iter_wind_directional_cases(hoist, wind_speed):
            pt = calc.compute_analysis_point(
                angle,
                0.0,
                hoist_id,
                wind_speed_m_s=wind_speed,
                wind_direction=case.wind_direction,
                hoist_runtime_overrides=hoist_runtime_overrides,
            )
            if pt is not None:
                points.extend(calc.slew_envelope_points(pt))
        return points

    def _capacities(
        points: list, design_limits_map: dict[str, dict], hook_mass_t: float
    ) -> tuple[Optional[AllowableCapacity], dict[str, float]]:
        """Worst capacity over the points, and each limit's own worst hook force.

        Each point's limits are inverted once; the governing capacity is what
        ``compute_allowable_load`` would return for the worst point.
        """
        best: Optional[AllowableCapacity] = None
        per_limit_kN = {lid: float("inf") for lid in design_limits_map}
        for pt in points:
            h_point_kN, governing = float("inf"), None
            for lid, h_kN in calc.compute_limit_capacities_kN(pt, design_limits_map).items():
                if h_kN < h_point_kN:
                    h_point_kN, governing = h_kN, lid
                if h_kN < per_limit_kN[lid]:
                    per_limit_kN[lid] = h_kN
            cap = calc.capacity_from_hook_force(
                pt,
                h_point_kN,
                governing_limit_id=governing,
                hook_daf=hoist.hook_daf,
                hook_mass_t=hook_mass_t,
            )
            if best is None or cap.max_allowable_load_kN < best.max_allowable_load_kN:
                best = cap
        return best, per_limit_kN

    def _resolve_entity(limit_key: str) -> str:
        for comp in KNOWN_LIMIT_COMPONENTS:
            if limit_key.endswith(f"_{comp}"):
                return limit_key[: -len(f"_{comp}")]
        return limit_key

    def _resolve_rope_entity(entity: str, comps: dict) -> str:
        if "T" not in comps:
            return entity
        candidates = [entity]
        if entity.endswith("_rope") and not entity.endswith("__rope"):
            candidates.append(f"{entity[:-5]}__rope")
        elif entity.endswith("__rope"):
            candidates.append(f"{entity[:-6]}_rope")
        for rid in candidates:
            rope = next((r for r in doc.ropes if r.id == rid), None)
            if rope is None:
                continue
            return "boom_hoist" if rope.tension_mode == "solve" else rid
        return entity

    def _affects_hook_load(pt_obj: AnalysisPoint, limit_key: str, comps: dict) -> bool:
        entity = _resolve_entity(limit_key)
        tol = 1e-9
        if entity in pt_obj.sensitivity_reactions:
            diameter = doc.support_widths.slewing_bearing_diameter_m
            for comp in comps:
                if connection_component_responds_to_hook_load(
                    pt_obj,
                    entity,
                    comp,
                    support_widths_diameter_m=diameter,
                    tolerance=tol,
                ):
                    return True
            return False
        rope_entity = _resolve_rope_entity(entity, comps)
        if rope_entity in pt_obj.sensitivity_rope_tensions:
            return "T" in comps and rope_tension_responds_to_hook_load(pt_obj, rope_entity, tol)
        return False

    step = max(0.01, float(outreach_step))
    lo_out = float(hoist.outreach_min_m or 0.0)
    hi_out = float(hoist.outreach_max_m or 200.0)
    if hi_out < lo_out:
        lo_out, hi_out = hi_out, lo_out
    outreach_grid = build_absolute_outreach_grid(lo_out, hi_out, step)

    def _compute_mode(mode_name: str) -> dict[str, Any]:
        check_cancelled()
        mode = analysis_mode_by_name(hoist, mode_name)
        mode_hook_mass_t = mode.hook_mass_t
        hoist_runtime_overrides = mode.runtime_overrides
        mode_contractual_points = mode.contractual_points
        if mode_name == "split" and not mode_contractual_points:
            return {
                "curve_data": [],
                "contractual_results": [],
                "limit_series": [],
                "n_points": 0,
            }
        mode_outreach_grid = sorted(
            set(
                [
                    *outreach_grid,
                    *(round(float(cp.outreach_m), 10) for cp in mode_contractual_points),
                ]
            )
        )

        report(f"Stage 1/2 ({mode_name}): Contractual sweep...")
        contractual_results: list[tuple[Any, Optional[float], Optional[bool]]] = []
        for cp in mode_contractual_points:
            check_cancelled()
            try:
                angle = kin.outreach_to_angle(cp.outreach_m, hoist_id)
            except (TypeError, ValueError, RuntimeError):
                angle = None
            if angle is None:
                contractual_results.append((cp, None, None))
                continue
            pts = _wind_points(angle, hoist_runtime_overrides)
            if not pts:
                contractual_results.append((cp, None, None))
                continue
            cap, _per_limit = _capacities(pts, enabled_limits, mode_hook_mass_t)
            if cap is None:
                contractual_results.append((cp, None, None))
                continue
            contractual_results.append(
                (cp, cap.max_allowable_load_t, cp.load_t <= cap.max_allowable_load_t)
            )

        report(f"Stage 2/2 ({mode_name}): Capacity curve sweep...")
        curve_outreach: list[float] = []
        curve_load_t: list[float] = []
        limit_series_map: dict[str, list] = {lid: [] for lid in enabled_limits}

        try:
            for outreach in mode_outreach_grid:
                check_cancelled()
                try:
                    angle = kin.outreach_to_angle(outreach, hoist_id)
                    if angle is None:
                        continue
                    pts = _wind_points(angle, hoist_runtime_overrides)
                    if not pts:
                        continue
                    cap, per_limit_kN = _capacities(pts, enabled_limits, mode_hook_mass_t)
                    if cap is None:
                        continue
                    if math.isfinite(cap.max_allowable_load_t):
                        curve_outreach.append(outreach)
                        curve_load_t.append(cap.max_allowable_load_t)
                    for lid, comps in enabled_limits.items():
                        if not any(_affects_hook_load(pt, lid, comps) for pt in pts):
                            continue
                        cap_limit = calc.capacity_from_hook_force(
                            pts[0],
                            per_limit_kN[lid],
                            governing_limit_id=lid,
                            hook_daf=hoist.hook_daf,
                            hook_mass_t=mode_hook_mass_t,
                        )
                        # CRITICAL: Use max_allowable_load_t (payload domain) for curves, not kN.
                        # Chart Y-axis shows payload tonnes, not hook-force.
                        if math.isfinite(cap_limit.max_allowable_load_t):
                            limit_series_map[lid].append((outreach, cap_limit.max_allowable_load_t))
                except (TypeError, ValueError, ArithmeticError) as exc:
                    _LOG.debug(
                        "Skipping outreach %.3f m for hoist %s (%s): %s",
                        outreach,
                        hoist_id,
                        mode_name,
                        exc,
                    )
        except (TypeError, ValueError, RuntimeError) as exc:
            _LOG.warning("Capacity sweep failed for hoist %s (%s): %s", hoist_id, mode_name, exc)
            curve_outreach, curve_load_t = [], []
            limit_series_map = {}

        if curve_outreach:
            pairs = sorted(zip(curve_outreach, curve_load_t))
            curve_outreach, curve_load_t = zip(*pairs)  # type: ignore[assignment]
        else:
            # Without a finite capacity curve, pass/fail status is not meaningful.
            # Keep contractual points visible as pending markers instead of
            # disappearing when pass/fail markers are hidden.
            contractual_results = [(cp, None, None) for cp in mode_contractual_points]

        non_rope_rank_seed = len(hoist_order_by_rope)
        limit_series = []
        for non_rope_offset, (lid, pts) in enumerate(limit_series_map.items()):
            if not pts:
                continue
            lid_s = str(lid)
            rope_id = lid_s[:-2] if lid_s.endswith("_T") else lid_s
            rank = hoist_order_by_rope.get(rope_id)
            if rank is None:
                rank = non_rope_rank_seed + non_rope_offset
            limit_series.append(
                (
                    lid_s,
                    limit_display_names.get(lid_s, lid_s),
                    int(rank),
                    sorted(pts),
                )
            )
        limit_series.sort(key=lambda row: (int(row[2]), str(row[1])))

        return {
            "curve_data": list(zip(curve_outreach, curve_load_t)),
            "contractual_results": contractual_results,
            "limit_series": limit_series,
            "n_points": len(curve_outreach),
        }

    mode_results: dict[str, dict[str, Any]] = {"normal": _compute_mode("normal")}
    if bool(getattr(hoist, "splitable_block", False)):
        split_hook_mass = getattr(hoist, "split_hook_mass_t", None)
        split_falls = getattr(hoist, "split_falls", None)
        if split_hook_mass is not None and split_falls is not None:
            mode_results["split"] = _compute_mode("split")

    return {
        "hoist": hoist,
        "modes": mode_results,
        "n_points": max((v.get("n_points", 0) for v in mode_results.values()), default=0),
        "n_points_by_mode": {k: int(v.get("n_points", 0)) for k, v in mode_results.items()},
    }
