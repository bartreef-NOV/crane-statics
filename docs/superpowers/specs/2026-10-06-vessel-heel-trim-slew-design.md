# Vessel heel, trim & slew — load charts as a 360° slew envelope

## Context

The crane sits on a vessel, but the statics model assumes a level base:
- The solver is planar (X–Z, the luffing plane).
- Gravity is hardcoded as −Z in `calculation/solver/crane_solver.py`, `calculation/engine.py` and `core/drawn_loads.py`.
- Load charts (`core/sweep.py::run_capacity_sweep`) are a 1-D capacity-vs-outreach sweep over the four wind directions.

Users need to enter a static **heel** and **trim** for the vessel and a **slew** angle (0–360°) for the crane. The load charts must then reflect the tilted gravity in combination with any slew angle.

**Decisions (from the user):**
- Heel and trim are a saved design condition in the YAML, edited in the Model → Environment panel.
- Slew is a Scene operating input in `SceneState` and is not saved.
- The load chart is the worst case **envelope over 0–360° slew** at the document's heel and trim. There is no per-slew chart.
- The chart x-axis stays crane-frame outreach (sheave position). The plumb-hanging hook is modelled as extra off-lead and side-lead.
- The Scene draws the waterline tilted by the in-plane tilt, gets a slew control, and shows readouts of the in-plane and out-of-plane tilt.
- Four existing statics bugs are fixed first, because tilt makes them material. The user selected all four.

**Out of scope:**
- Hydrostatics and load-induced heel.
- The crane's position on deck. A uniform gravity field makes static tilt independent of it.
- Vessel-frame accelerations. `vessel_motion` accelerations stay in the crane frame as today.
- A per-slew or per-sector chart.
- Drawing the hook plumb in the scene.
- The split pass giving every support group every body's masses (`engine.py:366-372`). This is existing behaviour and needs its own modelling decision.
- The double solve per scene edit.

On approval:
- Copy this plan to `docs/superpowers/specs/2026-10-06-vessel-heel-trim-slew-design.md`.
- Work on a new branch `feature/vessel-heel-trim-slew`, cut from the current branch.
- Use TDD in every phase. Each phase gets its own commits.

## Conventions and physics

**Crane frame:** X = outreach, Z = up, Y = crane-left. This is right-handed, as implied by `Mx = y·Fz − z·Fy` at `engine.py:371`. Document this in the `y_m` schema descriptions.

**Vessel frame:** x = forward, y = port, z = up.

**Signs:**
- Heel φ is positive when starboard is down.
- Trim θ is positive when the bow is down.
- Slew ψ is measured from the bow, positive clockwise seen from above (towards starboard).
- Rotation order is ZYX.

**Unit gravity in the crane frame:**
- `lateral_x = sinθ·cosψ + sinφ·cosθ·sinψ` (in-plane, + toward the boom tip)
- `lateral_y = sinθ·sinψ − sinφ·cosθ·cosψ` (out-of-plane)
- `vertical = cosφ·cosθ`. This does not depend on slew, so it is constant for a document.

**Linear decomposition.** The design agent checked this against the code.
- **Vertical part:** applied inside `_accumulate_loads`, never by post-scaling the basis. It scales:
  - mass points and rope-weight lumps: `gravity_eff = g·vertical` and `ax_eff = ax − g·lx` into the unchanged `inertia_force`
  - the hook-node force: `ld_fz -= H·vertical`
  - idle hook masses
  - the split compensation mass

  It does **not** scale rope tensions. Tensions stay H/n and m·g/n, because the hook hangs plumb.
- **Lateral parts:** these change with slew, so they become cheap unit channels on the `AnalysisPoint`:
  - In-plane `gravity_lateral_x_unit_*` is the response to g along +X. It covers masses, rope lumps, idle hooks (lateral part applied at their sheave) and the comp mass, and excludes rope tensions, wind and the hook.
  - Out-of-plane `gravity_lateral_y_unit_reactions` comes from the split pass.
  - Hook load direction: `sensitivity += lx·offlead_lateral_unit + ly·sidelead_lateral_unit`.

**Envelope sampling.** Let ψ* = atan2(sinφ·cosθ, sinθ). Sample a rotated grid ψ* + k·15°, which gives 24 samples and includes ψ*+{0, 90, 180, 270}.
- A level attitude gives the single sample `(0.0,)`, so results stay exactly as today.
- The under-estimate per linear output is ≤ R·hypot(Cx, Cy)·(1 − cos 7.5°).

