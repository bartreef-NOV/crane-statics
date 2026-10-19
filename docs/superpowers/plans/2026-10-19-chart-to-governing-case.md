# Load chart → governing case Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Right-click a load-chart series point → switch to the Scene with the governing case applied (all inputs + hook load at the design limit), with a Restore-my-inputs button.

**Architecture:** The envelope search (`core/chart_envelope.py`) already finds the worst case analytically and discards it; keep its argmax (`EnvelopeCase`). A pure `core/governing_case.py` re-evaluates one (hoist, mode, outreach, limit) on demand and returns Scene-state values. `SceneViewModel` applies them (snapshot, label, restore); `ChartViewModel` exposes the click slot; QML wires menu, tab switch and banner.

**Tech Stack:** Python 3, PySide6/QML (Fusion), numpy, pytest.

**Spec:** `docs/superpowers/specs/2026-10-19-chart-to-governing-case-design.md`

## Global Constraints

- Use `.venv/Scripts/python.exe`; tests `-m pytest` (`--no-cov` for one file); lint `-m pre_commit run --all-files` (black, flake8, mypy, `tests/test_architecture.py`).
- Domain packages (`core/`, `calculation/`) stay Qt-free; no presentation formatting in `core/`.
- **Continuous wind angle is dropped** (supersedes the spec): the worst-case wind is always an axis wind (`_linear_capacity` lines 508-511; magnitude corners at `_magnitude_capacity` line 690). `SceneState.wind_direction` ∈ {"+X","-X","+Y","-Y"} holds every case. Update the spec's "Also decided" bullet accordingly in Task 2.
- Vessel motion = the document's full ± limits (as the chart); tackle length = the value the load curve used (mode's); wind speed = `doc.environment.max_wind_speed_m_s`.
- Linear limits: Scene capacity must equal the chart value (rel. 1e-6). Magnitude limits (`resultant`, `fradial`, `mradial`, `max_bearing_line_load`): within 0.1 % (chart is a deliberate conservative bound; slew stretch 1/cos(π/360)).
- Hook load set to the limit with `hook_load_auto=False`.

## Review Focus

- Document with no vessel motion (single sign case) and wind speed 0: case still applies, wind direction stays "+X".
- Second apply while a snapshot exists keeps the *original* snapshot.
- Limit with no finite/responsive capacity (unlimited): menu entry disabled, no crash.
- Chart stale or busy when the user clicks: entry disabled (case would not match the drawn point).
- Split vs normal chart mode: case computed for the mode the chart was drawn in, applied to that hoist.
- Programmatic apply must not clear the label; any user edit (setter) must; hoist change / document load clears the snapshot.

---

### Task 1: Keep the envelope's argmax case

**Files:**
- Modify: `src/crane_statics/core/chart_envelope.py` (`_linear_capacity` ~473, `_magnitude_capacity` ~622, `envelope_capacity` ~771)
- Test: `tests/test_chart_envelope_case.py` (create; follow fixtures used by the existing chart_envelope tests)

**Interfaces:**
- Produces: `@dataclass(frozen=True) class EnvelopeCase` with `vessel_inputs: dict[str, float]` (keys = `VesselInputs` field names), `slew_deg: float`, `wind_axis: str` (one of "+X","-X","+Y","-Y", "" when no wind), `offlead_deg: float`, `sidelead_deg: float`, `limit_id: str`.
- Produces: `envelope_capacity_case(calc, probes, limits, *, vessel, offlead_deg, sidelead_deg, hook_daf, hook_mass_t) -> tuple[AllowableCapacity, Optional[EnvelopeCase]]`; `envelope_capacity` becomes a wrapper returning element 0 (signature unchanged).

