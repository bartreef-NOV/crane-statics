"""Scene workspace view model: geometry, environment, results and canvas sync."""

from __future__ import annotations

import dataclasses
import logging
import math
from dataclasses import dataclass
from typing import Any, Optional

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

from crane_statics.core.analysis_presenter import AnalysisPresenter
from crane_statics.core.analysis_services import (
    AnalysisCalculator,
    HoistStateService,
    KinematicsService,
)
from crane_statics.core.drawn_loads import active_hoist_dict
from crane_statics.core.governing_case import GoverningCase
from crane_statics.core.scene_build import SceneDisplay, SceneInputs, build_scene_frame
from crane_statics.core.session_model import SceneState
from crane_statics.qml_app.adapters.scene_adapter import SceneStateAdapter
from crane_statics.qml_app.scene.scene_drag import DragEdit, DragLimits, SceneDrag
from crane_statics.qml_app.session import SessionState

from ..models.list_models import DictListModel
from ..models.report_rows import (
    REPORT_ROLES,
    RESULT_ROLES,
    report_to_rows,
    result_row_payload,
    result_rows_to_dicts,
)

_LOG = logging.getLogger(__name__)

WIND_DIRECTIONS = ["+X", "-X", "+Y", "-Y"]


@dataclass(frozen=True)
class _InputsSnapshot:
    """The Scene inputs a governing case replaced, so Restore can put them back."""

    hoist_id: str
    scene_state: SceneState
    hook_load_t: float
    contractual_idx: Optional[int]
    # Every hoist's Scene split flag: applying a split case through
    # ``set_active_split_hoist`` clears the flag on the other hoists too. The Load
    # Chart modes are not touched by an apply, so they are not restored either.
    split_flags: dict[str, bool]
    # The tackle of the case shown last: the tackle range covers it until Restore.
    case_tackle_m: float


