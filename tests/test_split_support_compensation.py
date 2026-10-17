"""The split-block compensation mass is a weight, not a side force.

In split mode the hook block is lighter than the normal one; the difference is carried
as a mass at the support node. The out-of-plane (left/right) split pass used to apply
that weight as a lateral force Fy = -m*g, inventing a side load on the platform.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from crane_statics.calculation import CraneCalculator
from crane_statics.core import load_document

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"


def _platform_reaction(calc: CraneCalculator, overrides=None) -> dict[str, float]:
    point = calc.compute_analysis_point(
        45.0, 0.0, "MH", wind_speed_m_s=0.0, sidelead_deg=0.0, hoist_runtime_overrides=overrides
    )
    assert point is not None
    return point.baseline_reactions["platform_base"]


def test_split_compensation_mass_adds_no_side_force() -> None:
    doc = load_document(EXAMPLE)
    hook_mass_t = next(h for h in doc.hoists if h.id == "MH").hook_mass_t
    calc = CraneCalculator(doc)
    normal = _platform_reaction(calc)
    split = _platform_reaction(calc, {"MH": {"hook_mass_t": hook_mass_t - 10.0}})

    # The compensation mass sits on the support node (y = 0): no side force, no extra Mx.
    assert split["Fy"] == pytest.approx(normal["Fy"], abs=1e-9)
    assert split["Mx"] == pytest.approx(normal["Mx"], rel=1e-12, abs=1e-9)
    # It is still carried as weight in the in-plane solve.
    assert split["Fz"] > normal["Fz"]
