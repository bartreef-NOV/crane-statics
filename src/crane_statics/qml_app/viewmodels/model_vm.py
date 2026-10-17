"""Model workspace view model: component and hoist editing tables."""

from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

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
from crane_statics.qml_app.contracts import EnvironmentSettings
from crane_statics.qml_app.session import SessionState
from crane_statics.data import payload_hoist_ids

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

ENVIRONMENT_KEYS = [
    "gravity_m_s2",
    "max_wind_speed_m_s",
    "air_density_kg_m3",
]
VESSEL_MOTION_KEYS = [
    "roll_deg",
    "pitch_deg",
    "accel_x_m_s2",
    "accel_y_m_s2",
    "accel_z_m_s2",
    "roll_angular_accel_rad_s2",
    "pitch_angular_accel_rad_s2",
    "reference_x_m",
    "reference_z_m",
]
SUPPORT_WIDTH_KEYS = ["boom_width_m", "slewing_bearing_diameter_m"]
# Support-width keys that may be cleared back to "unset" via clearEnvironmentValue.
NULLABLE_SUPPORT_WIDTH_KEYS = {"slewing_bearing_diameter_m"}
# Document-level design duty: edited alongside the environment, stored on the document.
DOCUMENT_KEYS = ["hook_height_at_min_outreach_m"]

