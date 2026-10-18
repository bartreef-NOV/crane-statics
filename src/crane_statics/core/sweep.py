"""Toolkit-neutral capacity-curve sweep used by the QML front end."""

from __future__ import annotations

import logging
import math
from typing import Any, Callable, Optional

from ..calculation.engine import AllowableCapacity, AnalysisPoint, CraneCalculator
from ..calculation.solver.kinematics import KinematicsAdapter
from ..data.models import CraneDocument
from .analysis_cases import HoistAnalysisMode, analysis_mode_by_name
from .chart_envelope import ProbeSet, build_probes, envelope_capacity, lead_points
from .demand_extraction import (
    connection_component_responds_to_hook_load,
    rope_tension_responds_to_hook_load,
)
from .limit_components import KNOWN_LIMIT_COMPONENTS
from .sweep_cache import ComputeScope, LimitResult, limit_signature

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


def _split_applies(hoist: Any) -> bool:
    return (
        bool(getattr(hoist, "splitable_block", False))
        and getattr(hoist, "split_hook_mass_t", None) is not None
        and getattr(hoist, "split_falls", None) is not None
    )


def _hoist_order_by_rope(doc: CraneDocument) -> dict[str, int]:
    """Display rank of each hoist's rope: solve-tension ropes first, then document order."""
    solve_rope_ids = {
        str(r.id).strip()
        for r in doc.ropes
        if str(getattr(r, "tension_mode", "") or "").strip().lower() == "solve"
    }
    payload_hoists = [h for h in doc.hoists if str(h.rope_id).strip() not in solve_rope_ids]
    solve_hoists = [h for h in doc.hoists if str(h.rope_id).strip() in solve_rope_ids]
    ordered_hoists = solve_hoists + payload_hoists
    return {
        str(h.rope_id).strip(): idx
        for idx, h in enumerate(ordered_hoists)
        if str(h.rope_id).strip()
    }


def limit_series_layout(
    doc: CraneDocument, enabled_limits: dict, limit_display_names: dict
) -> list[tuple[str, str, int]]:
    """(limit id, display label, rank) for every enabled limit, in display order.

    The order is rank, then label: the order of the ``limit_series`` rows of a sweep, which
    are the rows of this layout that have points.
    """
    hoist_order_by_rope = _hoist_order_by_rope(doc)
    non_rope_rank_seed = len(hoist_order_by_rope)
    rows: list[tuple[str, str, int]] = []
    for non_rope_offset, lid in enumerate(enabled_limits):
        lid_s = str(lid)
        rope_id = lid_s[:-2] if lid_s.endswith("_T") else lid_s
        rank = hoist_order_by_rope.get(rope_id)
        if rank is None:
            rank = non_rope_rank_seed + non_rope_offset
        rows.append((lid_s, limit_display_names.get(lid_s, lid_s), int(rank)))
    rows.sort(key=lambda row: (row[2], row[1]))
    return rows


