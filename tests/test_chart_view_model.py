"""Load chart view model: design limits, sweep results and export."""

from pathlib import Path

import pytest

from crane_statics.core.io import load_document
from crane_statics.core.limit_auto_set import compute_required_rope_capacity_kN
from crane_statics.qml_app.session import SessionState
from crane_statics.core.sweep import SweepCancelled, run_capacity_sweep, run_mode_sweep
from crane_statics.qml_app.viewmodels.chart_vm import ChartViewModel
from tests.test_chart_background import limit_rows
from tests.authored_helpers import example_path

EXAMPLE = example_path("crane_input_22689.yaml")
# Coarse grid: these tests check wiring and caching, not curve resolution.
STEP = 10.0


@pytest.fixture
def chart_vm():
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    session = SessionState()
    vm = ChartViewModel(session)
    vm.setOutreachStep(STEP)
    session.model.set_document(load_document(EXAMPLE))
    return vm


@pytest.fixture(scope="class")
def rendered_chart_vm():
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    session = SessionState()
    vm = ChartViewModel(session)
    vm.setOutreachStep(STEP)
    session.model.set_document(load_document(EXAMPLE))
    vm.drawBlocking()
    return vm


class TestDesignLimits:
    def test_limits_models_populate_from_session(self, chart_vm):
        assert limit_rows(chart_vm, "rope")
        assert limit_rows(chart_vm, "connection")

    @staticmethod
    def _records(vm):
        return [vm.limitsModel.record_at(i) for i in range(vm.limitsModel.count)]

    def test_limits_are_grouped_by_component_ropes_first(self, chart_vm):
        records = self._records(chart_vm)
        headers = [r for r in records if r["isGroup"]]

        assert records[0]["isGroup"] and records[0]["groupName"] == "Ropes"
        assert len({r["groupId"] for r in headers}) == len(headers) > 1
        # Every limit sits under the header of its own group.
        current = None
        for r in records:
            current = r if r["isGroup"] else current
            assert r["groupId"] == current["groupId"]
        # Rows carry the quantity only; the component is the header.
        assert any(r["name"] == "Fx" for r in records if not r["isGroup"])

    def test_collapsing_a_group_hides_its_rows_only(self, chart_vm):
        full = chart_vm.limitsModel.count
        group = self._records(chart_vm)[0]
        members = len(group["limitIds"])

        chart_vm.toggleLimitGroup(0)
        assert chart_vm.limitsModel.count == full - members
        assert chart_vm.limitsModel.record_at(0)["name"].startswith("▸")

        chart_vm.toggleLimitGroup(0)
        assert chart_vm.limitsModel.count == full

    def test_filter_keeps_matching_groups_and_limits(self, chart_vm):
        chart_vm.toggleLimitGroup(0)  # a filter opens collapsed groups it matches
        chart_vm.setLimitFilter("rear hinge")
        records = self._records(chart_vm)
        assert records and {r["groupName"] for r in records} == {"Rear Hinge"}
        assert any(not r["isGroup"] for r in records)

        chart_vm.setLimitFilter("fx")
        rows = [r for r in self._records(chart_vm) if not r["isGroup"]]
        assert rows and all(r["name"] == "Fx" for r in rows)

        chart_vm.setLimitFilter("")
        assert limit_rows(chart_vm, "connection")

    def test_group_checkbox_switches_every_limit_and_shows_mixed_state(self, chart_vm):
        model = chart_vm.limitsModel
        header = model.record_at(0)
        assert model.cellAction(0, 0) == "group"
        assert model.cellAction(0, 3) == "check"
        assert len(header["limitIds"]) > 1
        for limit_id in header["limitIds"]:
            chart_vm.setLimitEnabled(limit_id, False)
        assert model.record_at(0)["checkState"] == 0

        chart_vm.setLimitEnabled(header["limitIds"][0], True)
        assert model.record_at(0)["checkState"] == 1

        model.toggleCheck(0, 3)
        assert model.record_at(0)["checkState"] == 2
        assert all(chart_vm._model.design_limits_by_id[i].enabled for i in header["limitIds"])

        model.toggleCheck(0, 3)
        assert model.record_at(0)["checkState"] == 0
        assert chart_vm.stale is True

    def test_group_header_has_no_editable_max(self, chart_vm):
        assert chart_vm.limitsModel.isCellEditable(0, 2) is False
        assert chart_vm.limitsModel.isCellEditable(1, 2) is True

    def test_auto_on_a_group_header_sets_its_limits(self, chart_vm):
        header = chart_vm.limitsModel.record_at(0)
        chart_vm.autoSetLimitRow(0)

        limits = [chart_vm._model.design_limits_by_id[i] for i in header["limitIds"]]
        if not any(dl.enabled for dl in limits):
            assert "Could not" in chart_vm.statusText
        else:
            assert "Auto-set" in chart_vm.statusText

    def test_setting_max_writes_through_and_marks_stale(self, chart_vm):
        row = limit_rows(chart_vm, "rope")[0]
        chart_vm.setLimitMax(row["limitId"], "1234.5")

        dl = chart_vm._model.design_limits_by_id[row["limitId"]]
        assert dl.max_kN == pytest.approx(1234.5)
        assert chart_vm.stale is True
        assert chart_vm._model.dirty is True

    def test_blank_max_clears_the_limit(self, chart_vm):
        row = limit_rows(chart_vm, "rope")[0]
        chart_vm.setLimitMax(row["limitId"], "500")
        chart_vm.setLimitMax(row["limitId"], "")

        assert chart_vm._model.design_limits_by_id[row["limitId"]].max_kN is None

    def test_non_numeric_max_is_ignored(self, chart_vm):
        row = limit_rows(chart_vm, "rope")[0]
        chart_vm.setLimitMax(row["limitId"], "800")
        chart_vm.setLimitMax(row["limitId"], "abc")

        assert chart_vm._model.design_limits_by_id[row["limitId"]].max_kN == pytest.approx(800.0)

    def test_toggling_enabled_updates_the_model_row(self, chart_vm):
        row = limit_rows(chart_vm, "rope")[0]
        chart_vm.setLimitEnabled(row["limitId"], True)

        assert limit_rows(chart_vm, "rope")[0]["checkState"] == 2

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
        rope_row = limit_rows(chart_vm, "rope")[0]
        chart_vm.autoSetLimit(rope_row["limitId"])

        dl = chart_vm._model.design_limits_by_id[rope_row["limitId"]]
        if dl.max_kN is None:
            assert "Could not compute" in chart_vm.statusText
        else:
            assert dl.enabled is True
            assert "Auto-set" in chart_vm.statusText

    def test_enabled_limits_payload_matches_session(self, chart_vm):
        row = limit_rows(chart_vm, "rope")[0]
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
        for row in limit_rows(chart_vm, "rope"):
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

        added = [
            chart_vm.contractualFields(i) for i in range(chart_vm.contractualModel.count)
        ].index({"outreach_m": 33.0, "load_t": 120.0})
        chart_vm.deleteContractualPoint(added)
        assert chart_vm.contractualModel.count == before
        assert {"outreach_m": 33.0, "load_t": 120.0} not in [
            chart_vm.contractualFields(i) for i in range(chart_vm.contractualModel.count)
        ]

    def test_markers_follow_edits_in_row_order(self, chart_vm):
        before = chart_vm.contractualModel.count

        chart_vm.addContractualPoint({"outreach_m": 33.0, "load_t": 120.0})
        assert len(chart_vm.markers) == before + 1
        # The new point takes its place in outreach order (was: appended last).
        row = next(
            i for i, m in enumerate(chart_vm.markers) if m["outreach"] == pytest.approx(33.0)
        )
        assert chart_vm.markers[row]["status"] == "pending"
        assert [m["outreach"] for m in chart_vm.markers] == sorted(
            m["outreach"] for m in chart_vm.markers
        )

        chart_vm.deleteContractualPoint(row)
        assert len(chart_vm.markers) == before

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