## Phases

### P0 — Calculator cache (correctness prerequisite)
- `calculation/engine.py`: `get_calculator()` returns a fresh `CraneCalculator(document)`. Construction costs 0.13 ms against 1.2 ms per point. Delete `_CALCULATOR_CACHE` and `clear_calculator_cache`; nothing references them.
- Tests:
  - a Model edit followed by a Scene result reflects the edit (reproduce the stale platform Fz)
  - no growth across chart sweeps

### P1 — Existing statics fixes (one commit and test each, before any tilt code)
- **(a) Exceeded limits.** In `CraneCalculator.compute_allowable_load`, accept `0.0 <= h < h_max` at `engine.py:793, 807, 821, 844, 862`. Replace the linear branch with magnitude semantics:
  - |baseline| > limit → 0
  - sens > tol → (lim − b)/s
  - sens < −tol → (lim + b)/−s
  - otherwise → inf

  This matches the `abs()` already used in result rows and `demand_extraction.py:104`. `calculation/capacity.py` already returns 0 or inf correctly. Factor the per-limit loop into a helper that returns per-limit H candidates; P5 reuses it. Test: a limit at half its baseline gives capacity 0 and is the governing limit.
- **(b) Split comp mass as Fz.** At `engine.py:443-446`, use `fz_comp = −m·g`. Test: split-mode platform Fy ≈ 0.
- **(c) Platform Mx origin.** At `engine.py:351`, take the `platform_base` origin from `node_pos["platform_base"]`, the same point used for M/My.
- **(d) Left/right split signs.**
  - `engine.py:474-477`: one consistent convention, with left = +Y and reactions acting on the body, for both Fx and Fz.
  - `engine.py:551`: report `platform_base` Fy as a reaction (−Σ applied), like Fx/Fz.
  - Make `test_acceptance.py:932/964` sign-aware.
- **(e) Sidelead at the sheave.**
  - Apply the side unit force at the support node (`below_node_id`), as offlead does.
  - The split pass uses the basis geometry (tackle-aware `node_pos` and rope lumps) through new `DirectionalResponseBasis` fields, instead of re-running `compute_all_node_positions`.
- **Golden capture.** Then capture level-attitude goldens (whole `AnalysisPoint` dicts plus sweep `curve_data` on `examples/crane_input_22689.yaml`) for the regression test in P4/P5.

### P2 — Pure attitude module
New `calculation/vessel_attitude.py`, pure and fully typed, containing:
- `VesselAttitude(heel_deg, trim_deg)`, with `.from_environment(mapping)` and `.is_level`
- `CraneFrameGravity(lateral_x, lateral_y, vertical)`, with properties `in_plane_tilt_deg`, `out_of_plane_tilt_deg` and `total_tilt_deg`
- `crane_frame_gravity(att, slew_deg)`
- `worst_in_plane_slew_deg(att)`
- `envelope_slew_angles(att, step_deg=15.0)`, which asserts `90 % step == 0`
- `normalize_slew_deg`, mapping to [0, 360)

Tests in `tests/test_vessel_attitude.py`:
- cardinal cases
- unit norm
- ψ*
- level gives `(0.0,)` with exactly 1.0 / 0.0 / 0.0
- the grid contains ψ*+{0, 90, 180, 270}

### P3 — Schema and data (inert until P4)
- `data/authored_models.py`:
  - add `heel_deg` and `trim_deg` to `AuthoredVesselMotion` (default 0, `ge=-30, le=30`, sign conventions in the descriptions)
  - bump `AUTHORED_SCHEMA_VERSION` to `"6.1.0"`
  - regenerate with `schemas/generate_schema.py`
- `data/models.py`:
  - add signed fields to `VesselMotion`, excluded from the ≥0 validator
  - add the keys to `DEFAULT_VESSEL_MOTION`
  - normalization (~:1154-1192) reads them without `abs()`
  - write-back in `document_to_authored_form` omits zero values (existing behaviour)
- UI:
  - `qml_app/viewmodels/model_vm.py`: `VESSEL_MOTION_KEYS` plus a clamp, because `setattr` bypasses validation
  - `qml_app/contracts.py::EnvironmentSettings`
  - `presentation/formatters.py` `EnvironmentFormatter._PROPERTY_LABELS`
  - `EnvironmentPanel.qml` rows "Heel (°, + starboard down)" and "Trim (°, + bow down)"
