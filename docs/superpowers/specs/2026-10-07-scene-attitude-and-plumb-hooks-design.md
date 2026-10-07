# Scene: no water, plumb hooks, scene-only heel/trim

## Context

The heel/trim/slew branch (`feature/vessel-heel-trim-slew`) shows vessel tilt in the Scene only as a sloped waterline and tilted force arrows. The hooks still hang straight down in the crane frame, and heel and trim can only be set in Model > Environment, which also changes the load charts. Requested changes:

1. Stop drawing the water in the Scene.
2. Draw every hook directly below its upper block (sheave) along the plumb line for the current heel/trim/slew.
3. Let heel and trim be entered in the Scene. The values affect only the Scene, not the Model inputs or the load charts.

**Classification:** architectural, because it changes scene-only state flow, the drawn-load model and the scene frame contract.

### Decisions

- **Seeding.** The Scene's heel/trim follow the Model's until edited in the Scene. After that the Scene keeps its own values, until the user clicks **Reset to Model** or loads a document.
- **Scope of the override.** It applies to the whole vessel, so every hoist sees it. Slew stays per hoist.
- **No side effects.** Scene heel/trim are never saved, do not mark the document dirty, and do not make the Load Chart stale.
- **Plumb hooks are drawing only.** A free-hanging hook loads its sheave with H·ĝ wherever it sits on the plumb line, so the solver, reactions, charts, auto-set and the level goldens do not change.
- **Which hooks.** The active hook hangs at its tackle length. Idle hooks hang at their 1.0 m placeholder drop. The boom hoist has no hook.
- **Outreach.** Outreach stays the crane-frame sheave X used by the R label, the spinbox, dragging and the chart. The R guide moves to the sheave's x, so a leaning hook does not shift it.
- **Out-of-plane tilt.** It is not drawn, because the scene is a 2-D luffing-plane projection. It stays a text readout.
- **Water removal.** The fill, the line and the MSL label all go. `environment.mean_sealevel_z_m` stays in the document, since other code uses it.
- **Tackle drag.** It keeps mapping vertical pointer motion to tackle length. The error is at most 1 − cos(in-plane tilt).

## Design

### A. Remove the water

Delete the whole waterline pipeline:
- `core/scene_build.py`: delete `_draw_waterline`, the `_msl_*` state and the `set_waterline` call in `_publish`, and update the fit-rect comment at :424.
- `core/scene_frame.py`: delete `SceneWaterline`, `SceneFrame.waterline`, the builder's `waterline` and `set_waterline`.
- `qml_app/adapters/scene_adapter.py`: remove the `"waterline"` key from both `empty_scene_frame` and `scene_frame_to_dict`.
- `qml_app/qml/scene/QuickSceneCanvas.qml`: remove `waterline*`, `waterlineYAt`, the `sea` Shape (:196-223) and the MSL label (:406-413).

### B. Scene-only heel/trim

**Core state.** In `core/session_model.py`, `SessionModel` gets `scene_attitude_override: Optional[VesselAttitude]`, which `set_document` clears. It also gets these methods:
- `document_attitude()` returns the attitude from `document.environment.vessel_motion`, or level when there is no document.
- `scene_attitude()` returns the override, falling back to `document_attitude()`.
- `scene_attitude_overridden` is true when an override exists and differs from the document's attitude.
- `set_scene_attitude(heel_deg, trim_deg)` clamps each angle to ±`MAX_VESSEL_TILT_DEG` (`data/authored_models.py:65`).
- `reset_scene_attitude()` clears the override.
- `scene_document()` returns `document` when it is not overridden, otherwise `document_with_attitude(document, scene_attitude())`.

**Pure helpers.** New module `core/scene_attitude.py`:
- `document_with_attitude(doc, attitude)` makes a shallow `model_copy(update=…)` chain: document → environment → vessel_motion.
- `document_dict_with_attitude(document_dict, attitude)` makes shallow dict copies of the same three levels. It must never mutate the cached `KinematicsAdapter.doc`.
- `AnalysisPresenter._overview_point_demand(level_vessel=True)` should reuse `document_with_attitude(doc, VesselAttitude())` instead of its deep copy at `analysis_presenter.py:251-254`.