class SceneViewModel(QObject):
    """Drives the QML scene workspace from the session and analysis service."""

    hoistsChanged = pyqtSignal()
    geometryChanged = pyqtSignal()
    angleBoundsChanged = pyqtSignal()
    tackleBoundsChanged = pyqtSignal()
    loadChanged = pyqtSignal()
    environmentChanged = pyqtSignal()
    hookModeChanged = pyqtSignal()
    contractualChanged = pyqtSignal()
    displayOptionsChanged = pyqtSignal()
    sceneFrameChanged = pyqtSignal()
    statusMessage = pyqtSignal(str)
    reportReady = pyqtSignal(str, str)
    loadOverviewReady = pyqtSignal("QVariantMap")
    governingCaseChanged = pyqtSignal()

    def __init__(self, session: SessionState, parent=None):
        super().__init__(parent)
        self._session = session
        self._model = session.model
        self._kinematics = KinematicsService(self._model)
        self._hoist_state = HoistStateService(self._model)
        self._calculator = AnalysisCalculator(self._model, self._kinematics, self._hoist_state)
        self._presenter = AnalysisPresenter(self._model, self._calculator, self._hoist_state)
        self._canvas: Optional[QObject] = None
        self._canvases: list[QObject] = []

        self._outreach = 0.0
        self._hook_load_t = 0.0
        self._display = SceneDisplay()
        self._contractual_rows: list[dict[str, Any]] = []
        self._geometry_sync_active = False
        self._scene_frame: dict[str, Any] = SceneStateAdapter.empty_scene_frame()
        self._frame_revision = 0
        self._analysis_point: Any = None
        self._drag: Optional[SceneDrag] = None
        self._initialized_load_hoist_id: Optional[str] = None
        self._governing_label = ""
        self._snapshot: Optional[_InputsSnapshot] = None
        self._applying = False
        self._last_unavailable_text: Optional[str] = None

        self._rope_rows_model = DictListModel(RESULT_ROLES, self)
        self._connection_rows_model = DictListModel(RESULT_ROLES, self)
        self._report_model = DictListModel(REPORT_ROLES, self)
        self._rope_payloads: list[Optional[dict]] = []
        self._connection_payloads: list[Optional[dict]] = []

        self._session.document_changed.connect(self._on_document_changed)
        self._session.content_changed.connect(self._on_content_changed)
        self._session.hoist_selected.connect(self._on_hoist_selected)
        self._model.register_history_extra(
            "scene_hook_load_t", self._capture_hook_load, self._restore_hook_load
        )

    def _capture_hook_load(self) -> float:
        return self._hook_load_t

    def _restore_hook_load(self, hook_load_t: float) -> None:
        """Undo/redo: keep the restored load; the reload that follows must not re-initialise it."""
        self._hook_load_t = float(hook_load_t)
        self._initialized_load_hoist_id = self._model.selected_hoist_id

    # ------------------------------------------------------------------
    # Canvas binding
    # ------------------------------------------------------------------

    @pyqtSlot(QObject)
    def bindCanvas(self, canvas: QObject) -> None:
        if canvas in self._canvases:
            return
        self._canvases.append(canvas)
        if self._canvas is None:
            self._canvas = canvas
        canvas.setSceneViewModel(self)
        canvas.boomAngleChanged.connect(self._on_canvas_angle_changed)
        canvas.tackleLengthChanged.connect(self._on_canvas_tackle_changed)
        self.reload()

    @pyqtSlot(QObject)
    def unbindCanvas(self, canvas: QObject) -> None:
        if canvas not in self._canvases:
            return
        self._canvases.remove(canvas)
        if canvas is self._canvas:
            self._canvas = self._canvases[0] if self._canvases else None

    def _renderer(self):
        return None if self._canvas is None else self._canvas.renderer

    def _renderers(self) -> list[Any]:
        return [canvas.renderer for canvas in self._canvases]

    @pyqtProperty("QVariantMap", notify=sceneFrameChanged)
    def sceneFrame(self) -> dict[str, Any]:
        return self._scene_frame

    def _scene_inputs(self) -> SceneInputs:
        """Everything the scene shows, as one value.

        The kinematics adapter carries the serialized document it was built from, so
        the whole scene is described by one cached ``model_dump()`` per document.
        """
        kinematics = self._kinematics.kinematics()
        document_dict = None if kinematics is None else kinematics.doc
        hoist_id = self._model.selected_hoist_id or ""
        state = self._model.get_active_hoist_state()
        tackle_min, tackle_max = self._tackle_bounds()
        tackle = 0.0 if state is None else float(state.scene_state.tackle_length_m)
        return SceneInputs(
            document_dict=document_dict,
            kinematics=kinematics,
            hoist_id=hoist_id,
            hoist=active_hoist_dict(document_dict or {}, hoist_id),
            conditions=self._calculator.drawn_load_conditions(),
            display=self._display,
            analysis_point=self._analysis_point,
            tackle_length_m=max(tackle_min, min(tackle_max, tackle)),
        )

    def _publish_scene_frame(self) -> None:
        """Build one frame and hand that same frame to every bound canvas."""
        self._frame_revision += 1
        frame = build_scene_frame(self._scene_inputs(), revision=self._frame_revision)
        for renderer in self._renderers():
            renderer.show(frame)

        as_dict = SceneStateAdapter.scene_frame_to_dict(frame)
        if as_dict != self._scene_frame:
            self._scene_frame = as_dict
            self.sceneFrameChanged.emit()

    def _on_canvas_angle_changed(self, angle: float) -> None:
        state = self._model.get_active_hoist_state()
        if state is None:
            return
        self._end_governing_label()
        state.scene_state.boom_angle_deg = float(angle)
        self.geometryChanged.emit()
        self._sync_outreach_from_angle(float(angle))
        self._after_state_changed()

    def _on_canvas_tackle_changed(self, tackle_m: float) -> None:
        state = self._model.get_active_hoist_state()
        if state is None:
            return
        self._end_governing_label()
        state.scene_state.tackle_length_m = float(tackle_m)
        self.geometryChanged.emit()
        self._after_state_changed()

    @pyqtSlot(str, float, float)
    def sceneDragStart(self, kind: str, scene_x: float, scene_y: float) -> None:
        """Start a drag operation (angle, outreach, or tackle)."""
        self._drag = SceneDrag.begin(kind, scene_y, self.tackle)

    @pyqtSlot(float, float, result=str)
    def sceneDragTargetAt(self, scene_x: float, scene_y: float) -> str:
        """Determine which drag target (if any) is under the pointer."""
        return SceneDrag.target_at(
            float(scene_x), float(scene_y), self._scene_frame.get("hitTargets", [])
        )

    @pyqtSlot(float, float, bool)
    def sceneDragUpdate(self, scene_x: float, scene_y: float, alt_snap: bool = False) -> None:
        """Apply what the pointer position asks the active drag to change."""
        renderer = self._renderer()
        if self._drag is None or renderer is None:
            return
        edit = self._drag.edit(
            renderer,
            float(scene_x),
            float(scene_y),
            limits=self._drag_limits(),
            alt_snap=bool(alt_snap),
        )
        if edit is not None:
            self._apply_drag_edit(edit)

    @pyqtSlot()
    def sceneDragEnd(self) -> None:
        """End the current drag operation."""
        self._drag = None

    def _drag_limits(self) -> DragLimits:
        """The range a drag may move each quantity through."""
        return DragLimits(
            angle_deg=self._kinematics.angle_bounds.get(
                self._model.selected_hoist_id or "", (-180.0, 180.0)
            ),
            tackle_m=self._tackle_bounds(),
        )

    def _apply_drag_edit(self, edit: DragEdit) -> None:
        """Route a requested edit to the setter that owns that quantity."""
        setters = {
            "angle_deg": self.setAngle,
            "outreach_m": self.setOutreach,
            "tackle_m": self.setTackle,
        }
        setters[edit.field](edit.value)

    @pyqtSlot(float)
    def nudgeOutreach(self, delta_m: float) -> None:
        self.setOutreach(self.outreach + float(delta_m))

    # ------------------------------------------------------------------
    # Hoists and hook mode
    # ------------------------------------------------------------------

    @pyqtProperty(list, notify=hoistsChanged)
    def hoistIds(self) -> list:
        return self._model.payload_hoist_ids()

    @pyqtProperty(str, notify=hoistsChanged)
    def selectedHoistId(self) -> str:
        return self._model.selected_hoist_id or ""

    @pyqtSlot(str)
    def selectHoist(self, hoist_id: str) -> None:
        if hoist_id and hoist_id != self._model.selected_hoist_id:
            self._model.select_payload_hoist(hoist_id)

    @pyqtProperty(bool, notify=hookModeChanged)
    def splitable(self) -> bool:
        return self._model.is_splitable_hoist(self._model.selected_hoist_id)

    @pyqtProperty(str, notify=hookModeChanged)
    def hookMode(self) -> str:
        state = self._model.get_active_hoist_state()
        return "split" if state is not None and state.split_mode_active else "normal"

    @pyqtSlot(str)
    def setHookMode(self, mode: str) -> None:
        hoist_id = self._model.selected_hoist_id
        if not hoist_id:
            return
        want_split = str(mode).lower() == "split"
        if want_split and not self.splitable:
            self.statusMessage.emit(f"Hoist {hoist_id} is not configured as splitable")
            self.hookModeChanged.emit()
            return

        self._model.set_hook_mode(hoist_id, mode)
        self._set_contractual_selection(None)
        self.hookModeChanged.emit()
        self._rebuild_contractual_rows()
        self._after_state_changed()
        self._model.mark_content_changed(scope="scene")

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    @pyqtProperty(float, notify=geometryChanged)
    def angle(self) -> float:
        state = self._model.get_active_hoist_state()
        return 0.0 if state is None else float(state.scene_state.boom_angle_deg)

    @pyqtSlot(float)
    def setAngle(self, value: float) -> None:
        if self._geometry_sync_active:
            return
        state = self._model.get_active_hoist_state()
        if state is None:
            return
        self._geometry_sync_active = True
        try:
            lo, hi = self._kinematics.spinbox_angle_bounds(self._model.selected_hoist_id)
            value = max(lo, min(hi, float(value)))
            self._clear_contractual_selection()
            state.scene_state.boom_angle_deg = float(value)
            self.geometryChanged.emit()
            self._sync_outreach_from_angle(float(value))
            if state.scene_state.hook_load_auto:
                self.recomputeAutoLoad()
            else:
                self._after_state_changed()
            self._model.mark_content_changed(scope="scene", key="angle")
        finally:
            self._geometry_sync_active = False

    @pyqtProperty(float, notify=geometryChanged)
    def outreach(self) -> float:
        return self._outreach

    @pyqtSlot(float)
    def setOutreach(self, value: float) -> None:
        hoist_id = self._model.selected_hoist_id
        if not self._model.document or not hoist_id:
            return
        kin = self._kinematics.kinematics()
        lo_m, hi_m = self._outreach_bounds()
        value = max(lo_m, min(hi_m, float(value)))
        try:
            angle = None if kin is None else kin.outreach_to_angle(float(value), hoist_id)
        except (TypeError, ValueError, RuntimeError) as exc:
            _LOG.debug("Failed outreach->angle for %s at %.3f m: %s", hoist_id, value, exc)
            angle = None
        if angle is None:
            self.statusMessage.emit(f"Outreach {value:.1f} m is outside the reachable range")
            self.geometryChanged.emit()
            return
        self.setAngle(float(angle))

    @pyqtProperty(float, notify=angleBoundsChanged)
    def angleMin(self) -> float:
        return self._kinematics.spinbox_angle_bounds(self._model.selected_hoist_id)[0]

    @pyqtProperty(float, notify=angleBoundsChanged)
    def angleMax(self) -> float:
        return self._kinematics.spinbox_angle_bounds(self._model.selected_hoist_id)[1]

    @pyqtProperty(float, notify=angleBoundsChanged)
    def outreachMin(self) -> float:
        return self._outreach_bounds()[0]

    @pyqtProperty(float, notify=angleBoundsChanged)
    def outreachMax(self) -> float:
        return self._outreach_bounds()[1]

    def _outreach_bounds(self) -> tuple[float, float]:
        """The reachable outreach band, derived from the boom-angle band.

        Deriving it rather than reading ``outreach_min_m``/``outreach_max_m`` keeps
        the two controls from ever disagreeing: unchecking Auto relaxes the angle
        floor to 0 deg, and the outreach the operator can dial has to follow it out.
        """
        hoist_id = self._model.selected_hoist_id
        hoist = self._hoist_state.selected_hoist()
        authored = (
            (float(hoist.outreach_min_m or 0.0), float(hoist.outreach_max_m or 200.0))
            if hoist is not None
            else (0.0, 200.0)
        )
        kin = self._kinematics.kinematics()
        if kin is None or not hoist_id:
            return authored
        lo_angle, hi_angle = self._kinematics.spinbox_angle_bounds(hoist_id)
        try:
            reach = [float(kin.compute_outreach(angle, hoist_id)) for angle in (lo_angle, hi_angle)]
        except (TypeError, ValueError, RuntimeError) as exc:
            _LOG.debug("Failed to derive outreach bounds for %s: %s", hoist_id, exc)
            return authored
        return min(reach), max(reach)

    @pyqtProperty(float, notify=geometryChanged)
    def tackle(self) -> float:
        state = self._model.get_active_hoist_state()
        return 0.0 if state is None else float(state.scene_state.tackle_length_m)

    @pyqtSlot(float)
    def setTackle(self, value: float) -> None:
        state = self._model.get_active_hoist_state()
        if state is None:
            return
        state.scene_state.tackle_length_m = float(value)
        self.geometryChanged.emit()
        self._after_state_changed()
        self._model.mark_content_changed(scope="scene", key="tackle")

    @pyqtProperty(float, notify=tackleBoundsChanged)
    def tackleMin(self) -> float:
        return self._tackle_bounds()[0]

    @pyqtProperty(float, notify=tackleBoundsChanged)
    def tackleMax(self) -> float:
        return self._tackle_bounds()[1]

    def _tackle_bounds(self) -> tuple[float, float]:
        hoist = self._hoist_state.selected_hoist()
        if hoist is None:
            return 0.0, 500.0
        hi = float(hoist.max_hook_travel_m) if hoist.max_hook_travel_m is not None else 500.0
        # A governing case can pay out more rope than the hook travel: keep it in range,
        # so neither the tackle field nor the canvas clamps the case back.
        if self._snapshot is not None:
            hi = max(hi, self._snapshot.case_tackle_m)
        return 0.0, max(0.0, hi)

    def _sync_outreach_from_angle(self, angle: float) -> None:
        hoist_id = self._model.selected_hoist_id
        kin = self._kinematics.kinematics()
        if kin is None or not hoist_id:
            return
        try:
            self._outreach = float(kin.compute_outreach(angle, hoist_id))
        except (TypeError, ValueError, RuntimeError) as exc:
            _LOG.debug("Failed to derive outreach for %s at %.3f deg: %s", hoist_id, angle, exc)
            return
        self.geometryChanged.emit()

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    @pyqtProperty(float, notify=loadChanged)
    def hookLoadTonnes(self) -> float:
        return self._hook_load_t

    @pyqtSlot(float)
    def setHookLoadTonnes(self, value: float) -> None:
        state = self._model.get_active_hoist_state()
        if state is None:
            return
        self._clear_contractual_selection()
        self._hook_load_t = max(0.0, float(value))
        state.scene_state.hook_load_kN = self._hoist_state.payload_t_to_hook_force_kN(
            self._hook_load_t
        )
        self.loadChanged.emit()
        self._after_state_changed()
        self._model.mark_content_changed(scope="scene", key="hook_load")

    @pyqtProperty(bool, notify=loadChanged)
    def hookLoadAuto(self) -> bool:
        state = self._model.get_active_hoist_state()
        return False if state is None else bool(state.scene_state.hook_load_auto)

    @pyqtSlot(bool)
    def setHookLoadAuto(self, enabled: bool) -> None:
        state = self._model.get_active_hoist_state()
        if state is None:
            return
        self._end_governing_label()
        state.scene_state.hook_load_auto = bool(enabled)
        self.angleBoundsChanged.emit()
        self.loadChanged.emit()
        if enabled:
            self.recomputeAutoLoad()
        else:
            self._after_state_changed()

    @pyqtProperty(float, notify=loadChanged)
    def offlead(self) -> float:
        state = self._model.get_active_hoist_state()
        return 0.0 if state is None else float(state.scene_state.offlead_deg)

    @pyqtSlot(float)
    def setOfflead(self, value: float) -> None:
        self._set_scene_field("offlead_deg", float(value), self.loadChanged)

    @pyqtProperty(float, notify=loadChanged)
    def sidelead(self) -> float:
        state = self._model.get_active_hoist_state()
        return 0.0 if state is None else float(state.scene_state.sidelead_deg)

    @pyqtSlot(float)
    def setSidelead(self, value: float) -> None:
        self._set_scene_field("sidelead_deg", float(value), self.loadChanged)

    @pyqtSlot()
    def recomputeAutoLoad(self) -> None:
        state = self._model.get_active_hoist_state()
        if state is None:
            return
        try:
            cap = self._calculator.compute_auto_load()
        except (TypeError, ValueError, RuntimeError) as exc:
            _LOG.warning("Auto load recompute failed: %s", exc)
            self.statusMessage.emit(f"Auto load error: {exc}")
            self._after_state_changed()
            return
        if cap is None:
            self._after_state_changed()
            return
        if not math.isfinite(cap.max_allowable_load_kN):
            # No enabled limit constrains the hook load: keep the current one.
            self.statusMessage.emit("Auto: no design limit applies")
            self._after_state_changed()
            return
        # Store both metrics: hook-force for internal state (scene visualization),
        # payload for user-facing display (UI label, status message).
        # METRIC DOMAINS: max_allowable_load_kN = hook-force (includes DAF & hook mass);
        #                 max_allowable_load_t = payload (net mass after subtracting hook mass)
        state.scene_state.hook_load_kN = cap.max_allowable_load_kN
        self._hook_load_t = float(cap.max_allowable_load_t)
        self._clear_contractual_selection()
        self.loadChanged.emit()
        self._after_state_changed()
        governs = (
            f"  governed by {cap.governing_limit_id}"
            if cap.governing_limit_id
            else "  (no active limits)"
        )
        wind = f", wind {cap.governing_wind_direction}" if cap.governing_wind_direction else ""
        self.statusMessage.emit(f"Auto: {cap.max_allowable_load_kN:.1f} kN{governs}{wind}")

    # ------------------------------------------------------------------
    # Environment
    # ------------------------------------------------------------------

    @pyqtProperty(float, notify=environmentChanged)
    def windSpeed(self) -> float:
        state = self._model.get_active_hoist_state()
        if state is None:
            return 0.0
        speed = float(state.scene_state.wind_speed_m_s)
        direction = str(state.scene_state.wind_direction)
        return -speed if direction.startswith("-") else speed

    @pyqtSlot(float)
    def setWindSpeed(self, value: float) -> None:
        state = self._model.get_active_hoist_state()
        if state is None:
            return
        signed_speed = float(value)
        axis = str(state.scene_state.wind_direction)[-1:]
        axis = axis if axis in {"X", "Y"} else "X"
        direction = ("-" if signed_speed < 0 else "+") + axis
        state.scene_state.wind_speed_m_s = abs(signed_speed)
        state.scene_state.wind_direction = direction
        self.environmentChanged.emit()
        self._after_state_changed()
        self._model.mark_content_changed(scope="scene", key="wind")

    @pyqtProperty(str, notify=environmentChanged)
    def windAxis(self) -> str:
        direction = str(self.windDirection)
        return direction[-1:] if direction[-1:] in {"X", "Y"} else "X"

    @pyqtSlot(str)
    def setWindAxis(self, axis: str) -> None:
        normalized = str(axis).upper()
        if normalized not in {"X", "Y"}:
            return
        direction = self.windDirection
        sign = "-" if direction.startswith("-") else "+"
        self.setWindDirection(sign + normalized)

    @pyqtProperty(str, notify=environmentChanged)
    def windDirection(self) -> str:
        state = self._model.get_active_hoist_state()
        return "+X" if state is None else str(state.scene_state.wind_direction)

    @pyqtSlot(str)
    def setWindDirection(self, value: str) -> None:
        if value in WIND_DIRECTIONS:
            self._set_scene_field("wind_direction", value, self.environmentChanged)

    @pyqtProperty(float, notify=environmentChanged)
    def accelX(self) -> float:
        return self._scene_field("accel_x_m_s2")

    @pyqtSlot(float)
    def setAccelX(self, value: float) -> None:
        self._set_scene_field("accel_x_m_s2", float(value), self.environmentChanged)

    @pyqtProperty(float, notify=environmentChanged)
    def accelY(self) -> float:
        return self._scene_field("accel_y_m_s2")

    @pyqtSlot(float)
    def setAccelY(self, value: float) -> None:
        self._set_scene_field("accel_y_m_s2", float(value), self.environmentChanged)

    @pyqtProperty(float, notify=environmentChanged)
    def accelZ(self) -> float:
        return self._scene_field("accel_z_m_s2")

    @pyqtSlot(float)
    def setAccelZ(self, value: float) -> None:
        self._set_scene_field("accel_z_m_s2", float(value), self.environmentChanged)

    @pyqtProperty(float, notify=environmentChanged)
    def pitchAccel(self) -> float:
        return self._scene_field("pitch_accel_rad_s2")

    @pyqtSlot(float)
    def setPitchAccel(self, value: float) -> None:
        self._set_scene_field("pitch_accel_rad_s2", float(value), self.environmentChanged)

    @pyqtProperty(float, notify=environmentChanged)
    def rollAccel(self) -> float:
        return self._scene_field("roll_accel_rad_s2")

    @pyqtSlot(float)
    def setRollAccel(self, value: float) -> None:
        self._set_scene_field("roll_accel_rad_s2", float(value), self.environmentChanged)

    @pyqtProperty(float, notify=environmentChanged)
    def vesselRoll(self) -> float:
        return self._scene_field("vessel_roll_deg")

    @pyqtSlot(float)
    def setVesselRoll(self, value: float) -> None:
        self._set_scene_field("vessel_roll_deg", float(value), self.environmentChanged)

    @pyqtProperty(float, notify=environmentChanged)
    def vesselPitch(self) -> float:
        return self._scene_field("vessel_pitch_deg")

    @pyqtSlot(float)
    def setVesselPitch(self, value: float) -> None:
        self._set_scene_field("vessel_pitch_deg", float(value), self.environmentChanged)

    @pyqtProperty(float, notify=environmentChanged)
    def craneSlewingAngle(self) -> float:
        return self._scene_field("crane_slewing_angle_deg")

    @pyqtSlot(float)
    def setCraneSlewingAngle(self, value: float) -> None:
        self._set_scene_field("crane_slewing_angle_deg", float(value), self.environmentChanged)

    def _scene_field(self, name: str) -> float:
        state = self._model.get_active_hoist_state()
        return 0.0 if state is None else float(getattr(state.scene_state, name))

    def _set_scene_field(self, name: str, value: Any, notify: pyqtSignal) -> None:
        state = self._model.get_active_hoist_state()
        if state is None:
            return
        setattr(state.scene_state, name, value)
        notify.emit()
        if state.scene_state.hook_load_auto:
            self.recomputeAutoLoad()
        else:
            self._after_state_changed()
        self._model.mark_content_changed(scope="scene", key=f"field:{name}")

    # ------------------------------------------------------------------
    # Display options
    # ------------------------------------------------------------------

    @pyqtProperty("QVariantMap", notify=displayOptionsChanged)
    def displayOptions(self) -> dict:
        return self._display.to_dict()

    @pyqtSlot(str, "QVariant")
    def setDisplayOption(self, key: str, value: Any) -> None:
        options = self._display.to_dict()
        if key not in options:
            return
        options[key] = value
        self._display = SceneDisplay.from_dict(options)
        # Overlays are drawn from the loads already solved for, so this only redraws.
        self._publish_scene_frame()
        self.displayOptionsChanged.emit()

    @pyqtSlot(str)
    def toggleFreebody(self, target: str) -> None:
        current = self._display.selected_freebody
        self.setDisplayOption("selected_freebody", "none" if current == target else target)

    # ------------------------------------------------------------------
    # Contractual points
    # ------------------------------------------------------------------

    @pyqtProperty(list, notify=contractualChanged)
    def contractualLabels(self) -> list:
        return [row["label"] for row in self._contractual_rows]

    @pyqtProperty(int, notify=contractualChanged)
    def selectedContractualIdx(self) -> int:
        state = self._model.get_active_hoist_state()
        if state is None or state.selected_contractual_idx is None:
            return -1
        for position, row in enumerate(self._contractual_rows):
            if row["index"] == state.selected_contractual_idx:
                return position
        return -1

    @pyqtSlot(int)
    def selectContractual(self, position: int) -> None:
        self._end_governing_label()
        if position < 0 or position >= len(self._contractual_rows):
            self._set_contractual_selection(None)
            self.contractualChanged.emit()
            return
        cp_index = self._contractual_rows[position]["index"]
        self._set_contractual_selection(cp_index)
        self._focus_on_contractual_point(cp_index)
        state = self._model.get_active_hoist_state()
        if state is not None and state.scene_state.hook_load_auto:
            self._set_contractual_selection(None)
        self.contractualChanged.emit()

    def _set_contractual_selection(self, cp_index: Optional[int]) -> None:
        state = self._model.get_active_hoist_state()
        if state is not None:
            state.selected_contractual_idx = cp_index

    def _clear_contractual_selection(self) -> None:
        state = self._model.get_active_hoist_state()
        if state is not None and state.selected_contractual_idx is not None:
            state.selected_contractual_idx = None
            self.contractualChanged.emit()

    def _focus_on_contractual_point(self, cp_index: int) -> None:
        hoist = self._model.active_payload_hoist()
        points = self._hoist_state.contractual_points_for_hoist_mode(hoist)
        if not (0 <= cp_index < len(points)):
            return
        cp = points[cp_index]
        state = self._model.get_active_hoist_state()
        if state is None:
            return
        self._hook_load_t = float(cp.load_t)
        state.scene_state.hook_load_kN = self._hoist_state.payload_t_to_hook_force_kN(
            self._hook_load_t
        )
        self.loadChanged.emit()

        kin = self._kinematics.kinematics()
        hoist_id = self._model.selected_hoist_id
        if kin is not None and hoist_id:
            try:
                angle = kin.outreach_to_angle(float(cp.outreach_m), hoist_id)
            except (TypeError, ValueError, RuntimeError):
                angle = None
            if angle is not None:
                state.scene_state.boom_angle_deg = float(angle)
                self._outreach = float(cp.outreach_m)
                self.geometryChanged.emit()
        self._after_state_changed()

    def _rebuild_contractual_rows(self) -> None:
        hoist = self._hoist_state.selected_hoist()
        points = self._hoist_state.contractual_points_for_hoist_mode(hoist)
        indexed = sorted(
            enumerate(points),
            key=lambda pair: (float(pair[1].outreach_m), float(pair[1].load_t), pair[0]),
        )
        self._contractual_rows = [
            {"index": idx, "label": f"{cp.load_t:g} t @ {cp.outreach_m:.1f} m"}
            for idx, cp in indexed
        ]
        self.contractualChanged.emit()

    # ------------------------------------------------------------------
    # Governing case
    # ------------------------------------------------------------------

    @pyqtProperty(str, notify=governingCaseChanged)
    def governingCaseLabel(self) -> str:
        return self._governing_label

    @pyqtProperty(bool, notify=governingCaseChanged)
    def canRestoreInputs(self) -> bool:
        return self._snapshot is not None

    def apply_governing_case(self, case: GoverningCase, label: str) -> None:
        """Show ``case`` on the active hoist, keeping the inputs it replaces for Restore.

        The fields are written as they are, not through the setters: the setters clamp
        (angle, vessel motion) and recompute the auto load, so their order would change
        the case. Only the first apply takes the snapshot; a second keeps the original.
        """
        hoist_id = self._model.selected_hoist_id
        state = self._model.get_active_hoist_state()
        if state is None or not hoist_id:
            return
        if self._snapshot is None:
            self._snapshot = _InputsSnapshot(
                hoist_id=hoist_id,
                scene_state=dataclasses.replace(state.scene_state),
                hook_load_t=self._hook_load_t,
                contractual_idx=state.selected_contractual_idx,
                split_flags=self._model.split_flags(),
                case_tackle_m=0.0,
            )
        case_tackle = case.scene_fields.get("tackle_length_m", state.scene_state.tackle_length_m)
        self._snapshot = dataclasses.replace(self._snapshot, case_tackle_m=float(case_tackle))
        self._applying = True
        try:
            # The case reproduces the chart only under its mode's hook configuration.
            want_split = case.mode_name == "split"
            if state.split_mode_active != want_split:
                self._model.set_active_split_hoist(hoist_id if want_split else None)
            state.selected_contractual_idx = None
            state.scene_state = dataclasses.replace(state.scene_state, **case.scene_fields)
            self._hook_load_t = self._hoist_state.hook_force_kN_to_payload_t(
                state.scene_state.hook_load_kN
            )
            self._sync_outreach_from_angle(float(state.scene_state.boom_angle_deg))
            self._emit_inputs_changed()
            self._after_state_changed()
        finally:
            self._applying = False
        self._governing_label = str(label)
        self.governingCaseChanged.emit()

    @pyqtSlot()
    def restoreInputs(self) -> None:
        """Put back the inputs the first governing case replaced, as a user edit would."""
        snapshot = self._snapshot
        state = self._model.get_active_hoist_state()
        if snapshot is None or state is None or snapshot.hoist_id != self._model.selected_hoist_id:
            return
        self._model.restore_split_flags(snapshot.split_flags)
        state.scene_state = dataclasses.replace(snapshot.scene_state)
        state.selected_contractual_idx = snapshot.contractual_idx
        self._hook_load_t = snapshot.hook_load_t
        self._snapshot = None
        self._governing_label = ""
        self._sync_outreach_from_angle(float(state.scene_state.boom_angle_deg))
        self._rebuild_contractual_rows()
        self._emit_inputs_changed()
        self._after_state_changed()
        self.governingCaseChanged.emit()
        self._model.mark_content_changed(scope="scene")

    def _emit_inputs_changed(self) -> None:
        self.hookModeChanged.emit()
        self.contractualChanged.emit()
        self.angleBoundsChanged.emit()
        self.tackleBoundsChanged.emit()
        self.geometryChanged.emit()
        self.loadChanged.emit()
        self.environmentChanged.emit()

    def _end_governing_label(self) -> None:
        """A user edit: the Scene no longer shows the case (Restore stays available)."""
        if self._applying or not self._governing_label:
            return
        self._governing_label = ""
        self.governingCaseChanged.emit()

    def _drop_snapshot(self) -> None:
        """Another hoist or document: the saved inputs no longer apply."""
        if self._snapshot is None and not self._governing_label:
            return
        self._snapshot = None
        self._governing_label = ""
        self.tackleBoundsChanged.emit()
        self.governingCaseChanged.emit()

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    @pyqtProperty(QObject, constant=True)
    def ropeRowsModel(self) -> QObject:
        return self._rope_rows_model

    @pyqtProperty(QObject, constant=True)
    def connectionRowsModel(self) -> QObject:
        return self._connection_rows_model

    @pyqtProperty(QObject, constant=True)
    def reportModel(self) -> QObject:
        return self._report_model

    @pyqtSlot(str, int)
    def openLoadOverview(self, section: str, row: int) -> None:
        payloads = self._rope_payloads if section == "rope" else self._connection_payloads
        payload = payloads[row] if 0 <= row < len(payloads) else None
        if payload is None:
            return
        overview = self._presenter.build_load_contribution_overview(payload)
        if overview is not None:
            self.loadOverviewReady.emit(overview)

    @pyqtSlot()
    def requestEquilibriumCheck(self) -> None:
        self._publish_report("Equilibrium Check", self._presenter.build_drawn_load_sections)

    @pyqtSlot()
    def requestLoadSummary(self) -> None:
        self._publish_report("Load Summary", self._presenter.build_drawn_load_sections)

    def _publish_report(self, title: str, builder) -> None:
        inputs = self._scene_inputs()
        if not inputs.has_geometry:
            report = {"available": False, "message": "No active analysis is available."}
        else:
            try:
                report = builder(
                    document_dict=inputs.document_dict,
                    analysis_point=inputs.analysis_point,
                    node_positions=inputs.node_positions(),
                    conditions=inputs.conditions,
                )
            except (TypeError, ValueError, KeyError, RuntimeError) as exc:
                _LOG.warning("%s failed: %s", title, exc)
                report = {"available": False, "message": f"{title} failed: {exc}"}
        self._report_model.set_rows(report_to_rows(report))
        verdict = (
            "" if not report.get("available") else ("PASS" if report.get("passed") else "FAIL")
        )
        self.reportReady.emit(title, verdict)

    # ------------------------------------------------------------------
    # Refresh pipeline
    # ------------------------------------------------------------------

    def _on_document_changed(self, _doc) -> None:
        self._drop_snapshot()
        if not self._model.restoring:  # undo/redo keeps the hook load it restored
            self._initialized_load_hoist_id = None
        self.reload()

    def _on_hoist_selected(self, _hoist_id: str) -> None:
        self._drop_snapshot()
        self.reload()

    def _on_content_changed(self) -> None:
        # Every Scene setter that edits an input marks the content changed: this is
        # the user-edit path that ends the governing case shown.
        self._end_governing_label()
        if self._model.document is not None:
            self.reload()

    @pyqtSlot()
    def reload(self) -> None:
        doc = self._model.document
        self._kinematics.invalidate_kinematics()
        self._kinematics.recompute_angle_bounds(doc)

        state = self._model.get_active_hoist_state()
        selected_hoist_id = self._model.selected_hoist_id
        initialize_load = selected_hoist_id != self._initialized_load_hoist_id
        if initialize_load:
            self._hook_load_t = 0.0
            self._initialized_load_hoist_id = selected_hoist_id
        if state is not None:
            if initialize_load:
                state.scene_state.hook_load_kN = self._hoist_state.payload_t_to_hook_force_kN(
                    self._hook_load_t
                )
            self._sync_outreach_from_angle(float(state.scene_state.boom_angle_deg))

        self._rebuild_contractual_rows()
        self.hoistsChanged.emit()
        self.hookModeChanged.emit()
        self.angleBoundsChanged.emit()
        self.tackleBoundsChanged.emit()
        self.geometryChanged.emit()
        self.loadChanged.emit()
        self.environmentChanged.emit()
        self._after_state_changed()

    def _after_state_changed(self) -> None:
        """Re-solve the current state, then publish the scene frame it draws as."""
        pt = None
        rope_rows: list = []
        conn_rows: list = []
        if self._model.get_active_hoist_state() is not None:
            try:
                pt, rope_rows, conn_rows = self._calculator.compute_current_result_rows()
            except (TypeError, ValueError, RuntimeError) as exc:
                _LOG.warning("Scene analysis refresh failed: %s", exc)
                pt, rope_rows, conn_rows = None, [], []

        # Reaction overlays are only ever drawn from the point just solved for, so a
        # failed solve clears them rather than leaving the previous one on screen.
        self._analysis_point = pt
        self._announce_unavailable(pt)
        self._set_result_rows(rope_rows, conn_rows)
        self._publish_scene_frame()

    def _announce_unavailable(self, pt: Any) -> None:
        """Say why the Scene shows no analysis; once per distinct reason, not on every refresh."""
        reason = None if pt is not None else self._calculator.unavailable_reason()
        if reason != self._last_unavailable_text:
            self._last_unavailable_text = reason
            if reason:
                self.statusMessage.emit(reason)

    def _set_result_rows(self, rope_rows, connection_rows) -> None:
        self._rope_rows_model.set_rows(result_rows_to_dicts(rope_rows))
        self._connection_rows_model.set_rows(result_rows_to_dicts(connection_rows))
        self._rope_payloads = [
            result_row_payload(row) if not row.is_group_header else None for row in rope_rows
        ]
        self._connection_payloads = [
            result_row_payload(row) if not row.is_group_header else None for row in connection_rows
        ]
