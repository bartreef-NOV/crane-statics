"""Model workspace view model: component and hoist editing tables."""

from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from crane_statics.qml_app.qt_compat import pyqtProperty

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
from crane_statics.core.model_health import health_status
from crane_statics.qml_app.session import SessionState
from crane_statics.data import payload_hoist_ids

from ..models.document_forms import (
    chart_point_rows,
    clear_support_width,
    condition_fields,
    entered_daf_value,
    condition_hoist_rows,
    condition_hoist_kwargs,
    contractual_fields,
    editable_conditions,
    environment_from_conditions,
    environment_settings,
    hoist_fields,
    mass_kwargs,
    mass_point_fields,
    new_condition,
    node_fields,
    node_kwargs,
    primary_structure_rows,
    rope_segment_fields,
    segment_kwargs,
    set_environment_value,
    wind_area_fields,
    wind_kwargs,
    with_condition_lift,
    with_condition_name,
    with_condition_value,
    hoist_kwargs,
)
from ..models.list_models import DictListModel
from ..models.document_models import (
    contractual_columns,
    hoist_columns,
    mass_point_columns,
    node_columns,
    rope_segment_columns,
    wind_area_columns,
)
from ..models.table_models import RecordTableModel

COMPONENT_LABELS = {
    "boom": "Boom",
    "rear_leg": "Rear Leg",
    "front_leg": "Front Leg",
    "platform": "Platform",
}
COMPONENT_ORDER = ["boom", "rear_leg", "front_leg", "platform"]

PRIMARY_ROLES = ["nodeId", "label", "posX", "posZ"]


