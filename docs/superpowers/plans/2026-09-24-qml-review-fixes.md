# QML Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the two confirmed regressions from the qt-qml-review of the outstanding diff — a real anti-aliasing regression on two rotated scene delegates, and a duplicated/binding-destroying null-display pattern in `EnvironmentPanel.qml` — without touching any of the value-identical token substitutions the review already cleared.

**Architecture:** Two independent, single-purpose fixes. Task 1 restores an explicit `antialiasing: true` on the two `Rectangle` delegates in `QuickSceneCanvas.qml` where Qt's default-antialiasing rule (radius-gated) actually changes behavior. Task 2 gives `NumberField` a `clear()` method and collapses `EnvironmentPanel.qml`'s two duplicated "blank vs. formatted value" branches in `EnvRow` into one `applyDisplayValue()` function, called from both the initial load and the live model-change handler.

**Tech Stack:** Qt6 QML (Qt Quick, Qt Quick Layouts, Qt Quick Controls Fusion), PyQt6, pytest.

**Spec:** The qt-qml-review report from this conversation (diff-scoped review of the 16 modified `*.qml` files under `src/crane_statics/qml_app/`). Findings D-001 (DesignTokens.qml color-scheme ternary) was investigated further during planning and found to match an existing, pre-diff convention (`chartPass`/`chartFail`/`chartPending`/`chartContractual` at DesignTokens.qml:68-71 already use the identical 2-way `dark`-only ternary for semantic colors with no `SystemPalette` equivalent) — it is **not** a regression and is excluded from this plan.

## Global Constraints