class TestClauseTrailExport:
    @staticmethod
    def _export(vm, tmp_path):
        import csv
        from PyQt6.QtCore import QUrl

        target = tmp_path / "chart.csv"
        assert vm.exportCsv(QUrl.fromLocalFile(str(target))) is True
        return target, list(csv.reader(target.read_text(encoding="utf-8").splitlines()))

    @staticmethod
    def _rules_vm():
        from tests.rules_docs import gale, rules_doc, without_suspended_rope

        session = SessionState()
        vm = ChartViewModel(session)
        vm.setOutreachStep(20.0)
        doc = without_suspended_rope(rules_doc("ABS", gale()))
        session.model.set_document(doc)
        vm.drawBlocking()
        return vm

    def test_legacy_export_is_byte_identical_to_the_pre_change_export(self, chart_vm, tmp_path):
        # Golden file: the export of this document at commit 6bf2331 (before the clause
        # trail existed), not derived from the current code.
        chart_vm.drawBlocking()
        target, _rows = self._export(chart_vm, tmp_path)
        golden = Path(__file__).parent / "data" / "legacy_chart_export.csv"

        def norm(data: bytes) -> bytes:
            return data.replace(b"\r\n", b"\n")  # git may normalise line endings

        assert norm(target.read_bytes()) == norm(golden.read_bytes())

    def test_rules_export_adds_the_clause_columns(self, tmp_path):
        vm = self._rules_vm()
        _target, rows = self._export(vm, tmp_path)
        assert rows[0] == [
            "series",
            "outreach_m",
            "load_t",
            "condition",
            "case",
            "factor",
            "unit",
            "inputs",
            "formula",
            "clause",
            "source",
            "warnings",
        ]
        assert all(len(r) == 12 for r in rows)
        capacity = [r for r in rows[1:] if r[0] == "capacity"]
        assert capacity
        assert {r[3] for r in capacity} == {"gale"}
        assert {r[4] for r in capacity} == {"In-service"}
        assert {r[10] for r in capacity} <= {"computed", "override"}
        assert all(r[9] and r[8] for r in capacity)  # clause and formula
        factors = [r for r in capacity if r[5].startswith("dynamic_factor=")]
        # One computed factor row per curve point (GT283's authored daf adds an override row).
        computed = [r for r in factors if r[10] == "computed"]
        assert len(computed) == len(vm.curvePoints)
        assert all("=" in r[7] for r in computed)  # inputs rendered as name=value; ...
        # Limit and contractual rows carry no clause trail.
        others = [r for r in rows[1:] if r[0] != "capacity"]
        assert all(r[3:] == [""] * 9 for r in others)

    def test_dnv_export_shows_the_governing_case(self, tmp_path):
        from tests.rules_docs import gale, rules_doc, without_suspended_rope

        session = SessionState()
        vm = ChartViewModel(session)
        vm.setOutreachStep(20.0)
        doc = without_suspended_rope(rules_doc("DNV", gale(wind=30.0), gale("calm", wind=5.0)))
        session.model.set_document(doc)
        vm.drawBlocking()
        _target, rows = self._export(vm, tmp_path)
        capacity = [r for r in rows[1:] if r[0] == "capacity"]
        assert capacity and {r[4] for r in capacity} <= {"Case I", "Case II"}
        assert all(r[4] for r in capacity)

    def test_dnv_vessel_accelerations_are_warned_in_csv_and_details(self, tmp_path):
        from tests.rules_docs import gale, rules_doc, without_suspended_rope

        session = SessionState()
        vm = ChartViewModel(session)
        vm.setOutreachStep(20.0)
        # gale()'s motion carries accel_x 0.8 m/s^2, which DNV does not apply.
        doc = without_suspended_rope(rules_doc("DNV", gale()))
        session.model.set_document(doc)
        vm.drawBlocking()
        warning = "vessel accelerations are not applied under DNV"
        _target, rows = self._export(vm, tmp_path)
        capacity = [r for r in rows[1:] if r[0] == "capacity"]
        assert capacity and all(warning in r[11] for r in capacity)
        vm.setDetailOutreach(vm.curvePoints[0][0])
        assert any(warning in w for w in vm.provenanceWarnings)

    def test_rules_export_marks_a_manual_daf_as_override(self, tmp_path):
        from tests.rules_docs import gale, rules_doc, without_suspended_rope

        session = SessionState()
        vm = ChartViewModel(session)
        vm.setOutreachStep(20.0)
        doc = without_suspended_rope(rules_doc("ABS", gale()))
        hoists = [h.model_copy(update={"hook_daf": 1.7}) for h in doc.hoists]
        session.model.set_document(doc.model_copy(update={"hoists": hoists}))
        vm.drawBlocking()
        _target, rows = self._export(vm, tmp_path)
        assert "override" in {r[10] for r in rows[1:]}

    def test_cached_chart_exports_its_own_trail_and_edits_change_the_key(
        self, tmp_path, monkeypatch
    ):
        import crane_statics.qml_app.viewmodels.chart_vm as chart_vm_module

        from tests.rules_docs import gale, rules_doc, without_suspended_rope

        session = SessionState()
        vm = ChartViewModel(session)
        vm.setOutreachStep(20.0)
        base = without_suspended_rope(rules_doc("ABS", gale()))

        def with_daf(daf):
            doc = base.model_copy(deep=True)
            for entry in doc.conditions["gale"].hoists.values():
                entry.daf = daf
            return doc

        plain = with_daf(None)  # derived (v12: hook_daf 1.0)
        manual = with_daf(1.7)  # the manual override

        def sources() -> set:
            _t, rows = self._export(vm, tmp_path)
            return {r[10] for r in rows[1:] if r[0] == "capacity"}

        session.model.set_document(plain)
        vm.drawBlocking()
        key_plain = vm._wanted_key()
        assert sources() == {"computed"}
        session.model.set_document(manual)
        vm.drawBlocking()
        key_manual = vm._wanted_key()
        assert key_manual != key_plain and sources() == {"computed", "override"}

        # A repeated draw is served from the cache and exports the same trail.
        def no_sweep(*_a, **_k):
            raise AssertionError("served from the cache")

        monkeypatch.setattr(chart_vm_module, "run_mode_sweep", no_sweep)
        assert vm._cache.get(key_manual) is not None
        vm.drawBlocking()
        assert sources() == {"computed", "override"}

    def test_a_condition_is_part_of_the_chart_key(self):
        from crane_statics.core.chart_cache import ChartCache, ChartKey

        cache = ChartCache()
        gale_key = ChartKey("MH", "normal", 20.0, "fp", "gale")
        calm_key = ChartKey("MH", "normal", 20.0, "fp", "calm")
        assert gale_key != calm_key
        cache.put(gale_key, {"condition": "gale", "provenance": []})
        cache.put(calm_key, {"condition": "calm", "provenance": []})
        assert cache.get(gale_key)["condition"] == "gale"
        assert cache.get(calm_key)["condition"] == "calm"

    def test_export_refuses_while_partial(self, chart_vm, tmp_path):
        from PyQt6.QtCore import QUrl

        chart_vm.drawBlocking()
        chart_vm._partial = True
        target = tmp_path / "chart.csv"
        assert chart_vm.exportCsv(QUrl.fromLocalFile(str(target))) is False
        assert not target.exists()


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
        limit_id = limit_rows(chart_vm, "rope")[0]["limitId"]
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


