# Load Chart Envelope Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The load chart reports the lowest capacity over every slewing angle, every wind direction, both signs of the hoist's offlead and sidelead, and both signs of the seven Model vessel-motion limits, at least 10x faster than the current enumeration.

**Architecture:** Capacity is evaluated on analysis points that are exactly affine in the crane-frame load channels (surge, sway, heave, pitch accel, roll accel, wind-x, wind-y). So each boom angle needs only 8 probe solves (zero + 5 motion channels + 2 wind channels); every case is then a vector combination of probes. Linear limits use the closed form over slew (`B0 + sqrt(P^2+Q^2)`) and over wind angle (`max(|a|,|b|)`); magnitude limits use a vectorised scan. The current brute force moves into `tests/` as the reference.

**Tech Stack:** Python 3.13, numpy, pydantic, PyQt6/QML, pytest. Use `.venv/Scripts/python.exe`.

**Spec:** `docs/superpowers/specs/2026-10-17-load-chart-envelope-design.md`

**Process note:** Do not commit unless the user asks (repo instruction). Steps end with a green test run instead.

## Global Constraints
- Vessel input names everywhere: Surge, Sway, Heave (m/s^2); Roll, Pitch (rad/s^2); Roll angle, Pitch angle (deg). Data keys (`accel_x_m_s2`, `roll_deg`, ...) are unchanged.
- Model vessel motion values are magnitudes (sign ignored via `abs`); `vessel_limit` / `vessel_motion_cases` in `core/vessel_envelope.py` already do this.
- Authored schema becomes major version 8 (`AUTHORED_SCHEMA_VERSION = "8.0.0"`, file `crane-statics-v8.schema.json`); `crane_slewing_angle_deg` is removed from the Model. Scene slewing angle stays (Geometry group), starts at 0.
- Wind at angle theta (from +X toward +Y, degrees) uses per-axis components: Fx from `area_w` with `(V cos theta)^2`, Fy from `area_v` with `(V sin theta)^2`, signs kept. Axis angles 0/90/180/270 equal today's `+X/+Y/-X/-Y` exactly.
- Fast path may be lower than brute force by at most 0.5% but never higher beyond 1e-6 relative.
- Sidelead force acts at `hoist.support_node_id` (the sheave), not `hoist.load_node_id`.
- Chart includes the hoist's authored `offlead_deg` and `sidelead_deg` with both signs (as Auto-Set does).
- Performance: >= 10x faster than 3.7 s on `examples/crane_input_GT283.yaml`, hoist `MH`, outreach step 2.0, limits `{"boom_hoist": {"T": 5000.0}}`, all seven vessel limits nonzero (accel 1,1,1; angular 0.1,0.1; angles 5,5). With all limits zero, no slower than today.

## Review Focus
- Wind speed 0: one case, no wind channels probed; result equals the no-wind capacity.
- All seven vessel limits zero: capacity equals today's value (slew, signs irrelevant).
- Masses with nonzero `y_m`: sway/roll sign flips must not be assumed symmetric (probes capture it); test with a modified example.
- A limit that does not respond to hook load (`_affects_hook_load` false): no per-limit series point, same as today.
- Split hook mode overrides and `hook_mass_t`: envelope uses the same `hoist_runtime_overrides` as today.
- Hoist with offlead/sidelead 0: lead cases collapse to one.
- Cancellation mid-sweep still raises `SweepCancelled`.
- Document without `vessel_motion` limits and negative authored limits (v8 files can still hold a negative value): treated by magnitude.

---

### Task 1: Schema v8 — remove the Model slewing angle

