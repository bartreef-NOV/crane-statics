"""The Equilibrium Check must not invent a moment at a pinned support.

drawn_loads used to report a "synthetic" reaction moment at the selected body's support
whenever the solver gave none, equal to the body's residual. The boom heel and both leg
hinges are pins: that moment is zero when the solver and the scene agree, and equal to
the error when they don't, so the check closed by construction and could not catch a
moment-only disagreement (such as boom masses placed at a wrong angle).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from crane_statics.calculation.solver import crane_solver
from crane_statics.core import load_document
from tests.test_acceptance import SceneHarness

EXAMPLES = Path(__file__).parent.parent / "examples"
PIN_BY_BODY = {"boom": "heel_point", "rear_leg": "rear_hinge", "front_leg": "front_hinge"}


def _gt283_harness() -> SceneHarness:
    harness = SceneHarness(load_document(EXAMPLES / "crane_input_GT283.yaml"), "MH")
    harness.apply(boom_angle_deg=45.0)
    return harness


@pytest.fixture
def boom_masses_ten_degrees_low(monkeypatch):
    """Make the solver place boom-local points 10 deg below where the scene draws them."""
    original = crane_solver.rotate_boom_local_point

    def wrong(local_x, local_z, node_pos, boom_angle_deg):
        return original(local_x, local_z, node_pos, boom_angle_deg - 10.0)

    monkeypatch.setattr(crane_solver, "rotate_boom_local_point", wrong)


def test_moment_only_disagreement_fails_the_boom_check(boom_masses_ten_degrees_low) -> None:
    report = _gt283_harness().report()

    boom = next(s for s in report["sections"] if s["name"] == "Boom")
    assert boom["passed"] is False, boom["message"]
    assert math.isclose(boom["sum_fx"], 0.0, abs_tol=1e-6)  # forces still balance
    assert abs(boom["sum_m"]) > 1.0  # the moment does not


def test_pinned_supports_draw_no_reaction_moment(boom_masses_ten_degrees_low) -> None:
    harness = _gt283_harness()
    for body, pin in PIN_BY_BODY.items():
        moments = harness.loads(body).moments
        assert not [m for m in moments if pin in m.label], (body, moments)


def test_consistent_solver_passes_the_check_on_every_example() -> None:
    for name in ("crane_input_22689", "crane_input_13778_retracted", "crane_input_GT283"):
        doc = load_document(EXAMPLES / f"{name}.yaml")
        harness = SceneHarness(doc, doc.hoists[0].id)
        harness.apply(boom_angle_deg=45.0)
        report = harness.report()
        failing = [s["message"] for s in report["sections"] if not s["passed"]]
        assert report["passed"] is True, (name, failing)
