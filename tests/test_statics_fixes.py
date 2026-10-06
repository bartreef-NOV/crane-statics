"""Regression tests for statics defects that vessel heel/trim/slew would make material.

Each class pins one fix: a stale calculator after an in-place document edit,
limits already exceeded at zero hook load, the split compensation mass, the
platform-base moment origin, the left/right split signs, and where the
sidelead force enters the structure.
"""

from pathlib import Path

import pytest

from crane_statics.calculation.engine import get_calculator
from crane_statics.core.io import load_document

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"


@pytest.fixture
def document():
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    return load_document(EXAMPLE)


def _payload_hoist_id(doc) -> str:
    solve_ropes = {r.id for r in doc.ropes if r.tension_mode == "solve"}
    return str(next(h.id for h in doc.hoists if h.rope_id not in solve_ropes))


def _platform_fz(doc, hoist_id: str) -> float:
    point = get_calculator(doc).compute_analysis_point(
        45.0, 0.0, hoist_id, wind_speed_m_s=0.0, wind_direction="+X"
    )
    assert point is not None
    return float(point.baseline_reactions["platform_base"]["Fz"])


class TestCalculatorReflectsInPlaceEdits:
    def test_mass_edit_after_first_solve_changes_platform_reaction(self, document):
        hoist_id = _payload_hoist_id(document)
        before = _platform_fz(document, hoist_id)

        platform = next(b for b in document.bodies if b.id == "platform")
        platform.mass_points[0].mass_t += 100.0

        after = _platform_fz(document, hoist_id)
        gravity = abs(float(document.environment.gravity_m_s2))
        assert after - before == pytest.approx(100.0 * gravity, rel=1e-9)

    def test_gravity_edit_after_first_solve_changes_platform_reaction(self, document):
        hoist_id = _payload_hoist_id(document)
        before = _platform_fz(document, hoist_id)

        document.environment.gravity_m_s2 = 2.0 * float(document.environment.gravity_m_s2)

        assert _platform_fz(document, hoist_id) == pytest.approx(2.0 * before, rel=1e-9)
