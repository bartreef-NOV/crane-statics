"""Model health checks used by the QML status row."""

from pathlib import Path

import pytest

from crane_statics.core.io import create_default_document, load_document
from crane_statics.data.models import is_solve_hoist
from crane_statics.core.model_health import (
    collect_model_health_issues,
    format_issue_summary,
    health_status,
)
from crane_statics.qml_app.session import SessionState
from crane_statics.qml_app.viewmodels.model_vm import ModelViewModel
from tests.authored_helpers import example_path

EXAMPLE = example_path("crane_input_22689.yaml")


@pytest.fixture
def document():
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    return load_document(EXAMPLE)


class TestHealthChecks:
    def test_no_document_is_neutral(self):
        assert health_status(None) == ("none", "—", "Checks: —")

    def test_example_document_has_no_blocking_issues(self, document):
        blocking, _warnings = collect_model_health_issues(document)

        assert blocking == []

    def test_duplicate_node_ids_block(self, document):
        document.nodes.append(document.nodes[-1].model_copy(deep=True))

        blocking, _warnings = collect_model_health_issues(document)

        assert any("Duplicate node IDs" in issue for issue in blocking)
        assert health_status(document)[0] == "blocking"

    def test_missing_rope_segments_block(self, document):
        document.ropes[0].segments = []

        blocking, _warnings = collect_model_health_issues(document)

        assert any("missing rope segments" in issue for issue in blocking)

    def test_missing_solve_hoist_blocks(self, document):
        for rope in document.ropes:
            rope.tension_mode = "fixed"

        blocking, _warnings = collect_model_health_issues(document)

        assert any("solve-mode boom hoist" in issue for issue in blocking)

    def test_insufficient_boom_hoist_rope_length_warns(self, document):
        boom_hoist = next(h for h in document.hoists if is_solve_hoist(document, h.id))
        boom_hoist.rope_length_m = 0.0

        _blocking, warnings = collect_model_health_issues(document)

        assert any("insufficient rope length" in issue for issue in warnings)

    def test_unspecified_rope_length_never_warns(self, document):
        for hoist in document.hoists:
            hoist.rope_length_m = None

        _blocking, warnings = collect_model_health_issues(document)

        assert not any("insufficient rope length" in issue for issue in warnings)

    def test_short_payload_rope_length_is_not_a_warning_because_it_is_derived(self, document):
        payload_hoist = next(h for h in document.hoists if not is_solve_hoist(document, h.id))
        payload_hoist.rope_length_m = 0.0

        _blocking, warnings = collect_model_health_issues(document)

        assert not any("insufficient rope length" in issue for issue in warnings)

    def test_failed_derivation_warns(self, document):
        payload_hoist = next(h for h in document.hoists if not is_solve_hoist(document, h.id))
        payload_hoist.rope_length_m = None
        payload_hoist.max_hook_travel_m = None

        _blocking, warnings = collect_model_health_issues(document)

        assert any("could not be derived" in issue for issue in warnings)

    def test_design_height_below_the_sheave_at_max_outreach_warns(self, document):
        # The sheaves sit at ~162 m boomed up and ~30 m boomed out, so a design
        # height of 40 m is reachable close in and unreachable far out.
        for hoist in document.hoists:
            hoist.lowest_hook_height_m = 40.0

        _blocking, warnings = collect_model_health_issues(document)

        assert any("cannot reach the lowest hook height" in issue for issue in warnings)

    def test_validation_error_is_prepended_as_blocking(self, document):
        severity, verdict, checks = health_status(document, "bad value")

        assert severity == "blocking"
        assert verdict == "⚠ Cannot apply changes"
        assert "Validation failed: bad value" in checks

    def test_issue_summary_counts_extras(self):
        assert format_issue_summary([]) == ""
        assert format_issue_summary(["only"]) == "only"
        assert format_issue_summary(["first", "second", "third"]) == "first (+2 more)"

    def test_sample_truncates_long_id_lists(self, document):
        for index in range(5):
            clone = document.nodes[0].model_copy(deep=True)
            clone.id = f"dup_{index}"
            document.nodes.extend([clone, clone.model_copy(deep=True)])

        blocking, _warnings = collect_model_health_issues(document)
        duplicate_issue = next(issue for issue in blocking if "Duplicate node IDs" in issue)

        assert "+2 more" in duplicate_issue


class TestHealthOnViewModel:
    def test_view_model_exposes_the_status_strip(self, document):
        session = SessionState()
        vm = ModelViewModel(session)
        session.model.set_document(document)

        assert vm.healthSeverity in {"ok", "warning", "blocking"}
        assert vm.healthVerdict.startswith(("✓", "⚠"))
        assert vm.healthChecks.startswith("Checks:")

    def test_default_document_reports_its_own_health(self):
        session = SessionState()
        vm = ModelViewModel(session)
        session.model.set_document(create_default_document())

        severity, verdict, checks = health_status(session.model.document)
        assert vm.healthSeverity == severity
        assert vm.healthVerdict == verdict
        assert vm.healthChecks == checks


class TestConditionHoistHealth:
    """The conditions own each hoist's settings and charts: their gaps are health issues."""

    @staticmethod
    def _doc():
        from tests.rules_docs import GT283, load_v13

        return load_v13(GT283)

    def test_migrated_document_has_no_condition_issues(self):
        blocking, warnings = collect_model_health_issues(self._doc())
        assert blocking == []
        assert not any("contractual" in w for w in warnings)

    def test_payload_hoist_usable_in_no_condition_blocks(self):
        doc = self._doc()
        doc.conditions["default"].hoists.pop("AH")
        blocking, _warnings = collect_model_health_issues(doc)
        assert "Hoists usable in no condition: AH" in blocking

    def test_boom_or_unknown_hoist_in_a_condition_blocks(self):
        doc = self._doc()
        mh = doc.conditions["default"].hoists["MH"]
        doc.conditions["default"].hoists.update({"BH": mh, "XX": mh})
        blocking, _warnings = collect_model_health_issues(doc)
        assert "The boom hoist cannot be usable in a condition: BH in default" in blocking
        assert "Conditions list unknown hoists: XX in default" in blocking

    def test_usable_hoist_without_points_warns_naming_the_condition(self):
        doc = self._doc()
        doc.conditions["default"].hoists["AH"].contractual_points.clear()
        _blocking, warnings = collect_model_health_issues(doc)
        assert "Hoists without contractual points: AH in default" in warnings

    def test_document_without_conditions_blocks_without_crashing(self):
        doc = self._doc().model_copy(update={"conditions": {}})
        blocking, _warnings = collect_model_health_issues(doc)
        assert "At least one load condition is required" in blocking
