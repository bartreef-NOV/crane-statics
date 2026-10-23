"""Load chart view model: design limits, sweep results and export."""

from pathlib import Path

import pytest

from crane_statics.core.io import load_document
from crane_statics.core.limit_auto_set import compute_required_rope_capacity_kN
from crane_statics.qml_app.session import SessionState
from crane_statics.core.sweep import SweepCancelled, run_capacity_sweep, run_mode_sweep
from crane_statics.qml_app.viewmodels.chart_vm import ChartViewModel

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"


@pytest.fixture
def chart_vm():
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    session = SessionState()
    vm = ChartViewModel(session)
    session.model.set_document(load_document(EXAMPLE))
    return vm


@pytest.fixture(scope="class")
def rendered_chart_vm():
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    session = SessionState()
    vm = ChartViewModel(session)
    session.model.set_document(load_document(EXAMPLE))
    vm.drawBlocking()
    return vm


class TestDesignLimits:
    def test_limits_models_populate_from_session(self, chart_vm):
        assert chart_vm.ropeLimitsModel.count > 0
        assert chart_vm.connectionLimitsModel.count > 0

    def test_setting_max_writes_through_and_marks_stale(self, chart_vm):
        row = chart_vm.ropeLimitsModel.record_at(0)
        chart_vm.setLimitMax(row["limitId"], "1234.5")

        dl = chart_vm._model.design_limits_by_id[row["limitId"]]
        assert dl.max_kN == pytest.approx(1234.5)
        assert chart_vm.stale is True
        assert chart_vm._model.dirty is True

    def test_blank_max_clears_the_limit(self, chart_vm):
        row = chart_vm.ropeLimitsModel.record_at(0)
        chart_vm.setLimitMax(row["limitId"], "500")
        chart_vm.setLimitMax(row["limitId"], "")

        assert chart_vm._model.design_limits_by_id[row["limitId"]].max_kN is None

    def test_non_numeric_max_is_ignored(self, chart_vm):
        row = chart_vm.ropeLimitsModel.record_at(0)
        chart_vm.setLimitMax(row["limitId"], "800")
        chart_vm.setLimitMax(row["limitId"], "abc")

        assert chart_vm._model.design_limits_by_id[row["limitId"]].max_kN == pytest.approx(800.0)

    def test_toggling_enabled_updates_the_model_row(self, chart_vm):
        row = chart_vm.ropeLimitsModel.record_at(0)
        chart_vm.setLimitEnabled(row["limitId"], True)

        assert chart_vm.ropeLimitsModel.record_at(0)["limitEnabled"] is True

    def test_uplift_limit_is_listed_and_auto_sets_like_the_max_limit(self, chart_vm):
        limit_id = "platform_base_min_bearing_line_load"
        dl = chart_vm._model.design_limits_by_id[limit_id]
        assert (dl.max_kN, dl.enabled) == (None, False)

        chart_vm.autoSetLimit(limit_id)

        if dl.max_kN is None:
            assert dl.enabled is False
            assert chart_vm.statusText.startswith(("Could not compute", "No uplift"))
        else:
            assert dl.max_kN > 0.0 and dl.enabled is True
            assert "Auto-set" in chart_vm.statusText
            assert limit_id in chart_vm._enabled_limits()

    def test_auto_set_fills_and_enables_a_rope_limit(self, chart_vm):
        rope_row = chart_vm.ropeLimitsModel.record_at(0)
        chart_vm.autoSetLimit(rope_row["limitId"])

        dl = chart_vm._model.design_limits_by_id[rope_row["limitId"]]
        if dl.max_kN is None:
            assert "Could not compute" in chart_vm.statusText
        else:
            assert dl.enabled is True
            assert "Auto-set" in chart_vm.statusText

    def test_enabled_limits_payload_matches_session(self, chart_vm):
        row = chart_vm.ropeLimitsModel.record_at(0)
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
        row = chart_vm.contractualModel.record_at(0)

        assert row["allowable"] != ""
        assert row["status"] in {"pass", "fail", "pending"}

    def test_limit_series_appear_when_limits_are_enabled(self, chart_vm):
        for index in range(chart_vm.ropeLimitsModel.count):
            row = chart_vm.ropeLimitsModel.record_at(index)
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