**Solve side.** These sites switch to `session.scene_document()`. The chart (`core/sweep.py`), auto-set (`core/limit_auto_set.py`) and the Model workspace keep reading `session.document`, so they stay untouched.
- `core/analysis_services.py:235` (`compute_analysis_point`)
- `core/analysis_services.py:470` (`compute_auto_load`)
- `core/analysis_presenter.py:248` and `:279`
- The `tilted` check at `analysis_presenter.py:325-327` becomes `not session.scene_attitude().is_level`.

**Draw side.**
- `scene_vm._scene_inputs` (`scene_vm.py:129-130`) builds `document_dict = document_dict_with_attitude(kinematics.doc, model.scene_attitude())`.
- Every scene reader of `environment.vessel_motion` then sees the scene attitude: `SceneInputs.vessel_attitude()`, `drawn_crane_gravity`'s fallback, `_LoadBuilder`, and the Equilibrium Check through `_publish_report`.
- No change is needed to `LoadConditions`, the engine or ADR-0002's rule.

**View model** (`qml_app/viewmodels/scene_vm.py`):
- New properties: `heel` and `trim` (notify `attitudeChanged`), `attitudeOverridden`, and the constant `maxTiltDeg`.
- New slots: `setHeel`, `setTrim` and `resetAttitude`.
- They share a private `_set_scene_attitude`. It calls `model.set_scene_attitude`, emits `attitudeChanged`, then runs `recomputeAutoLoad()` if the active hoist's load is on Auto, otherwise `_after_state_changed()`.
- It deliberately does not call `mark_content_changed`: no dirty flag and no chart going stale.
- Remove `vesselLevel` and `vesselAttitudeText` and their readout keys; the spinboxes replace them. Delete `VesselAttitudeFormatter.attitude_text` if nothing else calls it.
- `reload()` already emits `attitudeChanged`, so Model edits flow into the spinboxes while the Scene is not overridden.

**QML** (`SceneControlRail.qml:113-165`, following the `qml-ui-development` skill):
- Replace the "Attitude:" label row with two `NumericRow`s, both ±`sceneVm.maxTiltDeg` with 2 decimals:
  - "Heel (°, + stbd down):"
  - "Trim (°, + bow down):"
- Add a **Reset to Model** button that is enabled when `sceneVm.attitudeOverridden`.
- Keep the slew row and the in-plane and out-of-plane readouts.

### C. Plumb hooks

**Positions** (`core/scene_build.py`).
- `SceneInputs.node_positions()` returns `plumb_hook_positions(base, hook_drops, self.crane_gravity())`. This replaces `SceneFrameBuilder.with_hook_tackle` (`scene_frame.py:269-288`), which moves out of the frame builder.
- `hook_drops` maps each hoist whose load node is a hanging node to `(sheave_id, drop_m)`:
  - The sheave comes from `rope_mass.hook_support_node_id`, the same lookup `drawn_loads._sheave_of` uses.
  - The drop is the clamped tackle length for the active hoist, and the node's `hanging_drop_m` (default 1.0) otherwise.
- `hook = sheave + drop·(lateral_x, −vertical)`. On a level vessel this gives exactly today's positions.
- `base_node_positions()` (kinematic, used for the boom axes) is unchanged.

**Drawn loads** (`core/drawn_loads.py`):
- `hook_load()`: the gravity part (H·lateral_x, −H·vertical) is drawn at the hook. Offlead `sin(offlead)·H` stays at the sheave, labelled "Offlead". The "(offlead + tilt)" label goes away.
- `idle_hook_mass_node_forces()`: the whole weight acts at the idle hook.
- Each hook lies on its sheave's plumb line and the force is parallel to that line, so the moments equal the solver's split (vertical below the sheave, lateral at the sheave).
- The hook node shares its sheave's body (`models.py:706-708`), so the slanted fall is internal and collinear, and cancels.
- Document in the `build_body_loads` docstring that `node_positions` must be the positions as drawn.

