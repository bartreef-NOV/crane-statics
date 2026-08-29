"""The scene's pointer gesture: press, move, release.

One drag gesture is a value. It reads geometry from the canvas it was started on
and returns the edit it implies; it never writes scene state itself. That keeps
the parts that can actually be wrong -- clamping to the angle and tackle limits,
alt-snap rounding, the heel-relative ``atan2`` and the pixels-to-metres tackle
delta -- testable against a stub canvas and plain numbers, with no view model,
no session and no Qt.

The hit-test that decides *which* quantity a press grabs lives here too, since
it reads the same ``hit_targets`` the gesture is named after.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence, Tuple

BOOM_ANGLE = "boom_angle"
OUTREACH = "outreach"
TACKLE_LENGTH = "tackle_length"

#: The quantities the scene can be dragged by.
DRAG_KINDS = (BOOM_ANGLE, OUTREACH, TACKLE_LENGTH)

#: Holding Alt rounds every dragged quantity to this step (degrees or metres).
SNAP_STEP = 0.5


class SceneCanvasContract(Protocol):
    """What a drag gesture needs to know about the canvas it happens on.

    Three read-only properties: enough to turn pointer pixels into world metres
    and to find the pivot an angle is measured from. Any object providing them
    can be dragged, which is what lets the gesture be tested with a stub.
    """

    @property
    def scene_to_world(self) -> Callable[[float, float], Tuple[float, float]]:
        """Map scene (canvas) coordinates to world coordinates.

        Returns:
            Callable that takes (scene_x, scene_y) and returns (world_x, world_z)
        """
        ...

    @property
    def map_scale(self) -> float:
        """Canvas-to-world scale factor (pixels per world unit)."""
        ...

    @property
    def heel_world(self) -> Optional[Tuple[float, float]]:
        """Position of the heel point in world coordinates, or None if undefined.

        Returns:
            Tuple of (world_x, world_z) or None
        """
        ...


@dataclass(frozen=True)
class DragLimits:
    """The range each dragged quantity is clamped to.

    Outreach is absent on purpose: an outreach drag is clamped by reachability,
    which only the kinematics can answer, so the caller resolves it.
    """

    angle_deg: Tuple[float, float] = (-180.0, 180.0)
    tackle_m: Tuple[float, float] = (0.0, 500.0)


@dataclass(frozen=True)
class DragEdit:
    """What one pointer move asks the scene to become.

    ``field`` names the driven quantity -- ``"angle_deg"``, ``"outreach_m"`` or
    ``"tackle_m"`` -- so a caller dispatches on one value instead of re-deciding
    what kind of gesture is in progress.
    """

    field: str
    value: float


@dataclass(frozen=True)
class SceneDrag:
    """One drag gesture in progress.

    Build with :meth:`begin` on press, ask :meth:`edit` on every move, and drop
    it on release.
    """

    kind: str
    start_scene_y: float = 0.0
    start_tackle_m: float = 0.0

    @classmethod
    def begin(cls, kind: str, scene_y: float, tackle_m: float) -> Optional["SceneDrag"]:
        """Start a gesture, or ``None`` when ``kind`` names nothing draggable."""
        if kind not in DRAG_KINDS:
            return None
        return cls(kind=kind, start_scene_y=float(scene_y), start_tackle_m=float(tackle_m))

    def edit(
        self,
        canvas: SceneCanvasContract,
        scene_x: float,
        scene_y: float,
        *,
        limits: DragLimits = DragLimits(),
        alt_snap: bool = False,
    ) -> Optional[DragEdit]:
        """The scene quantity this pointer position asks for.

        Returns ``None`` when the position carries no information -- an angle
        drag with no heel to pivot about, or one landing exactly on it.
        """
        if self.kind == OUTREACH:
            world_x, _world_z = canvas.scene_to_world(float(scene_x), float(scene_y))
            return DragEdit("outreach_m", _snap(world_x, alt_snap))

        if self.kind == TACKLE_LENGTH:
            # Dragging down pays out rope, so scene-y and tackle length agree in sign.
            delta_m = (float(scene_y) - self.start_scene_y) / max(1e-9, canvas.map_scale)
            low, high = limits.tackle_m
            clamped = max(low, min(high, self.start_tackle_m + delta_m))
            return DragEdit("tackle_m", _snap(clamped, alt_snap))

        heel = canvas.heel_world
        if heel is None:
            return None
        world_x, world_z = canvas.scene_to_world(float(scene_x), float(scene_y))
        dx = world_x - heel[0]
        dz = world_z - heel[1]
        if abs(dx) < 1e-9 and abs(dz) < 1e-9:
            return None
        angle = _snap(math.degrees(math.atan2(dz, dx)), alt_snap)
        low, high = limits.angle_deg
        return DragEdit("angle_deg", max(low, min(high, angle)))

    @staticmethod
    def target_at(
        scene_x: float,
        scene_y: float,
        hit_targets: Sequence[Mapping[str, Any]],
    ) -> str:
        """Which quantity a press at this point would grab, or ``""`` for none.

        The first matching target wins, so the frame's ordering decides which
        quantity gets the gesture where two overlap.
        """
        for target in hit_targets:
            kind = str(target.get("kind", ""))
            radius = float(target.get("radius", 0.0))
            start_x = float(target.get("start_x", 0.0))
            start_y = float(target.get("start_y", 0.0))

            if kind == BOOM_ANGLE:
                distance = _distance_to_segment(
                    scene_x,
                    scene_y,
                    start_x,
                    start_y,
                    float(target.get("end_x", 0.0)),
                    float(target.get("end_y", 0.0)),
                )
                if distance <= radius:
                    return kind
            elif kind == OUTREACH:
                # The outreach guide drops from its anchor, so only below counts.
                if abs(scene_x - start_x) <= radius and scene_y >= start_y:
                    return kind
            elif kind == TACKLE_LENGTH:
                # The hook-height guide runs right from its anchor.
                if abs(scene_y - start_y) <= radius and scene_x >= start_x:
                    return kind

        return ""


def _snap(value: float, alt_snap: bool) -> float:
    """Round to :data:`SNAP_STEP` while Alt is held, else pass through."""
    return round(value / SNAP_STEP) * SNAP_STEP if alt_snap else value


def _distance_to_segment(
    scene_x: float,
    scene_y: float,
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
) -> float:
    """Closest distance from a point to a line segment, endpoints included."""
    delta_x = end_x - start_x
    delta_y = end_y - start_y
    length_squared = delta_x * delta_x + delta_y * delta_y

    if length_squared <= 1e-9:
        return math.hypot(scene_x - start_x, scene_y - start_y)

    ratio = max(
        0.0,
        min(
            1.0,
            ((scene_x - start_x) * delta_x + (scene_y - start_y) * delta_y) / length_squared,
        ),
    )
    return math.hypot(
        scene_x - (start_x + ratio * delta_x),
        scene_y - (start_y + ratio * delta_y),
    )
