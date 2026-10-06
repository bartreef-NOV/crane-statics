"""Load chart view model: design limits, sweep results and export."""

from pathlib import Path

import pytest

from crane_statics.core.io import load_document
from crane_statics.core.limit_auto_set import compute_required_rope_capacity_kN
from crane_statics.qml_app.session import SessionState
from crane_statics.core.sweep import SweepCancelled, run_capacity_sweep
from crane_statics.qml_app.viewmodels.chart_vm import ChartViewModel

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"


@pytest.fixture
def chart_vm():
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    session = SessionState()
    vm = ChartViewModel(session)
    session.model.set_document(load_document(EXAMPLE))
    yield vm
    # Edits start a debounced background sweep; stop it before the next test runs.
    vm.shutdown()


@pytest.fixture(scope="class")
def rendered_chart_vm():
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    session = SessionState()
    vm = ChartViewModel(session)
    session.model.set_document(load_document(EXAMPLE))
    vm.drawBlocking()
    yield vm
    vm.shutdown()


class TestDesignLimits:
    def test_limits_models_populate_from_session(self, chart_vm):
        assert chart_vm.ropeLimitsModel.count > 0
        assert chart_vm.connectionLimitsModel.count > 0

    def test_setting_max_writes_through_and_marks_stale(self, chart_vm):
        row = chart_vm.ropeLimitsModel.row_at(0)
        chart_vm.setLimitMax(row["limitId"], "1234.5")

        dl = chart_vm._model.design_limits_by_id[row["limitId"]]
        assert dl.max_kN == pytest.approx(1234.5)
        assert chart_vm.stale is True
        assert chart_vm._model.dirty is True

    def test_blank_max_clears_the_limit(self, chart_vm):
        row = chart_vm.ropeLimitsModel.row_at(0)
        chart_vm.setLimitMax(row["limitId"], "500")
        chart_vm.setLimitMax(row["limitId"], "")

        assert chart_vm._model.design_limits_by_id[row["limitId"]].max_kN is None

    def test_non_numeric_max_is_ignored(self, chart_vm):
        row = chart_vm.ropeLimitsModel.row_at(0)
        chart_vm.setLimitMax(row["limitId"], "800")
        chart_vm.setLimitMax(row["limitId"], "abc")

        assert chart_vm._model.design_limits_by_id[row["limitId"]].max_kN == pytest.approx(800.0)

    def test_toggling_enabled_updates_the_model_row(self, chart_vm):
        row = chart_vm.ropeLimitsModel.row_at(0)
        chart_vm.setLimitEnabled(row["limitId"], True)

        assert chart_vm.ropeLimitsModel.row_at(0)["limitEnabled"] is True

    def test_auto_set_fills_and_enables_a_rope_limit(self, chart_vm):
        rope_row = chart_vm.ropeLimitsModel.row_at(0)
        chart_vm.autoSetLimit(rope_row["limitId"])

        dl = chart_vm._model.design_limits_by_id[rope_row["limitId"]]
        if dl.max_kN is None:
            assert "Could not compute" in chart_vm.statusText
        else:
            assert dl.enabled is True
            assert "Auto-set" in chart_vm.statusText

    def test_enabled_limits_payload_matches_session(self, chart_vm):
        row = chart_vm.ropeLimitsModel.row_at(0)
        chart_vm.setLimitMax(row["limitId"], "999")
        chart_vm.setLimitEnabled(row["limitId"], True)

        assert chart_vm._enabled_limits()[row["limitId"]] == {
            chart_vm._model.design_limits_by_id[row["limitId"]].component: 999.0
        }

    def test_rope_auto_set_requires_an_exact_rope_id(self, chart_vm):
        canonical_id = next(
            rope.id for rope in chart_vm._model.document.ropes if rope.id.endswith("__rope")
        )
        legacy_alias = canonical_id.replace("__rope", "_rope")

        assert (
            compute_required_rope_capacity_kN(
                chart_vm._model.document, canonical_id
            ).evaluated_hoists
            > 0
        )
        result = compute_required_rope_capacity_kN(chart_vm._model.document, legacy_alias)
        assert result.required_kN is None
        assert result.evaluated_hoists == 0


