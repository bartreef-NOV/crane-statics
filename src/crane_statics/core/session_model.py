"""Pure session state and events shared by application front ends."""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from crane_statics.data import CraneDocument, Hoist, payload_hoist_ids

from .edit_history import EditHistory
from .limit_components import validate_limit_component
from .limit_factory import DesignLimitFactory
from .vessel_envelope import vessel_limit


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
    required_factor: float = 1.0
    """Margin a rule requires on ``max_kN`` (the capacity): demand may use ``1 / factor`` of it."""

    def __post_init__(self) -> None:
        self.component = validate_limit_component(self.component)

    @property
    def allowable_kN(self) -> Optional[float]:
        """The value demand is checked against: ``max_kN`` reduced by the required factor."""
        return None if self.max_kN is None else float(self.max_kN) / self.required_factor


SessionListener = Callable[..., None]


@dataclass(frozen=True, eq=False)
class HoistSnapshot:
    """The restorable part of a hoist's runtime state (sweep caches are not kept)."""

    scene_state: SceneState
    split_mode_active: bool
    chart_mode: str
    selected_contractual_idx: Optional[int]


@dataclass(frozen=True, eq=False)
class SessionSnapshot:
    """Everything an undo step restores. Treated as immutable once taken."""

    document: Optional[CraneDocument]
    design_limits: tuple[DesignLimit, ...]
    hoists: dict[str, HoistSnapshot]
    selected_hoist_id: Optional[str]
    selected_editor_hoist_id: Optional[str]
    extras: dict[str, Any]


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
        self.history: EditHistory[SessionSnapshot] = EditHistory()
        self._restoring = False
        self._history_extras: dict[str, tuple[Callable[[], Any], Callable[[Any], None]]] = {}

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
                        sidelead_deg=float(hoist.sidelead_deg),
                        wind_speed_m_s=float(env.max_wind_speed_m_s),
                        wind_direction="+X",
                        # The Model's vessel motion values are ± limits; the Scene starts at +limit.
                        vessel_roll_deg=vessel_limit(vessel_motion, "roll_deg"),
                        vessel_pitch_deg=vessel_limit(vessel_motion, "pitch_deg"),
                        crane_slewing_angle_deg=0.0,
                        accel_x_m_s2=vessel_limit(vessel_motion, "accel_x_m_s2"),
                        accel_y_m_s2=vessel_limit(vessel_motion, "accel_y_m_s2"),
                        accel_z_m_s2=vessel_limit(vessel_motion, "accel_z_m_s2"),
                        pitch_accel_rad_s2=vessel_limit(
                            vessel_motion, "pitch_angular_accel_rad_s2"
                        ),
                        roll_accel_rad_s2=vessel_limit(vessel_motion, "roll_angular_accel_rad_s2"),
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
        # After the listeners ran, so view-model state captured as extras is initialised.
        self._reset_history()

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

    def mark_content_changed(self, *, scope: str = "document", key: Optional[str] = None) -> None:
        """Record an edit that has just been applied.

        ``scope="scene"`` is for edits that only touch Scene inputs: the document and limits
        of the previous undo state are reused instead of copied. Edits with the same ``key``
        in quick succession (a slider drag) merge into one undo step.
        """
        if self._restoring:
            return
        self.set_dirty(True)
        if self.document is not None:
            previous = self.history.current if scope == "scene" else None
            self.history.record(self._capture(previous), key)
            self._emit("history_changed")
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

    def split_flags(self) -> dict[str, bool]:
        """Every hoist's Scene split flag (not its Load Chart mode)."""
        return {hid: state.split_mode_active for hid, state in self.hoist_states.items()}

    def restore_split_flags(self, flags: dict[str, bool]) -> None:
        """Put back flags taken by ``split_flags``; each hoist's chart mode is left alone."""
        for hid, split in flags.items():
            state = self.hoist_states.get(hid)
            if state is not None:
                state.split_mode_active = split

    # ------------------------------------------------------------------
    # Undo / redo
    # ------------------------------------------------------------------

    def register_history_extra(
        self, name: str, capture: Callable[[], Any], restore: Callable[[Any], None]
    ) -> None:
        """Add view-model state to snapshots (``restore`` runs before listeners reload)."""
        self._history_extras[name] = (capture, restore)

    def _capture(self, reuse: Optional[SessionSnapshot]) -> SessionSnapshot:
        if reuse is not None:
            document, limits = reuse.document, reuse.design_limits
        else:
            document = None if self.document is None else self.document.model_copy(deep=True)
            limits = tuple(dataclasses.replace(limit) for limit in self.design_limits)
        return SessionSnapshot(
            document=document,
            design_limits=limits,
            hoists={
                hid: HoistSnapshot(
                    scene_state=dataclasses.replace(state.scene_state),
                    split_mode_active=state.split_mode_active,
                    chart_mode=state.chart_mode,
                    selected_contractual_idx=state.selected_contractual_idx,
                )
                for hid, state in self.hoist_states.items()
            },
            selected_hoist_id=self.selected_hoist_id,
            selected_editor_hoist_id=self.selected_editor_hoist_id,
            extras={name: capture() for name, (capture, _restore) in self._history_extras.items()},
        )

    def _reset_history(self) -> None:
        self.history.reset(None if self.document is None else self._capture(None))
        self._emit("history_changed")

    @property
    def restoring(self) -> bool:
        """True while undo/redo is putting a snapshot back (and listeners are reloading)."""
        return self._restoring

    @property
    def can_undo(self) -> bool:
        return self.history.can_undo

    @property
    def can_redo(self) -> bool:
        return self.history.can_redo

    def mark_saved(self) -> None:
        """The document was written to disk: the current state is clean."""
        self.history.mark_saved()
        self.set_dirty(False)

    def undo(self) -> bool:
        return self._travel(self.history.undo)

    def redo(self) -> bool:
        return self._travel(self.history.redo)

    def _travel(self, step: Callable[[], Optional[SessionSnapshot]]) -> bool:
        snapshot = step()
        if snapshot is None:
            return False
        self._restore(snapshot)
        return True

    def _restore(self, snapshot: SessionSnapshot) -> None:
        self._restoring = True
        try:
            document = snapshot.document
            self.document = None if document is None else document.model_copy(deep=True)
            limits = [dataclasses.replace(limit) for limit in snapshot.design_limits]
            self.design_limits[:] = limits
            self.design_limits_by_id.clear()
            self.design_limits_by_id.update({limit.id: limit for limit in limits})
            for hid in [hid for hid in self.hoist_states if hid not in snapshot.hoists]:
                del self.hoist_states[hid]
            for hid, saved in snapshot.hoists.items():
                self.hoist_states[hid] = HoistState(
                    hoist_id=hid,
                    scene_state=dataclasses.replace(saved.scene_state),
                    split_mode_active=saved.split_mode_active,
                    chart_mode=saved.chart_mode,
                    selected_contractual_idx=saved.selected_contractual_idx,
                )
            if self.selected_hoist_id not in self.payload_hoist_ids():
                self.selected_hoist_id = snapshot.selected_hoist_id
            if self.selected_editor_hoist_id not in self.editor_hoist_ids():
                self.selected_editor_hoist_id = snapshot.selected_editor_hoist_id
            for name, (_capture, restore) in self._history_extras.items():
                if name in snapshot.extras:
                    restore(snapshot.extras[name])
            self._emit("document_changed", self.document)
        finally:
            self._restoring = False
        self.set_dirty(not self.history.is_at_saved)
        self._emit("history_changed")
