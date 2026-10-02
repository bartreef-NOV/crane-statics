"""Boot the QML app headless, open a model, and save a PNG of the window.

Replicates the bootstrap in crane_statics.qml_app.app so the window can be grabbed
without entering the blocking app.exec() loop. Reports any QML warning it saw --
Main.qml is expected to load warning-free (tests/test_qml_shell.py enforces that).

Usage:
    python .claude/skills/run-app/scripts/screenshot.py [MODEL_JSON] [-o OUT.png]
                                                        [--workspace scene|chart|model]
                                                        [--size WxH] [--settle MS]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEventLoop, QObject, Qt, QTimer, QUrl  # noqa: E402
from PyQt6.QtGui import QGuiApplication  # noqa: E402
from PyQt6.QtQml import QQmlApplicationEngine  # noqa: E402

# Imported so sip wraps Main.qml's ApplicationWindow root as a QQuickWindow (which
# has grabWindow()) rather than falling back to plain QWindow.
from PyQt6.QtQuick import QQuickWindow  # noqa: E402,F401

from crane_statics.qml_app.app import (  # noqa: E402
    DESIGN_DIR,
    QML_DIR,
    configure_controls_style,
    configure_surface_format,
)
from crane_statics.qml_app.items.quick_scene_canvas import QuickSceneCanvasBacking  # noqa: E402
from crane_statics.qml_app.session import SessionState  # noqa: E402
from crane_statics.qml_app.viewmodels.app_vm import AppViewModel  # noqa: E402
from crane_statics.qml_app.viewmodels.chart_vm import ChartViewModel  # noqa: E402
from crane_statics.qml_app.viewmodels.model_vm import ModelViewModel  # noqa: E402
from crane_statics.qml_app.viewmodels.scene_vm import SceneViewModel  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_MODEL = REPO_ROOT / "examples" / "crane_input_22689.json"
WORKSPACE_INDEX = {"scene": 0, "chart": 1, "model": 2}


def _settle(ms: int) -> None:
    """Let the event loop run so bindings, layout and the scene graph catch up."""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", nargs="?", default=str(DEFAULT_MODEL))
    parser.add_argument("-o", "--out", default="app-screenshot.png")
    parser.add_argument("--workspace", choices=sorted(WORKSPACE_INDEX), default=None)
    parser.add_argument("--size", default="1600x1000", help="window size, e.g. 1600x1000")
    parser.add_argument("--settle", type=int, default=1200, help="ms to let the UI settle")
    args = parser.parse_args(argv)

    configure_controls_style()
    configure_surface_format()
    app = QGuiApplication(sys.argv[:1])
    hints = app.styleHints()
    if hints is not None:
        hints.setColorScheme(Qt.ColorScheme.Light)

    warnings: list[str] = []
    session = SessionState()
    engine = QQmlApplicationEngine(app)
    engine.warnings.connect(lambda errs: warnings.extend(e.toString() for e in errs))
    engine.addImportPath(str(QML_DIR))
    engine.addImportPath(str(DESIGN_DIR))

    app_vm = AppViewModel(session, engine)
    model_vm = ModelViewModel(session, engine)
    scene_vm = SceneViewModel(session, engine)
    chart_vm = ChartViewModel(session, engine)

    context = engine.rootContext()
    context.setContextProperty("appVm", app_vm)
    context.setContextProperty("modelVm", model_vm)
    context.setContextProperty("sceneVm", scene_vm)
    context.setContextProperty("chartVm", chart_vm)

    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    roots = engine.rootObjects()
    if not roots:
        print("FAILED: Main.qml did not load", file=sys.stderr)
        for line in warnings:
            print(f"  QML: {line}", file=sys.stderr)
        return 1

    window = roots[0]
    scene_vm.bindCanvas(QuickSceneCanvasBacking(engine))

    width, _, height = args.size.partition("x")
    window.setWidth(int(width))
    window.setHeight(int(height))
    window.show()

    model_path = Path(args.model)
    if not model_path.is_file():
        print(f"FAILED: model not found: {model_path}", file=sys.stderr)
        return 1
    app_vm.openPath(str(model_path))
    _settle(args.settle)

    if args.workspace is not None:
        # Main.qml gives the header TabBar objectName "workspaceTabs"; the workspace
        # StackLayout binds its currentIndex.
        tabs = window.findChild(QObject, "workspaceTabs")
        if tabs is None:
            print("FAILED: no 'workspaceTabs' object in Main.qml", file=sys.stderr)
            return 1
        tabs.setProperty("currentIndex", WORKSPACE_INDEX[args.workspace])
        _settle(args.settle)

    image = window.grabWindow()
    if image.isNull():
        print("FAILED: grabWindow() returned a null image", file=sys.stderr)
        return 1

    out = Path(args.out).resolve()
    if not image.save(str(out)):
        print(f"FAILED: could not write {out}", file=sys.stderr)
        return 1

    print(f"Saved {out} ({image.width()}x{image.height()})")
    print(f"Title: {app_vm.title}")
    print(f"Status: {app_vm.statusText}")
    if warnings:
        print(f"\n{len(warnings)} QML warning(s):", file=sys.stderr)
        for line in warnings:
            print(f"  {line}", file=sys.stderr)
        return 1

    # Tear down in the same order as app.py's cleanup handler.
    chart_vm.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