- Do not modify any of the value-identical token substitutions (ContractualTable.qml, DataTable.qml, DesignLimitsTable.qml, ResultRowDelegate.qml, ResultsTable.qml, SceneControlRail.qml, SceneWorkspace.qml, StyledCheckBox.qml, StyledRadioButton.qml) — the review confirmed these are behavior-preserving.
- Do not restore `antialiasing: true` on the other 6 removed instances in `QuickSceneCanvas.qml` (waterline rectangles, guide `Shape`s, `guideLabel`, `winchSpoolCard`) or in `SceneAxisArrow.qml`/`SceneCgMarker.qml`/`SceneForceArrow.qml`/`SceneMomentGlyph.qml` — the review confirmed those removals are inert no-ops.
- Do not touch `DesignTokens.qml` — see the Spec note above; D-001 is not a regression.
- Tests run with: `python -m pytest tests/test_qml_shell.py -v` (uses a real `QQmlApplicationEngine` + real `ModelViewModel`/`SceneViewModel`, no mocking — follow this file's existing convention, do not introduce mocks).

## Review Focus

- A non-nullable environment field (e.g. `boom_width_m`) must still display `"0.000"`, not blank, after the `EnvRow` refactor — covered by Task 2's test asserting both a nullable and a non-nullable field's text.
- `modelVm.environment[key]` may surface an unset value to QML as either `null` or `undefined` depending on PyQt's `QVariant` marshalling of Python `None` — the pre-existing `displayValue()` check already handles both; Task 2's refactor must not narrow that check to only one of the two.
- The two fixed delegates in `QuickSceneCanvas.qml` (`structuralSegments`, `ropeSegments`) can end up axis-aligned when `dx` or `dy` is 0 (rotation 0/90/180) — `antialiasing: true` must be unconditional, not skipped for those cases, since it's harmless either way and the fix must not special-case rotation.
- `NumberField.clear()` must leave the field usable afterward (empty text, no validator lockup) — Task 2's test only checks the resulting `text`; if a manual smoke check shows the field can't be typed into after `clear()`, that's a red flag, not a pass.
- The other 6 already-removed `antialiasing: true` lines must stay removed — no task in this plan touches those files; a reviewer diffing the final branch against the pre-fix diff should see only the two Global-Constraints-scoped files changed plus the test file.

---

## File Structure

- Modify: `src/crane_statics/qml_app/qml/scene/QuickSceneCanvas.qml` — restore `antialiasing: true` on the `structuralSegments` and `ropeSegments` delegates.
- Modify: `src/crane_statics/qml_app/qml/NumberField.qml` — add a `clear()` function.
- Modify: `src/crane_statics/qml_app/qml/EnvironmentPanel.qml` — add an `objectName` to `EnvRow`'s `NumberField` (for test discoverability) and consolidate the duplicated display logic into one `applyDisplayValue()` function.
- Modify: `tests/test_qml_shell.py` — add one test for the restored anti-aliasing, one test for the nullable-field display behavior.

---

### Task 1: Restore anti-aliasing on rotated scene delegates

**Files:**
- Modify: `src/crane_statics/qml_app/qml/scene/QuickSceneCanvas.qml:220-231` (structuralSegments delegate), `:237-248` (ropeSegments delegate)
- Test: `tests/test_qml_shell.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: nothing other tasks rely on. Independent of Task 2.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_qml_shell.py`, after `test_delegate_component_compiles` (currently ends at line 240):

```python
def test_scene_canvas_segment_delegates_are_antialiased(qml_engine):
    """Booms and ropes are drawn at arbitrary angles; Qt only antialiases a
    Rectangle by default when it has a radius, so these delegates need the
    property set explicitly or their diagonal edges come out jagged.
    """
    engine, _app_vm, _model_vm, warnings = qml_engine
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / "scene/QuickSceneCanvas.qml")))
    canvas = component.create()
    assert canvas is not None, component.errorString()

    canvas.setProperty("frame", {
        "structuralSegments": [
            {"start_x": 0.0, "start_y": 0.0, "end_x": 10.0, "end_y": 6.0, "width": 4.0, "color": "#808080"},
        ],
        "ropeSegments": [
            {"start_x": 0.0, "start_y": 0.0, "end_x": 8.0, "end_y": -3.0, "width": 2.0, "color": "#c0c0c0"},
        ],
    })
    QTest.qWait(20)

    segment_rects = [
        child for child in canvas.findChildren(QObject)
        if child.metaObject().className() == "QQuickRectangle" and child.property("rotation") != 0
    ]
    assert len(segment_rects) == 2, "expected one structural and one rope segment delegate"
    assert all(rect.property("antialiasing") for rect in segment_rects)
    assert warnings == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_qml_shell.py::test_scene_canvas_segment_delegates_are_antialiased -v`
Expected: FAIL — `assert all(rect.property("antialiasing") for rect in segment_rects)` is false, because the current file has no `antialiasing` property on either delegate (default `false`, since neither has `radius` set).

- [ ] **Step 3: Restore the property on both delegates**

In `src/crane_statics/qml_app/qml/scene/QuickSceneCanvas.qml`, the `structuralSegments` delegate currently reads:

```qml
            delegate: Rectangle {
                required property var modelData
                readonly property real dx: modelData.end_x - modelData.start_x
                readonly property real dy: modelData.end_y - modelData.start_y
                x: modelData.start_x
                y: modelData.start_y - height / 2
                width: Math.hypot(dx, dy)
                height: modelData.width
                color: modelData.color
                rotation: Math.atan2(dy, dx) * 180 / Math.PI
                transformOrigin: Item.Left
            }
```

Change to:

```qml
            delegate: Rectangle {
                required property var modelData
                readonly property real dx: modelData.end_x - modelData.start_x
                readonly property real dy: modelData.end_y - modelData.start_y
                x: modelData.start_x
                y: modelData.start_y - height / 2
                width: Math.hypot(dx, dy)
                height: modelData.width
                color: modelData.color
                antialiasing: true
                rotation: Math.atan2(dy, dx) * 180 / Math.PI
                transformOrigin: Item.Left
            }
```

The `ropeSegments` delegate immediately below it has the identical structure — apply the same one-line addition (`antialiasing: true` after `color: modelData.color`) there too.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_qml_shell.py::test_scene_canvas_segment_delegates_are_antialiased -v`
Expected: PASS

- [ ] **Step 5: Run the existing scene-canvas smoke test to confirm no regression**

Run: `python -m pytest tests/test_qml_shell.py -k QuickSceneCanvas -v`
Expected: PASS (the parametrized `test_component_loads_without_warnings` case for `scene/QuickSceneCanvas.qml` still loads warning-free)

- [ ] **Step 6: Commit**

```bash
git add src/crane_statics/qml_app/qml/scene/QuickSceneCanvas.qml tests/test_qml_shell.py
git commit -m "fix: restore antialiasing on rotated scene segment delegates"
```

---

### Task 2: Consolidate EnvironmentPanel's null-display logic

**Files:**
- Modify: `src/crane_statics/qml_app/qml/NumberField.qml:24-26` (add `clear()` next to `setValue()`)
- Modify: `src/crane_statics/qml_app/qml/EnvironmentPanel.qml:16-71` (the `EnvRow` component)
- Test: `tests/test_qml_shell.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `NumberField.clear()` — a no-argument function that sets `text` to `""`. `EnvRow.applyDisplayValue()` — a no-argument function that reads `envRow.displayValue()` and routes it to either `envField.clear()` or `envField.setValue(v)`. Nothing outside this task calls either.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_qml_shell.py`, after the `test_component_loads_without_warnings` parametrized block (currently ends at line 223):

```python
def test_environment_panel_nullable_field_shows_blank_when_unset(qml_engine):
    """slewing_bearing_diameter_m is optional; with no document loaded it must
    read as blank, not '0.000', while an ordinary field like boom_width_m
    still shows its numeric default.
    """
    engine, _app_vm, _model_vm, warnings = qml_engine
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / "EnvironmentPanel.qml")))
    panel = component.create()
    assert panel is not None, component.errorString()

    nullable_field = panel.findChild(QObject, "envField_slewing_bearing_diameter_m")
    ordinary_field = panel.findChild(QObject, "envField_boom_width_m")

    assert nullable_field is not None, "NumberField for the nullable row must be discoverable"
    assert ordinary_field is not None, "NumberField for an ordinary row must be discoverable"
    assert nullable_field.property("text") == ""
    assert ordinary_field.property("text") == "0.000"
    assert warnings == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_qml_shell.py::test_environment_panel_nullable_field_shows_blank_when_unset -v`
Expected: FAIL — `panel.findChild(QObject, "envField_slewing_bearing_diameter_m")` returns `None`, because no `NumberField` in the current file has an `objectName` set.

- [ ] **Step 3: Add the objectName**

In `src/crane_statics/qml_app/qml/EnvironmentPanel.qml`, the `NumberField` inside `EnvRow` currently starts:

```qml
        NumberField {
            id: envField
            Layout.preferredWidth: 96
            decimals: envRow.decimals
```

Change to:

```qml
        NumberField {
            id: envField
            objectName: "envField_" + envRow.fieldKey
            Layout.preferredWidth: 96
            decimals: envRow.decimals
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_qml_shell.py::test_environment_panel_nullable_field_shows_blank_when_unset -v`
Expected: PASS — this confirms the objectName lookup works and the pre-existing display logic already behaves correctly; the refactor in the next step must not change this result.

- [ ] **Step 5: Add `NumberField.clear()`**

In `src/crane_statics/qml_app/qml/NumberField.qml`, immediately after the existing `setValue` function:

```qml
    function setValue(newValue) {
        text = Number(newValue).toFixed(decimals)
    }
```

Add:

```qml
    function setValue(newValue) {
        text = Number(newValue).toFixed(decimals)
    }

    function clear() {
        text = ""
    }
```

- [ ] **Step 6: Consolidate the duplicated branch into `applyDisplayValue()`**

In `src/crane_statics/qml_app/qml/EnvironmentPanel.qml`, the `EnvRow` component currently reads:

```qml
    component EnvRow: RowLayout {
        id: envRow

        property string label: ""
        property string fieldKey: ""
        property int decimals: 3
        // When true, an empty field means "unset" rather than 0 - the field is
        // cleared on the document instead of being written as a numeric value.
        property bool nullable: false

        Layout.fillWidth: true
        spacing: root.layoutSpacing

        function displayValue() {
            const v = modelVm.environment[envRow.fieldKey]
            return (envRow.nullable && (v === null || v === undefined)) ? "" : v
        }

        Label {
            Layout.fillWidth: true
            text: envRow.label
            elide: Text.ElideRight
        }

        NumberField {
            id: envField
            objectName: "envField_" + envRow.fieldKey
            Layout.preferredWidth: 96
            decimals: envRow.decimals
            Component.onCompleted: {
                const v = envRow.displayValue()
                if (v === "")
                    envField.text = ""
                else
                    envField.setValue(v)
            }
            onEditingFinished: {
                if (envRow.nullable && envField.text.trim() === "")
                    modelVm.clearEnvironmentValue(envRow.fieldKey)
                else
                    modelVm.setEnvironmentValue(envRow.fieldKey, value)
            }

            Connections {
                target: modelVm
                function onEnvironmentChanged() {
                    if (envField.activeFocus)
                        return
                    const v = envRow.displayValue()
                    if (v === "")
                        envField.text = ""
                    else
                        envField.setValue(v)
                }
            }
        }
    }
```

Change to:

```qml
    component EnvRow: RowLayout {
        id: envRow

        property string label: ""
        property string fieldKey: ""
        property int decimals: 3
        // When true, an empty field means "unset" rather than 0 - the field is
        // cleared on the document instead of being written as a numeric value.
        property bool nullable: false

        Layout.fillWidth: true
        spacing: root.layoutSpacing

        function displayValue() {
            const v = modelVm.environment[envRow.fieldKey]
            return (envRow.nullable && (v === null || v === undefined)) ? "" : v
        }

        function applyDisplayValue() {
            const v = envRow.displayValue()
            if (v === "")
                envField.clear()
            else
                envField.setValue(v)
        }

        Label {
            Layout.fillWidth: true
            text: envRow.label
            elide: Text.ElideRight
        }

        NumberField {
            id: envField
            objectName: "envField_" + envRow.fieldKey
            Layout.preferredWidth: 96
            decimals: envRow.decimals
            Component.onCompleted: envRow.applyDisplayValue()
            onEditingFinished: {
                if (envRow.nullable && envField.text.trim() === "")
                    modelVm.clearEnvironmentValue(envRow.fieldKey)
                else
                    modelVm.setEnvironmentValue(envRow.fieldKey, value)
            }

            Connections {
                target: modelVm
                function onEnvironmentChanged() {
                    if (envField.activeFocus)
                        return
                    envRow.applyDisplayValue()
                }
            }
        }
    }
```

- [ ] **Step 7: Run the test again to confirm the refactor is behavior-preserving**

Run: `python -m pytest tests/test_qml_shell.py::test_environment_panel_nullable_field_shows_blank_when_unset -v`
Expected: PASS (unchanged from Step 4 — proves the consolidation didn't alter the observable result)

- [ ] **Step 8: Run the full QML shell test file to catch any collateral warning**

Run: `python -m pytest tests/test_qml_shell.py -v`
Expected: All PASS, including the existing `EnvironmentPanel.qml` and `NumberField.qml` entries in `test_component_loads_without_warnings`.

- [ ] **Step 9: Commit**

```bash
git add src/crane_statics/qml_app/qml/NumberField.qml src/crane_statics/qml_app/qml/EnvironmentPanel.qml tests/test_qml_shell.py
git commit -m "refactor: consolidate EnvironmentPanel's null-display logic into one helper"
```

---

## Self-Review

**Spec coverage:** L-001/L-002 (BND-2 on `EnvironmentPanel.qml:47,65`) → Task 2. D-002 (antialiasing regression on `QuickSceneCanvas.qml`) → Task 1. D-001 (DesignTokens.qml color ternary) → excluded, confirmed not a regression (see Spec note). No other findings from the review required a fix (Layout & Anchoring, Component Loading & Lifecycle, ListView & Delegates, and States & Structure agents all reported zero findings; the token-substitution files were confirmed value-identical).

**Placeholder scan:** No TBD/TODO markers; every step shows the exact before/after code or the exact command to run.

**Type consistency:** `applyDisplayValue()` and `clear()` are named and used identically in Steps 5-6 of Task 2. `envField_<fieldKey>` objectName format matches between Step 3's edit and both test functions' lookups.

**Review Focus:** all five items above are either directly exercised by a task's test (items 1, 2 via Task 2's dual-field assertion) or called out as an explicit non-goal with a stated reason (items 3, 4, 5), which is the honest outcome when a plan's scope is deliberately narrow.
