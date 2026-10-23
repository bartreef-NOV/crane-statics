---
name: qml-ui-development
description: Rules and patterns for building the Crane Statics Qt Quick/QML front end — native Qt Quick Controls (Fusion) styling with SystemPalette colors, the view-model/context-property bridge, QAbstractItemModel table models, the QQuickItem scene canvas, and keeping the Qt event loop unblocked. Use when editing anything under src/crane_statics/qml_app/ or any .qml file, adding a view model property or signal, wiring a new QML view, or debugging a frozen UI, a QML warning, or a binding loop.
---

# Crane Statics QML UI Development

This app is **Qt Quick / QML only**. There are no QWidgets anywhere in `src/` — no
`QWidget`, no `QVBoxLayout`, no `setStyleSheet`, no QSS. Advice written for PyQt6
Widgets does not apply; QML has its own layout, styling and model systems. The entry
point is `QGuiApplication` (not `QApplication`) in
[qml_app/app.py](../../../src/crane_statics/qml_app/app.py).

## Layout of the front end

| Path | Role |
|---|---|
| `qml_app/app.py` | Bootstrap: controls style, surface format, view models, context properties, loads `Main.qml` |
| `qml_app/session.py` | `SessionState` — the session's change events as Qt signals, plus the `SessionModel` the view models read and write |
| `qml_app/viewmodels/` | `app_vm`, `model_vm`, `scene_vm`, `chart_vm` — `QObject`s exposed to QML |
| `qml_app/models/` | `QAbstractItemModel` subclasses for tables and lists |
| `qml_app/adapters/scene_adapter.py` | `SceneStateAdapter` — a `SceneFrame` becomes plain dicts for QML |
| `qml_app/items/quick_scene_canvas.py` | `QQuickItem` backing for the scene canvas |
| `qml_app/scene/` | `scene_renderer.py` (shows the published frame) and `scene_drag.py` (the pointer gesture) |
| `qml_app/qml/` | Views (`Main.qml`, the three workspaces, tables, dialogs, `scene/`) |

## Iron laws

**Use plain, native `QtQuick.Controls` elements — don't hand-paint chrome.**
There used to be a `qml/components/` wrapper library (`Button`, `TextField`,
`ComboBox`, `Dialog`, `StyledCheckBox`, etc.) that repainted every control's
`background:`/`contentItem:`/`palette.*` by hand. It has been deleted. Use the
bare native control (`Button`, `TextField`, `ComboBox`, `CheckBox`,
`RadioButton`, `GroupBox`, `TabButton`, `Dialog`, …) and let the app's Controls
style (Fusion, see below) render it. Do not reintroduce a `background:`/
`contentItem:` override or a `palette.*` color assignment on a native control
unless there is no other way to express something the style genuinely can't —
that's exactly the pattern that made the UI look custom-skinned before.

**No design-system module.** There are no `Theme`/`Metrics`/`Typography`
singletons (the `BF.DesignSystem` module was deleted). Use literal spacing/margins
(`spacing: 8`), let controls take their implicit Fusion size and the default app
font, and don't set `font.family`/`font.pixelSize` unless it carries meaning.

**Colors come from `SystemPalette`.** Custom-painted surfaces (`QuickChartPlot.qml`,
`scene/QuickSceneCanvas.qml`, the utilization bar in `ResultRowDelegate.qml`) use a
local `SystemPalette { id: pal }`; only the pass/fail/pending status colors are
inline constants.

**Hand-rolled tables use `SystemPalette`.** `DataTable.qml`,
`ResultsTable.qml`, and
`ResultRowDelegate.qml` are bespoke `TableView`+`Rectangle`-delegate grids (no
native "data grid" control exists to fall back to). They source their zebra-
stripe/text/border/selection colors from a local `SystemPalette { id:
sysPalette }` (`sysPalette.base`/`alternateBase`/`text`/`mid`/`highlight`/
`highlightedText`) so they stay visually consistent with the native controls
around them automatically.

**Never block the Qt event loop.** Solver sweeps in `calculation/` can be slow. Long
work goes off the GUI thread, or is chunked, or is cached — `calculation/cache.py`
and `core/sweep.py` exist for this. A synchronous solve inside a `pyqtProperty`
getter freezes the window, because QML re-reads properties during binding
evaluation.

**Never compute in a property getter.** QML calls getters far more often than you
expect. Compute on change, store the result, emit the notify signal. `title` in
`app_vm.py` is the acceptable ceiling: string assembly over already-resolved state.

**QML must not reach into the domain.** QML talks to the four context properties
(`appVm`, `modelVm`, `sceneVm`, `chartVm`) and to the exposed item models — never to
`core/`, `data/` or `calculation/` types directly. Formatting for display belongs in
`presentation/formatters.py`, not in a QML expression.

