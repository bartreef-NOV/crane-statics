"""QML application bootstrap."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QEvent, Qt, QTimer, QUrl
from PyQt6.QtGui import QGuiApplication, QSurfaceFormat
from PyQt6.QtQml import QQmlApplicationEngine

from crane_statics.qml_app.session import SessionState

from .items.quick_scene_canvas import QuickSceneCanvasBacking
from .viewmodels.app_vm import AppViewModel
from .viewmodels.chart_vm import ChartViewModel
from .viewmodels.model_vm import ModelViewModel
from .viewmodels.scene_vm import SceneViewModel

_LOG = logging.getLogger(__name__)

QML_DIR = Path(__file__).parent / "qml"
DESIGN_DIR = Path(__file__).parent / "design"
QML_MODULE = "CraneStatics"


def configure_controls_style() -> None:
    """Use the working desktop Qt Quick Controls style before controls load."""
    os.environ["QT_QUICK_CONTROLS_STYLE"] = "Fusion"
    os.environ.setdefault("QT_QUICK_CONTROLS_FALLBACK_STYLE", "Basic")


def configure_surface_format() -> None:
    """Request multisample antialiasing for Qt Quick geometry and shape edges."""
    surface_format = QSurfaceFormat.defaultFormat()
    surface_format.setSamples(8)
    QSurfaceFormat.setDefaultFormat(surface_format)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    args = list(sys.argv if argv is None else argv)

    configure_controls_style()
    configure_surface_format()
    app = QGuiApplication(args)
    # The app has a single, light-only appearance; force it regardless of the
    # OS color scheme so the native style's chrome doesn't follow a dark OS theme.
    hints = app.styleHints()
    if hints is not None:
        hints.setColorScheme(Qt.ColorScheme.Light)

    session = SessionState()
    engine = QQmlApplicationEngine(app)
    app_vm = AppViewModel(session, engine)
    model_vm = ModelViewModel(session, engine)
    scene_vm = SceneViewModel(session, engine)
    chart_vm = ChartViewModel(session, engine)

    def cleanup() -> None:
        chart_vm.shutdown()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    app.aboutToQuit.connect(cleanup)
    engine.addImportPath(str(QML_DIR))
    engine.addImportPath(str(DESIGN_DIR))
    context = engine.rootContext()
    context.setContextProperty("appVm", app_vm)
    context.setContextProperty("modelVm", model_vm)
    context.setContextProperty("sceneVm", scene_vm)
    context.setContextProperty("chartVm", chart_vm)

    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    if not engine.rootObjects():
        _LOG.error("Failed to load Main.qml")
        return 1

    # Create and bind the scene canvas backing object (provides renderer to view model)
    canvas_backing = QuickSceneCanvasBacking(engine)
    scene_vm.bindCanvas(canvas_backing)

    if len(args) > 1:
        QTimer.singleShot(0, lambda: app_vm.openPath(args[1]))

    return int(app.exec())
