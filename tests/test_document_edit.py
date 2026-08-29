"""Document editing: the headless editor and the QML model view model that drives it."""

from pathlib import Path

import pytest
from PyQt6.QtCore import Qt

from crane_statics.core.document_edit import (
    DocumentEditError,
    DocumentEditor,
    build_contractual_point,
    build_mass_point,
    build_node,
    build_payload_hoist,
    build_segment,
    build_wind_area,
)
from crane_statics.core.io import load_document
from crane_statics.core.session_model import SessionModel
from crane_statics.qml_app.session import SessionState
from crane_statics.qml_app.viewmodels.model_vm import ModelViewModel

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"


@pytest.fixture
def document():
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    return load_document(EXAMPLE)


@pytest.fixture
def editor(document):
    return DocumentEditor(document)


@pytest.fixture
def model_vm(document):
    session = SessionState()
    vm = ModelViewModel(session)
    session.model.set_document(document)
    return vm


class TestSelectionOwnership:
    def test_editor_selection_does_not_change_payload_selection(self, document):
        session = SessionModel()
        session.set_document(document)
        solve_hoist = next(h for h in document.hoists if h.rope_id == "BH__rope")
        payload_id = session.selected_hoist_id

        session.select_editor_hoist(solve_hoist.id)

        assert session.selected_editor_hoist_id == solve_hoist.id
        assert session.selected_hoist_id == payload_id


class TestNodeEditing:
    def test_add_and_delete_node(self, editor, document):
        before = len(document.nodes)
        editor.add_node(build_node("platform", "qa_node", x_m=1.0, z_m=2.0))

        assert len(document.nodes) == before + 1
        editor.delete_node("qa_node")
        assert len(document.nodes) == before

    def test_duplicate_node_id_is_rejected(self, editor, document):
        existing = document.nodes[0].id
        with pytest.raises(DocumentEditError, match="already exists"):
            editor.add_node(build_node("platform", existing, x_m=0.0, z_m=0.0))

    def test_reserved_node_id_is_rejected(self, editor):
        with pytest.raises(DocumentEditError, match="reserved"):
            editor.add_node(build_node("platform", "boom_heel", x_m=0.0, z_m=0.0))

    def test_boom_node_uses_local_coordinates(self, editor, document):
        editor.add_node(build_node("boom", "qa_boom_node", local_x_m=4.0, local_z_m=5.0))
        node = next(n for n in document.nodes if n.id == "qa_boom_node")

        assert node.local_x_m == 4.0
        assert node.local_z_m == 5.0
        assert node.x_m == 0.0

    def test_rename_node_keeps_position_in_document(self, editor, document):
        editor.add_node(build_node("platform", "qa_before", x_m=3.0, z_m=4.0))
        editor.update_node("qa_before", build_node("platform", "qa_after", x_m=7.0, z_m=8.0))

        assert not any(n.id == "qa_before" for n in document.nodes)
        renamed = next(n for n in document.nodes if n.id == "qa_after")
        assert renamed.x_m == 7.0

    def test_empty_node_id_is_rejected(self):
        with pytest.raises(DocumentEditError, match="cannot be empty"):
            build_node("platform", "   ")

    def test_hanging_node_requires_reference(self):
        with pytest.raises(DocumentEditError, match="Hang From"):
            build_node("platform", "qa", hanging=True, below_node_id="")

    def test_visible_nodes_exclude_reserved_and_managed(self, editor):
        ids = {n.id for n in editor.visible_nodes_for_body("boom")}

        assert "boom_heel" not in ids
        assert not any("__hook__" in nid for nid in ids)


class TestBodyCollectionEditing:
    def test_mass_point_round_trip(self, editor, document):
        body = next(b for b in document.bodies if b.id == "platform")
        before = len(body.mass_points)

        editor.add_mass_point(
            "platform", build_mass_point("platform", "qa_mp", 5.0, x_m=1.0, z_m=2.0)
        )
        assert len(body.mass_points) == before + 1

        editor.update_mass_point("platform", before, build_mass_point("platform", "qa_mp", 9.0))
        assert body.mass_points[before].mass_t == 9.0

        editor.delete_mass_point("platform", before)
        assert len(body.mass_points) == before

    def test_wind_area_round_trip(self, editor, document):
        body = next(b for b in document.bodies if b.id == "platform")
        before = len(body.wind_areas)

        editor.add_wind_area("platform", build_wind_area("platform", "qa_wa", 2.0, 3.0, cd=1.2))
        assert len(body.wind_areas) == before + 1

        editor.delete_wind_area("platform", before)
        assert len(body.wind_areas) == before

    def test_out_of_range_index_is_rejected(self, editor):
        with pytest.raises(DocumentEditError, match="mass point"):
            editor.delete_mass_point("platform", 999)