def run_mode_sweep(
    doc: CraneDocument,
    hoist_id: str,
    mode_name: str,
    enabled_limits: dict,
    outreach_step: float,
    limit_display_names: dict,
    progress: Optional[Callable[[str], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    on_points: Optional[Callable[[list[tuple[float, float]]], None]] = None,
    batch_points: int = 20,
    compute_scope: Optional[ComputeScope] = None,
    on_contractual: Optional[
        Callable[[list[tuple[Any, Optional[float], Optional[bool]]]], None]
    ] = None,
    on_limit_points: Optional[Callable[[dict[str, list[tuple[float, float]]]], None]] = None,
) -> Optional[dict[str, Any]]:
    """Compute one analysis mode's curve, contractual verdicts and per-limit series.

    Returns None when the mode does not apply to the hoist (split without a split block).
    ``on_points`` receives the finite (outreach, load_t) pairs in ascending outreach, in
    batches of at most ``batch_points``; the batches concatenate to ``curve_data``.
    ``compute_scope`` (for this document, hoist and mode) supplies and keeps the probe
    solves and per-limit results, so a re-sweep only evaluates what changed; the payload
    is the same with or without it.
    ``on_contractual`` receives a copy of the contractual results once, right after stage 1
    (not when the mode has no contractual points). ``on_limit_points`` receives, with each
    flush when any limit gained points (the final flush may bring limit points without a
    curve batch), the points the limit series gained since the previous call, keyed by
    limit id; per limit the batches concatenate to its ``limit_series`` points.
    """
    report = progress if progress is not None else (lambda _msg: None)
    cancel_requested = should_cancel if should_cancel is not None else (lambda: False)

    def check_cancelled() -> None:
        if cancel_requested():
            raise SweepCancelled()

    hoist = next(h for h in doc.hoists if h.id == hoist_id)
    if mode_name == "split" and not _split_applies(hoist):
        return None
    # A private calculator: the shared get_calculator cache never evicts, so every sweep
    # would leak a document copy.
    calc = CraneCalculator(doc)
    kin = KinematicsAdapter(doc.model_dump())
    wind_speed = float(doc.environment.max_wind_speed_m_s)
    # The Model's vessel motion values are ± limits and the hoist's leads are taken with
    # both signs; the chart reports the worst case over them, every slew and wind angle.
    vessel = doc.environment.vessel_motion
    offlead_deg = float(getattr(hoist, "offlead_deg", 0.0))
    sidelead_deg = float(getattr(hoist, "sidelead_deg", offlead_deg))

    def _capacity(
        probes: ProbeSet, design_limits_map: dict[str, dict], hook_mass_t: float
    ) -> AllowableCapacity:
        return envelope_capacity(
            calc,
            probes,
            design_limits_map,
            vessel=vessel,
            offlead_deg=offlead_deg,
            sidelead_deg=sidelead_deg,
            hook_daf=hoist.hook_daf,
            hook_mass_t=hook_mass_t,
        )

    def _limit_results(
        angle: float, probes: ProbeSet, hook_mass_t: float
    ) -> dict[str, LimitResult]:
        leads: list[AnalysisPoint] = []
        results: dict[str, LimitResult] = {}
        for lid, comps in enabled_limits.items():
            if not any(comps.values()):
                continue  # envelope_capacity skips falsy values: unlimited, never plotted

            def compute(lid: str = lid, comps: dict = comps) -> LimitResult:
                if not leads:
                    leads.extend(lead_points(probes, offlead_deg, sidelead_deg))
                cap = _capacity(probes, {lid: comps}, hook_mass_t)
                # Sensitivities do not depend on motion or wind, but the lead channels
                # add to them: a limit responds if it does at any lead sign case.
                responsive = any(_affects_hook_load(pt, lid, comps) for pt in leads)
                return LimitResult(cap.max_allowable_load_t, cap.max_allowable_load_kN, responsive)

            if compute_scope is None:
                results[lid] = compute()
            else:
                signature = limit_signature(lid, {c: v or 0.0 for c, v in comps.items()})
                results[lid] = compute_scope.limit_result(angle, signature, compute)
        return results

    # Stage 2 revisits the contractual outreaches of stage 1; their solves are reused.
    envelope_cache: dict[tuple[float, str], Optional[tuple[float, dict[str, LimitResult]]]] = {}

    def _envelope(
        angle: float, mode: HoistAnalysisMode
    ) -> Optional[tuple[float, dict[str, LimitResult]]]:
        """Combined payload capacity and per-limit results at ``angle``, None if unsolved.

        envelope_capacity evaluates every limit on its own and keeps the lowest, so the
        combined capacity is the per-limit result of lowest hook load (first one on a tie).
        """
        key = (round(float(angle), 10), mode.name)
        if key not in envelope_cache:

            def build() -> Optional[ProbeSet]:
                return build_probes(
                    calc, hoist_id, angle, wind_speed, mode.runtime_overrides, vessel=vessel
                )

            probes = build() if compute_scope is None else compute_scope.probes(angle, build)
            if probes is None:
                envelope_cache[key] = None
            else:
                results = _limit_results(angle, probes, mode.hook_mass_t)
                if results:
                    load_t = min(results.values(), key=lambda r: r.load_kN).load_t
                else:
                    # No limit applies: the unlimited capacity.
                    load_t = _capacity(
                        probes, enabled_limits, mode.hook_mass_t
                    ).max_allowable_load_t
                envelope_cache[key] = (load_t, results)
        return envelope_cache[key]

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
            envelope = _envelope(angle, mode)
            if envelope is None:
                contractual_results.append((cp, None, None))
                continue
            load_t, _results = envelope
            contractual_results.append((cp, load_t, cp.load_t <= load_t))

        if on_contractual is not None and contractual_results:
            on_contractual(list(contractual_results))

        report(f"Stage 2/2 ({mode_name}): Capacity curve sweep...")
        curve_outreach: list[float] = []
        curve_load_t: list[float] = []
        limit_series_map: dict[str, list] = {lid: [] for lid in enabled_limits}
        pending: list[tuple[float, float]] = []

        sent_counts: dict[str, int] = {}

        def _flush() -> None:
            if pending and on_points is not None:
                on_points(list(pending))
            pending.clear()
            if on_limit_points is not None:
                gained = {
                    lid: pts[sent_counts.get(lid, 0) :]
                    for lid, pts in limit_series_map.items()
                    if len(pts) > sent_counts.get(lid, 0)
                }
                if gained:
                    sent_counts.update({lid: len(limit_series_map[lid]) for lid in gained})
                    on_limit_points(gained)

        try:
            for outreach in mode_outreach_grid:
                check_cancelled()
                try:
                    angle = kin.outreach_to_angle(outreach, hoist_id)
                    if angle is None:
                        continue
                    envelope = _envelope(angle, mode)
                    if envelope is None:
                        continue
                    load_t, results = envelope
                    for lid, result in results.items():
                        # CRITICAL: Use load_t (payload domain) for curves, not kN.
                        # Chart Y-axis shows payload tonnes, not hook-force.
                        if result.responsive and math.isfinite(result.load_t):
                            limit_series_map[lid].append((outreach, result.load_t))
                    if math.isfinite(load_t):
                        curve_outreach.append(outreach)
                        curve_load_t.append(load_t)
                        pending.append((outreach, load_t))
                        if len(pending) >= batch_points:
                            _flush()
                except (TypeError, ValueError, ArithmeticError) as exc:
                    _LOG.debug(
                        "Skipping outreach %.3f m for hoist %s (%s): %s",
                        outreach,
                        hoist_id,
                        mode_name,
                        exc,
                    )
            _flush()
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

        limit_series = [
            (lid, label, rank, sorted(limit_series_map[lid]))
            for lid, label, rank in limit_series_layout(doc, enabled_limits, limit_display_names)
            if limit_series_map.get(lid)
        ]

        return {
            "curve_data": list(zip(curve_outreach, curve_load_t)),
            "contractual_results": contractual_results,
            "limit_series": limit_series,
            "n_points": len(curve_outreach),
        }

    return _compute_mode(mode_name)


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
    hoist = next(h for h in doc.hoists if h.id == hoist_id)
    mode_results: dict[str, dict[str, Any]] = {}
    for mode_name in ("normal", "split"):
        payload = run_mode_sweep(
            doc,
            hoist_id,
            mode_name,
            enabled_limits,
            outreach_step,
            limit_display_names,
            progress,
            should_cancel,
        )
        if payload is not None:
            mode_results[mode_name] = payload

    return {
        "hoist": hoist,
        "modes": mode_results,
        "n_points": max((v.get("n_points", 0) for v in mode_results.values()), default=0),
        "n_points_by_mode": {k: int(v.get("n_points", 0)) for k, v in mode_results.items()},
    }