class TestChartCaching:
    @pytest.fixture
    def sweep_calls(self, monkeypatch):
        from crane_statics.qml_app.viewmodels import chart_vm as chart_vm_module

        calls: list[tuple] = []
        real = chart_vm_module.run_mode_sweep

        def counting(*args, **kwargs):
            calls.append(args[1:3])
            return real(*args, **kwargs)

        monkeypatch.setattr(chart_vm_module, "run_mode_sweep", counting)
        return calls

    @staticmethod
    def _other_hoist(vm):
        return next((h for h in vm.hoistIds if h != vm.selectedHoistId), None)

    def test_switching_back_to_a_computed_chart_does_not_sweep(self, chart_vm, sweep_calls):
        other = self._other_hoist(chart_vm)
        if other is None:
            pytest.skip("Example has one payload hoist")
        first = chart_vm.selectedHoistId
        chart_vm.drawBlocking()
        first_points = list(chart_vm.curvePoints)
        chart_vm.selectHoist(other)
        chart_vm.drawBlocking()

        chart_vm.selectHoist(first)

        assert len(sweep_calls) == 2
        assert chart_vm.curvePoints == first_points
        assert chart_vm.stale is False

    def test_mode_switch_after_both_modes_computed_does_not_sweep(self, chart_vm, sweep_calls):
        splitable = next((h for h in chart_vm.hoistIds if _splitable(chart_vm, h)), None)
        if splitable is None:
            pytest.skip("No splitable hoist in example")
        chart_vm.selectHoist(splitable)
        chart_vm.drawBlocking()
        chart_vm.setChartMode("split")
        chart_vm.drawBlocking()
        assert len(sweep_calls) == 2

        chart_vm.setChartMode("normal")
        chart_vm.setChartMode("split")

        assert len(sweep_calls) == 2
        assert chart_vm.stale is False

    def test_a_limit_edit_misses_and_restoring_it_hits(self, chart_vm, sweep_calls):
        limit_id = chart_vm.ropeLimitsModel.record_at(0)["limitId"]
        chart_vm.setLimitEnabled(limit_id, True)
        chart_vm.setLimitMax(limit_id, "900")
        chart_vm.drawBlocking()
        assert len(sweep_calls) == 1

        chart_vm.setLimitMax(limit_id, "950")
        chart_vm.drawBlocking()
        assert len(sweep_calls) == 2

        chart_vm.setLimitMax(limit_id, "900")
        chart_vm.drawBlocking()
        assert len(sweep_calls) == 2

    def test_outreach_step_change_misses_the_cache(self, chart_vm, sweep_calls):
        chart_vm.drawBlocking()

        chart_vm.setOutreachStep(2.0)
        chart_vm.drawBlocking()

        assert len(sweep_calls) == 2

    def test_switching_hoist_clears_the_displayed_chart_until_available(self, chart_vm):
        other = self._other_hoist(chart_vm)
        if other is None:
            pytest.skip("Example has one payload hoist")
        chart_vm.drawBlocking()
        assert chart_vm.curvePoints

        chart_vm.selectHoist(other)

        assert chart_vm.curvePoints == []
        assert chart_vm.stale is True

    def test_result_is_never_rendered_under_another_hoist(self, chart_vm):
        other = self._other_hoist(chart_vm)
        if other is None:
            pytest.skip("Example has one payload hoist")
        key = chart_vm._wanted_key()
        payload = run_mode_sweep(
            chart_vm._model.document,
            key.hoist_id,
            key.mode,
            chart_vm._enabled_limits(),
            chart_vm.outreachStep,
            chart_vm._limit_display_names(),
        )
        chart_vm._busy = True
        chart_vm.selectHoist(other)
        emitted: list[int] = []
        chart_vm.statusChanged.connect(lambda: emitted.append(1))

        chart_vm._on_sweep_finished(key, payload)

        assert chart_vm.curvePoints == []
        assert chart_vm.markers == []
        assert chart_vm.busy is False
        assert emitted
        assert chart_vm._cache.get(key) is payload

    def test_discarded_result_restores_the_cached_chart_status(self, chart_vm):
        other = self._other_hoist(chart_vm)
        if other is None:
            pytest.skip("Example has one payload hoist")
        first = chart_vm.selectedHoistId
        key = chart_vm._wanted_key()
        payload = run_mode_sweep(
            chart_vm._model.document,
            key.hoist_id,
            key.mode,
            chart_vm._enabled_limits(),
            chart_vm.outreachStep,
            chart_vm._limit_display_names(),
        )
        chart_vm.selectHoist(other)
        chart_vm.drawBlocking()
        shown = list(chart_vm.curvePoints)
        chart_vm._busy = True
        chart_vm._set_status("Sweeping... 40%")
        chart_vm.selectHoist(first)
        chart_vm.selectHoist(other)
        emitted: list[int] = []
        chart_vm.statusChanged.connect(lambda: emitted.append(1))

        chart_vm._on_sweep_finished(key, payload)

        assert chart_vm.curvePoints == shown
        assert chart_vm.busy is False
        assert emitted
        assert chart_vm.statusText.startswith("Done - ")

    def test_failed_sweep_for_an_unwanted_key_clears_busy(self, chart_vm):
        other = self._other_hoist(chart_vm)
        if other is None:
            pytest.skip("Example has one payload hoist")
        key = chart_vm._wanted_key()
        chart_vm._busy = True
        chart_vm.selectHoist(other)
        emitted: list[int] = []
        chart_vm.statusChanged.connect(lambda: emitted.append(1))

        chart_vm._on_sweep_failed("boom", key)

        assert chart_vm.busy is False
        assert emitted


def _splitable(vm: ChartViewModel, hoist_id: str) -> bool:
    doc = vm._model.document
    assert doc is not None
    hoist = next((h for h in doc.hoists if h.id == hoist_id), None)
    return bool(hoist is not None and getattr(hoist, "splitable_block", False))