class TestHoistEditing:
    def test_add_hoist_creates_rope_and_managed_hook(self, editor, document):
        support = editor.visible_nodes_for_body("boom")[0].id
        editor.add_hoist(build_payload_hoist("QA", support, falls=2, hook_mass_t=3.0))

        hoist = next(h for h in document.hoists if h.id == "QA")
        assert any(r.id == hoist.rope_id for r in document.ropes)
        assert any(n.id == hoist.load_node_id for n in document.nodes)
        assert hoist.support_node_id == support

    def test_duplicate_hoist_is_rejected(self, editor, document):
        support = editor.visible_nodes_for_body("boom")[0].id
        existing = document.hoists[0].id
        with pytest.raises(DocumentEditError, match="already exists"):
            editor.add_hoist(build_payload_hoist(existing, support))

    def test_split_falls_must_not_exceed_normal_falls(self):
        with pytest.raises(DocumentEditError, match="Split falls"):
            build_payload_hoist(
                "QA", "n1", falls=2, splitable_block=True, split_falls=4, split_hook_mass_t=1.0
            )

    def test_split_hook_mass_must_not_exceed_normal(self):
        with pytest.raises(DocumentEditError, match="Split hook mass"):
            build_payload_hoist(
                "QA",
                "n1",
                falls=4,
                hook_mass_t=2.0,
                splitable_block=True,
                split_falls=2,
                split_hook_mass_t=9.0,
            )

    def test_delete_hoist_removes_rope_and_managed_hook(self, editor, document):
        support = editor.visible_nodes_for_body("boom")[0].id
        editor.add_hoist(build_payload_hoist("QA", support))
        hoist = next(h for h in document.hoists if h.id == "QA")
        rope_id, hook_id = hoist.rope_id, hoist.load_node_id

        editor.delete_hoist("QA")

        assert not any(h.id == "QA" for h in document.hoists)
        assert not any(r.id == rope_id for r in document.ropes)
        assert not any(n.id == hook_id for n in document.nodes)

    def test_update_hoist_preserves_contractual_points(self, editor, document):
        payload = next(h for h in document.hoists if not editor.is_solve_hoist(h))
        original = [(cp.outreach_m, cp.load_t) for cp in payload.contractual_points]
        assert original

        editor.update_hoist(
            payload.id,
            build_payload_hoist(
                payload.id, editor.resolved_support_node_id(payload), hook_mass_t=42.0
            ),
        )

        updated = next(h for h in document.hoists if h.id == payload.id)
        assert updated.hook_mass_t == 42.0
        assert [(cp.outreach_m, cp.load_t) for cp in updated.contractual_points] == original

    def test_solve_hoist_cannot_be_deleted(self, editor, document):
        solve = next((h for h in document.hoists if editor.is_solve_hoist(h)), None)
        if solve is None:
            pytest.skip("No solve hoist in example")
        with pytest.raises(DocumentEditError, match="Boom hoist"):
            editor.delete_hoist(solve.id)


class TestRopeAndContractualEditing:
    def test_visible_segments_exclude_managed_hook_segment(self, editor, document):
        payload = next(h for h in document.hoists if not editor.is_solve_hoist(h))
        managed = str(payload.load_node_id)
        visible = editor.visible_rope_segments(payload)

        assert all(managed not in (seg.from_node_id, seg.to_node_id) for _idx, seg in visible)

    def test_segment_round_trip_uses_visible_indices(self, editor, document):
        payload = next(h for h in document.hoists if not editor.is_solve_hoist(h))
        before = len(editor.visible_rope_segments(payload))
        nodes = editor.editable_node_ids()

        editor.add_rope_segment(payload.id, build_segment(nodes[0], nodes[1], mult=2))
        assert len(editor.visible_rope_segments(payload)) == before + 1

        editor.delete_rope_segment(payload.id, before)
        assert len(editor.visible_rope_segments(payload)) == before

    def test_segment_endpoints_must_differ(self):
        with pytest.raises(DocumentEditError, match="must differ"):
            build_segment("a", "a")

    def test_contractual_point_round_trip(self, editor, document):
        payload = next(h for h in document.hoists if not editor.is_solve_hoist(h))
        before = len(payload.contractual_points)

        editor.add_contractual_point(payload.id, build_contractual_point(30.0, 100.0))
        assert len(payload.contractual_points) == before + 1

        editor.delete_contractual_point(payload.id, before)
        assert len(payload.contractual_points) == before


