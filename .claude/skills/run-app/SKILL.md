---
name: run-app
description: Launch the Crane Statics app or screenshot a workspace headlessly.
---

# Running Crane Statics

**Use when** asked to run/start/open the app, to show a UI change working, or to screenshot the Scene, Load Chart or Model workspace. Confirms a change works in the real app, not only in tests.

The app needs a model file to show anything — with no argument it opens on
`NoDocumentPage`. The bundled fixture is
[examples/crane_input_22689.yaml](../../../examples/crane_input_22689.yaml), the same
one the acceptance and QML shell tests use.

## Interactive run (hands the window to the user)

```bash
.venv/Scripts/python.exe -m crane_statics examples/crane_input_22689.yaml
```

The `crane-statics` console script is equivalent. This blocks until the user closes
the window, so run it in the background if you need to keep working:
pass `run_in_background: true` to Bash.

## Screenshot (what you want for verifying a change)

`scripts/screenshot.py` replicates the `app.py` bootstrap without entering the
blocking `app.exec()` loop, opens a model, grabs the window to PNG, and prints the
window title and status bar text. It exits non-zero and dumps the QML warnings if
`engine.warnings` fired, so it doubles as a smoke test.

```bash
# Scene workspace, offscreen
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe \
  .claude/skills/run-app/scripts/screenshot.py -o /tmp/scene.png --workspace scene

# Load Chart, native rendering, custom size
QT_QPA_PLATFORM=windows .venv/Scripts/python.exe \
  .claude/skills/run-app/scripts/screenshot.py -o /tmp/chart.png \
  --workspace chart --size 1920x1080
```

Then Read the PNG to actually look at it.

Options: positional model path (defaults to the bundled example), `-o/--out`,
`--workspace scene|chart|model`, `--size WxH` (default 1600x1000), `--settle MS`
(default 1200, ms of event-loop time before grabbing — raise it if the scene or chart
comes out half-drawn, since the solver populates asynchronously).

### Which platform to use

| | `offscreen` | `windows` (native) |
|---|---|---|
| Text | **Renders as tofu boxes** — no font rasterisation | Real, readable text |
| Geometry, layout, colours, chart curves | Accurate | Accurate |
| Side effects | None | Briefly flashes a real window on the user's desktop |

**Use `offscreen` by default** for layout, scene geometry and theming checks — it is
also what CI uses (`QT_QPA_PLATFORM: offscreen` in
[.github/workflows/ci.yml](../../../.github/workflows/ci.yml)). Switch to `windows`
only when the thing you need to read is text: table values, labels, status messages,
number formatting. Do not conclude "the labels are broken" from an offscreen grab.

## Prefer the test suite when it can answer the question

Launching the app is slower and noisier than the tests, and `tests/test_qml_shell.py`
already loads every view and fails on any QML warning:

```bash
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/test_qml_shell.py -q --no-cov
```

Reach for a screenshot when the question is genuinely visual — spacing, alignment,
theme, scene rendering, chart shape — or when the user asked to see it.

## Gotchas

- **`QGuiApplication`, not `QApplication`.** There are no QWidgets in this project.
- **One application object per process.** `tests/conftest.py` supplies a
  session-scoped `QGuiApplication`; never construct a second one.
- **Controls style is set before any control loads.** `configure_controls_style()`
  sets `QT_QUICK_CONTROLS_STYLE=Fusion` (Qt's "Windows"/"FluentWinUI3" native styles
  are broken in this environment — missing native plugin dependencies). Don't
  override it. The app is light-only (`Qt.ColorScheme.Light` is forced at startup).
- **The scene canvas is bound after `Main.qml` loads**, via
  `scene_vm.bindCanvas(QuickSceneCanvasBacking(engine))`. Skip it and the Scene
  workspace comes up empty.
- **Parent view models to the engine** so QML objects tear down before their Python
  backing objects; otherwise you get a crash on quit.
- **Workspace tabs** are switched through the `workspaceTabs` object name in
  `Main.qml` (Scene=0, Load Chart=1, Model=2).
