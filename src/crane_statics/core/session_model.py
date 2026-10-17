"""Pure session state and events shared by application front ends."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from crane_statics.data import CraneDocument, Hoist, payload_hoist_ids

from .limit_components import validate_limit_component
from .limit_factory import DesignLimitFactory


@dataclass
class SceneState:
    """Current scene operating state for the active hoist."""

    boom_angle_deg: float = 0.0
    hook_load_kN: float = 0.0
    hook_load_auto: bool = False
    tackle_length_m: float = 50.0
    offlead_deg: float = 0.0
    sidelead_deg: float = 0.0
    wind_speed_m_s: float = 0.0
    wind_direction: str = "+X"
    accel_x_m_s2: float = 0.0
    accel_y_m_s2: float = 0.0
    accel_z_m_s2: float = 0.0
    pitch_accel_rad_s2: float = 0.0
    roll_accel_rad_s2: float = 0.0
    vessel_roll_deg: float = 0.0
    vessel_pitch_deg: float = 0.0
    crane_slewing_angle_deg: float = 0.0


@dataclass
class HoistState:
    """Runtime state for a single hoist."""

    hoist_id: str
    scene_state: SceneState = field(default_factory=SceneState)
    split_mode_active: bool = False
    chart_mode: str = "normal"
    selected_contractual_idx: Optional[int] = None
    chart_sweep_data: Optional[dict[str, Any]] = None
    chart_curve_sweep_data: Optional[dict[str, Any]] = None
    contractual_sweep_data: Optional[dict[str, Any]] = None


@dataclass
class DesignLimit:
    """A design limit for rope or connection component."""

    id: str
    kind: str
    entity_id: str
    component: str
    min_kN: Optional[float] = None
    max_kN: Optional[float] = None
    enabled: bool = False
    max_enabled: bool = True
    min_enabled: bool = False
    pressure_D: Optional[float] = None

    def __post_init__(self) -> None:
        self.component = validate_limit_component(self.component)


SessionListener = Callable[..., None]


class SessionModel:
    """Pure mutable session state with named change-event subscriptions."""

    def __init__(self) -> None:
        self.document_path: Optional[Path] = None
        self.document: Optional[CraneDocument] = None
        self.is_new_document = False
        self.dirty = False
        self.selected_hoist_id: Optional[str] = None
        self.selected_editor_hoist_id: Optional[str] = None
        self.hoist_states: dict[str, HoistState] = {}
        self.design_limits: list[DesignLimit] = []
        self.design_limits_by_id: dict[str, DesignLimit] = {}
        self.notification_history: list[str] = []
        self.max_notifications = 100
        self._listeners: dict[str, list[SessionListener]] = defaultdict(list)

    def subscribe(self, event: str, listener: SessionListener) -> Callable[[], None]:
        """Register a listener and return an unsubscribe callback."""
        self._listeners[event].append(listener)

        def unsubscribe() -> None:
            listeners = self._listeners.get(event, [])
            if listener in listeners:
                listeners.remove(listener)

        return unsubscribe

    def _emit(self, event: str, *args: Any) -> None:
        for listener in tuple(self._listeners.get(event, ())):
            listener(*args)

    def set_document(self, doc: Optional[CraneDocument], path: Optional[Path] = None) -> None:
        self.document = doc
        self.document_path = path
        self.dirty = False
        self.is_new_document = path is None
        self.hoist_states.clear()
        self.selected_hoist_id = None
        self.selected_editor_hoist_id = None
        self.design_limits.clear()
        self.design_limits_by_id.clear()

        if doc is not None:
            env = doc.environment
            vessel_motion = env.vessel_motion
            for hoist in doc.hoists:
                self.hoist_states[hoist.id] = HoistState(
                    hoist_id=hoist.id,
                    scene_state=SceneState(
                        tackle_length_m=0.0,
                        offlead_deg=float(hoist.offlead_deg),
                        sidelead_deg=float(getattr(hoist, "sidelead_deg", hoist.offlead_deg)),
                        wind_speed_m_s=float(env.max_wind_speed_m_s),
                        wind_direction="+X",
                        accel_x_m_s2=float(vessel_motion.accel_x_m_s2),
                        accel_y_m_s2=float(getattr(vessel_motion, "accel_y_m_s2", 0.0)),
                        accel_z_m_s2=float(vessel_motion.accel_z_m_s2),
                        pitch_accel_rad_s2=float(vessel_motion.pitch_angular_accel_rad_s2),
                        roll_accel_rad_s2=float(
                            getattr(vessel_motion, "roll_angular_accel_rad_s2", 0.0)
                        ),
                    ),
                )
            visible_payload_hoists = payload_hoist_ids(doc)
            if visible_payload_hoists:
                self.selected_hoist_id = visible_payload_hoists[0]
            if doc.hoists:
                self.selected_editor_hoist_id = doc.hoists[0].id
            limits = DesignLimitFactory.create_for_document(doc)
            self.design_limits = limits
            self.design_limits_by_id = DesignLimitFactory.index_by_id(limits)

        self._emit("document_changed", self.document)

    def payload_hoist_ids(self) -> list[str]:
        return [] if self.document is None else list(payload_hoist_ids(self.document))

    def select_payload_hoist(self, hoist_id: str) -> None:
        if hoist_id not in self.payload_hoist_ids() or hoist_id not in self.hoist_states:
            return
        self.selected_hoist_id = hoist_id
        self._emit("hoist_selected", hoist_id)

    def editor_hoist_ids(self) -> list[str]:
        return [] if self.document is None else [hoist.id for hoist in self.document.hoists]

    def select_editor_hoist(self, hoist_id: str) -> None:
        if hoist_id in self.editor_hoist_ids():
            self.selected_editor_hoist_id = hoist_id

    def editor_hoist_by_id(self, hoist_id: Optional[str]) -> Optional[Hoist]:
        if self.document is None or not hoist_id:
            return None
        return next((hoist for hoist in self.document.hoists if hoist.id == hoist_id), None)

    def payload_hoist_by_id(self, hoist_id: Optional[str]) -> Optional[Hoist]:
        return self.editor_hoist_by_id(hoist_id) if hoist_id in self.payload_hoist_ids() else None

    def active_payload_hoist(self) -> Optional[Hoist]:
        return self.payload_hoist_by_id(self.selected_hoist_id)

    def selected_editor_hoist(self) -> Optional[Hoist]:
        return self.editor_hoist_by_id(self.selected_editor_hoist_id)

    def is_splitable_hoist(self, hoist_id: Optional[str]) -> bool:
        hoist = self.payload_hoist_by_id(hoist_id)
        return bool(hoist is not None and getattr(hoist, "splitable_block", False))

    def contractual_points_for_mode(self, hoist_id: Optional[str], mode: str = "normal") -> list:
        hoist = self.payload_hoist_by_id(hoist_id)
        if hoist is None:
            return []
        if str(mode).lower() == "split" and self.is_splitable_hoist(hoist_id):
            split_points = getattr(hoist, "split_contractual_points", None)
            if isinstance(split_points, list) and split_points:
                return split_points
        return hoist.contractual_points

    def chart_mode_for_hoist(self, hoist_id: Optional[str]) -> str:
        state = self.hoist_states.get(hoist_id) if hoist_id else None
        return (
            "split"
            if state is not None
            and state.chart_mode == "split"
            and self.is_splitable_hoist(hoist_id)
            else "normal"
        )

    def set_chart_mode(self, hoist_id: Optional[str], mode: str) -> str:
        normalized = (
            "split"
            if str(mode).lower() == "split" and self.is_splitable_hoist(hoist_id)
            else "normal"
        )
        state = self.hoist_states.get(hoist_id) if hoist_id else None
        if state is not None:
            state.chart_mode = normalized
        return normalized

    def hook_mode_for_hoist(self, hoist_id: Optional[str]) -> str:
        state = self.hoist_states.get(hoist_id) if hoist_id else None
        return "split" if state is not None and state.split_mode_active else "normal"

    def set_hook_mode(self, hoist_id: Optional[str], mode: str) -> str:
        active_id = self.set_active_split_hoist(hoist_id if str(mode).lower() == "split" else None)
        for state in self.hoist_states.values():
            state.chart_mode = "split" if state.split_mode_active else "normal"
        return "split" if active_id is not None else "normal"

    def get_active_hoist_state(self) -> Optional[HoistState]:
        return self.hoist_states.get(self.selected_hoist_id) if self.selected_hoist_id else None

    def set_dirty(self, dirty: bool) -> None:
        if self.dirty != dirty:
            self.dirty = dirty
            self._emit("dirty_changed", dirty)

    def mark_content_changed(self) -> None:
        self.set_dirty(True)
        self._emit("content_changed")

    def update_design_limits(self, limits: list[DesignLimit]) -> None:
        self.design_limits = limits
        self.design_limits_by_id = {limit.id: limit for limit in limits}
        self.mark_content_changed()
        self._emit("design_limits_changed", limits)

    def add_notification(self, message: str, level: str = "info") -> None:
        self.notification_history.append(f"[{level.upper()}] {message}")
        if len(self.notification_history) > self.max_notifications:
            self.notification_history.pop(0)
        self._emit("notification", message, level)

    def clear_notifications(self) -> None:
        self.notification_history.clear()

    def set_active_split_hoist(self, hoist_id: Optional[str]) -> Optional[str]:
        if hoist_id is not None:
            state = self.hoist_states.get(hoist_id)
            if state is None or self.document is None or not self.is_splitable_hoist(hoist_id):
                return next(
                    (hid for hid, item in self.hoist_states.items() if item.split_mode_active), None
                )
        for candidate_id, state in self.hoist_states.items():
            state.split_mode_active = hoist_id is not None and candidate_id == hoist_id
        return hoist_id