- Tests:
  - `test_document_io_formats.py`: round-trip, omitted = 0, negatives OK, out-of-bounds rejected
  - `test_document_edit.py`: environment keys
  - `test_schema_contract.py`
  - update the 6.0.0 version assertions

### P4 — Solver channels and drawn loads (one phase, so the Equilibrium Check keeps proving the solver)
- **`crane_solver.py`:**
  - `_accumulate_loads` gains `gravity_vertical_fraction` and `gravity_lateral_x_fraction`, applied as described under Conventions.
  - `build_directional_response_basis` adds a `gravity_x_raw` channel, skipped when level.
  - `compose_unit_basis_point` emits `gravity_lateral_x_unit_*`.
- **`engine.py`:**
  - `_build_split_support_reactions` gets the vertical scaling and a `gravity_y` unit channel (parity with `accel_y = −g·ly`).
  - `_augment_point_with_split_supports` adds split-entity entries (0.5 × the total entity) for the offlead and gravity-x channels. Today `heel_left` etc. would silently miss lateral-x terms.
  - New `AnalysisPoint` fields: `gravity_lateral_x_unit_rope_tensions`, `gravity_lateral_x_unit_reactions`, `gravity_lateral_y_unit_reactions`, `crane_gravity` and `slew_deg`.
- **Compose function.** New pure `compose_lateral_channels(point, *, hook_lx, hook_ly, gravity)` in `calculation/point_composition.py`. It allocates fresh nested dicts. Reimplement `limit_auto_set._compose_lead_channel_point` on top of it.
- **Analysis entry points.** `CraneCalculator.compute_analysis_point(..., slew_deg=0.0)` composes at one slew. Log the exceptions it currently swallows at `:698`.
- **`core/drawn_loads.py`:**
  - `LoadConditions` gets `slew_deg: float = 0.0`. The fractions are not carried here; they are derived from `document_dict["environment"]` through the same `vessel_attitude` function, per ADR-0002.
  - `gravity()`, `rope_weight()` and `idle_hook_mass_node_forces()` change: vertical at the hook, lateral at `below_node_id`.
  - `hook_load()` changes: fz = −H·vertical, sheave lateral = (sin(offlead) + lx)·H, and the `abs(offlead)` gate is removed.
- **Scene and presenter callers.** `core/analysis_services.py` `compute_analysis_point` (:245) and `compute_auto_load` (:485) pass `SceneState.slew_deg`. So do the `_overview_point_demand` calls in `core/analysis_presenter.py` (:219, :278).
- **Tests in `tests/test_vessel_attitude_statics.py`**, using `test_optional_slewing_bearing_diameter.py` as the template:
  - level golden `==`
  - whole-crane invariants: platform Fx = −g·lx·M, Fz = g·vertical·M, sensitivities Fz = vertical and Fx = −(lx + sin offlead)
  - trim over the bow equals the explicit accelerations `ax = −g·sinθ`, `az = −g(1−cosθ)`, with idle hook masses at 0 and not in split mode
  - composing equals a direct build, including split entities
  - mirror symmetry on a copy with `y_m = 0`
- **Tests in `test_acceptance.py`:** equilibrium closes for every free body at several slews, via `scene_inputs_at_drawn_tackle(..., slew_deg=…)`.

### P5 — Envelope in the chart and Auto-Set
- New `CraneCalculator.compute_slew_envelope_points(...) -> list[(slew_deg, AnalysisPoint)]`. It builds the basis once and composes at each `envelope_slew_angles` sample.
- **Performance:**
  - Build one in-plane basis per outreach for all four wind directions: ±X differ only in sign, ±Y have in-plane wind 0, and only the split pass differs.
  - Use the single-pass per-limit candidates from P1(a), so the sweep derives the overall and the per-limit minima from one evaluation per point.
  - Add `governing_slew_deg` to `AllowableCapacity`.
- `core/sweep.py::_wind_points` and `_min_capacity` loop over the envelope points. Contractual verdicts therefore use the envelope.
- `core/limit_auto_set.py::_evaluate_contractual_points` (:164-208) loops over the slew points and records the governing slew in `ContractualPointResult`.
- `compute_omnidirectional_allowable_load` gains `slew_deg`, so the Scene auto-load uses the selected slew.
- **Tests:**
  - envelope ≤ capacity at each sampled slew, and ≤ a few off-grid slews plus the amplitude bound
  - heel 3° / trim 0 envelope == heel 0 / trim 3° envelope
  - level sweep == golden
  - `test_chart_view_model.py`: heel set through `model_vm.setEnvironmentValue` → redraw → curve changes and equals the core sweep
  - timing check: tilted sweep ≤ ~3× level, level unchanged

