"""Python backing object for QuickSceneCanvas QML component."""

from PyQt6.QtCore import QObject, pyqtSignal

from crane_statics.qml_app.scene.scene_renderer import CraneSceneRenderer


class QuickSceneCanvasBacking(QObject):
    """Provides renderer and signal infrastructure for QML-based scene canvas."""

    boomAngleChanged = pyqtSignal(float)
    tackleLengthChanged = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.renderer = CraneSceneRenderer(self)
        self._scene_vm = None

    def setSceneViewModel(self, scene_vm):
        """Register with the view model."""
        self._scene_vm = scene_vm