class TestModelViewModelEditing:
    def test_add_node_through_view_model_marks_session_dirty(self, model_vm):
        model_vm.selectBody("platform")
        before = model_vm.nodesModel.count
        edited: list[int] = []
        model_vm.modelEdited.connect(lambda: edited.append(1))

        model_vm.addNode({"id": "qa_vm_node", "x_m": 1.0, "z_m": 2.0})

        assert model_vm.nodesModel.count == before + 1
        assert edited
        assert model_vm._model.dirty is True

    def test_invalid_edit_emits_edit_failed_and_changes_nothing(self, model_vm):
        model_vm.selectBody("platform")
        before = model_vm.nodesModel.count
        failures: list[str] = []
        model_vm.editFailed.connect(failures.append)

        model_vm.addNode({"id": "  "})

        assert failures
        assert model_vm.nodesModel.count == before

    def test_delete_node_through_view_model(self, model_vm):
        model_vm.selectBody("platform")
        model_vm.addNode({"id": "qa_vm_delete", "x_m": 0.0, "z_m": 0.0})
        row = next(
            i
            for i in range(model_vm.nodesModel.count)
            if model_vm.nodesModel.record_at(i).id == "qa_vm_delete"
        )

        model_vm.deleteNode(row)

        assert all(
            model_vm.nodesModel.record_at(i).id != "qa_vm_delete"
            for i in range(model_vm.nodesModel.count)
        )

    def test_node_fields_round_trip_through_dialog_payload(self, model_vm):
        model_vm.selectBody("boom")
        model_vm.addNode({"id": "qa_boom_vm", "local_x_m": 2.5, "local_z_m": -1.5})
        row = next(
            i
            for i in range(model_vm.nodesModel.count)
            if model_vm.nodesModel.record_at(i).id == "qa_boom_vm"
        )

        fields = model_vm.nodeFields(row)

        assert fields["local_x_m"] == 2.5
        assert fields["local_z_m"] == -1.5
        assert fields["hanging"] is False

    def test_hoist_fields_expose_editable_values(self, model_vm):
        fields = model_vm.hoistFields(0)

        assert fields["id"] == model_vm.hoistsModel.record_at(0).id
        assert "hook_mass_t" in fields
        assert fields["linear_mass_kg_m"] == pytest.approx(
            model_vm.hoistsModel.record_at(0).linear_mass_kg_m
        )
        assert fields["rope_length_m"] == pytest.approx(
            model_vm.hoistsModel.record_at(0).rope_length_m
        )
        assert "support_node_id" in fields

    def test_boom_hoist_fields_and_table_hide_payload_values(self, model_vm):
        boom_row = next(
            row
            for row in range(model_vm.hoistsModel.count)
            if model_vm.hoistsModel.record_at(row).id == "BH"
        )
        boom_fields = model_vm.hoistFields(boom_row)

        assert boom_fields["is_boom_hoist"] is True
        assert boom_fields["linear_mass_kg_m"] == pytest.approx(
            model_vm.hoistsModel.record_at(boom_row).linear_mass_kg_m
        )

        headers = [
            model_vm.hoistsModel.headerData(
                column, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole
            )
            for column in range(model_vm.hoistsModel.columnCount())
        ]
        for payload_header in (
            "Support Node",
            "Falls",
            "Hook Mass (t)",
            "Splittable",
            "Split Falls",
            "Split Hook Mass (t)",
            "DAF",
            "Off Lead (deg)",
            "Side Lead (deg)",
            "Min Hook Travel (m)",
            "Max Hook Travel (m)",
        ):
            column = headers.index(payload_header)
            assert (
                model_vm.hoistsModel.data(
                    model_vm.hoistsModel.index(boom_row, column),
                    Qt.ItemDataRole.DisplayRole,
                )
                == ""
            )

        linear_mass_column = headers.index("Linear Mass (kg/m)")
        assert (
            model_vm.hoistsModel.data(
                model_vm.hoistsModel.index(boom_row, linear_mass_column),
                Qt.ItemDataRole.DisplayRole,
            )
            == f"{float(boom_fields['linear_mass_kg_m']):.3f}"
        )