def _rules_chart_vm(doc) -> ChartViewModel:
    session = SessionState()
    vm = ChartViewModel(session)
    vm.setOutreachStep(20.0)
    session.model.set_document(doc)
    return vm


class TestConditionSelector:
    def test_a_rules_less_document_selects_its_default_condition(self, chart_vm):
        # v13: its one condition is ``default`` (was: no condition to select).
        assert chart_vm.conditionNames == ["default"]
        assert chart_vm.currentCondition == "default"
        assert chart_vm._wanted_job().condition == "default"
        chart_vm.setCurrentCondition("nope")  # ignored: not a condition of the document
        assert chart_vm.currentCondition == "default"

    def test_switching_the_condition_draws_its_own_chart(self):
        from tests.rules_docs import gale, rules_doc, without_suspended_rope

        doc = without_suspended_rope(rules_doc("ABS", gale(wind=30.0), gale("calm", wind=5.0)))
        vm = _rules_chart_vm(doc)
        assert vm.conditionNames == ["gale", "calm"]
        assert vm.currentCondition == "gale"
        vm.drawBlocking()
        gale_key = vm._wanted_key()
        gale_points = [list(p) for p in vm.curvePoints]
        assert gale_key.condition == "gale" and gale_points

        emitted: list[int] = []
        vm.conditionChanged.connect(lambda: emitted.append(1))
        vm.setCurrentCondition("calm")
        assert emitted and vm.currentCondition == "calm"
        calm_key = vm._wanted_key()
        assert calm_key.condition == "calm" and calm_key != gale_key
        # The gale chart is not reused for calm: nothing is shown until it is computed.
        assert vm._cache.get(calm_key) is None
        assert vm.curvePoints == [] and vm.provenanceRows == []
        # Every job is re-planned for calm: the one started and the precompute behind it.
        assert vm._running is not None and vm._running.job.condition == "calm"
        assert vm._queue and all(job.condition == "calm" for job in vm._queue)
        vm._cancel_all()
        vm.drawBlocking()
        assert vm.curvePoints and vm.curvePoints != gale_points
        assert vm._cache.get(gale_key) is not None

        # Back to gale: served from its own cache entry.
        vm.setCurrentCondition("gale")
        assert [list(p) for p in vm.curvePoints] == gale_points
        vm.setCurrentCondition("nope")
        assert vm.currentCondition == "gale"
        vm.shutdown()

    def test_a_removed_condition_falls_back_to_the_first(self):
        from tests.rules_docs import gale, rules_doc, without_suspended_rope

        doc = without_suspended_rope(rules_doc("ABS", gale(wind=30.0), gale("calm", wind=5.0)))
        vm = _rules_chart_vm(doc)
        vm.setCurrentCondition("calm")
        vm._cancel_all()
        doc.conditions.pop("calm")
        vm._model.mark_content_changed()
        assert vm.conditionNames == ["gale"]
        assert vm.currentCondition == "gale"
        vm.shutdown()


