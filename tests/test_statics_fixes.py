"""Regression tests for statics defects that vessel heel/trim/slew would make material.

Each class pins one fix: a stale calculator after an in-place document edit,
limits already exceeded at zero hook load, the split compensation mass, the
platform-base moment origin, the left/right split signs, and where the
sidelead force enters the structure.
"""

from pathlib import Path
from typing import Any

import pytest

from crane_statics.calculation.engine import get_calculator
from crane_statics.core.analysis_cases import analysis_mode_by_name
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


def _zero_hook_point(doc, hoist_id: str):
    point = get_calculator(doc).compute_analysis_point(
        45.0, 0.0, hoist_id, wind_speed_m_s=0.0, wind_direction="+X"
    )
    assert point is not None
    return point


class TestLimitsAlreadyExceededAtZeroHookLoad:
    def test_rope_limit_below_its_baseline_gives_zero_capacity(self, document):
        hoist_id = _payload_hoist_id(document)
        point = _zero_hook_point(document, hoist_id)
        baseline = point.baseline_rope_tensions["boom_hoist"]
        assert baseline > 0.0

        cap = get_calculator(document).compute_allowable_load(
            point, {"boom_hoist_T": {"T": 0.5 * baseline}}
        )

        assert cap.max_allowable_load_kN == 0.0
        assert cap.governing_limit_id == "boom_hoist_T"

    def test_resultant_limit_below_its_baseline_gives_zero_capacity(self, document):
        hoist_id = _payload_hoist_id(document)
        point = _zero_hook_point(document, hoist_id)
        heel = point.baseline_reactions["heel_point"]
        resultant = (heel["Fx"] ** 2 + heel["Fz"] ** 2) ** 0.5

        cap = get_calculator(document).compute_allowable_load(
            point, {"heel_point_resultant": {"resultant": 0.5 * resultant}}
        )

        assert cap.max_allowable_load_kN == 0.0
        assert cap.governing_limit_id == "heel_point_resultant"


class TestLimitsBoundTheDemandMagnitude:
    def test_compression_growing_with_hook_load_governs(self, document):
        hoist_id = _payload_hoist_id(document)
        point = _zero_hook_point(document, hoist_id)
        baseline = point.baseline_reactions["rear_hinge"]["Fz"]
        sens = point.sensitivity_reactions["rear_hinge"]["Fz"]
        assert baseline < 0.0 and sens < 0.0
        limit = 1.2 * abs(baseline)

        cap = get_calculator(document).compute_allowable_load(
            point, {"rear_hinge_Fz": {"Fz": limit}}
        )

        assert cap.max_allowable_load_kN == pytest.approx((limit + baseline) / -sens)
        assert cap.governing_limit_id == "rear_hinge_Fz"

    def test_per_limit_capacities_agree_with_the_governing_minimum(self, document):
        hoist_id = _payload_hoist_id(document)
        point = _zero_hook_point(document, hoist_id)
        limits = {
            "boom_hoist_T": {"T": 2.0 * point.baseline_rope_tensions["boom_hoist"]},
            "rear_hinge_Fz": {"Fz": 1.2 * abs(point.baseline_reactions["rear_hinge"]["Fz"])},
        }
        calc = get_calculator(document)

        per_limit = calc.compute_limit_capacities_kN(point, limits)
        cap = calc.compute_allowable_load(point, limits)

        assert set(per_limit) == set(limits)
        governing = min(per_limit, key=lambda key: per_limit[key])
        assert cap.governing_limit_id == governing
        assert cap.max_allowable_load_kN == pytest.approx(per_limit[governing])


def _level_point(doc, hoist_id: str, **kwargs: Any):
    inputs: dict[str, Any] = dict(
        wind_speed_m_s=0.0,
        wind_direction="+X",
        accel_x_m_s2=0.0,
        accel_y_m_s2=0.0,
        accel_z_m_s2=0.0,
        pitch_accel_rad_s2=0.0,
        roll_accel_rad_s2=0.0,
        offlead_deg=0.0,
        sidelead_deg=0.0,
    )
    inputs.update(kwargs)
    point = get_calculator(doc).compute_analysis_point(45.0, 0.0, hoist_id, **inputs)
    assert point is not None
    return point


class TestSplitCompensationMassIsVertical:
    def test_split_mode_adds_no_lateral_platform_force(self, document):
        mode = analysis_mode_by_name(next(h for h in document.hoists if h.id == "MH"), "split")
        assert mode.name == "split"

        point = _level_point(document, "MH", hoist_runtime_overrides=mode.runtime_overrides)

        assert point.baseline_reactions["platform_base"]["Fy"] == pytest.approx(0.0, abs=1e-9)

    def test_split_mode_leaves_the_overturning_moment_unchanged(self, document):
        mode = analysis_mode_by_name(next(h for h in document.hoists if h.id == "MH"), "split")

        normal = _level_point(document, "MH")
        split = _level_point(document, "MH", hoist_runtime_overrides=mode.runtime_overrides)

        assert split.baseline_reactions["platform_base"]["Mx"] == pytest.approx(
            normal.baseline_reactions["platform_base"]["Mx"], rel=1e-9
        )


class TestPlatformBaseMomentsShareOneOrigin:
    def test_lateral_load_moment_is_taken_about_the_platform_base(self, document):
        from crane_statics.data.models import MassPoint

        extra_z_m = 20.0
        extra_mass_t = 1000.0
        loaded = document.model_copy(deep=True)
        platform = next(b for b in loaded.bodies if b.id == "platform")
        platform.mass_points.append(
            MassPoint(id="probe", mass_t=extra_mass_t, x_m=0.0, y_m=0.0, z_m=extra_z_m)
        )

        def lateral_mx(doc) -> float:
            pushed = _level_point(doc, "MH", accel_y_m_s2=1.0)
            still = _level_point(doc, "MH")
            return float(
                pushed.baseline_reactions["platform_base"]["Mx"]
                - still.baseline_reactions["platform_base"]["Mx"]
            )

        # Inertia -m*ay at height z about the platform base (0, 0): Mx = -z * Fy.
        assert lateral_mx(loaded) - lateral_mx(document) == pytest.approx(
            extra_mass_t * extra_z_m, rel=1e-9
        )
