"""Bearing uplift limit: the negated minimum line load, entered as a positive magnitude."""

import math
from pathlib import Path

import pytest

from crane_statics.calculation.engine import (
    compute_platform_base_max_bearing_line_load_kN_per_m,
    compute_platform_base_min_bearing_line_load_kN_per_m,
    get_calculator,
)
from crane_statics.core.analysis_services import (
    AnalysisCalculator,
    HoistStateService,
    KinematicsService,
)
from crane_statics.core.demand_extraction import (
    extract_connection_component_demand,
    extract_connection_component_response,
)
from crane_statics.core.io import load_document
from crane_statics.core.limit_components import KNOWN_LIMIT_COMPONENTS, LimitComponent
from crane_statics.core.limit_factory import DesignLimitFactory
from crane_statics.core.session_model import SessionModel

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"


class _FakePoint:
    def __init__(self, baseline, sensitivity):
        self.baseline_reactions = baseline
        self.sensitivity_reactions = sensitivity


def _point(fz: float, mx: float) -> _FakePoint:
    return _FakePoint(
        baseline={"platform_base": {"Fz": fz, "Mx": mx, "My": 0.0}},
        sensitivity={"platform_base": {}},
    )


def test_min_line_load_pure_axial_matches_max():
    kwargs = dict(fz_kN=100.0, mx_kNm=0.0, my_kNm=0.0, slewing_bearing_diameter_m=10.0)
    assert compute_platform_base_min_bearing_line_load_kN_per_m(
        **kwargs
    ) == compute_platform_base_max_bearing_line_load_kN_per_m(**kwargs)


def test_min_line_load_subtracts_moment_term():
    d = 4.0
    result = compute_platform_base_min_bearing_line_load_kN_per_m(
        fz_kN=100.0, mx_kNm=30.0, my_kNm=40.0, slewing_bearing_diameter_m=d
    )
    assert result == pytest.approx(100.0 / (math.pi * d) - 4.0 * 50.0 / (math.pi * d * d))


def test_min_line_load_rejects_non_positive_diameter():
    with pytest.raises(ValueError):
        compute_platform_base_min_bearing_line_load_kN_per_m(
            fz_kN=1.0, mx_kNm=0.0, my_kNm=0.0, slewing_bearing_diameter_m=0.0
        )


def test_component_registered():
    assert LimitComponent.MIN_BEARING_LINE_LOAD == "min_bearing_line_load"
    assert "min_bearing_line_load" in KNOWN_LIMIT_COMPONENTS


class TestUpliftDemand:
    def test_needs_the_bearing_diameter(self):
        assert (
            extract_connection_component_response(
                _point(10.0, 500.0),
                0.0,
                "platform_base",
                "min_bearing_line_load",
                support_widths_diameter_m=None,
            )
            is None
        )

    def test_uplift_is_positive_when_the_ring_lifts(self):
        d = 5.0
        q_min = compute_platform_base_min_bearing_line_load_kN_per_m(
            fz_kN=10.0, mx_kNm=500.0, my_kNm=0.0, slewing_bearing_diameter_m=d
        )
        assert q_min < 0.0
        demand = extract_connection_component_demand(
            _point(10.0, 500.0),
            0.0,
            "platform_base",
            "min_bearing_line_load",
            support_widths_diameter_m=d,
        )
        assert demand == pytest.approx(-q_min)

    def test_uplift_demand_is_zero_when_fully_compressed(self):
        demand = extract_connection_component_demand(
            _point(5000.0, 10.0),
            0.0,
            "platform_base",
            "min_bearing_line_load",
            support_widths_diameter_m=5.0,
        )
        assert demand == 0.0


class TestFactory:
    @pytest.fixture
    def document(self):
        if not EXAMPLE.exists():
            pytest.skip("Example file not found")
        return load_document(EXAMPLE)

    def test_limit_matches_the_max_limit_defaults(self, document):
        limits = {dl.id: dl for dl in DesignLimitFactory.create_for_document(document)}
        uplift = limits["platform_base_min_bearing_line_load"]
        peak = limits["platform_base_max_bearing_line_load"]
        assert uplift.component == "min_bearing_line_load"
        assert (uplift.max_kN, uplift.enabled) == (peak.max_kN, peak.enabled) == (None, False)

    def test_limit_omitted_without_diameter(self, document):
        document.support_widths.slewing_bearing_diameter_m = None
        limits = DesignLimitFactory.create_for_document(document)
        assert not any(dl.id == "platform_base_min_bearing_line_load" for dl in limits)


@pytest.fixture
def analysed():
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    doc = load_document(EXAMPLE)
    session = SessionModel()
    session.set_document(doc)
    calculator = AnalysisCalculator(session, KinematicsService(session), HoistStateService(session))
    pt = calculator.compute_analysis_point()
    assert pt is not None
    return doc, session, calculator, pt


def test_allowable_load_stops_at_the_uplift_limit(analysed):
    doc, _session, _calculator, pt = analysed
    base = pt.baseline_reactions["platform_base"]
    sens = pt.sensitivity_reactions["platform_base"]
    d = float(doc.support_widths.slewing_bearing_diameter_m)

    def uplift(h: float) -> float:
        return -compute_platform_base_min_bearing_line_load_kN_per_m(
            fz_kN=base.get("Fz", 0.0) + sens.get("Fz", 0.0) * h,
            mx_kNm=base.get("Mx", 0.0) + sens.get("Mx", 0.0) * h,
            my_kNm=base.get("My", base.get("M", 0.0)) + sens.get("My", sens.get("M", 0.0)) * h,
            slewing_bearing_diameter_m=d,
        )

    limit = max(uplift(0.0), 0.0) + 5.0
    limits = {"platform_base_min_bearing_line_load": {"min_bearing_line_load": limit}}
    capacity = get_calculator(doc).compute_allowable_load(pt, limits)

    if capacity.max_allowable_load_kN == float("inf"):
        pytest.skip("example never reaches the uplift limit")
    assert capacity.governing_limit_id == "platform_base_min_bearing_line_load"
    assert uplift(capacity.max_allowable_load_kN) == pytest.approx(limit, abs=1e-3)


def test_result_row_shows_uplift_and_utilization(analysed):
    _doc, session, calculator, pt = analysed
    limit = session.design_limits_by_id["platform_base_min_bearing_line_load"]
    limit.max_kN = 50.0
    limit.enabled = True

    _rope_rows, conn_rows = calculator.compute_result_rows(pt, hook_load_kN=0.0)

    row = next(r for r in conn_rows if r.component == "min_bearing_line_load")
    assert row.limit_kN == 50.0
    assert row.demand_kN >= 0.0
    assert row.utilization_pct == pytest.approx(row.demand_kN / 50.0 * 100.0)