class TestChartMode:
    def test_default_mode_is_normal(self, chart_vm):
        assert chart_vm.chartMode == "normal"

    def test_split_mode_only_for_splitable_hoist(self, chart_vm):
        non_splitable = next(
            (hid for hid in chart_vm.hoistIds if not _splitable(chart_vm, hid)), None
        )
        if non_splitable is None:
            pytest.skip("No non-splitable hoist in example")
        chart_vm.selectHoist(non_splitable)

        chart_vm.setChartMode("split")

        assert chart_vm.chartMode == "normal"

    def test_split_mode_switches_contractual_dataset(self, chart_vm):
        splitable = next((hid for hid in chart_vm.hoistIds if _splitable(chart_vm, hid)), None)
        if splitable is None:
            pytest.skip("No splitable hoist in example")
        chart_vm.selectHoist(splitable)
        normal_count = chart_vm.contractualModel.count

        chart_vm.setChartMode("split")

        assert chart_vm.chartMode == "split"
        assert chart_vm.contractualModel.count != normal_count or normal_count == 0


class TestSweepRendering:
    def test_capacity_sweep_honors_cancellation(self, chart_vm):
        with pytest.raises(SweepCancelled):
            run_capacity_sweep(
                chart_vm._model.document,
                chart_vm.selectedHoistId,
                chart_vm._enabled_limits(),
                chart_vm.outreachStep,
                chart_vm._limit_display_names(),
                should_cancel=lambda: True,
            )

    def test_draw_populates_curve_and_markers(self, rendered_chart_vm):
        chart_vm = rendered_chart_vm

        assert chart_vm.stale is False
        assert len(chart_vm.curvePoints) > 0
        assert len(chart_vm.markers) > 0
        assert {m["status"] for m in chart_vm.markers} <= {"pass", "fail", "pending"}

    def test_curve_matches_the_core_sweep(self, rendered_chart_vm):
        chart_vm = rendered_chart_vm

        expected = run_capacity_sweep(
            chart_vm._model.document,
            chart_vm.selectedHoistId,
            chart_vm._enabled_limits(),
            chart_vm.outreachStep,
            chart_vm._limit_display_names(),
        )["modes"]["normal"]["curve_data"]

        assert len(chart_vm.curvePoints) == len(expected)
        for (x, y), (ex, ey) in zip(chart_vm.curvePoints, expected):
            assert x == pytest.approx(ex)
            assert y == pytest.approx(ey)

    def test_axis_ranges_cover_the_data(self, rendered_chart_vm):
        chart_vm = rendered_chart_vm
        ranges = chart_vm.axisRanges
        xs = [p[0] for p in chart_vm.curvePoints]

        assert ranges["xMin"] <= min(xs)
        assert ranges["xMax"] >= max(xs)
        assert ranges["yMin"] >= 0.0

    def test_axis_y_range_uses_capacity_not_limit_outliers(self, rendered_chart_vm):
        chart_vm = rendered_chart_vm
        capacity_range = chart_vm.axisRanges
        chart_vm._limit_series = [
            {
                "id": "outlier-limit",
                "label": "Outlier limit",
                "color": "#D55E00",
                "points": [[0.0, capacity_range["yMax"] * 100.0]],
            }
        ]

        updated_range = chart_vm.axisRanges

        assert updated_range["yMax"] == pytest.approx(capacity_range["yMax"])
        assert updated_range["yMin"] == pytest.approx(capacity_range["yMin"])

    def test_axis_ranges_are_safe_without_data(self, chart_vm):
        ranges = chart_vm.axisRanges

        assert ranges["xMax"] > ranges["xMin"]
        assert ranges["yMax"] > ranges["yMin"]

    def test_contractual_rows_gain_allowable_after_draw(self, rendered_chart_vm):
        chart_vm = rendered_chart_vm
        row = chart_vm.contractualModel.row_at(0)

        assert row["allowable"] != ""
        assert row["status"] in {"pass", "fail", "pending"}

    def test_limit_series_appear_when_limits_are_enabled(self, chart_vm):
        for index in range(chart_vm.ropeLimitsModel.count):
            row = chart_vm.ropeLimitsModel.row_at(index)
            chart_vm.autoSetLimit(row["limitId"])
        chart_vm.drawBlocking()

        if not chart_vm.limitSeries:
            pytest.skip("Example produced no sensitive limit series")
        assert all(series["points"] for series in chart_vm.limitSeries)
        assert len({series["id"] for series in chart_vm.limitSeries}) == len(chart_vm.limitSeries)