**Guides** (`scene_build.py:768-783`, `:441-493`):
- The hook-height guide and the tackle hit target stay at the drawn hook.
- The outreach guide and its hit target are anchored at (sheave scene x, hook scene y). The R label reads the kinematic load-node x, which is the spinbox outreach.

**Solver.** Untouched (`crane_solver`, `rope_mass`, `engine`).

### D. Docs

- **`docs/adr/0003-vessel-attitude-and-slew-envelope.md`:** amend :27-29 to say the Scene may override heel/trim for its own solve only. Replace the waterline sentence at :65 with the plumb-hook drawing rule.
- **`CONTEXT-EXTENDED.md`:**
  - drop "waterline" at :145;
  - list slew and the scene attitude override under "Scene state";
  - add a note under "Vessel attitude".

## Implementation order (TDD: failing test first for each step)

1. Water removal. Update the adapter key-set test (`tests/test_scene_adapters.py:15-32`), then remove the pipeline. Also update `test_scene_view_model.py:158-164` (keep the guide checks) and `:433-438`, `test_scene_frame.py:63,87`, and delete `TestTiltedWaterline` in `test_scene_vessel_attitude.py:87-118`.
2. Core scene attitude, with tests in a new `tests/test_scene_attitude.py` (no Qt). Use the `_tilted` and `_scene_services` helpers from `tests/test_vessel_attitude_statics.py:51-55, 258-278`. Test that:
   - the scene attitude follows the document and the setter clamps;
   - `set_document` clears the override;
   - `scene_document()` returns the same object when not overridden, and `session.document` is unmutated when overridden;
   - the dict helper does not mutate its input;
   - the point's `crane_gravity` equals `crane_frame_gravity(override, slew)`;
   - auto-load follows the override;
   - the contribution overview has a "Vessel attitude" term and `delta_kN ≈ 0` when a level document is overridden.
3. Scene attitude in the view model and QML. Tests in `tests/test_scene_vessel_attitude.py` using the `_scene_vm` helper (:17-27) check that:
   - `setHeel`/`setTrim` update the readouts and the point's gravity;
   - `session.dirty` stays False;
   - the override survives a hoist switch;
   - Reset and document reload restore the Model's values;
   - Model edits flow through while not overridden.

   A test modelled on `tests/test_chart_view_model.py:285-333` checks the chart curve and `conditionText` are unchanged and the chart is not stale after a Scene heel edit.
4. Plumb hooks. Test that:
   - `plumb_hook_positions` returns identical positions on a level vessel;
   - on a tilted vessel, hook − sheave equals drop·(lx, −v) for the active and idle hooks, and the boom-hoist node is untouched;
   - the R label and the outreach guide x are unchanged by tilt.

   Strengthen `TestDrawnLoadsBalanceTheTiltedSolve` (`test_vessel_attitude_statics.py:206-255`): assert the drawn hook actually leans, so the closure check is meaningful, then keep every free body closing. Update the `test_scene_frame.py:193` test (`with_hook_tackle`) for the move.
5. Docs (section D).

## Verification

- Full `pytest` suite, plus the lint and type checks configured in `pyproject.toml`. `tests/test_level_attitude_goldens.py` must pass unchanged, which proves the solver is untouched. The `test_architecture.py` guards and the "scene_vm imports no `crane_statics.calculation`" guard (`test_scene_vessel_attitude.py:146-156`) must pass too.
- `run-app` skill: screenshot the Scene at heel 5°, trim 2°, slew 90°. Confirm there is no water, the hooks visibly lean along the plumb line, the Equilibrium Check passes, the title shows no unsaved mark, and the Load Chart is not stale. Then click Reset to Model and confirm the Model's values return.
- Run the `domain-boundary-reviewer` agent on the diff, since it touches `session_model.py`, `scene_adapter.py` and the view model.

## Known non-changes

- Slew and the other `SceneState` edits still call `mark_content_changed`, so they still dirty the document and stale the chart. That is existing behaviour and is left alone.
- The solver's hook stays directly below its sheave in the crane frame; only the drawing changes.
