"""The load-chart sweep takes its capacities from the probe envelope (chart_envelope)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from tests.chart_reference import reference_capacity
from crane_statics.calculation.engine import CraneCalculator
from crane_statics.calculation.solver.kinematics import KinematicsAdapter
from crane_statics.core import load_document
from crane_statics.core.analysis_cases import analysis_mode_by_name
from crane_statics.core.chart_envelope import build_probes, envelope_capacity
from crane_statics.core.sweep import SweepCancelled, run_capacity_sweep
from crane_statics.data.models import CraneDocument

ROOT = Path(__file__).parent.parent
GT283 = ROOT / "examples" / "crane_input_GT283.yaml"
EXAMPLE_22689 = ROOT / "examples" / "crane_input_22689.yaml"
HOIST = "MH"
LIMITS: dict[str, dict] = {"boom_hoist": {"T": 5000.0}}
ORACLE_LIMITS: dict[str, dict] = {
    "boom_hoist": {"T": 5000.0},
    "platform_base": {"max_bearing_line_load": 3000.0},
}
UNSAFE_REL = 1e-6
CONSERVATIVE_REL = 0.005
BENCHMARK_S = 0.37


def _set_vessel(doc: CraneDocument, values: dict[str, float]) -> CraneDocument:
    vm = doc.environment.vessel_motion
    for field, value in values.items():
        setattr(vm, field, float(value))
    return doc


SEVEN_LIMITS = {
    "accel_x_m_s2": 0.8,
    "accel_y_m_s2": 0.6,
    "accel_z_m_s2": 1.1,
    "roll_angular_accel_rad_s2": 0.05,
    "pitch_angular_accel_rad_s2": 0.03,
    "roll_deg": 4.0,
    "pitch_deg": 2.5,
}
BENCHMARK_LIMITS = {
    "accel_x_m_s2": 1.0,
    "accel_y_m_s2": 1.0,
    "accel_z_m_s2": 1.0,
    "roll_angular_accel_rad_s2": 0.1,
    "pitch_angular_accel_rad_s2": 0.1,
    "roll_deg": 5.0,
    "pitch_deg": 5.0,
}


def _curve(result: dict, mode: str = "normal") -> list[tuple[float, float]]:
    curve: list[tuple[float, float]] = list(result["modes"][mode]["curve_data"])
    return curve


@pytest.mark.slow
def test_sweep_matches_reference_curve() -> None:
    """Realistic wind, all seven vessel limits and the example's leads, against brute force."""
    doc = _set_vessel(load_document(GT283), SEVEN_LIMITS)
    doc.environment.max_wind_speed_m_s = 20.0
    hoist = next(h for h in doc.hoists if h.id == HOIST)
    assert hoist.offlead_deg != 0.0 and hoist.sidelead_deg != 0.0

    curve = _curve(run_capacity_sweep(doc, HOIST, ORACLE_LIMITS, 10.0, {}))
    assert len(curve) >= 3
    calc = CraneCalculator(doc)
    kin = KinematicsAdapter(doc.model_dump())
    picks = [curve[0], curve[len(curve) // 2], curve[-1]]
    for outreach, load_t in picks:
        angle = kin.outreach_to_angle(outreach, HOIST)
        assert angle is not None
        ref = reference_capacity(
            calc,
            doc,
            HOIST,
            angle,
            ORACLE_LIMITS,
            hook_daf=hoist.hook_daf,
            hook_mass_t=hoist.hook_mass_t,
            overrides=None,
            slew_step_deg=15.0,
            wind_step_deg=45.0,
        )
        r = ref.max_allowable_load_t
        print(f"{outreach} m: sweep {load_t:.6f} t, reference {r:.6f} t")
        assert r > 0.0
        assert load_t <= r * (1.0 + UNSAFE_REL) + 1e-9, (outreach, load_t, r)
        assert load_t >= r * (1.0 - CONSERVATIVE_REL), (outreach, load_t, r)


def test_sweep_meets_the_benchmark() -> None:
    """GT283 / MH / 2 m step with all seven vessel limits set: 10x faster than 3.7 s."""
    doc = _set_vessel(load_document(GT283), BENCHMARK_LIMITS)
    run_capacity_sweep(doc, HOIST, LIMITS, 2.0, {})  # warm-up
    start = time.perf_counter()
    result = run_capacity_sweep(doc, HOIST, LIMITS, 2.0, {})
    elapsed = time.perf_counter() - start
    print(f"benchmark sweep: {elapsed:.3f} s")
    assert result["n_points"] > 0
    assert elapsed < BENCHMARK_S


def test_zero_limits_and_wind_give_the_single_solve_curve() -> None:
    """No vessel limits, no wind and no leads: the curve is today's single-solve capacity."""
    doc = load_document(GT283)
    doc.environment.max_wind_speed_m_s = 0.0
    hoist = next(h for h in doc.hoists if h.id == HOIST)
    hoist.offlead_deg = 0.0
    hoist.sidelead_deg = 0.0
    curve = _curve(run_capacity_sweep(doc, HOIST, LIMITS, 2.0, {}))
    assert len(curve) >= 2
    calc = CraneCalculator(doc)
    kin = KinematicsAdapter(doc.model_dump())
    for outreach, load_t in (curve[0], curve[-1]):
        angle = kin.outreach_to_angle(outreach, HOIST)
        assert angle is not None
        pt = calc.compute_analysis_point(angle, 0.0, HOIST, wind_speed_m_s=0.0)
        assert pt is not None
        expected = calc.compute_allowable_load(
            pt, LIMITS, hook_daf=hoist.hook_daf, hook_mass_t=hoist.hook_mass_t
        )
        assert load_t == pytest.approx(expected.max_allowable_load_t, rel=1e-9)


def test_cancelled_sweep_raises() -> None:
    doc = load_document(GT283)
    with pytest.raises(SweepCancelled):
        run_capacity_sweep(doc, HOIST, LIMITS, 2.0, {}, should_cancel=lambda: True)


def _envelope_t(doc: CraneDocument, outreach: float, mode_name: str) -> float:
    hoist = next(h for h in doc.hoists if h.id == HOIST)
    mode = analysis_mode_by_name(hoist, mode_name)
    assert mode.name == mode_name
    calc = CraneCalculator(doc)
    angle = KinematicsAdapter(doc.model_dump()).outreach_to_angle(outreach, HOIST)
    assert angle is not None
    probes = build_probes(
        calc, HOIST, angle, float(doc.environment.max_wind_speed_m_s), mode.runtime_overrides
    )
    assert probes is not None
    cap = envelope_capacity(
        calc,
        probes,
        LIMITS,
        vessel=doc.environment.vessel_motion,
        offlead_deg=hoist.offlead_deg,
        sidelead_deg=hoist.sidelead_deg,
        hook_daf=hoist.hook_daf,
        hook_mass_t=mode.hook_mass_t,
    )
    return float(cap.max_allowable_load_t)


@pytest.mark.parametrize("mode_name", ["normal", "split"])
def test_sweep_points_are_the_envelope_with_the_mode_overrides(mode_name: str) -> None:
    doc = _set_vessel(load_document(EXAMPLE_22689), {"accel_x_m_s2": 0.5, "roll_deg": 2.0})
    result = run_capacity_sweep(doc, HOIST, LIMITS, 5.0, {})
    curve = _curve(result, mode_name)
    assert curve
    for outreach, load_t in (curve[0], curve[-1]):
        assert load_t == pytest.approx(_envelope_t(doc, outreach, mode_name), rel=1e-12)


def test_limit_series_only_for_hook_load_responsive_limits() -> None:
    doc = _set_vessel(load_document(GT283), {"accel_x_m_s2": 0.5})
    limits: dict[str, Any] = {**LIMITS, "AH__rope": {"T": 1.0e9}}
    result = run_capacity_sweep(doc, HOIST, limits, 4.0, {})
    series = {row[0]: row for row in result["modes"]["normal"]["limit_series"]}
    assert set(series) == {"boom_hoist"}
    # One limit responds, so its series is the capacity curve itself.
    assert series["boom_hoist"][3] == pytest.approx(_curve(result))
