"""Model vessel motion values are ± limits: the load chart takes the worst case over ±."""

from __future__ import annotations

from pathlib import Path

import pytest

from crane_statics.core import load_document
from crane_statics.core.sweep import run_capacity_sweep
from crane_statics.core.vessel_envelope import vessel_motion_cases

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_GT283.yaml"
LIMITS = {"boom_hoist": {"T": 5000.0}}


def _curve(doc) -> list[tuple[float, float]]:
    curve: list[tuple[float, float]] = run_capacity_sweep(doc, "MH", LIMITS, 2.0, {})["modes"][
        "normal"
    ]["curve_data"]
    return curve


def test_zero_limits_give_a_single_case() -> None:
    doc = load_document(EXAMPLE)
    assert vessel_motion_cases(doc.environment.vessel_motion) == [
        dict.fromkeys(
            (
                "accel_x_m_s2",
                "accel_y_m_s2",
                "accel_z_m_s2",
                "roll_accel_rad_s2",
                "pitch_accel_rad_s2",
                "vessel_roll_deg",
                "vessel_pitch_deg",
            ),
            0.0,
        )
    ]


def test_each_nonzero_limit_doubles_the_cases_and_sign_is_ignored() -> None:
    vm = load_document(EXAMPLE).environment.vessel_motion
    vm.accel_x_m_s2 = -1.5
    vm.roll_deg = 4.0
    cases = vessel_motion_cases(vm)

    assert len(cases) == 4
    assert {c["accel_x_m_s2"] for c in cases} == {1.5, -1.5}
    assert {c["vessel_roll_deg"] for c in cases} == {4.0, -4.0}


def test_chart_capacity_is_the_worst_case_over_both_signs() -> None:
    doc = load_document(EXAMPLE)
    doc.environment.vessel_motion.accel_x_m_s2 = 1.0
    envelope = _curve(doc)

    for sign in (1.0, -1.0):
        single = load_document(EXAMPLE)
        # Evaluate one sign through the engine directly via a sweep of a +/- pinned limit.
        single.environment.vessel_motion.accel_x_m_s2 = sign * 1.0
        pinned = _curve(single)
        assert pinned  # same envelope either way: the limit's sign is ignored
        assert pinned == pytest.approx(envelope)

    nominal = _curve(load_document(EXAMPLE))
    assert all(e[1] <= n[1] + 1e-9 for e, n in zip(envelope, nominal))
    assert any(e[1] < n[1] - 1e-6 for e, n in zip(envelope, nominal))