### P6 — Scene UI
- `core/session_model.py::SceneState.slew_deg = 0.0`.
- `qml_app/viewmodels/scene_vm.py`:
  - `slew` property and `setSlew` slot through `_set_scene_field`, wrapped to [0, 360)
  - readouts `inPlaneTiltText`, `outOfPlaneTiltText` and `vesselAttitudeText`, formatted in `presentation/formatters.py`
  - `_load_conditions` (:143-158) passes `slew_deg`
- `SceneControlRail.qml`: a slew `NumericRow` (0–360) plus the readouts. Follow the qml-ui-development skill: Metrics/Typography tokens, no computing in getters.
- **Waterline:**
  - `core/scene_frame.py::SceneWaterline` gets defaulted `pivot_x`, `pivot_y` and `slope` fields, so existing frames still build.
  - `core/scene_build.py::_draw_waterline` and `_publish` emit a scene slope of −lx/vertical, pivoting at `platform_base` x and MSL z.
  - `QuickSceneCanvas.qml:190-208` draws a `Shape` polygon in place of the horizontal `Rectangle`, and fixes the dead `mslLabelText` (`z_msl` → `elevation_z`).
- **Tests:**
  - `test_scene_view_model.py`: slew wraps, readouts, slew has no effect when level
  - `test_scene_frame.py`: slope

### P7 — Chart labelling and docs
- `chart_vm`: a `conditionText` property, e.g. "Envelope over 360° slew · heel 3.0°, trim 1.0°", empty when level. Show it in `LoadChartWorkspace.qml`.
- New `docs/adr/0003-vessel-attitude-and-slew-envelope.md` covering frames, signs, the linear decomposition, envelope semantics, and that the Scene shows the selected slew while the chart shows the envelope.
- A scope note in ADR-0002: the in-plane part of tilted gravity is drawn; lateral_y stays out of plane.
- `CONTEXT-EXTENDED.md` terms: vessel heel vs `boom_heel` / `heel_world`.

## Critical files
- `src/crane_statics/calculation/solver/crane_solver.py`
- `src/crane_statics/calculation/engine.py`
- `calculation/vessel_attitude.py` (new)
- `calculation/point_composition.py` (new)
- `src/crane_statics/core/drawn_loads.py`
- `core/sweep.py`
- `core/limit_auto_set.py`
- `core/analysis_services.py`
- `core/analysis_presenter.py`
- `src/crane_statics/data/authored_models.py`
- `data/models.py`
- `src/crane_statics/qml_app/viewmodels/scene_vm.py`
- `chart_vm.py`
- `model_vm.py`
- `core/scene_build.py`
- `core/scene_frame.py`
- `QuickSceneCanvas.qml`
- `SceneControlRail.qml`
- `EnvironmentPanel.qml`

Existing code to reuse:
- `_compose_lead_channel_point` (limit_auto_set.py:81)
- the offlead/sidelead unit channels
- `iter_wind_directional_cases`
- `solve_capacity_limit_kN` / `solve_radial_capacity_kN` (capacity.py)
- `_set_scene_field` (scene_vm.py:612)
- `NumericRow.qml`
- the `test_optional_slewing_bearing_diameter.py` pattern

## Verification
- `pytest`: the full suite, including the new attitude, statics, acceptance, chart, scene and schema tests.
- `mypy src`.
- `python src/crane_statics/schemas/generate_schema.py --check`.
- The design agents (`schema-contract-reviewer` and `domain-boundary-reviewer`) after P3, P4 and P6.
- Regression: with a level attitude, every golden is identical (exact `==`).
- End-to-end with the run-app skill on `examples/crane_input_22689.yaml`:
  1. Set heel 3° and trim 1° in Model → Environment.
  2. In the Scene, slew 0→90→180 and confirm the waterline tilt, the readouts and that the Equilibrium Check closes.
  3. In Load Chart, confirm the curve lies on or below the level curve, the condition label shows, and contractual verdicts update.
  4. Save, reload and check the YAML contains `heel_deg` / `trim_deg` and schema 6.1.0.