**Files:**
- Modify: `src/crane_statics/data/authored_models.py` (`AUTHORED_SCHEMA_MAJOR_VERSION = 8`, `AUTHORED_SCHEMA_VERSION = "8.0.0"`, drop `crane_slewing_angle_deg` from `AuthoredVesselMotion`, update docstring)
- Modify: `src/crane_statics/data/models.py` (`DEFAULT_VESSEL_MOTION`, `VesselMotion`)
- Modify: `src/crane_statics/core/session_model.py` (seed `crane_slewing_angle_deg=0.0`)
- Modify: `src/crane_statics/qml_app/viewmodels/model_vm.py` (`VESSEL_MOTION_KEYS`), `qml_app/contracts.py` (`EnvironmentSettings`), `qml_app/qml/EnvironmentPanel.qml` (delete the "Crane Orientation" group), `presentation/formatters.py` (drop the label)
- Regenerate: `python -m crane_statics.schemas.generate_schema` (deletes nothing; `git rm` the v7 file)
- Modify: `examples/*.yaml` (version line), `README.md:119`, `docs/cpp-port-plan.md:17`, `CONTEXT-CORE.md`, `CONTEXT-EXTENDED.md`
- Test: `tests/test_vessel_motion_schema.py`, plus every test pinning `7.0.0`/`7.1.0`/major 7 (`grep -rn "7\.[01]\.0\|MAJOR_VERSION == 7\|v7" tests`)

**Interfaces:**
- Produces: `VesselMotion` has no slew field; engine `_vm_default(None, "crane_slewing_angle_deg")` resolves to 0.0 via the existing `getattr(vm, name, 0.0)`.