class TestEnvironmentEditing:
    def test_environment_map_covers_all_editable_groups(self, model_vm, document):
        env = model_vm.environment

        assert env["gravity_m_s2"] == pytest.approx(document.environment.gravity_m_s2)
        assert env["accel_x_m_s2"] == pytest.approx(document.environment.vessel_motion.accel_x_m_s2)
        assert env["slewing_bearing_diameter_m"] == pytest.approx(
            document.support_widths.slewing_bearing_diameter_m
        )

    def test_setting_environment_value_writes_through(self, model_vm, document):
        model_vm.setEnvironmentValue("max_wind_speed_m_s", 33.0)

        assert document.environment.max_wind_speed_m_s == pytest.approx(33.0)
        assert model_vm._model.dirty is True

    def test_setting_vessel_motion_value_writes_through(self, model_vm, document):
        model_vm.setEnvironmentValue("pitch_angular_accel_rad_s2", 0.125)

        assert document.environment.vessel_motion.pitch_angular_accel_rad_s2 == pytest.approx(0.125)

    def test_setting_support_width_writes_through(self, model_vm, document):
        model_vm.setEnvironmentValue("boom_width_m", 4.5)

        assert document.support_widths.boom_width_m == pytest.approx(4.5)

    def test_unknown_environment_key_is_ignored(self, model_vm):
        model_vm.setEnvironmentValue("not_a_field", 1.0)

        assert "not_a_field" not in model_vm.environment

    def test_primary_structure_model_lists_the_bound_points(self, model_vm):
        labels = [
            model_vm.primaryStructureModel.row_at(i)["label"]
            for i in range(model_vm.primaryStructureModel.count)
        ]

        assert "Heel Point" in labels
        assert model_vm.primaryStructureModel.count > 0

    def test_moving_a_primary_structure_point_updates_the_node(self, model_vm, document):
        row = model_vm.primaryStructureModel.row_at(0)

        model_vm.setPrimaryStructurePoint(row["nodeId"], 12.0, -3.0)

        node = next(n for n in document.nodes if n.id == row["nodeId"])
        assert node.x_m == pytest.approx(12.0)
        assert node.z_m == pytest.approx(-3.0)
        assert model_vm.primaryStructureModel.row_at(0)["posX"] == pytest.approx(12.0)

    def test_unknown_primary_node_reports_an_error(self, model_vm):
        failures: list[str] = []
        model_vm.editFailed.connect(failures.append)

        model_vm.setPrimaryStructurePoint("nope", 0.0, 0.0)

        assert failures


class TestContractualModeEditing:
    def _splitable_hoist(self, model_vm):
        doc = model_vm._model.document
        return next((h.id for h in doc.hoists if getattr(h, "splitable_block", False)), None)

    def test_mode_defaults_to_normal(self, model_vm):
        assert model_vm.contractualMode == "normal"

    def test_split_mode_is_rejected_for_non_splitable_hoists(self, model_vm):
        doc = model_vm._model.document
        plain = next((h.id for h in doc.hoists if not getattr(h, "splitable_block", False)), None)
        if plain is None:
            pytest.skip("No non-splitable hoist in example")
        model_vm.selectHoist(plain)

        model_vm.setContractualMode("split")

        assert model_vm.contractualMode == "normal"

    def test_split_mode_shows_the_split_dataset(self, model_vm):
        hoist_id = self._splitable_hoist(model_vm)
        if hoist_id is None:
            pytest.skip("No splitable hoist in example")
        model_vm.selectHoist(hoist_id)
        hoist = next(h for h in model_vm._model.document.hoists if h.id == hoist_id)

        model_vm.setContractualMode("split")

        assert model_vm.contractualMode == "split"
        assert model_vm.contractualModel.count == len(hoist.split_contractual_points)

    def test_edits_in_split_mode_target_the_split_dataset(self, model_vm):
        hoist_id = self._splitable_hoist(model_vm)
        if hoist_id is None:
            pytest.skip("No splitable hoist in example")
        model_vm.selectHoist(hoist_id)
        model_vm.setContractualMode("split")
        hoist = next(h for h in model_vm._model.document.hoists if h.id == hoist_id)
        normal_before = len(hoist.contractual_points)
        split_before = len(hoist.split_contractual_points)

        model_vm.addContractualPoint({"outreach_m": 40.0, "load_t": 60.0})

        assert len(hoist.split_contractual_points) == split_before + 1
        assert len(hoist.contractual_points) == normal_before

    def test_switching_hoist_resets_mode_when_not_splitable(self, model_vm):
        hoist_id = self._splitable_hoist(model_vm)
        doc = model_vm._model.document
        plain = next((h.id for h in doc.hoists if not getattr(h, "splitable_block", False)), None)
        if hoist_id is None or plain is None:
            pytest.skip("Example lacks both hoist kinds")
        model_vm.selectHoist(hoist_id)
        model_vm.setContractualMode("split")

        model_vm.selectHoist(plain)

        assert model_vm.contractualMode == "normal"