- [ ] **Step 1: Write failing tests** — `test_linear_limit_case_reproduces_capacity`: re-evaluate the returned case through `compute_allowable_load` (via `compute_analysis_point` with the case's vessel inputs, slew, wind axis, leads) and assert `max_allowable_load_kN` equals the envelope's within rel 1e-6. `test_magnitude_limit_case_within_tolerance`: same for a `resultant` limit, rel 1e-3, scene result ≥ chart value. `test_no_vessel_motion_single_case`: zero vessel motion → `vessel_inputs` all 0.
- [ ] **Step 2: Run** `-m pytest tests/test_chart_envelope_case.py --no-cov` → FAIL (names undefined).
- [ ] **Step 3: Implement.** Thread `(cap, EnvelopeCase)` pairs through `_lower`-style selection: `_linear_capacity` and `_magnitude_capacity` return the pair (magnitude: record `(lead, case, cos, sin, corner)` at `_evaluate` next to `best`). Map `case` index → `vessel_motion_cases(vessel)[case]` keys via `_VESSEL_INPUT_FIELDS`; `slew_deg = degrees(atan2(sin, cos))`; wind axis from the corner/sign; leads from the lead point's signed offlead/sidelead (extend `lead_points` internals to keep the signed values). Keep `envelope_capacity` behaviour byte-identical.
- [ ] **Step 4: Run** new tests plus `tests/` chart/sweep tests (`-m pytest -k "envelope or sweep"`) → PASS.
- [ ] **Step 5: Commit** `Chart: envelope keeps the argmax case`.

### Task 2: On-demand governing case

**Files:**
- Create: `src/crane_statics/core/governing_case.py`
- Modify: `docs/superpowers/specs/2026-10-19-chart-to-governing-case-design.md` (replace continuous-wind bullet with the axis-wind finding)
- Test: `tests/test_governing_case.py`

**Interfaces:**
- Consumes: `envelope_capacity_case`, `EnvelopeCase`, `build_probes`, `KinematicsAdapter.outreach_to_angle`, mode objects as used in `run_mode_sweep` (`mode.runtime_overrides`, `mode.hook_mass_t`).
- Produces: `@dataclass(frozen=True) class GoverningCase` with `limit_id: str`, `scene_fields: dict[str, Any]` (keys are `SceneState` field names: `boom_angle_deg, hook_load_kN, hook_load_auto, tackle_length_m, offlead_deg, sidelead_deg, wind_speed_m_s, wind_direction, accel_x_m_s2, accel_y_m_s2, accel_z_m_s2, pitch_accel_rad_s2, roll_accel_rad_s2, vessel_roll_deg, vessel_pitch_deg, crane_slewing_angle_deg`), `outreach_m: float`.
- Produces: `governing_case(doc: CraneDocument, hoist_id: str, mode_name: str, enabled_limits: dict, outreach_m: float, limit_id: Optional[str]) -> Optional[GoverningCase]`. `limit_id=None` → limit of lowest `load_kN` at that outreach (first key on a tie). Returns None for unlimited / unresolved / non-responsive limits.

- [ ] **Step 1: Failing tests** with a fixture document: `test_case_hook_load_equals_chart_point` (hook_load_kN equals the sweep's per-limit `load_kN` at that outreach, rel 1e-6, 1e-3 for magnitude limits); `test_none_limit_picks_lowest`; `test_unlimited_returns_none`; `test_tackle_length_is_mode_value`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `governing_case` mirroring `run_mode_sweep`'s calc/vessel/leads setup and `_envelope` (probes at `kin.outreach_to_angle(outreach)`), single-limit `envelope_capacity_case`, hook load from `max_allowable_load_kN` the same way `AnalysisCalculator.compute_auto_load` stores it (`core/analysis_services.py:514`; reuse its conversion rather than re-deriving). Vessel inputs → `SceneState` names via the inverse of `_VESSEL_INPUT_FIELDS` (roll_deg → vessel_roll_deg etc.).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `Core: governing_case re-evaluates one chart point`.

### Task 3: Scene view model — apply, label, restore

**Files:**
- Modify: `src/crane_statics/qml_app/viewmodels/scene_vm.py` (setters ~281-664, `_after_state_changed` 895)
- Test: `tests/test_scene_vm_governing_case.py`

**Interfaces:**
- Consumes: `GoverningCase`.
- Produces on `SceneViewModel`: `def apply_governing_case(self, case: GoverningCase, label: str) -> None`; property `governingCaseLabel: str` (notify `governingCaseChanged`); property `canRestoreInputs: bool` (same signal); slot `restoreInputs()`.

- [ ] **Step 1: Failing tests** (names): `test_apply_sets_fields_and_label`; `test_apply_runs_without_vessel_clamp_side_effects` (all vessel fields land exactly); `test_user_setter_clears_label_keeps_restore`; `test_second_apply_keeps_original_snapshot`; `test_restore_restores_fields_and_auto_flag_and_hides_button`; `test_hoist_change_clears_snapshot`; `test_document_change_clears_snapshot`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Snapshot = `dataclasses.replace(scene_state)` of the active hoist, taken only if none exists. Apply writes the `SceneState` fields directly (bypasses clamp-order setters), then `_after_state_changed()`; wrap in a `_applying` flag so the central user-edit path (find where `_set_scene_field` / setters call `mark_content_changed`) clears only the label when not `_applying`. Subscribe to `SessionState.hoist_selected` and `document_changed` to drop the snapshot.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `Scene: apply a governing case, restore previous inputs`.

### Task 4: Chart view model slot and tab signal

**Files:**
- Modify: `src/crane_statics/qml_app/viewmodels/chart_vm.py` (near `_JobStream` 151, properties ~1024); wiring where `ChartViewModel` and `SceneViewModel` are created (find via `Grep "ChartViewModel("`)
- Test: `tests/test_chart_vm_governing_case.py`

**Interfaces:**
- Consumes: `governing_case`, `SceneViewModel.apply_governing_case`.
- Produces: slot `showGoverningCase(seriesId: str, outreach: float)` (`seriesId == ""` = combined curve); slot `governingCaseAvailable(seriesId: str) -> bool` (False when stale, busy, split-mismatch or limit unlimited); signal `showSceneRequested()`.

- [ ] **Step 1: Failing tests:** `test_show_applies_case_and_emits_signal`; `test_unavailable_when_stale_or_busy`; `test_unlimited_series_unavailable`; `test_split_mode_uses_chart_mode` (case computed with the hoist's `chart_mode_for_hoist`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Compute off the GUI thread (small `QThread`/`QRunnable` like `_SweepWorker`), apply and emit on the GUI thread. Label text `"Governing case: {limit display name} at {outreach:.1f} m"` built here (presentation), using the chart's `limit_display_names`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `Chart: show the governing case of a clicked point`.

### Task 5: QML — menu entry, tab switch, banner

**Files:**
- Modify: `qml/QuickChartPlot.qml` (`nearestPoint` 177 must also return `seriesId`; `collectSeries` series already carry `id`), `qml/LoadChartWorkspace.qml` (TapHandler 113, `chartMenu` 160), `qml/Main.qml` (add `Connections` on `chartVm.onShowSceneRequested` → `workspaceTabs.currentIndex = 0`; confirm Scene index), Scene workspace QML (banner: `Label` bound to `sceneVm.governingCaseLabel`, visible when non-empty; `Button` "Restore my inputs" visible when `sceneVm.canRestoreInputs`, calls `restoreInputs()`)
- Follow the `qml-ui-development` skill (native Fusion, SystemPalette, no hard-coded colours).

- [ ] **Step 1:** In the right-click `onTapped`, store `plot.nearestPoint(position)` (or the hovered point) in `chartMenu.targetPoint` before `popup`.
- [ ] **Step 2:** Add `MenuItem` "Show governing case in Scene" above the export separator: `enabled: chartMenu.targetPoint !== null && chartVm.governingCaseAvailable(chartMenu.targetPoint.seriesId)`; `onTriggered: chartVm.showGoverningCase(targetPoint.seriesId, targetPoint.outreach)`.
- [ ] **Step 3:** Banner + button in the Scene workspace; tab-switch `Connections` in `Main.qml`.
- [ ] **Step 4: Verify** headlessly: run the `run-app` skill to screenshot Load Chart, then Scene after triggering the case; confirm no QML warnings in the log.
- [ ] **Step 5: Commit** `QML: governing-case menu entry, banner and restore button`.

### Task 6: Verification

- [ ] **Step 1:** `-m pytest` (full) → all pass, coverage gate holds.
- [ ] **Step 2:** `-m pre_commit run --all-files` → clean (incl. `tests/test_architecture.py`).
- [ ] **Step 3:** Manual check with `run-app`: pick a linear-limit point and a magnitude-limit point; Scene component load equals the chart value (0.1 % for magnitude); edit wind → label disappears, Restore stays; Restore returns previous inputs.
- [ ] **Step 4:** Run the `domain-boundary-reviewer` agent on the diff.