# Authored primary-structure points and the runtime nodes they map to.
PRIMARY_STRUCTURE_BINDINGS = [
    ("boom_heel", "Heel Point"),
    ("rear_top", "Upper Hinge"),
    ("rear_base", "Rear Hinge"),
    ("front_base", "Front Hinge"),
]
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

    def __init__(self, session: SessionState, parent=None):
        super().__init__(parent)
        self._session = session
        self._model = session.model
        self._selected_body_id: str = COMPONENT_ORDER[0]
        self._contractual_mode: str = "normal"

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
            hoist_columns(self._is_boom_hoist), self, commit=self._commit_hoist_cell
        )
        self._rope_segments_model = RecordTableModel(
            rope_segment_columns(), self, commit=self._commit_rope_segment_cell
        )
        self._contractual_model = RecordTableModel(
            contractual_columns(), self, commit=self._commit_contractual_cell
        )
        self._primary_structure_model = DictListModel(PRIMARY_ROLES, self)

        self._session.document_changed.connect(lambda _doc: self.refresh())

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
        doc = self._model.document
        available = self.bodyIds
        if available and self._selected_body_id not in available:
            self.selectBody(available[0])
        hoist_ids = self.hoistIds
        if hoist_ids and self._model.selected_editor_hoist_id not in hoist_ids:
            self._model.select_editor_hoist(hoist_ids[0])
        elif not hoist_ids:
            self._model.selected_editor_hoist_id = None

        self._hoists_model.set_records([] if doc is None else doc.hoists)
        self._refresh_component_tables()
        self._refresh_hoist_tables()
        self._refresh_primary_structure()
        self.componentsChanged.emit()
        self.hoistsChanged.emit()
        self.selectedHoistChanged.emit()
        self.environmentChanged.emit()
        self.healthChanged.emit()

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

    def _refresh_hoist_tables(self) -> None:
        editor = self._editor()
        hoist = self._hoist()
        segments = (
            []
            if editor is None or hoist is None
            else [seg for _idx, seg in editor.visible_rope_segments(hoist)]
        )
        self._rope_segments_model.set_records(segments)
        if hoist is None:
            self._contractual_model.set_records([])
        elif self._contractual_mode == "split" and self.hoistSplitable:
            self._contractual_model.set_records(hoist.split_contractual_points)
        else:
            self._contractual_model.set_records(hoist.contractual_points)

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
        doc = self._model.document
        if doc is None:
            return EnvironmentSettings.defaults().to_dict()
        env_dict: dict[str, Optional[float]] = {
            key: float(getattr(doc.environment, key)) for key in ENVIRONMENT_KEYS
        }
        env_dict.update(
            {key: float(getattr(doc.environment.vessel_motion, key)) for key in VESSEL_MOTION_KEYS}
        )
        env_dict.update(
            {
                key: (float(raw) if (raw := getattr(doc.support_widths, key)) is not None else None)
                for key in SUPPORT_WIDTH_KEYS
            }
        )
        env_dict["hook_height_at_min_outreach_m"] = float(
            doc.hook_height_at_min_outreach_m
            if doc.hook_height_at_min_outreach_m is not None
            else 0.0
        )
        return EnvironmentSettings.from_dict(env_dict).to_dict()

    @pyqtSlot(str, float)
    def setEnvironmentValue(self, key: str, value: float) -> None:
        doc = self._model.document
        if doc is None:
            return
        target: Any
        if key in ENVIRONMENT_KEYS:
            target = doc.environment
        elif key in VESSEL_MOTION_KEYS:
            target = doc.environment.vessel_motion
        elif key in SUPPORT_WIDTH_KEYS:
            target = doc.support_widths
        elif key in DOCUMENT_KEYS:
            target = doc
        else:
            return
        previous = getattr(target, key)
        if float(previous or 0.0) == float(value):
            return
        setattr(target, key, float(value))
        if key in DOCUMENT_KEYS:
            try:
                DocumentEditor(doc).refresh_derived_geometry()
            except ValueError as exc:
                setattr(target, key, previous)
                DocumentEditor(doc).refresh_derived_geometry()
                self.editFailed.emit(str(exc))
                return
            self.refresh()
        self._model.mark_content_changed()
        self.environmentChanged.emit()
        self.healthChanged.emit()
        self.modelEdited.emit()

    @pyqtSlot(str)
    def clearEnvironmentValue(self, key: str) -> None:
        doc = self._model.document
        if doc is None or key not in NULLABLE_SUPPORT_WIDTH_KEYS:
            return
        target = doc.support_widths
        if getattr(target, key) is None:
            return
        setattr(target, key, None)
        self._model.mark_content_changed()
        self.environmentChanged.emit()
        self.healthChanged.emit()
        self.modelEdited.emit()

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
        doc = self._model.document
        by_id = {} if doc is None else {n.id: n for n in doc.nodes}
        rows = []
        for node_id, label in PRIMARY_STRUCTURE_BINDINGS:
            node = by_id.get(node_id)
            if node is None:
                continue
            rows.append(
                {
                    "nodeId": node_id,
                    "label": label,
                    "posX": float(node.x_m),
                    "posZ": float(node.z_m),
                }
            )
        self._primary_structure_model.set_rows(rows)

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
        return {
            "id": node.id,
            "hanging": bool(node.below_node_id),
            "below_node_id": node.below_node_id or "",
            "x_m": float(node.x_m),
            "z_m": float(node.z_m),
            "local_x_m": float(node.local_x_m or 0.0),
            "local_z_m": float(node.local_z_m or 0.0),
        }

    @pyqtSlot("QVariantMap")
    def addNode(self, fields: dict) -> None:
        body_id = self._selected_body_id
        self._apply_edit(
            lambda editor: editor.add_node(build_node(body_id, **_node_kwargs(fields)))
        )

    @pyqtSlot(int, "QVariantMap", result=bool)
    def updateNode(self, row: int, fields: dict) -> bool:
        current = self._nodes_model.record_at(row)
        if current is None:
            self.editFailed.emit("Select a node first")
            return False
        body_id = self._selected_body_id
        return self._apply_edit(
            lambda editor: editor.update_node(
                current.id, build_node(body_id, **_node_kwargs(fields))
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
        return {
            "id": point.id,
            "mass_t": float(point.mass_t),
            "x_m": float(point.x_m),
            "y_m": float(point.y_m),
            "z_m": float(point.z_m),
            "local_x_m": float(point.local_x_m or 0.0),
            "local_y_m": float(point.local_y_m or 0.0),
            "local_z_m": float(point.local_z_m or 0.0),
        }

    @pyqtSlot("QVariantMap")
    def addMassPoint(self, fields: dict) -> None:
        body_id = self._selected_body_id
        self._apply_edit(
            lambda editor: editor.add_mass_point(
                body_id, build_mass_point(body_id, **_mass_kwargs(fields))
            )
        )

    @pyqtSlot(int, "QVariantMap", result=bool)
    def updateMassPoint(self, row: int, fields: dict) -> bool:
        body_id = self._selected_body_id
        return self._apply_edit(
            lambda editor: editor.update_mass_point(
                body_id, row, build_mass_point(body_id, **_mass_kwargs(fields))
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
        return {
            "id": area.id,
            "area_w_m2": float(area.area_w_m2),
            "area_v_m2": float(area.area_v_m2),
            "x_m": float(area.x_m),
            "z_m": float(area.z_m),
            "local_x_m": float(area.local_x_m or 0.0),
            "local_z_m": float(area.local_z_m or 0.0),
            "cd": float(area.cd),
        }

    @pyqtSlot("QVariantMap")
    def addWindArea(self, fields: dict) -> None:
        body_id = self._selected_body_id
        self._apply_edit(
            lambda editor: editor.add_wind_area(
                body_id, build_wind_area(body_id, **_wind_kwargs(fields))
            )
        )

    @pyqtSlot(int, "QVariantMap", result=bool)
    def updateWindArea(self, row: int, fields: dict) -> bool:
        body_id = self._selected_body_id
        return self._apply_edit(
            lambda editor: editor.update_wind_area(
                body_id, row, build_wind_area(body_id, **_wind_kwargs(fields))
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
        return {
            "id": hoist.id,
            "is_boom_hoist": self._is_boom_hoist(hoist),
            "support_node_id": hoist.support_node_id or hoist.load_node_id,
            "falls": int(hoist.falls or 1),
            "hook_mass_t": float(hoist.hook_mass_t),
            "linear_mass_kg_m": float(hoist.linear_mass_kg_m),
            "rope_length_m": None if hoist.rope_length_m is None else float(hoist.rope_length_m),
            "splitable_block": bool(hoist.splitable_block),
            "split_falls": int(hoist.split_falls or hoist.falls or 1),
            "split_hook_mass_t": float(
                hoist.split_hook_mass_t
                if hoist.split_hook_mass_t is not None
                else hoist.hook_mass_t
            ),
            "hook_daf": float(hoist.hook_daf),
            "offlead_deg": float(hoist.offlead_deg),
            "sidelead_deg": float(hoist.sidelead_deg),
            "max_hook_travel_m": float(hoist.max_hook_travel_m or 0.0),
            "drum_dead_turns": int(hoist.drum_dead_turns or 0),
            "drum_diameter_m": (
                None if hoist.drum_diameter_m is None else float(hoist.drum_diameter_m)
            ),
        }

    def _is_boom_hoist(self, hoist: Any) -> bool:
        doc = self._model.document
        if doc is None:
            return False
        rope = next((rope for rope in doc.ropes if rope.id == hoist.rope_id), None)
        return bool(rope is not None and rope.tension_mode == "solve")

    @pyqtSlot("QVariantMap")
    def addHoist(self, fields: dict) -> None:
        self._apply_edit(
            lambda editor: editor.add_hoist(build_payload_hoist(**_hoist_kwargs(fields)))
        )

    @pyqtSlot(int, "QVariantMap", result=bool)
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
        return self._apply_edit(
            lambda editor: editor.update_hoist(
                current.id, build_payload_hoist(**_hoist_kwargs(fields))
            )
        )

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
        return {
            "from_node_id": segment.from_node_id,
            "to_node_id": segment.to_node_id,
            "mult": int(segment.mult),
        }

    @pyqtSlot("QVariantMap")
    def addRopeSegment(self, fields: dict) -> None:
        hoist_id = self._model.selected_editor_hoist_id
        self._apply_edit(
            lambda editor: editor.add_rope_segment(
                hoist_id, build_segment(**_segment_kwargs(fields))
            )
        )

    @pyqtSlot(int, "QVariantMap", result=bool)
    def updateRopeSegment(self, row: int, fields: dict) -> bool:
        hoist_id = self._model.selected_editor_hoist_id
        return self._apply_edit(
            lambda editor: editor.update_rope_segment(
                hoist_id, row, build_segment(**_segment_kwargs(fields))
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
        return {"outreach_m": float(point.outreach_m), "load_t": float(point.load_t)}

    @pyqtSlot("QVariantMap")
    def addContractualPoint(self, fields: dict) -> None:
        hoist_id = self._model.selected_editor_hoist_id
        mode = self._contractual_mode
        self._apply_edit(
            lambda editor: editor.add_contractual_point(
                hoist_id,
                build_contractual_point(fields.get("outreach_m", 0.0), fields.get("load_t", 0.0)),
                mode,
            )
        )

    @pyqtSlot(int, "QVariantMap", result=bool)
    def updateContractualPoint(self, row: int, fields: dict) -> bool:
        hoist_id = self._model.selected_editor_hoist_id
        mode = self._contractual_mode
        return self._apply_edit(
            lambda editor: editor.update_contractual_point(
                hoist_id,
                row,
                build_contractual_point(fields.get("outreach_m", 0.0), fields.get("load_t", 0.0)),
                mode,
            )
        )

    @pyqtSlot(int)
    def deleteContractualPoint(self, row: int) -> None:
        hoist_id = self._model.selected_editor_hoist_id
        mode = self._contractual_mode
        self._apply_edit(lambda editor: editor.delete_contractual_point(hoist_id, row, mode))


def _node_kwargs(fields: dict) -> dict:
    return {
        "node_id": str(fields.get("id", "")),
        "hanging": bool(fields.get("hanging", False)),
        "below_node_id": str(fields.get("below_node_id", "") or ""),
        "x_m": float(fields.get("x_m", 0.0)),
        "z_m": float(fields.get("z_m", 0.0)),
        "local_x_m": float(fields.get("local_x_m", 0.0)),
        "local_z_m": float(fields.get("local_z_m", 0.0)),
    }


def _mass_kwargs(fields: dict) -> dict:
    return {
        "mass_point_id": str(fields.get("id", "")),
        "mass_t": float(fields.get("mass_t", 0.0)),
        "x_m": float(fields.get("x_m", 0.0)),
        "y_m": float(fields.get("y_m", 0.0)),
        "z_m": float(fields.get("z_m", 0.0)),
        "local_x_m": float(fields.get("local_x_m", 0.0)),
        "local_y_m": float(fields.get("local_y_m", 0.0)),
        "local_z_m": float(fields.get("local_z_m", 0.0)),
    }


def _wind_kwargs(fields: dict) -> dict:
    return {
        "wind_area_id": str(fields.get("id", "")),
        "area_w_m2": float(fields.get("area_w_m2", 0.0)),
        "area_v_m2": float(fields.get("area_v_m2", 0.0)),
        "x_m": float(fields.get("x_m", 0.0)),
        "z_m": float(fields.get("z_m", 0.0)),
        "local_x_m": float(fields.get("local_x_m", 0.0)),
        "local_z_m": float(fields.get("local_z_m", 0.0)),
        "cd": float(fields.get("cd", 1.0)),
    }


def _hoist_kwargs(fields: dict) -> dict:
    splitable = bool(fields.get("splitable_block", False))
    drum_diameter_m = fields.get("drum_diameter_m")
    return {
        "hoist_id": str(fields.get("id", "")),
        "support_node_id": str(fields.get("support_node_id", "")),
        "falls": int(fields.get("falls", 1)),
        "hook_mass_t": float(fields.get("hook_mass_t", 0.0)),
        "linear_mass_kg_m": max(0.0, float(fields.get("linear_mass_kg_m", 0.0))),
        "drum_dead_turns": max(0, int(fields.get("drum_dead_turns", 0) or 0)),
        "drum_diameter_m": (
            None
            if drum_diameter_m is None or drum_diameter_m == ""
            else max(0.0, float(drum_diameter_m))
        ),
        "splitable_block": splitable,
        "split_falls": int(fields.get("split_falls", 1)) if splitable else None,
        "split_hook_mass_t": float(fields.get("split_hook_mass_t", 0.0)) if splitable else None,
        "hook_daf": float(fields.get("hook_daf", 1.0)),
        "offlead_deg": float(fields.get("offlead_deg", 0.0)),
        "sidelead_deg": float(fields.get("sidelead_deg", 0.0)),
    }


def _segment_kwargs(fields: dict) -> dict:
    return {
        "from_node_id": str(fields.get("from_node_id", "")),
        "to_node_id": str(fields.get("to_node_id", "")),
        "mult": int(fields.get("mult", 1)),
    }