class TestCalculationDetails:
    @staticmethod
    def _drawn(doc) -> ChartViewModel:
        vm = _rules_chart_vm(doc)
        vm.drawBlocking()
        return vm

    def test_the_inspected_point_lists_the_dynamic_factor_with_its_clause(self):
        from tests.rules_docs import gale, rules_doc, without_suspended_rope

        vm = self._drawn(without_suspended_rope(rules_doc("ABS", gale())))
        assert vm.provenanceRows == []  # nothing inspected yet
        x = vm.curvePoints[1][0]
        vm.setDetailOutreach(x + 0.3)  # the nearest curve point
        rows = vm.provenanceRows
        keys = {"quantity", "value", "unit", "clause", "formula", "source", "warnings", "case"}
        assert rows and all(keys <= set(r) for r in rows)
        factor = [r for r in rows if r["quantity"] == "Dynamic factor"]
        assert factor and all(r["clause"] for r in factor)
        assert {r["case"] for r in rows} == {"In-service"}
        assert "gale" in vm.provenanceHeading and f"{x:.1f} m" in vm.provenanceHeading
        assert any("rope-only" in note for note in vm.calculationNotes)
        assert not any("SH" in note for note in vm.calculationNotes)

        vm.setDetailOutreach(-1.0)  # nothing inspected
        assert vm.provenanceRows == []
        vm.shutdown()

    def test_a_manual_daf_shows_as_an_override(self):
        from tests.rules_docs import gale, rules_doc, without_suspended_rope

        doc = without_suspended_rope(rules_doc("ABS", gale()))
        hoists = [h.model_copy(update={"hook_daf": 1.7}) for h in doc.hoists]
        vm = self._drawn(doc.model_copy(update={"hoists": hoists}))
        vm.setDetailOutreach(vm.curvePoints[0][0])
        overrides = [r for r in vm.provenanceRows if r["source"] == "override"]
        assert overrides and overrides[0]["quantity"] == "Dynamic factor"
        assert overrides[0]["display"].endswith("(manual override)")
        assert not any(
            r["display"].endswith("(manual override)")
            for r in vm.provenanceRows
            if r["source"] == "computed"
        )
        vm.shutdown()

    def test_a_hoisting_speed_below_the_minimum_is_listed_as_a_warning(self):
        from tests.rules_docs import rules_doc
        from tests.test_lift_factor import _rules, _sea

        doc = _rules(rules_doc("ABS", _sea()), daf=None)  # v12 hook_daf 1.0: derived
        hoists = [
            h.model_copy(update={"max_hoisting_speed_m_s": 0.1}) if h.id == "MH" else h
            for h in doc.hoists
        ]
        vm = _rules_chart_vm(doc.model_copy(update={"hoists": hoists}))
        vm.selectHoist("MH")
        vm.drawBlocking()
        vm.setDetailOutreach(vm.curvePoints[0][0])
        warnings = vm.provenanceWarnings
        speed = [w for w in warnings if "max_hoisting_speed_m_s" in w]
        assert len(speed) == 1 and "below the ABS minimum" in speed[0]
        assert all(r["warnings"] == " | ".join(warnings) for r in vm.provenanceRows)
        vm.shutdown()

    def test_values_and_inputs_are_plain_numbers(self):
        from crane_statics.presentation.formatters import ProvenanceFormatter
        from crane_statics.rules.types import ProvenanceRecord

        record = ProvenanceRecord(
            "load_wind_force", 10600.0, "kN", "c", "F", {"W_kN": 10560.4, "cabin": True}, "computed"
        )
        (row,) = ProvenanceFormatter.detail_rows([record], (), "Case II")
        assert row["value"] == "10600" and row["unit"] == "kN"
        assert row["inputs"] == "W_kN=10560; cabin=true"
        assert row["display"] == "Load wind force = 10600 kN  [c]  F"
        assert ProvenanceFormatter.plain_number(0.00012) == "0.00012"
        assert ProvenanceFormatter.plain_number(4.71683) == "4.717"
        assert "e" not in ProvenanceFormatter.plain_number(1.06e-7)

    def test_the_plot_point_decides_what_is_inspected(self):
        from tests.rules_docs import gale, rules_doc, without_suspended_rope

        vm = self._drawn(without_suspended_rope(rules_doc("ABS", gale())))
        x = vm.curvePoints[0][0]
        vm.inspectChartPoint({"seriesId": "", "outreach": x, "load": 1.0})
        assert vm.provenanceRows
        vm.inspectChartPoint({"index": 0, "outreach": x, "load": 1.0})  # a contractual marker
        assert vm.provenanceRows == []
        vm.inspectChartPoint({"seriesId": "BH__rope_T", "outreach": x})
        assert vm.provenanceRows
        vm.inspectChartPoint(None)
        assert vm.provenanceRows == []
        vm.shutdown()

    @pytest.mark.parametrize(
        "example", ["crane_input_GT283_abs.yaml", "crane_input_GT283_dnv.yaml"]
    )
    def test_inspect_from_a_drawn_chart_fills_rows(self, example):
        """The shipped rules examples, drawn to completion: a curve point and a limit
        point both fill the details."""
        vm = self._drawn(load_document(EXAMPLE.parent / example))
        assert vm.chartComplete and vm.curvePoints
        x = vm.curvePoints[len(vm.curvePoints) // 2][0]
        vm.inspectChartPoint({"seriesId": "", "outreach": x, "load": 1.0})
        assert vm.provenanceRows
        vm.inspectChartPoint(None)
        assert vm.provenanceRows == []
        assert vm.limitSeries
        limit_id = vm.limitSeries[0]["id"]
        vm.inspectChartPoint({"seriesId": limit_id, "outreach": x, "load": 1.0})
        assert vm.provenanceRows
        vm.shutdown()

    def test_dnv_notes_state_that_sh_is_omitted(self):
        from tests.rules_docs import gale, rules_doc, without_suspended_rope

        vm = _rules_chart_vm(without_suspended_rope(rules_doc("DNV", gale())))
        assert any("SH" in note for note in vm.calculationNotes)
        assert any("rope-only" in note for note in vm.calculationNotes)
        vm.shutdown()

    def test_a_legacy_chart_has_no_details(self, chart_vm):
        chart_vm.drawBlocking()
        chart_vm.setDetailOutreach(chart_vm.curvePoints[0][0])
        assert chart_vm.provenanceRows == []
        assert chart_vm.calculationNotes == []
        assert chart_vm.provenanceHeading == ""


class TestConditionLifecycle:
    @staticmethod
    def _doc():
        from tests.rules_docs import gale, rules_doc, without_suspended_rope

        return without_suspended_rope(rules_doc("ABS", gale(wind=30.0), gale("calm", wind=5.0)))

    def test_switching_during_a_running_sweep_ignores_the_old_payload(self):
        from tests.qt_helpers import wait_until

        reference = _rules_chart_vm(self._doc())
        reference.setCurrentCondition("calm")
        reference._cancel_all()
        reference.drawBlocking()
        calm_points = [list(p) for p in reference.curvePoints]
        reference.shutdown()

        vm = _rules_chart_vm(self._doc())
        vm.draw()  # the gale sweep starts on its worker
        assert vm._running is not None and vm._running.job.condition == "gale"
        vm.setCurrentCondition("calm")
        calm_key = vm._wanted_key()
        wait_until(lambda: vm._cache.get(calm_key) is not None and vm.chartComplete)
        wait_until(lambda: vm._displayed_key == calm_key)
        assert [list(p) for p in vm.curvePoints] == calm_points
        assert vm._displayed_key.condition == "calm"
        vm.shutdown()

    def test_the_condition_persists_across_edits_and_resets_on_another_document(self):
        vm = _rules_chart_vm(self._doc())
        model = vm._model
        resets: list[int] = []
        vm.detailsReset.connect(lambda: resets.append(1))
        vm.setCurrentCondition("calm")
        vm._cancel_all()
        limit = next(dl for dl in model.design_limits if dl.kind == "rope")
        vm.setLimitMax(limit.id, "1234")  # an edit of the same document
        vm._cancel_all()
        assert vm.currentCondition == "calm"
        assert model.undo()
        vm._cancel_all()
        assert vm.currentCondition == "calm" and resets == [1]
        assert model.redo()
        vm._cancel_all()
        assert vm.currentCondition == "calm" and resets == [1, 1]
        model.set_document(self._doc())  # another document: its first condition
        vm._cancel_all()
        assert vm.currentCondition == "gale" and len(resets) == 3
        vm.shutdown()

    def test_renaming_the_charted_condition_falls_back(self):
        from crane_statics.qml_app.viewmodels.model_vm import ModelViewModel
        from tests.rules_docs import gale, rules_doc, without_suspended_rope

        session = SessionState()
        chart = ChartViewModel(session)
        chart.setOutreachStep(20.0)
        model = ModelViewModel(session)
        session.model.set_document(
            without_suspended_rope(rules_doc("ABS", gale("a", wind=30.0), gale("b", wind=5.0)))
        )
        assert chart.currentCondition == "a"
        model.renameCondition("z")
        chart._cancel_all()
        assert model.conditionNames == ["z", "b"]
        assert chart.currentCondition in model.conditionNames
        chart.shutdown()