- [ ] **Step 1: Write failing tests** in `tests/test_vessel_motion_schema.py`: `test_major_version_is_8` (`AUTHORED_SCHEMA_MAJOR_VERSION == 8`); `test_slewing_angle_is_not_a_model_field` (`AuthoredVesselMotion(crane_slewing_angle_deg=1.0)` raises `ValidationError`; `"crane_slewing_angle_deg" not in` the generated schema's `AuthoredVesselMotion.properties`); `test_saved_documents_are_version_8` (save/load round trip of an example gives `schema.version == "8.0.0"`).
- [ ] **Step 2:** Run `.venv/Scripts/python.exe -m pytest tests/test_vessel_motion_schema.py --no-cov -q`; expect FAIL.
- [ ] **Step 3:** Make the code and doc edits listed under Files; update the existing tests that pin the old version or the seeded Scene slew (`tests/test_scene_view_model.py::test_document_vessel_motion_seeds_every_hoist_scene_state` now expects `crane_slewing_angle_deg == 0.0`).
- [ ] **Step 4:** Run `.venv/Scripts/python.exe -m pytest --no-cov -q`; expect only the two known failures `test_scene_equilibrium_report_handles_unavailable_analysis` and `test_load_summary_handles_unavailable_analysis`. Run `-m pre_commit run --all-files`; expect pass.

### Task 2: Sidelead force at the sheave

**Files:**
- Modify: `src/crane_statics/calculation/engine.py` (`_build_out_of_plane_reactions`, the `load_node` lookup near line 396)
- Test: `tests/test_vessel_frame_engine.py`

**Interfaces:**
- Consumes: `hoist.support_node_id`; `node_pos` already built in the method.

- [ ] **Step 1: Write failing test** `test_sidelead_force_acts_at_the_support_node(calc)`: for GT283 hoist `MH` at 45 deg, call `calc._build_out_of_plane_reactions(point, "MH", 45.0, 0.0, 0.0, 0.0, 0.0, side_lateral_force_kN=F, ...)` for `F = 0.0` and `F = 100.0` using a point from `calc.compute_analysis_point(45.0, 0.0, "MH")`. Assert the difference in the returned platform `Fy` is `100.0` and the difference in platform `Mx` equals `-(z_support - z_platform_heel) * 100.0` with positions from `calc._kinematics.compute_all_node_positions(45.0)` and `calc.hoists["MH"].support_node_id`.
- [ ] **Step 2:** Run it; expect FAIL (arm uses the hook node).
- [ ] **Step 3:** In `_build_out_of_plane_reactions` replace `node_pos.get(str(hoist.load_node_id))` with the node for `str(getattr(hoist, "support_node_id", "") or "")`, falling back to `load_node_id` only if the support node is missing. Add a comment: the rope delivers the lateral load to the crane at the sheave.
- [ ] **Step 4:** Run `tests/test_vessel_frame_engine.py` and the full suite; update any test pinning sidelead moment numbers. Expected: pass apart from the two known failures.

### Task 3: Arbitrary wind angle in the engine

**Files:**
- Modify: `src/crane_statics/calculation/engine.py` (`compute_analysis_point`, add `split_wind_angle_components`)
- Test: `tests/test_vessel_frame_engine.py` (or new `tests/test_wind_angle.py`)

**Interfaces:**
- Produces: `split_wind_angle_components(wind_speed_m_s: float, wind_angle_deg: float) -> tuple[float, float]` returning `(V*cos, V*sin)` with values below 1e-12 snapped to 0.0. `compute_analysis_point(..., wind_angle_deg: Optional[float] = None)`: when given it overrides `wind_direction` (`wind_x_ref, wind_y_ref` from the function above, `wind_dir` unused; `governing_wind_direction` becomes `None`).

- [ ] **Step 1: Write failing tests:** `test_axis_wind_angles_match_direction_strings` (angles 0/90/180/270 vs `+X/+Y/-X/-Y`: identical `baseline_reactions` and `baseline_rope_tensions`, `pytest.approx` rel 1e-12); `test_oblique_wind_is_the_sum_of_half_axis_effects` (at 45 deg, with `Z` = the no-wind point, every baseline reaction component equals `Z + 0.5*(P0 - Z) + 0.5*(P90 - Z)` where `P0`, `P90` are the 0 and 90 deg points, rel 1e-9).
- [ ] **Step 2:** Run; expect FAIL (`unexpected keyword`).
- [ ] **Step 3:** Implement as specified in Interfaces. No other physics changes.
- [ ] **Step 4:** Run the new tests and the full suite; expect pass apart from the two known failures.

### Task 4: Public lead composition and the brute-force reference

**Files:**
- Create: `src/crane_statics/core/lead_channels.py` (move `_compose_lead_channel_point` from `core/limit_auto_set.py`, unchanged logic)
- Modify: `src/crane_statics/core/limit_auto_set.py` (import it)
- Create: `tests/chart_reference.py`
- Test: `tests/test_chart_reference.py`

**Interfaces:**
- Produces: `compose_lead_channel_point(pt: AnalysisPoint, offlead_deg: float, sidelead_deg: float) -> AnalysisPoint`.
- Produces: `reference_capacity(calc, doc, hoist_id, angle_deg, limits, *, hook_daf, hook_mass_t, overrides, slew_step_deg=15.0, wind_step_deg=15.0) -> AllowableCapacity`: minimum of `compute_allowable_load` over `vessel_motion_cases(doc.environment.vessel_motion)` x slews `range(0, 360, slew_step_deg)` (passed as `crane_slewing_angle_deg`) x wind angles (`wind_angle_deg`; single angle 0 when wind is 0) x lead signs (`_signed_candidates` of the hoist's `offlead_deg`/`sidelead_deg`, via `compose_lead_channel_point`). This is slow by design.

- [ ] **Step 1: Write failing tests:** `test_compose_lead_channel_point_matches_auto_set` (Auto-Set results unchanged: run the existing `tests/test_limit_auto_set*.py` unchanged); `test_reference_equals_single_case_when_everything_is_zero` (GT283, zero vessel limits, wind speed set to 0 on a copied doc: `reference_capacity(...)` equals `calc.compute_allowable_load(calc.compute_analysis_point(45.0, 0.0, "MH"), limits, ...)` after composing zero leads).
- [ ] **Step 2:** Run; expect FAIL (module missing).
- [ ] **Step 3:** Move the function and write the reference per Interfaces.
- [ ] **Step 4:** Run the new tests plus `tests/test_limit_auto_set*.py`; expect pass.

### Task 5: Probe set and superposition

**Files:**
- Create: `src/crane_statics/core/chart_envelope.py`
- Test: `tests/test_chart_envelope.py`

**Interfaces:**
- Consumes: `CraneCalculator.compute_analysis_point` (Task 3 `wind_angle_deg`), `crane_frame_motion`/`VesselInputs`/`CraneFrameMotion` from `calculation/vessel_frame.py`.
- Produces:
  - `@dataclass(frozen=True) class ProbeSet: zero: AnalysisPoint; motion: tuple[AnalysisPoint, AnalysisPoint, AnalysisPoint, AnalysisPoint, AnalysisPoint]` (order: accel_x, accel_y, accel_z, pitch_accel, roll_accel, each probed at +1.0 on a level vessel, slew 0); `wind_x: AnalysisPoint`, `wind_y: AnalysisPoint` (probed at wind angle 0 and 90 deg, speed `V`).
  - `build_probes(calc: CraneCalculator, hoist_id: str, boom_angle_deg: float, wind_speed_m_s: float, overrides: Optional[dict]) -> Optional[ProbeSet]` (`None` if any probe returns `None`; zero-wind speed gives `wind_x = wind_y = zero`).
  - `motion_channels(gravity: float, inputs: VesselInputs) -> numpy.ndarray` shape (5,): `crane_frame_motion` output minus its output for all-zero inputs, ordered as `motion`.
  - `superpose(probes: ProbeSet, channels: Sequence[float], wind_x_scale: float, wind_y_scale: float) -> AnalysisPoint`: `dataclasses.replace(probes.zero, baseline_rope_tensions=..., baseline_reactions=...)` where every baseline number is `zero + sum_j channels[j]*(motion_j - zero) + wind_x_scale*(wind_x - zero) + wind_y_scale*(wind_y - zero)`; sensitivities and lead channels stay the zero point's.

- [ ] **Step 1: Write failing tests** on GT283 `MH`, 45 deg, document wind speed, vessel limits all nonzero: `test_superposition_matches_direct_solve` for 20 seeded random (signs, slew in 0..360, wind angle in 0..360, tilt) combos: `superpose(...)` baseline reactions and rope tensions equal `calc.compute_analysis_point(45.0, 0.0, "MH", wind_speed_m_s=V, wind_angle_deg=theta, **vessel kwargs, crane_slewing_angle_deg=slew)` for every entity/component, `pytest.approx(rel=1e-9, abs=1e-9)`, with wind scales `cos*|cos|`, `sin*|sin|`; the same test on a copy of the example with a nonzero `y_m` on one boom mass point.
- [ ] **Step 2:** Run; expect FAIL (module missing).
- [ ] **Step 3:** Implement per Interfaces.
- [ ] **Step 4:** Run `tests/test_chart_envelope.py`; expect pass. If it fails beyond 1e-9, stop and report: the affine assumption is wrong and the design must change.

### Task 6: Worst-case capacity from probes

**Files:**
- Modify: `src/crane_statics/core/chart_envelope.py`
- Test: `tests/test_chart_envelope.py`

**Interfaces:**
- Consumes: Task 5 API, `vessel_motion_cases` / `vessel_limit` / `VESSEL_LIMIT_INPUTS` (`core/vessel_envelope.py`), `compose_lead_channel_point` (Task 4), `CraneCalculator.compute_allowable_load`.
- Produces: `envelope_capacity(calc: CraneCalculator, probes: ProbeSet, limits: dict[str, dict], *, vessel: VesselMotion, offlead_deg: float, sidelead_deg: float, hook_daf: float, hook_mass_t: float) -> AllowableCapacity`.

Algorithm (the implementer writes the code): build the set of crane-frame motion channel vectors for every sign combination in `vessel_motion_cases(vessel)` (converted from the case kwargs to `VesselInputs`, `slew_deg` = 0, 90, 180, 270) with `motion_channels`. Per lead case (the signed candidates of `offlead_deg` and `sidelead_deg`, via `compose_lead_channel_point` on `probes.zero`) and per limit component:
- Linear limits (anything not `resultant`, `fradial`, `mradial`, `max_bearing_line_load`): the baseline is affine in the channels, so take the extremes (max and min) of the baseline over the set. Per sign combination, the extremes over slew are `B0 +/- sqrt(P^2+Q^2)` from the four slews (`B0 = (f0+f180)/2`, `P = (f0-f180)/2`, `Q = (f90-f270)/2`); the wind term extremes are `+/- max(|a|,|b|)` where `a` is the baseline response to the full-speed +X wind probe and `b` the response to the full-speed +Y wind probe (for this quantity). Reason: the wind contribution at angle theta is `a*u + b*v` with `u = cos(theta)*|cos(theta)|`, `v = sin(theta)*|sin(theta)|`, and `|u|+|v| = 1`, so a linear function is extreme at a corner, i.e. an axis wind (+X, -X, +Y or -Y); wind from -X/-Y is the sign flip. This holds only per single quantity, not for the magnitude limits below, where one wind angle drives two or three quantities at once. Evaluate `compute_allowable_load` on `superpose`-style points built from the max and min baselines (replace the baseline dicts for that one quantity) and keep the smaller capacity.
- Magnitude limits: vectorised numpy scan over sign combinations x slew every 5 deg x wind angle every 5 deg, then refine around the worst by evaluating a 0.25 deg grid within +/-5 deg of the worst slew and wind angle; evaluate with the existing `compute_allowable_load` closed form (`solve_radial_capacity_kN`) vectorised, or call it per candidate for the 20 worst candidates only. Bearing line load goes through `solve_capacity_limit_kN` for the 20 worst candidates (ranked by baseline magnitude) only.
- Return the minimum over lead cases and limits, `governing_limit_id` as `compute_allowable_load` reports it.

- [ ] **Step 1: Write failing tests** (GT283 `MH`, angles 20, 45, 70 deg; limits: `{"boom_hoist": {"T": 5000.0}}`, `{"platform_base": {"fradial": 20000.0}}`, `{"platform_base": {"max_bearing_line_load": 3000.0}}`, `{"heel_point": {"Fx": 20000.0}}`; vessel limits all nonzero): `test_envelope_never_exceeds_the_reference` asserts `fast.max_allowable_load_kN <= ref.max_allowable_load_kN * (1 + 1e-6)` and `fast >= ref * 0.995` against `tests/chart_reference.reference_capacity` with 5 deg steps; `test_zero_limits_and_no_wind_equal_the_single_solve`; `test_zero_leads_collapse_to_one_case` (monkeypatch counts `compose_lead_channel_point` calls == 1).
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement `envelope_capacity` as described.
- [ ] **Step 4:** Run `tests/test_chart_envelope.py`; expect pass. If the 0.5% band fails for a magnitude limit, tighten the refinement, not the tolerance.

### Task 7: Use the envelope in the sweep

**Files:**
- Modify: `src/crane_statics/core/sweep.py` (`_wind_points` replaced; `_min_capacity`, `_affects_hook_load` callers)
- Modify: `src/crane_statics/core/analysis_cases.py` (remove `iter_wind_directional_cases` if unused afterwards)
- Delete: the `motion_cases` plumbing added earlier in `sweep.py`
- Test: `tests/test_acceptance.py` (sweep tests around 1555-1600), `tests/test_chart_view_model.py`, `tests/test_chart_envelope.py`

**Interfaces:**
- Consumes: `build_probes`, `envelope_capacity`.
- Produces: `run_capacity_sweep(...)` signature and return shape unchanged. Per outreach: one `build_probes` call (or `None` -> skip, as `pts` empty today); `_affects_hook_load` evaluated on `probes.zero`; per-limit series use `envelope_capacity(..., limits={lid: comps})`. Stage-2 reuses stage-1 contractual results for outreaches already computed (cache keyed by `(round(angle, 10), mode_name)`).

- [ ] **Step 1: Write failing tests:** `test_sweep_matches_reference_curve` (GT283 `MH`, step 10.0, three outreaches: each curve point within the 0.5% band below `reference_capacity` and never above); `test_sweep_meets_the_benchmark` (the Global Constraints benchmark; assert elapsed seconds `< 0.37`); `test_cancelled_sweep_raises` (cancel callback true on first check raises `SweepCancelled`).
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Rewire `run_capacity_sweep` to the probes; keep `SweepCancelled`, progress messages and result structure identical.
- [ ] **Step 4:** Run the full suite. Expected changes: example-based chart capacity tests shift slightly (leads and wind angle now included); update only values the design explains. Pre-commit passes.

### Task 8: Verification and docs

**Files:**
- Modify: `CONTEXT-CORE.md`, `CONTEXT-EXTENDED.md`, `docs/adr/0003-vessel-frame-load-acceleration.md` (chart envelope paragraph: slew 0-360, any wind angle, leads, ± limits, probes)

- [ ] **Step 1:** Run the benchmark script from Global Constraints; record before/after numbers in the ADR paragraph.
- [ ] **Step 2:** Use the `run-app` skill to screenshot the Load Chart workspace for `examples/crane_input_GT283.yaml` and confirm it draws and is not slower.
- [ ] **Step 3:** Run `.venv/Scripts/python.exe -m pytest` and `-m pre_commit run --all-files`; expected: only the two known pre-existing failures.

---

**Deferred (YAGNI):** removing the redundant hook-1 out-of-plane call. With 8 probes per angle instead of 512 points it is no longer on the critical path; revisit only if the benchmark misses 10x.