class TestContractualEditing:
    def test_add_and_delete_round_trip(self, chart_vm):
        before = chart_vm.contractualModel.count

        chart_vm.addContractualPoint({"outreach_m": 33.0, "load_t": 120.0})
        assert chart_vm.contractualModel.count == before + 1

        chart_vm.deleteContractualPoint(before)
        assert chart_vm.contractualModel.count == before

    def test_update_writes_back_to_the_document(self, chart_vm):
        chart_vm.updateContractualPoint(0, {"outreach_m": 31.5, "load_t": 77.0})
        fields = chart_vm.contractualFields(0)

        assert fields["outreach_m"] == pytest.approx(31.5)
        assert fields["load_t"] == pytest.approx(77.0)


class TestChartViewCommands:
    def test_reset_view_emits_for_the_plot(self, chart_vm):
        requested: list[int] = []
        chart_vm.resetViewRequested.connect(lambda: requested.append(1))

        chart_vm.resetView()

        assert requested == [1]


class TestExport:
    def test_csv_contains_every_series(self, chart_vm, tmp_path):
        from PyQt6.QtCore import QUrl

        chart_vm.drawBlocking()
        target = tmp_path / "chart.csv"

        assert chart_vm.exportCsv(QUrl.fromLocalFile(str(target))) is True

        lines = target.read_text(encoding="utf-8").splitlines()
        assert lines[0] == "series,outreach_m,load_t"
        assert any(line.startswith("capacity,") for line in lines[1:])
        assert any(line.startswith("contractual (") for line in lines[1:])

    def test_csv_export_reports_failure_for_bad_path(self, chart_vm, tmp_path):
        from PyQt6.QtCore import QUrl

        target = tmp_path / "missing_dir" / "chart.csv"

        assert chart_vm.exportCsv(QUrl.fromLocalFile(str(target))) is False
        assert "CSV export failed" in chart_vm.statusText


def _splitable(vm: ChartViewModel, hoist_id: str) -> bool:
    doc = vm._model.document
    assert doc is not None
    hoist = next((h for h in doc.hoists if h.id == hoist_id), None)
    return bool(hoist is not None and getattr(hoist, "splitable_block", False))


class TestVesselAttitude:
    def test_heel_edited_in_the_model_workspace_reaches_the_chart(self):
        from crane_statics.qml_app.viewmodels.model_vm import ModelViewModel

        if not EXAMPLE.exists():
            pytest.skip("Example file not found")
        session = SessionState()
        chart_vm = ChartViewModel(session)
        model_vm = ModelViewModel(session)
        session.model.set_document(load_document(EXAMPLE))
        chart_vm.drawBlocking()
        level_curve = list(chart_vm.curvePoints)

        model_vm.setEnvironmentValue("heel_deg", 3.0)
        chart_vm.drawBlocking()
        chart_vm.shutdown()

        expected = run_capacity_sweep(
            session.model.document,
            chart_vm.selectedHoistId,
            chart_vm._enabled_limits(),
            chart_vm.outreachStep,
            chart_vm._limit_display_names(),
        )["modes"]["normal"]["curve_data"]
        assert len(chart_vm.curvePoints) == len(expected)
        for (x, y), (ex, ey) in zip(chart_vm.curvePoints, expected):
            assert x == pytest.approx(ex)
            assert y == pytest.approx(ey)
        assert any(
            y != pytest.approx(level_y) for (_x, y), (_lx, level_y) in zip(expected, level_curve)
        )

    def test_condition_text_names_the_slew_envelope_on_a_tilted_vessel(self):
        if not EXAMPLE.exists():
            pytest.skip("Example file not found")
        doc = load_document(EXAMPLE)
        doc.environment.vessel_motion.heel_deg = 3.0
        doc.environment.vessel_motion.trim_deg = -1.0
        session = SessionState()
        chart_vm = ChartViewModel(session)
        session.model.set_document(doc)

        chart_vm.drawBlocking()
        chart_vm.shutdown()

        assert chart_vm.conditionText == "Worst case over 360° slew · heel +3.0°, trim -1.0°"

    def test_condition_text_is_empty_for_a_level_vessel(self, rendered_chart_vm):
        assert rendered_chart_vm.conditionText == ""
