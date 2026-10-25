# App Consistency Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the platform-base reaction signs, the left/right support swap, the Y-wind boom scaling and the singular/no-solve-rope handling in the app, then make the Excel validation workbook follow.

**Architecture:** Four small, test-pinned changes in `calculation/engine.py`, `calculation/solver/crane_solver.py` and `core/drawn_loads.py`, plus a status-message path to the Scene. Then the workbook generator (`scripts/excel_workbook/`, branch `excel-validation-workbook`) is rebased, updated and regenerated against the fixed app.

**Tech Stack:** Python 3.11, numpy, PyQt6/QML, pytest, openpyxl, `formulas`.

**Spec:** `docs/superpowers/specs/2026-10-25-app-consistency-fixes-design.md`

## Global Constraints

- Preconditions (user actions, not tasks): the user's uncommitted v11 work is committed on `main`; Tasks 1-5 run on a new branch `app-consistency-fixes` from that `main` (own worktree). Find code by symbol, not line number.
- Reaction convention: the force the support exerts on the crane. +Y points to port (left looking along +x).
- Only these numbers may change: `platform_base` Fy and Mx (sign), the `heel`/`front_leg`/`rear_leg` left/right pairs (swapped), Y-wind loads on boom-local areas (no sin θ). Every in-plane number, rope tension and hinge/heel total stays identical (assert on the 22689 and GT283 golden cases).
- X-wind boom areas keep `|sin(boom angle)|` in the solver (every boom-body area).
- Singular threshold: `abs(det(A)) / prod(row norms of A) <= 1e-12`.
- Test commands: `.venv/Scripts/python.exe -m pytest <file> --no-cov -q`; full suite `... -m pytest -n auto --dist loadfile`; lint `... -m pre_commit run --all-files`.
- Known unrelated failure: `tests/test_qml_shell.py::test_chart_menu_edits_contractual_points_at_the_cursor`. Do not fix, do not stage `tests/test_qml_shell.py`.
- Stage only files named in each task. Regenerated golden files are reviewed as diffs: only the allowed numbers above may move.

## Review Focus

- Sign flip must reach baseline, hook sensitivity and sidelead unit reactions alike (all derive from `_out_of_plane_variants`); test with hook load and sidelead non-zero, not only the baseline.
- Wind speed 0 and Y wind at boom angles 0° and 90° (sin θ = 0 or 1) give the same Y result and no error.
- `fradial`, `mradial`, min/max bearing line load and `resultant` are sign-agnostic (`hypot`) and must not change.
- Chart/limit sweeps over many boom angles must still skip unsolvable points quietly; the new singular threshold must not make a previously solvable example fail.
- A document with no solve rope, or only an exactly/nearly singular geometry, shows a message and does not raise.

---

## File Structure

- `src/crane_statics/calculation/engine.py`: signs, left/right, Y wind, failure reason.
- `src/crane_statics/calculation/solver/crane_solver.py`: conditioning check, reasons for `None`.
- `src/crane_statics/core/drawn_loads.py`: X-wind boom scaling parity.
- `src/crane_statics/core/analysis_services.py`, `src/crane_statics/qml_app/viewmodels/scene_vm.py`: carry the reason to `statusMessage`.
- `tests/test_app_consistency_fixes.py`: new tests for Tasks 1-5.
- `tests/golden/gt283_*.json`: regenerated.
- Workbook: `scripts/excel_workbook/*`, `tests/test_excel_workbook_*.py`, `tests/golden/22689_workbook_cases.json`, `docs/crane-statics-validation-22689.xlsx`, `docs/excel-validation-workbook.md`.

---

### Task 1: Platform-base Fy and Mx become support reactions

**Files:**
- Modify: `src/crane_statics/calculation/engine.py` (`CraneCalculator._out_of_plane_variants`, `_augment_point_with_out_of_plane_loads`)
- Test: `tests/test_app_consistency_fixes.py`; regenerate `tests/golden/gt283_*.json` if they store Fy/Mx.

**Interfaces:**
- Produces: `AnalysisPoint.baseline_reactions["platform_base"]["Fy"|"Mx"]`, `sensitivity_reactions[...]` and `sidelead_lateral_unit_reactions["platform_base"]` now hold the force/moment the support exerts on the crane (opposite sign to today).

