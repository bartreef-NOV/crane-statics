"""Canvas-side view of one published scene frame.

Everything the scene shows is decided by :func:`crane_statics.core.scene_build.
build_scene_frame`, which :class:`SceneViewModel` calls once per state change. A
canvas adopts the frame it is handed and answers the two view questions QML and
the drag gestures ask of it: where a scene point lies in the world, and where the
boom heel is.
"""

from __future__ import annotations

from typing import Optional, Tuple

from PyQt6.QtCore import QObject

from crane_statics.core.scene_frame import SceneFrame, SceneFrameBuilder, SceneMapping


class CraneSceneRenderer(QObject):
    """One canvas's view of the current :class:`SceneFrame`.

    Satisfies :class:`~crane_statics.qml_app.scene.scene_drag.SceneCanvasContract`
    through three public properties:
    - scene_to_world: callable for coordinate transformation
    - map_scale: canvas-to-world scale factor
    - heel_world: heel point position in world coordinates
    """

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        # Revision 0: nothing published yet, so QML has nothing to draw.
        self._scene_frame = SceneFrameBuilder().build(fit_rect=(0.0, 0.0, 0.0, 0.0), revision=0)
        self._mapping: Optional[SceneMapping] = None
        self._heel_world: Optional[Tuple[float, float]] = None

    def show(self, frame: SceneFrame) -> None:
        """Adopt the frame this canvas draws, and the transform it was built with."""
        self._scene_frame = frame
        self._mapping = frame.mapping
        self._heel_world = frame.heel_world

    @property
    def scene_frame(self) -> SceneFrame:
        return self._scene_frame

    @property
    def scene_to_world(self):
        """Map scene (canvas) coordinates to world coordinates.

        Returns a callable that takes (scene_x, scene_y) and returns (world_x, world_z).
        """
        return self._scene_to_world

    @property
    def map_scale(self) -> float:
        """Canvas-to-world scale factor (pixels per world unit)."""
        return 1.0 if self._mapping is None else self._mapping.scale

    @property
    def heel_world(self) -> Optional[Tuple[float, float]]:
        """Position of the heel point in world coordinates, or None if undefined."""
        return self._heel_world

    def _scene_to_world(self, sx: float, sy: float) -> Tuple[float, float]:
        return (0.0, 0.0) if self._mapping is None else self._mapping.to_world(sx, sy)