class ModelViewModel(QObject):
    """Exposes document components and hoists as selectable, tabulated data."""

    componentsChanged = pyqtSignal()
    selectedBodyChanged = pyqtSignal()
    hoistsChanged = pyqtSignal()
    selectedHoistChanged = pyqtSignal()
    modelEdited = pyqtSignal()
    editFailed = pyqtSignal(str)
    environmentChanged = pyqtSignal()
    healthChanged = pyqtSignal()
    conditionsChanged = pyqtSignal()

    def __init__(self, session: SessionState, parent=None):
        super().__init__(parent)
        self._session = session
        self._model = session.model
        self._selected_body_id: str = COMPONENT_ORDER[0]
        self._contractual_mode: str = "normal"
        self._selected_condition: Optional[str] = None
        # The condition whose hoist settings and charts the hoist tables show (the Scene's
        # at the last refresh): edits from those tables go to it.
        self._shown_condition: Optional[str] = None

        self._nodes_model = RecordTableModel(
            node_columns(self._selected_body_id), self, commit=self._commit_node_cell
        )
        self._mass_points_model = RecordTableModel(
            mass_point_columns(self._selected_body_id), self, commit=self._commit_mass_point_cell
        )
        self._wind_areas_model = RecordTableModel(
            wind_area_columns(self._selected_body_id), self, commit=self._commit_wind_area_cell
        )
        self._hoists_model = RecordTableModel(
            hoist_columns(self._is_boom_hoist, self._shown_settings),
            self,
            commit=self._commit_hoist_cell,
        )
        self._rope_segments_model = RecordTableModel(
            rope_segment_columns(), self, commit=self._commit_rope_segment_cell
        )
        self._contractual_model = RecordTableModel(
            contractual_columns(), self, commit=self._commit_contractual_cell
        )
        self._primary_structure_model = DictListModel(PRIMARY_ROLES, self)

        self._session.document_changed.connect(self._on_document_changed)
        self._session.scene_condition_changed.connect(self._on_scene_condition_changed)

    def _on_scene_condition_changed(self) -> None:
        """The hoist tables show the Scene's condition: follow it."""
        self._refresh_hoist_records()
        self._refresh_hoist_tables()
        self.hoistsChanged.emit()
        self.selectedHoistChanged.emit()

    def _on_document_changed(self, _doc) -> None:
        if not self._model.restoring:
            # Another document: its first condition. Undo/redo keeps the selection.
            self._selected_condition = None
        self.refresh()

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    @pyqtProperty(list, notify=componentsChanged)
    def bodyIds(self) -> list:
        doc = self._model.document
        if doc is None:
            return list(COMPONENT_ORDER)
        present = {b.id for b in doc.bodies}
        return [bid for bid in COMPONENT_ORDER if bid in present]

    @pyqtProperty(list, notify=componentsChanged)
    def bodyLabels(self) -> list:
        return [COMPONENT_LABELS.get(bid, bid) for bid in self.bodyIds]

    @pyqtProperty(str, notify=selectedBodyChanged)
    def selectedBodyId(self) -> str:
        return self._selected_body_id

    @pyqtSlot(str)
    def selectBody(self, body_id: str) -> None:
        if body_id == self._selected_body_id:
            return
        self._selected_body_id = body_id
        # Column layout differs per body (global XZ vs boom-local UW).
        self._nodes_model = RecordTableModel(
            node_columns(body_id), self, commit=self._commit_node_cell
        )
        self._mass_points_model = RecordTableModel(
            mass_point_columns(body_id), self, commit=self._commit_mass_point_cell
        )
        self._wind_areas_model = RecordTableModel(
            wind_area_columns(body_id), self, commit=self._commit_wind_area_cell
        )
        self._refresh_component_tables()
        self.selectedBodyChanged.emit()

    @pyqtProperty(list, notify=hoistsChanged)
    def hoistIds(self) -> list:
        return self._model.editor_hoist_ids()

    @pyqtProperty(list, notify=hoistsChanged)
    def hoistList(self) -> list:
        """``{id, isBoom}`` per hoist, in the order the hoists model's rows use."""
        doc = self._model.document
        if doc is None:
            return []
        return [{"id": h.id, "isBoom": self._is_boom_hoist(h)} for h in doc.hoists]

    @pyqtProperty(list, notify=hoistsChanged)
    def payloadHoistIds(self) -> list:
        doc = self._model.document
        return [] if doc is None else list(payload_hoist_ids(doc))

    @pyqtProperty(str, notify=selectedHoistChanged)
    def selectedHoistId(self) -> str:
        return self._model.selected_editor_hoist_id or ""

    @pyqtSlot(str)
    def selectHoist(self, hoist_id: str) -> None:
        if hoist_id == self._model.selected_editor_hoist_id:
            return
        self._model.select_editor_hoist(hoist_id)
        if hoist_id != self._model.selected_editor_hoist_id:
            return
        if not self.hoistSplitable:
            self._contractual_mode = "normal"
        self._refresh_hoist_tables()
        self.selectedHoistChanged.emit()

    @pyqtProperty(bool, notify=selectedHoistChanged)
    def hoistSplitable(self) -> bool:
        return self._model.is_splitable_hoist(self._model.selected_editor_hoist_id)

    @pyqtProperty(str, notify=selectedHoistChanged)
    def contractualMode(self) -> str:
        return self._contractual_mode

    @pyqtSlot(str)
    def setContractualMode(self, mode: str) -> None:
        normalized = "split" if str(mode).lower() == "split" and self.hoistSplitable else "normal"
        if normalized == self._contractual_mode:
            return
        self._contractual_mode = normalized
        self._refresh_hoist_tables()
        self.selectedHoistChanged.emit()

    # ------------------------------------------------------------------
    # Models
    # ------------------------------------------------------------------

    @pyqtProperty(QObject, notify=selectedBodyChanged)
    def nodesModel(self) -> QObject:
        return self._nodes_model

    @pyqtProperty(QObject, notify=selectedBodyChanged)
    def massPointsModel(self) -> QObject:
        return self._mass_points_model

    @pyqtProperty(QObject, notify=selectedBodyChanged)
    def windAreasModel(self) -> QObject:
        return self._wind_areas_model

    @pyqtProperty(QObject, constant=True)
    def hoistsModel(self) -> QObject:
        return self._hoists_model

    @pyqtProperty(QObject, constant=True)
    def ropeSegmentsModel(self) -> QObject:
        return self._rope_segments_model

    @pyqtProperty(QObject, constant=True)
    def contractualModel(self) -> QObject:
        return self._contractual_model

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------

    @pyqtSlot()
    def refresh(self) -> None:
        available = self.bodyIds
        if available and self._selected_body_id not in available:
            self.selectBody(available[0])
        hoist_ids = self.hoistIds
        if hoist_ids and self._model.selected_editor_hoist_id not in hoist_ids:
            self._model.select_editor_hoist(hoist_ids[0])
        elif not hoist_ids:
            self._model.selected_editor_hoist_id = None

        self._refresh_hoist_records()
        self._refresh_component_tables()
        self._refresh_hoist_tables()
        self._refresh_primary_structure()
        self._follow_conditions()
        self.componentsChanged.emit()
        self.hoistsChanged.emit()
        self.selectedHoistChanged.emit()
        self.environmentChanged.emit()
        self.healthChanged.emit()
        self.conditionsChanged.emit()

    def _body(self):
        doc = self._model.document
        if doc is None:
            return None
        return next((b for b in doc.bodies if b.id == self._selected_body_id), None)

    def _hoist(self):
        return self._model.selected_editor_hoist()

    def _refresh_component_tables(self) -> None:
        editor = self._editor()
        body = self._body()
        nodes = [] if editor is None else editor.visible_nodes_for_body(self._selected_body_id)
        self._nodes_model.set_records(nodes)
        self._mass_points_model.set_records([] if body is None else body.mass_points)
        self._wind_areas_model.set_records([] if body is None else body.wind_areas)

    def _refresh_hoist_records(self) -> None:
        """Re-read the hoist rows under the Scene's current condition."""
        condition = self._model.scene_condition_or_none()
        self._shown_condition = None if condition is None else condition.condition_name
        doc = self._model.document
        self._hoists_model.set_records([] if doc is None else doc.hoists)

    def _refresh_hoist_tables(self) -> None:
        editor = self._editor()
        hoist = self._hoist()
        segments = (
            []
            if editor is None or hoist is None
            else [seg for _idx, seg in editor.visible_rope_segments(hoist)]
        )
        self._rope_segments_model.set_records(segments)
        # The hoist's chart under the Scene's condition (none when not usable there).
        settings = None if hoist is None else self._shown_settings(hoist)
        if settings is None:
            self._contractual_model.set_records([])
        elif self._contractual_mode == "split" and self.hoistSplitable:
            self._contractual_model.set_records(settings.split_contractual_points)
        else:
            self._contractual_model.set_records(settings.contractual_points)

    def _shown_settings(self, hoist: Any) -> Any:
        """``hoist``'s entry (``ConditionHoist``) in the condition the tables show, or None.

        The hoist DAF/lead columns and the contractual table show and edit the condition
        the Scene runs under (``_shown_condition``, followed on every change); Task 6
        gives the conditions their own hoist editor.
        """
        doc = self._model.document
        spec = None if doc is None else doc.conditions.get(self._shown_condition or "")
        return None if spec is None else spec.hoists.get(getattr(hoist, "id", ""))

    # ------------------------------------------------------------------
    # Model health
    # ------------------------------------------------------------------

    @pyqtProperty(str, notify=healthChanged)
    def healthSeverity(self) -> str:
        return health_status(self._model.document)[0]

    @pyqtProperty(str, notify=healthChanged)
    def healthVerdict(self) -> str:
        return health_status(self._model.document)[1]

    @pyqtProperty(str, notify=healthChanged)
    def healthChecks(self) -> str:
        return health_status(self._model.document)[2]

    # ------------------------------------------------------------------
    # Environment, support widths and primary structure
    # ------------------------------------------------------------------

    @pyqtProperty("QVariantMap", notify=environmentChanged)
    def environment(self) -> dict:
        return environment_settings(self._model.document)

    @pyqtProperty(bool, notify=environmentChanged)
    def environmentFromConditions(self) -> bool:
        """True on a rules document: wind and vessel motion are set per load condition."""
        return environment_from_conditions(self._model.document)

    @pyqtSlot(str, float)
    def setEnvironmentValue(self, key: str, value: float) -> None:
        doc = self._model.document
        if doc is not None and set_environment_value(doc, key, value):
            self._announce_environment_edit()

    @pyqtSlot(str)
    def clearEnvironmentValue(self, key: str) -> None:
        doc = self._model.document
        if doc is not None and clear_support_width(doc, key):
            self._announce_environment_edit()

    def _announce_environment_edit(self) -> None:
        self._model.mark_content_changed()
        self.environmentChanged.emit()
        self.healthChanged.emit()
        self.modelEdited.emit()

    # ------------------------------------------------------------------
    # Load conditions (rules documents)
    # ------------------------------------------------------------------

    @pyqtProperty(list, notify=conditionsChanged)
    def conditionNames(self) -> list:
        return list(editable_conditions(self._model.document))

    @pyqtProperty(str, notify=conditionsChanged)
    def selectedCondition(self) -> str:
        return self._selected_condition or ""

    @pyqtProperty("QVariantMap", notify=conditionsChanged)
    def condition(self) -> dict:
        spec = self._selected_spec()
        return {} if spec is None else condition_fields(spec)

    @pyqtSlot(str)
    def selectCondition(self, name: str) -> None:
        if name == self._selected_condition or name not in self.conditionNames:
            return
        self._selected_condition = name
        self.conditionsChanged.emit()

    @pyqtSlot(str, float)
    def setConditionValue(self, key: str, value: float) -> None:
        self._edit_selected_condition(lambda spec: with_condition_value(spec, key, value))

    @pyqtSlot(str)
    def clearConditionValue(self, key: str) -> None:
        self._edit_selected_condition(lambda spec: with_condition_value(spec, key, None))

    @pyqtSlot(str)
    def setConditionLift(self, lift: str) -> None:
        self._edit_selected_condition(lambda spec: with_condition_lift(spec, lift))

    @pyqtSlot(str)
    def renameCondition(self, new_name: str) -> None:
        spec = self._selected_spec()
        if spec is not None and new_name == spec.name:
            return
        self._edit_selected_condition(
            lambda spec: with_condition_name(spec, new_name), select=new_name
        )

    @pyqtSlot()
    def addCondition(self) -> None:
        selected = self._selected_spec()
        wind = 0.0 if selected is None else selected.wind_speed_m_s
        added = new_condition(self.conditionNames, wind)

        def mutate(editor: DocumentEditor) -> None:
            editor.add_condition(added)
            self._selected_condition = added.name

        self._apply_edit(mutate)

    @pyqtSlot()
    def duplicateCondition(self) -> None:
        name = self._selected_condition
        if name is None:
            self.editFailed.emit("Select a condition first")
            return

        def mutate(editor: DocumentEditor) -> None:
            self._selected_condition = editor.duplicate_condition(name)

        self._apply_edit(mutate)

    @pyqtSlot()
    def deleteCondition(self) -> None:
        name = self._selected_condition
        if name is None:
            self.editFailed.emit("Select a condition first")
            return
        self._apply_edit(lambda editor: editor.delete_condition(name))

    # -- the selected condition's hoists -------------------------------

    @pyqtProperty(list, notify=conditionsChanged)
    def conditionHoists(self) -> list:
        """One row per payload hoist for the selected condition (``condition_hoist_rows``)."""
        return condition_hoist_rows(self._model.document, self._selected_spec())

    @pyqtSlot(str, float, float, "QVariant")
    def setConditionHoist(
        self, hoist_id: str, offlead_deg: float, sidelead_deg: float, daf: Any
    ) -> None:
        """Make ``hoist_id`` usable in the selected condition with these lead limits and
        DAF (None/empty: no override, derived under rules)."""
        name = self._selected_condition
        if name is None:
            self.editFailed.emit("Select a condition first")
            return
        self._apply_edit(
            lambda editor: editor.enter_condition_hoist(
                name,
                hoist_id,
                float(offlead_deg),
                float(sidelead_deg),
                entered_daf_value(daf),
            )
        )

    @pyqtSlot(str, bool)
    def setConditionHoistUsable(self, hoist_id: str, usable: bool) -> None:
        """The table's "usable" checkbox (``DocumentEditor.set_condition_hoist_usable``)."""
        name = self._selected_condition
        if name is None:
            self.editFailed.emit("Select a condition first")
            return
        spec = self._selected_spec()
        if spec is not None and (hoist_id in spec.hoists) == bool(usable):
            return  # already so: no edit, no undo step
        self._apply_edit(
            lambda editor: editor.set_condition_hoist_usable(name, hoist_id, bool(usable))
        )

    @pyqtSlot(str)
    def removeConditionHoist(self, hoist_id: str) -> None:
        name = self._selected_condition
        if name is None:
            self.editFailed.emit("Select a condition first")
            return
        self._apply_edit(lambda editor: editor.remove_condition_hoist(name, hoist_id))

    # -- the selected hoist's load chart, with each point's conditions --

    @pyqtProperty(list, notify=selectedHoistChanged)
    def chartPoints(self) -> list:
        """The selected hoist's chart in the current mode as saved: each point once with
        the conditions it names (``chart_point_rows``); [] for the boom hoist."""
        editor = self._editor()
        hoist = self._hoist()
        if editor is None or hoist is None or self._is_boom_hoist(hoist):
            return []
        split = self._contractual_mode == "split" and self.hoistSplitable
        return chart_point_rows(editor.tagged_chart(hoist.id, split))

    @pyqtSlot(int, list)
    def setPointConditions(self, index: int, conditions: list) -> None:
        """Make chart point ``index`` (of ``chartPoints``) name exactly ``conditions``."""
        hoist_id = self._model.selected_editor_hoist_id
        if hoist_id is None:
            self.editFailed.emit("Select a hoist first")
            return
        split = self._contractual_mode == "split" and self.hoistSplitable
        names = [str(name) for name in conditions]
        self._apply_edit(
            lambda editor: editor.set_point_conditions(hoist_id, split, int(index), names)
        )

    def _selected_spec(self):
        return editable_conditions(self._model.document).get(self._selected_condition or "")

    def _edit_selected_condition(self, edit, select: Optional[str] = None) -> None:
        """Replace the selected condition by ``edit(spec)``; on success select ``select``."""
        spec = self._selected_spec()
        if spec is None:
            self.editFailed.emit("Select a condition first")
            return

        def mutate(editor: DocumentEditor) -> None:
            editor.update_condition(spec.name, edit(spec))
            if select is not None:
                self._selected_condition = select

        self._apply_edit(mutate)

    def _follow_conditions(self) -> None:
        """A selection that no longer exists becomes the first condition (or none)."""
        names = self.conditionNames
        if self._selected_condition not in names:
            self._selected_condition = names[0] if names else None

    @pyqtProperty(QObject, constant=True)
    def primaryStructureModel(self) -> QObject:
        return self._primary_structure_model

    @pyqtSlot(str, float, float)
    def setPrimaryStructurePoint(self, node_id: str, x_m: float, z_m: float) -> None:
        doc = self._model.document
        if doc is None:
            return
        node = next((n for n in doc.nodes if n.id == node_id), None)
        if node is None:
            self.editFailed.emit(f"Primary structure node '{node_id}' not found")
            return
        node.x_m = float(x_m)
        node.z_m = float(z_m)
        DocumentEditor(doc).refresh_derived_geometry()
        self._model.mark_content_changed()
        self._refresh_primary_structure()
        self.refresh()
        self.modelEdited.emit()

    def _refresh_primary_structure(self) -> None:
        self._primary_structure_model.set_rows(primary_structure_rows(self._model.document))

    # ------------------------------------------------------------------
    # Editing
    # ------------------------------------------------------------------

    def _editor(self) -> Optional[DocumentEditor]:
        doc = self._model.document
        return None if doc is None else DocumentEditor(doc)

    @pyqtProperty(list, notify=componentsChanged)
    def editableNodeIds(self) -> list:
        editor = self._editor()
        return [] if editor is None else editor.editable_node_ids()

    def _apply_edit(self, mutate) -> bool:
        editor = self._editor()
        if editor is None:
            self.editFailed.emit("No document loaded")
            return False
        try:
            mutate(editor)
            editor.refresh_derived_geometry()
        except (DocumentEditError, ValueError) as exc:
            self.editFailed.emit(str(exc))
            return False
        self._model.mark_content_changed()
        self.refresh()
        self.modelEdited.emit()
        return True

    # -- in-cell editing -----------------------------------------------
    #
    # A cell edit is a row edit with one field replaced, so it re-submits the whole
    # record through the same builders and the same validation the Add dialogs use.
    # There is no second, looser way into the document.

    @staticmethod
    def _commit_cell(fields: dict[str, Any], field: str, value: Any, submit) -> bool:
        if not fields:
            return False
        fields[str(field)] = value
        return bool(submit(fields))

    def _commit_node_cell(self, row: int, field: str, value: Any) -> bool:
        return self._commit_cell(
            self.nodeFields(row), field, value, lambda fields: self.updateNode(row, fields)
        )

    def _commit_mass_point_cell(self, row: int, field: str, value: Any) -> bool:
        return self._commit_cell(
            self.massPointFields(row),
            field,
            value,
            lambda fields: self.updateMassPoint(row, fields),
        )

    def _commit_wind_area_cell(self, row: int, field: str, value: Any) -> bool:
        return self._commit_cell(
            self.windAreaFields(row), field, value, lambda fields: self.updateWindArea(row, fields)
        )

    def _commit_hoist_cell(self, row: int, field: str, value: Any) -> bool:
        return self._commit_cell(
            self.hoistFields(row), field, value, lambda fields: self.updateHoist(row, fields)
        )

    def _commit_rope_segment_cell(self, row: int, field: str, value: Any) -> bool:
        return self._commit_cell(
            self.ropeSegmentFields(row),
            field,
            value,
            lambda fields: self.updateRopeSegment(row, fields),
        )

    def _commit_contractual_cell(self, row: int, field: str, value: Any) -> bool:
        return self._commit_cell(
            self.contractualFields(row),
            field,
            value,
            lambda fields: self.updateContractualPoint(row, fields),
        )

    # -- nodes ---------------------------------------------------------

    @pyqtSlot(int, result="QVariantMap")
    def nodeFields(self, row: int) -> dict[str, Any]:
        node = self._nodes_model.record_at(row)
        if node is None:
            return {}
        return node_fields(node)

    @pyqtSlot("QVariantMap")
    def addNode(self, fields: dict) -> None:
        body_id = self._selected_body_id
        self._apply_edit(lambda editor: editor.add_node(build_node(body_id, **node_kwargs(fields))))

    @pyqtSlot(int, "QVariantMap", result="bool")
    def updateNode(self, row: int, fields: dict) -> bool:
        current = self._nodes_model.record_at(row)
        if current is None:
            self.editFailed.emit("Select a node first")
            return False
        body_id = self._selected_body_id
        return self._apply_edit(
            lambda editor: editor.update_node(
                current.id, build_node(body_id, **node_kwargs(fields))
            )
        )

    @pyqtSlot(int)
    def deleteNode(self, row: int) -> None:
        current = self._nodes_model.record_at(row)
        if current is None:
            self.editFailed.emit("Select a node first")
            return
        self._apply_edit(lambda editor: editor.delete_node(current.id))

    # -- mass points ---------------------------------------------------

    @pyqtSlot(int, result="QVariantMap")
    def massPointFields(self, row: int) -> dict[str, Any]:
        point = self._mass_points_model.record_at(row)
        if point is None:
            return {}
        return mass_point_fields(point)

    @pyqtSlot("QVariantMap")
    def addMassPoint(self, fields: dict) -> None:
        body_id = self._selected_body_id
        self._apply_edit(
            lambda editor: editor.add_mass_point(
                body_id, build_mass_point(body_id, **mass_kwargs(fields))
            )
        )

    @pyqtSlot(int, "QVariantMap", result="bool")
    def updateMassPoint(self, row: int, fields: dict) -> bool:
        body_id = self._selected_body_id
        return self._apply_edit(
            lambda editor: editor.update_mass_point(
                body_id, row, build_mass_point(body_id, **mass_kwargs(fields))
            )
        )

    @pyqtSlot(int)
    def deleteMassPoint(self, row: int) -> None:
        body_id = self._selected_body_id
        self._apply_edit(lambda editor: editor.delete_mass_point(body_id, row))

    # -- wind areas ----------------------------------------------------

    @pyqtSlot(int, result="QVariantMap")
    def windAreaFields(self, row: int) -> dict[str, Any]:
        area = self._wind_areas_model.record_at(row)
        if area is None:
            return {}
        return wind_area_fields(area)

    @pyqtSlot("QVariantMap")
    def addWindArea(self, fields: dict) -> None:
        body_id = self._selected_body_id
        self._apply_edit(
            lambda editor: editor.add_wind_area(
                body_id, build_wind_area(body_id, **wind_kwargs(fields))
            )
        )

    @pyqtSlot(int, "QVariantMap", result="bool")
    def updateWindArea(self, row: int, fields: dict) -> bool:
        body_id = self._selected_body_id
        return self._apply_edit(
            lambda editor: editor.update_wind_area(
                body_id, row, build_wind_area(body_id, **wind_kwargs(fields))
            )
        )

    @pyqtSlot(int)
    def deleteWindArea(self, row: int) -> None:
        body_id = self._selected_body_id
        self._apply_edit(lambda editor: editor.delete_wind_area(body_id, row))

    # -- hoists --------------------------------------------------------

    @pyqtSlot(int, result="QVariantMap")
    def hoistFields(self, row: int) -> dict[str, Any]:
        hoist = self._hoists_model.record_at(row)
        if hoist is None:
            return {}
        return hoist_fields(
            hoist, is_boom_hoist=self._is_boom_hoist(hoist), settings=self._shown_settings(hoist)
        )

    def _is_boom_hoist(self, hoist: Any) -> bool:
        doc = self._model.document
        if doc is None:
            return False
        rope = next((rope for rope in doc.ropes if rope.id == hoist.rope_id), None)
        return bool(rope is not None and rope.tension_mode == "solve")

    @pyqtSlot("QVariantMap")
    def addHoist(self, fields: dict) -> None:
        # Usable under the condition shown, with the form's DAF and leads (none without
        # a condition).
        condition_name = self._shown_condition
        values = condition_hoist_kwargs(fields)

        def mutate(editor: DocumentEditor) -> None:
            settings = (
                None
                if condition_name is None or values is None
                else editor.hoist_form_settings(None, condition_name, **values)
            )
            editor.add_hoist(
                build_payload_hoist(**hoist_kwargs(fields)),
                settings=settings,
                condition_name=condition_name,
            )

        self._apply_edit(mutate)

    @pyqtSlot(int, "QVariantMap", result="bool")
    def updateHoist(self, row: int, fields: dict) -> bool:
        current = self._hoists_model.record_at(row)
        if current is None:
            self.editFailed.emit("Select a hoist first")
            return False
        if self._is_boom_hoist(current):
            rope_length_m = fields.get("rope_length_m")
            return self._apply_edit(
                lambda editor: editor.update_boom_hoist(
                    current.id,
                    linear_mass_kg_m=float(fields.get("linear_mass_kg_m", 0.0)),
                    rope_length_m=(
                        None
                        if rope_length_m is None or rope_length_m == ""
                        else float(rope_length_m)
                    ),
                )
            )
        # The form carries DAF and leads only for a hoist the condition shown lists; an
        # unchanged DAF number keeps the stored DAF (``hoist_form_settings``).
        values = condition_hoist_kwargs(fields)
        condition_name = self._shown_condition
        shown = self._shown_settings(current) is not None

        def mutate(editor: DocumentEditor) -> None:
            settings = (
                editor.hoist_form_settings(current.id, condition_name, **values)
                if values is not None and shown
                else None
            )
            editor.update_hoist(
                current.id,
                build_payload_hoist(**hoist_kwargs(fields)),
                settings=settings,
                condition_name=condition_name,
            )

        return self._apply_edit(mutate)

    @pyqtSlot(int, str, "QVariant", result="bool")
    def setHoistField(self, row: int, field: str, value: Any) -> bool:
        """Replace one field of the hoist in ``row``; the hoist form commits through this."""
        return self._commit_hoist_cell(row, field, value)

    @pyqtSlot(int)
    def deleteHoist(self, row: int) -> None:
        current = self._hoists_model.record_at(row)
        if current is None:
            self.editFailed.emit("Select a hoist first")
            return
        self._apply_edit(lambda editor: editor.delete_hoist(current.id))

    # -- rope segments -------------------------------------------------

    @pyqtSlot(int, result="QVariantMap")
    def ropeSegmentFields(self, row: int) -> dict[str, Any]:
        segment = self._rope_segments_model.record_at(row)
        if segment is None:
            return {}
        return rope_segment_fields(segment)

    @pyqtSlot("QVariantMap")
    def addRopeSegment(self, fields: dict) -> None:
        hoist_id = self._model.selected_editor_hoist_id
        self._apply_edit(
            lambda editor: editor.add_rope_segment(
                hoist_id, build_segment(**segment_kwargs(fields))
            )
        )

    @pyqtSlot(int, "QVariantMap", result="bool")
    def updateRopeSegment(self, row: int, fields: dict) -> bool:
        hoist_id = self._model.selected_editor_hoist_id
        return self._apply_edit(
            lambda editor: editor.update_rope_segment(
                hoist_id, row, build_segment(**segment_kwargs(fields))
            )
        )

    @pyqtSlot(int)
    def deleteRopeSegment(self, row: int) -> None:
        hoist_id = self._model.selected_editor_hoist_id
        self._apply_edit(lambda editor: editor.delete_rope_segment(hoist_id, row))

    # -- contractual points --------------------------------------------

    @pyqtSlot(int, result="QVariantMap")
    def contractualFields(self, row: int) -> dict[str, Any]:
        point = self._contractual_model.record_at(row)
        if point is None:
            return {}
        return contractual_fields(point)

    @pyqtSlot("QVariantMap")
    def addContractualPoint(self, fields: dict) -> None:
        hoist_id = self._model.selected_editor_hoist_id
        mode = self._contractual_mode
        condition_name = self._shown_condition
        self._apply_edit(
            lambda editor: editor.add_contractual_point(
                hoist_id,
                build_contractual_point(fields.get("outreach_m", 0.0), fields.get("load_t", 0.0)),
                mode,
                condition_name,
            )
        )

    @pyqtSlot(int, "QVariantMap", result="bool")
    def updateContractualPoint(self, row: int, fields: dict) -> bool:
        hoist_id = self._model.selected_editor_hoist_id
        mode = self._contractual_mode
        condition_name = self._shown_condition
        return self._apply_edit(
            lambda editor: editor.update_contractual_point(
                hoist_id,
                row,
                build_contractual_point(fields.get("outreach_m", 0.0), fields.get("load_t", 0.0)),
                mode,
                condition_name,
            )
        )

    @pyqtSlot(int)
    def deleteContractualPoint(self, row: int) -> None:
        hoist_id = self._model.selected_editor_hoist_id
        mode = self._contractual_mode
        condition_name = self._shown_condition
        self._apply_edit(
            lambda editor: editor.delete_contractual_point(hoist_id, row, mode, condition_name)
        )