- [ ] **Step 1: Write failing tests.**
  - `test_platform_base_fy_balances_y_loads`: 22689, level vessel, wind 0, sidelead 0, `accel_y = +1.0`: `platform_base` baseline Fy is positive and equals `accel_y * (sum of all mass points + lumped point masses on the response basis)` within 1e-6 (support pushes +Y to accelerate the crane +Y).
  - `test_platform_base_fy_positive_for_wind_toward_minus_y` (wind from +Y pushes the crane toward -Y, support reacts +Y — pick the repo's wind-angle convention from `split_wind_angle_components`) and `test_platform_base_mx_is_moment_balance`: for a single known mass at y=+3 m above/at the platform heel, Mx equals `-(y*Fz_applied - rel_z*Fy_applied)` by hand.
  - `test_platform_base_sign_applies_to_hook_and_sidelead`: sidelead 4.5° and hook 1000 kN: Fy from `baseline + sensitivity*hook` is positive-sign-consistent with a hand computation of the side force (sidelead pushes the crane toward the load side; support reacts opposite).
  - `test_sign_agnostic_consumers_unchanged`: `extract_connection_demand` (`core/demand_extraction.py`) for `resultant`, `fradial`, `mradial`, `max_bearing_line_load`, `min_bearing_line_load` on 22689 case 3 (Y wind, roll, sidelead) equals values captured from the pre-change code (hard-code them from a run before Step 3).
- [ ] **Step 2: Run; expect the first three to FAIL.**
- [ ] **Step 3: Implement.** Negate `platform_mx` and `platform_fy` once, where `_out_of_plane_variants` appends each variant's `(split, mx, fy)`, so baseline, sensitivity and side-unit values all inherit it. Check every other caller of `_out_of_plane_variants` (the `[0]`-returning wrapper near the top of the out-of-plane section) and every reader of `Fy`/`Mx` (`demand_extraction.py`, `chart_envelope.py`, `limit_components.py`, `limit_factory.py`, `presentation/formatters.py`); the readers are expected to be sign-agnostic, record any that are not and adapt so their output is unchanged.
- [ ] **Step 4: Run new tests and the full suite; expect only golden-file failures in GT283 files that store platform_base Fy/Mx.** Regenerate those goldens with their existing generation script (find it by grep; if none exists, edit the two numbers' signs by script and say so); review the diff: only platform_base Fy/Mx sign flips.
- [ ] **Step 5: Commit** `engine.py`, test, golden files.

---

### Task 2: Left/right support pairs follow +Y = port

**Files:**
- Modify: `src/crane_statics/calculation/engine.py` (`_out_of_plane_variants` split block); inspect `src/crane_statics/core/drawn_loads.py` `reactions()` and `src/crane_statics/presentation/formatters.py` labels.
- Test: `tests/test_app_consistency_fixes.py`

- [ ] **Step 1: Write failing tests.**
  - `test_heel_left_carries_more_when_mass_is_to_port`: a mass point at y=+5 m (port): Fz of `heel_left` > `heel_right`; same for `front_leg_left/right` and `rear_leg_left/right`; mirrored for y=-5 m. Use a synthetic or modified 22689 document built the way other engine tests do.
  - `test_left_right_sum_to_total`: `left + right` equals the group total (`heel_point`, `front_hinge`, `rear_hinge`) for Fx and Fz, in every case of the 22689 acceptance set.
  - `test_reaction_arrows_sit_on_the_matching_side`: for `heel_left`, the reaction arrow anchor (from `drawn_loads` reactions) has the y-side the label says, if arrows carry a y position; otherwise assert the label/entity pairing only. If the arrow anchors or table labels turn out to be positioned by the old (wrong) side, fix them in this task and extend the test.
- [ ] **Step 2: Run; expect the first test to FAIL.**
- [ ] **Step 3: Implement.** In the loop over `total_map`, assign `0.5*total + d` to the right entity and `0.5*total - d` to the left (swap the two `split[...]` assignments). Do not touch `d_fx`/`d_fz`.
- [ ] **Step 4: Run new tests and the full suite; regenerate left/right values in any golden file and review the diff (left and right swap only).**
- [ ] **Step 5: Commit.**

---

### Task 3: Wind scaling parity

**Files:**
- Modify: `src/crane_statics/calculation/engine.py` (`_out_of_plane_geometry`), `src/crane_statics/core/drawn_loads.py` (wind vector build)
- Test: `tests/test_app_consistency_fixes.py`

- [ ] **Step 1: Write failing tests.**
  - `test_y_wind_on_boom_does_not_scale_with_boom_angle`: boom-local wind area only, Y wind 15 m/s: platform-base Fy (and moments) at boom angles 30° and 75° differ only through lever arms: assert `sum(wind force)` (recover from the out-of-plane geometry's `wind_coef` and wind speed) equals `0.5*rho*cd*area_v*V²/1000` at both angles.
  - `test_x_wind_boom_areas_scale_in_arrow_and_solver_alike`: for a boom-body wind area that is not boom-local, the X-wind arrow length from `drawn_loads` equals the solver force (`crane_solver` wind Fx) at a boom angle not 90°.
  - `test_wind_speed_zero_gives_zero_and_no_error` at boom angles 0° and 90°.
- [ ] **Step 2: Run; expect the first two to FAIL.**
- [ ] **Step 3: Implement.** In `_out_of_plane_geometry`, drop the `boom_proj` factor on `area_v_m2` (remove the now-unused `boom_wind_projection_scale` import if nothing else uses it). In `drawn_loads` make the X-wind scaling apply to every area of the boom body, as `crane_solver` does (`is_boom_body`, not `is_boom_local`). Y-wind arrows are unscaled.
- [ ] **Step 4: Run new tests and the full suite; regenerate goldens that include Y wind on the boom and review (only Y-wind numbers move).**
- [ ] **Step 5: Commit.**

---

### Task 4: Near-singular statics fail clearly, with a reason

**Files:**
- Modify: `src/crane_statics/calculation/solver/crane_solver.py` (`_run_statics` boom 3x3 and leg 6x6 solves), `src/crane_statics/calculation/engine.py` (`compute_analysis_point`)
- Test: `tests/test_app_consistency_fixes.py`

**Interfaces:**
- Produces: `crane_solver.is_ill_conditioned(matrix: np.ndarray) -> bool` (`abs(det)/prod(row norms) <= 1e-12`; a zero row counts as ill-conditioned). `CraneCalculator.unavailable_reason: Optional[str]`, reset to `None` at the start of every `compute_analysis_point` call and set to a human-readable sentence whenever it returns `None` for a known cause.

- [ ] **Step 1: Write failing tests.**
  - `test_is_ill_conditioned_flags_singular_and_near_singular` (identity: False; two equal rows: True; rows differing by 1e-15: True).
  - `test_all_examples_still_solve`: for every `examples/*.yaml`, at their default boom angle and at 10 angles spanning the boom range, `compute_analysis_point` is not `None` and `unavailable_reason` is `None`.
  - `test_collapsed_geometry_reports_reason`: collapse the rear and front hinge to the same point (as the workbook's singular test does); `compute_analysis_point` returns `None`, `unavailable_reason` contains "singular" and the matrix name ("boom" or "leg frame").
  - `test_chart_sweep_skips_unsolvable_points`: a sweep (`chart_envelope`/`limit_auto_set` path) over an angle range that includes an ill-conditioned angle completes without exception.
- [ ] **Step 2: Run; expect FAIL (function missing).**
- [ ] **Step 3: Implement.** Check conditioning before each `np.linalg.solve`; on failure `_run_statics` keeps returning `{}` as today (so sweeps still skip) and records the reason where the engine can read it (return it through the existing basis/`solver_ctx` object or a small result field; choose the least invasive carrier). `compute_analysis_point` copies the reason into `self.unavailable_reason`. Never let the broad `except Exception: return None` hide a recorded reason.
- [ ] **Step 4: Run new tests; expect PASS. Run the full suite; fix any example that now fails by checking whether its matrix is truly ill-conditioned (report to the user rather than loosening the threshold).**
- [ ] **Step 5: Commit.**

---

### Task 5: Scene says why nothing is shown

**Files:**
- Modify: `src/crane_statics/calculation/solver/crane_solver.py` (`build_directional_response_basis` and the other `return None` paths it uses), `src/crane_statics/calculation/engine.py`, `src/crane_statics/core/analysis_services.py` (`AnalysisCalculator.compute_analysis_point`), `src/crane_statics/qml_app/viewmodels/scene_vm.py`
- Test: `tests/test_app_consistency_fixes.py`, plus the existing scene view-model test module.

**Interfaces:**
- Consumes: `CraneCalculator.unavailable_reason` (Task 4).
- Produces: `AnalysisCalculator.unavailable_reason() -> Optional[str]` (reason from the last `compute_analysis_point`); `SceneVM.statusMessage` emits it when the Scene analysis is unavailable.

- [ ] **Step 1: Write failing tests.**
  - `test_no_solve_rope_gives_reason`: 22689 with the solve rope's `tension_mode` changed so no rope has `tension_mode == "solve"`: `compute_analysis_point` is `None` and the reason mentions "solve" and "rope".
  - `test_each_none_path_has_a_reason` (parametrised): enumerate the `return None` paths in `build_directional_response_basis` and `compute_analysis_point` (missing hoist, no solve rope, missing required node, etc.); each triggered case yields a non-empty reason. If a path is reached only by a bug/defensive guard, give it the generic reason "Analysis unavailable: <path>".
  - `test_scene_vm_emits_reason`: with the no-solve-rope document loaded in `SceneVM`, a refresh emits `statusMessage` with that reason once (not on every repaint with unchanged state).
  - `test_success_clears_reason`: after a failing then a succeeding call, `unavailable_reason` is `None` and no message is emitted.
- [ ] **Step 2: Run; expect FAIL.**
- [ ] **Step 3: Implement.** Set reasons at each `None` path using sentences in the style of existing `statusMessage` texts. Emit from the scene view-model at the point where it refreshes analysis results (follow the pattern of `statusMessage.emit` at the Auto handling), de-duplicated against the last emitted text.
- [ ] **Step 4: Run new tests, the QML shell tests and the full suite; expect only the known unrelated failure.**
- [ ] **Step 5: Commit.**

---

### Task 6: Workbook follows the fixed app

**Preconditions:** Tasks 1-5 merged to `main`; branch `excel-validation-workbook` (worktree `C:\Users\ReefB\Desktop\crane_statics-xlsx`, tip 67ca296) rebased onto it. Resolve conflicts keeping the branch's `scripts/`, tests and docs; if `reference.py` or tests break on v11 (`hoists`, removed `clear_calculator_cache`), fix them here.

**Files:**
- Modify: `scripts/excel_workbook/layout.py`, `layout_oop.py`, `build_oop.py`, `build_results.py`, `build_loads.py`, `reference.py` (docstring sign conventions and dependency list), `docs/excel-validation-workbook.md`
- Regenerate: `tests/golden/22689_workbook_cases.json` (`python -m scripts.excel_workbook.reference`), `docs/crane-statics-validation-22689.xlsx` (`python -m scripts.excel_workbook.build examples/crane_input_22689.yaml docs/crane-statics-validation-22689.xlsx`)
- Test: existing `tests/test_excel_workbook_*.py`

- [ ] **Step 1: Rebase, regenerate the golden file from the fixed app, run the workbook tests; expect FAILS exactly at `platform_base` Fy/Mx, the left/right pairs and Y-wind boom loads (case 3).** Anything else failing is a rebase issue; fix it first.
- [ ] **Step 2: Update the workbook formulas.** Negate platform Fy and Mx (support-on-crane); swap the left/right result rows' formulas (or labels, whichever the layout makes simpler and clearer on `Conventions`); remove sin θ on Y-wind boom areas in the OutOfPlane wind block while keeping it on X-wind boom areas. Update the `Conventions` sheet text and the guide's "Known limits and deliberate app parity" section: remove the three resolved quirks and keep the deferred ones.
- [ ] **Step 3: Run the workbook tests; expect PASS at 0.01 kN / 0.01 kNm on all four cases; GT283 and 13778 smoke tests pass.**
- [ ] **Step 4: Regenerate the delivered `.xlsx`; commit** the changed scripts, goldens, workbook, docs.

---

### Task 7: New workbook checks

**Files:**
- Modify: `scripts/excel_workbook/layout.py` (`CHECK_DESCRIPTIONS`), `build_checks.py`, `build_inputs.py`, `build_geometry.py` as needed
- Test: `tests/test_excel_workbook_checks.py`, `tests/test_excel_workbook_robustness.py`

- [ ] **Step 1: Write failing tests.**
  - `test_bearing_diameter_must_be_positive`: diameter 0 and -1 trip a Checks cell (the app rejects it at validation).
  - `test_boom_local_on_non_boom_body_is_flagged`: a node or mass row with a boom-local coordinate type on a non-boom body trips a check.
  - `test_row_inserted_at_table_start_or_end_is_flagged`: a row inserted as the first data row, or between the last data row and the guard row, trips the `mirror` check (extend the existing mirror mechanism; if a guard can't catch the first-row case in `formulas`, document the limit and test the last-row case only).
- [ ] **Step 2: Run; expect FAIL.**
- [ ] **Step 3: Implement the checks in the same style as the existing ones (a count cell plus a description, stop-style validation where it applies).**
- [ ] **Step 4: Run the workbook tests; expect PASS.**
- [ ] **Step 5: Commit.**

---

### Task 8: Final verification and handoff

- [ ] **Step 1: Run the full suite and `pre_commit run --all-files`; expect only the known unrelated failure.**
- [ ] **Step 2: Confirm the regenerated 22689 `.xlsx` has no error values (`test_no_error_values_anywhere`) and `fullCalcOnLoad` set.**
- [ ] **Step 3: Write the handoff: list of changed numbers by golden file, any consumer that needed adaptation (Task 1), any example near the 1e-12 threshold (Task 4), and the reminder that the workbook is verified with the `formulas` library only, so the user should open it in Excel 2016 or later and compare the four cases.**
- [ ] **Step 4: Commit.**

---

## Self-Review

- Spec coverage: fix 1 (T1), fix 2 (T2), fix 3 (T3), fix 4 (T4), fix 5 (T5), workbook formulas/regeneration/docs (T6), new checks (T7), acceptance and handoff (T8). Non-goals (name-based rules, arrow-vs-solver differences) are not touched.
- Types: `unavailable_reason` is defined in T4 (`CraneCalculator`) and consumed in T5; `is_ill_conditioned` only in T4.
- Known risk: T4's reason carrier through `_run_statics` and the basis depends on the v11 code shape; the implementer picks the least invasive carrier and reports it.