**Use anchors, `Layout`, and `Item` sizing** — not absolute `x`/`y`. Qt Quick is
DPI-scaled; fixed coordinates break on scaled displays.

## The view-model bridge

Every view model is a `QObject` parented to the `QQmlApplicationEngine` so QML
objects are torn down before their backing Python objects. The pattern, from
`app_vm.py`:

```python
class AppViewModel(QObject):
    titleChanged = pyqtSignal()            # one notify signal per property
    notification = pyqtSignal(str, str)    # typed payload signals for events

    @pyqtProperty(str, notify=titleChanged)
    def title(self) -> str:
        ...

    @pyqtSlot(str)
    def openPath(self, path: str) -> None:
        ...
```

Rules when adding to a view model:

- **camelCase** for anything QML touches — properties, signals, slots. Python-side
  internals stay `snake_case`. `payload_hoist_ids` on `SessionModel` is domain state a
  view model reads through `self._model`, not a QML surface; do not confuse the two
  conventions.
- Every `pyqtProperty` needs a `notify=` signal, and every state change must emit it.
  A missing emit shows up as stale UI that refreshes only when something else
  changes — the hardest class of bug to trace here.
- Anything QML *calls* needs `@pyqtSlot` with declared argument types. An
  undecorated method is invisible or silently coerced.
- Register new view models as context properties in `app.py` **before**
  `engine.load(...)`. A context property set afterwards is not visible to bindings
  already evaluated.
- View models adapt; they do not compute statics. See the `domain-boundary-reviewer`
  agent for that boundary.

## Tables and lists

Tabular data goes through `QAbstractItemModel` subclasses in `qml_app/models/`
(`table_models.py`, `list_models.py`, `document_models.py`, `report_rows.py`) — not
through a list of dicts in a property. Emit the correct structural signals
(`beginInsertRows`/`endInsertRows`, `dataChanged` with the right roles); mutating
rows without them corrupts the delegate cache and produces rows that render stale or
duplicated.

## The scene canvas

`QuickSceneCanvasBacking` is a `QQuickItem` bound to `SceneViewModel` via
`scene_vm.bindCanvas(...)` after `Main.qml` loads. What the scene shows is decided by
`core.scene_build.build_scene_frame`, which the view model calls once per state change
and hands to every bound canvas; the renderer's whole interface is `show(frame)` plus
the three `SceneCanvasContract` properties in `scene/scene_drag.py` — `scene_to_world`,
`map_scale`, `heel_world`. `tests/test_architecture.py` asserts both: that the surface
does not grow, and that those three stay `@property` and not methods. If you need
something new from the renderer, ask whether it belongs in the frame instead; do not
touch `_`-prefixed members from outside.

The app requests 8× MSAA via `configure_surface_format()`. Do not add per-item
antialiasing hacks to compensate for something that is actually a geometry bug.

## Controls style

`configure_controls_style()` sets `QT_QUICK_CONTROLS_STYLE=Fusion` with a `Basic`
fallback, before any control loads. Fusion is the chosen style — Qt's own
"Windows" and "FluentWinUI3" native styles were tried and are both broken in
this environment (their style-impl plugin DLLs fail to load, a missing native
dependency unrelated to this app's code). Fusion renders every native control
without the custom repainting the old `qml/components/` wrapper library did.
Don't switch styles, and don't set the env var anywhere else — ordering
matters, it must precede control instantiation. The app forces
`Qt.ColorScheme.Light` at startup (in `app.py`, right after constructing
`QGuiApplication`) so it stays light-only regardless of the OS theme.

## Verifying a change

QML errors are runtime errors, so a QML change that type-checks can still be broken.
`tests/test_qml_shell.py` loads every view through a `QQmlApplicationEngine` with
`engine.warnings` connected and **fails on any warning** — including binding loops
and unresolved properties. Run it after touching QML:

```bash
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/test_qml_shell.py -q --no-cov
```

`tests/conftest.py` provides a session-scoped `QGuiApplication`; never construct
another one in a test. To see a change in the real window, use the `run-app` skill.

## Debugging checklist

| Symptom | First thing to check |
|---|---|
| UI never updates | `pyqtProperty` has no `notify=`, or the setter never emits it |
| UI freezes on analysis | Synchronous solve on the GUI thread, or work inside a property getter |
| `TypeError` calling from QML | Method missing `@pyqtSlot`, or wrong declared arg types |
| Property is `undefined` in QML | Context property registered after `engine.load`, or snake_case name |
| Binding loop warning | Two properties whose notify signals each trigger the other's recompute |
| Import not found for a QML type | Missing `qmldir` entry, or `engine.addImportPath` not covering it |
| Crash on quit | Object not parented to the engine, so Python outlived its QML wrapper |
