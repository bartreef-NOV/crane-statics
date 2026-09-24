"""Behavior when 'slewing_bearing_diameter_m' is absent from a document.

The field is optional: omitting it must not fabricate a bearing-line-load
result anywhere downstream (limit catalog, demand extraction, result rows).
"""

import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from crane_statics.core.analysis_services import (
    AnalysisCalculator,
    HoistStateService,
    KinematicsService,
)
from crane_statics.core.demand_extraction import extract_connection_component_response
from crane_statics.core.io import load_document
from crane_statics.core.limit_factory import DesignLimitFactory
from crane_statics.core.session_model import SessionModel
from crane_statics.data.models import SupportWidths

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"


@pytest.fixture
def document():
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    return load_document(EXAMPLE)


class _FakePoint:
    def __init__(self, baseline, sensitivity):
        self.baseline_reactions = baseline
        self.sensitivity_reactions = sensitivity


class TestSupportWidthsModel:
    def test_allows_none_diameter(self):
        widths = SupportWidths(slewing_bearing_diameter_m=None)
        assert widths.slewing_bearing_diameter_m is None

    def test_still_rejects_non_positive_diameter(self):
        with pytest.raises(ValidationError):
            SupportWidths(slewing_bearing_diameter_m=0.0)


class TestDemandExtraction:
    def test_max_bearing_line_load_returns_none_when_diameter_missing(self):
        pt = _FakePoint(
            baseline={"platform_base": {"Fz": 100.0, "Mx": 10.0, "My": 5.0}},
            sensitivity={"platform_base": {}},
        )
        result = extract_connection_component_response(
            pt, 0.0, "platform_base", "max_bearing_line_load", support_widths_diameter_m=None
        )
        assert result is None

    def test_max_bearing_line_load_computes_when_diameter_present(self):
        pt = _FakePoint(
            baseline={"platform_base": {"Fz": 100.0, "Mx": 0.0, "My": 0.0}},
            sensitivity={"platform_base": {}},
        )
        result = extract_connection_component_response(
            pt, 0.0, "platform_base", "max_bearing_line_load", support_widths_diameter_m=10.0
        )
        assert result == pytest.approx(100.0 / (math.pi * 10.0))


class TestDesignLimitFactory:
    def test_omits_bearing_line_load_limit_when_diameter_none(self, document):
        document.support_widths.slewing_bearing_diameter_m = None
        limits = DesignLimitFactory.create_for_document(document)
        assert not any(dl.id == "platform_base_max_bearing_line_load" for dl in limits)

    def test_includes_bearing_line_load_limit_when_diameter_set(self, document):
        assert document.support_widths.slewing_bearing_diameter_m is not None
        limits = DesignLimitFactory.create_for_document(document)
        assert any(dl.id == "platform_base_max_bearing_line_load" for dl in limits)


class TestResultRowsOmitBearingLineLoad:
    def _compute_conn_rows(self, document):
        session = SessionModel()
        session.set_document(document)
        kin_svc = KinematicsService(session)
        hoist_svc = HoistStateService(session)
        calc = AnalysisCalculator(session, kin_svc, hoist_svc)
        pt = calc.compute_analysis_point()
        assert pt is not None
        _rope_rows, conn_rows = calc.compute_result_rows(pt, hook_load_kN=0.0)
        return conn_rows

    def test_no_bearing_line_load_row_when_diameter_none(self, document):
        document.support_widths.slewing_bearing_diameter_m = None
        conn_rows = self._compute_conn_rows(document)
        assert not any(r.component == "max_bearing_line_load" for r in conn_rows)

    def test_bearing_line_load_row_present_when_diameter_set(self, document):
        conn_rows = self._compute_conn_rows(document)
        assert any(r.component == "max_bearing_line_load" for r in conn_rows)
