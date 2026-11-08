# ABS / DNV In-Service Crane Loads Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a Crane Statics document select ABS or DNV, define several lift conditions, and get class-correct dynamic factors, cases, pedestal/slewing-bearing loads and one capacity chart per condition, with a clause trail on every value.

**Architecture:** A new pure-Python `rules` package holds the ABS and DNV profiles. A profile turns a condition into load cases, a closed-form-invertible `DynamicFactor`, a live-load lateral spec, foundation multipliers and provenance records. `calculation/` and `core/` only receive those generic objects and never name a standard. Documents without a `rules` section take today's code path unchanged.

**Tech Stack:** Python 3.13, pydantic v2, PyYAML, PyQt6/QML (UI only), pytest, black/flake8/mypy via pre-commit.

**Spec:** `docs/superpowers/specs/2026-11-08-abs-dnv-crane-loads-design.md` (read it first; equations and clauses are cited there from the PDFs in `docs/rules/`).

## Global Constraints

- Commands: tests `.venv/Scripts/python.exe -m pytest <file> --no-cov -q` (full: `-m pytest -n auto --dist loadfile`); lint `.venv/Scripts/python.exe -m pre_commit run --all-files`.
- Units are SI only: t, m, kN, kN/m, m/s, degrees. No unit-conversion layer.
- Authored schema bumps to `11.1.0` (minor). Major stays 11; `schemas/crane-statics-v11.schema.json` is regenerated.
- A document without `rules` must load, save and compute exactly as today: golden files in `tests/golden/` and `test_reeving.py::test_examples_round_trip_byte_stable` must stay green untouched.
- `core/`, `data/`, `calculation/` and the new `rules/` must not import PyQt6 or `crane_statics.qml_app` (`tests/test_architecture.py`). `calculation/` must not import `rules`.
- Required velocities (Vin, Vt) are never filled from the standards' Hs tables.
- Manual `daf` wins over the computed factor; both values are always computed and the override is flagged.
- Line length 100, black, mypy clean; `.coveragerc` `fail_under = 75`.

## Plan-level calls (the spec did not fix these; check them)

1. `conditions` is a mapping keyed by condition name (like `hoists` and `limits`), not a list.
2. DNV cases pass `vessel_motion` roll/pitch (static heel/trim) but zero all accelerations: DNV 4.1.5.1 puts ship-motion inertia in Case III, and 4.1.4 (SH) is out of scope.
3. "Worst case over the hook's travel" for stiffness is the hook at the support node (tackle length 0). That is very stiff and conservative; the per-condition `hook_height_override_m` is the practical escape.
4. PF, SF1 and 3.75x scale the platform-base demand used by chart limits as well as the reported rows (not reported rows only).
5. Authoring conditions in the UI is out of scope; YAML only. The UI gets a condition selector, a details view and CSV columns.

## Review Focus

- A `rules` document with only onboard conditions and hoists lacking EA or speed must load and run (those fields are required only for offboard conditions).
- Zero velocities, zero payload and zero hook mass must not divide by zero; ψ must reduce to its floor or 1.
- `rules` with no conditions, duplicate condition names, `crane_class` under DNV, or ABS without `crane_class` must fail with a one-line message naming the field.
- Heavy-lift accelerations exactly 0.07 g pass; 0.0701 g fail with a message pointing to the offshore requirements.
- Switching condition in the chart must never show another condition's cached chart.

---

## File Structure

- Create `src/crane_statics/rules/` (`__init__.py`, `types.py`, `stiffness.py`, `factors.py`, `abs_profile.py`, `dnv_profile.py`, `validation.py`, `foundation.py`): pure domain package, one responsibility per file.
- Create `tests/rules_reference.py`: independent hand-calculation oracle (imports nothing from `src`).
- Modify `data/authored_models.py`, `data/models.py`, `data/normalize/authored.py`, `data/authored_form.py`, `schemas/crane-statics-v11.schema.json`, `core/load_condition.py`, `core/sweep.py`, `core/governing_case.py`, `core/limit_auto_set.py`, `core/chart_cache.py`, `core/analysis_services.py`, `calculation/rope_mass.py`, `calculation/allowable.py`, `calculation/engine.py`, `calculation/solver/crane_solver.py`, `qml_app/viewmodels/chart_vm.py`, `tests/test_architecture.py`.

---

## Phase 0: Reference cases first (acceptance criteria)

### Task 1: Hand-calculation oracle and signed-off cases

**Files:**
- Create: `tests/rules_reference.py`, `tests/test_rules_reference.py`
- Create: `docs/superpowers/plans/2026-11-08-abs-dnv-reference-cases.md` (the human-readable case sheet for sign-off)

**Interfaces:**
- Produces (pure functions, SI, kN, written only from the PDF equations, no `src` imports):
  `abs_vaf_onboard(ll_kN, a_v_g) -> float`, `abs_vaf_offboard(ll_kN, k_kN_m, v_r, a_v_g) -> float`, `abs_v_r(v_h, v_d, v_c) -> float`, `abs_v_hmin(h_sig) -> float`, `abs_heavy_lift_vaf(a_v_g) -> float`, `abs_pedestal_factor(ll_kN, crane_class) -> float`, `abs_list_trim_load(l_kN, list_deg, trim_deg) -> float`, `abs_live_load_wind_area(ll_kN) -> float`, `abs_wind_pressure(v_m_s, cs) -> float`, `dnv_psi(c, w_kN, v_r) -> float`, `dnv_psi_floor(w_kN) -> float`, `dnv_v_r(v_l, v_in, v_t, h_s) -> float`, `dnv_v_h(h_s) -> float`, `dnv_sf1(swl_kN) -> float`, `hook_stiffness(ropes: list[tuple[float, float, float]]) -> float` (tuples are `(tension_per_unit_hook_load, reeved_length_m, ea_kN)`).

- [ ] **Step 1: Write the failing tests** in `tests/test_rules_reference.py`, with the values below (`pytest.approx`, rel 1e-4):
  - `abs_vaf_onboard(1000, 0) == 1.181429`; `abs_vaf_onboard(100, 0) == 1.33` (cap); `abs_vaf_onboard(2000, 0) == 1.1` (floor); `abs_vaf_onboard(1000, 0.05) == 1.231429`.
  - `abs_v_r(0.5, 0.8, 0.6) == 1.5`; `abs_vaf_offboard(1000, 5000, 1.5, 0) == 2.070883`; `abs_vaf_offboard(1000, 5000, 0.0, 0) == abs_vaf_onboard(1000, 0)` (never below onboard).
  - `abs_v_hmin(1.0) == 0.108`; `abs_v_hmin(2.0) == 0.201`; `abs_heavy_lift_vaf(0.05) == 1.15`.
  - `abs_pedestal_factor(1000,"offshore") == 1.31`; `(0,"offshore") == 1.5`; `(2000,"offshore") == 1.2`; `(2000,"heavy_lift") == 1.06`; `(3000,"heavy_lift") == 1.0`.
  - `abs_live_load_wind_area(1000) == 12.15`; `abs_wind_pressure(20, 1.0) == 0.244350`; `abs_list_trim_load(1000, 5, 2) == 93.85` (abs 0.01).
  - `dnv_psi(5000, 1000, 1.3) == 1.928098`; `dnv_psi_floor(2000) == 1.3`, `(3000) == 1.26`, `(6000) == 1.1`; `dnv_v_h(2.0) == 0.3`; `dnv_v_r(0.5, 0.8, 0.6, 2.0) == 1.3` (0.5·VL=0.25 < VH=0.3 so VH is used); `dnv_sf1(2000) == 1.3`, `(3000) == 1.1`.
  - `hook_stiffness([(0.5, 100.0, 100000.0)]) == 4000.0` (2 falls, 100 m reeved); `hook_stiffness([(0.5, 100.0, 100000.0), (0.5, 50.0, 200000.0)]) == 3200.0` (the second tuple is the boom-hoist term).
- [ ] **Step 2: Run** `pytest tests/test_rules_reference.py --no-cov -q`. Expected: FAIL, import error.
- [ ] **Step 3: Implement** the functions in `tests/rules_reference.py` with the cited equations (ABS 2-2/9.3.1, 9.3.2, 11.3, 5.15, 5.19, 5.21; DNV 4.1.3.2, 8.2.2.1, 8.2.2.2, 8.2.2.4; hook stiffness `1 / sum(t**2 * L / EA)`), each with a docstring naming clause and page.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Case sheet and sign-off.** Write the case sheet listing each case's inputs, the oracle's output, and the PDF page the equation came from. Commit, then ask the owner to name the reviewer and obtain their sign-off before Task 5 starts. Commit: `git add tests docs && git commit -m "test: independent ABS/DNV hand-calculation oracle"`.

---

## Phase 1: Schema and data

### Task 2: Authored and runtime models for `rules`, `conditions`, rope EA, hoisting speed

**Files:**
- Modify: `data/authored_models.py` (constants 32-34, `AuthoredEnvironment` 94, `AuthoredBoomHoistRope` 364, `AuthoredPayloadHoistRope` 390, `AuthoredPayloadHoist` 406, `AuthoredModelDefinition` 514, `EXAMPLE_DOCUMENT`), `data/models.py`, `data/normalize/authored.py` (`_runtime_environment` 660, `_normalize_payload_hoist` 193, `_normalize_boom_hoist` 304, `_runtime_hoists`, `_runtime_ropes`, `_normalize_authored_document` 676), `data/authored_form.py` (344-374 and hoist writers), `schemas/crane-statics-v11.schema.json`
- Test: `tests/test_rules_schema.py`; update `tests/test_vessel_motion_schema.py::test_saved_documents_are_version_9` to `"11.1.0"`

**Interfaces:**
- Produces authored models: `AuthoredRules(standard: Literal["ABS","DNV"], crane_class: Optional[Literal["offshore","heavy_lift"]] = None, cabin_above_slewing_bearing: bool = False)`; `AuthoredCondition(lift: Literal["onboard","offboard"] = "onboard", wind_speed_m_s: float = Field(ge=0), vessel_motion: AuthoredVesselMotion = default, significant_wave_height_m: Optional[float] = Field(None, ge=0), v_in_m_s: Optional[float] = None, v_t_m_s: Optional[float] = None, load_wind_area_m2: float = Field(0.0, ge=0), load_drag_coefficient: float = Field(1.0, gt=0), hook_height_override_m: Optional[float] = None)`.
- `AuthoredModelDefinition` gains `rules: Optional[AuthoredRules] = None` and `conditions: dict[IdName, AuthoredCondition] = {}`. A model validator requires: `rules` present iff `conditions` non-empty; with `rules`, top-level `vessel_motion` must be absent/default and `environment.max_wind_speed_m_s` absent (it becomes `Optional[float]`, still required without `rules`).
- Both rope models gain `ea_kN: Optional[float] = Field(None, gt=0)`, `elastic_modulus_kN_mm2: Optional[float] = Field(None, gt=0)`, `metallic_area_mm2: Optional[float] = Field(None, gt=0)`, validated so either `ea_kN` alone or modulus and area together are given. `AuthoredPayloadHoist` gains `max_hoisting_speed_m_s: Optional[float] = Field(None, gt=0)`.
- Runtime (`data/models.py`): `RulesSpec`, `ConditionSpec(name, lift, wind_speed_m_s, vessel_motion: VesselMotion, significant_wave_height_m, v_in_m_s, v_t_m_s, load_wind_area_m2, load_drag_coefficient, hook_height_override_m)`, `CraneDocument.rules: Optional[RulesSpec] = None`, `CraneDocument.conditions: dict[str, ConditionSpec] = {}`, `Rope.ea_kN/elastic_modulus_kN_mm2/metallic_area_mm2`, `Rope.axial_stiffness_kN -> Optional[float]` (property), `Hoist.max_hoisting_speed_m_s`.

- [ ] **Step 1: Write the failing tests** in `tests/test_rules_schema.py`: (a) `test_legacy_examples_unchanged`: the three `examples/*.yaml` load, `doc.rules is None`, `doc.conditions == {}`; (b) `test_rules_document_round_trips`: a DNV document with two conditions saves and reloads with equal `rules`/`conditions` and a second save is byte-identical; (c) `test_ea_pair_normalizes`: modulus 100 kN/mm² and area 500 mm² give `axial_stiffness_kN == 50000`; (d) rejection tests, each asserting the message names the field: `rules` without conditions, conditions without `rules`, `vessel_motion` or `max_wind_speed_m_s` present beside `rules`, `ea_kN` together with modulus.
- [ ] **Step 2: Run** `pytest tests/test_rules_schema.py --no-cov -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the models above; set `AUTHORED_SCHEMA_VERSION = "11.1.0"`; normalize `rules`/`conditions`/EA/speed into the runtime dict; write them back in `document_to_authored_form` only when set (so legacy output is byte-identical); regenerate the schema with `.venv/Scripts/python.exe -m crane_statics.schemas.generate_schema`.
- [ ] **Step 4: Run** `pytest tests/test_rules_schema.py tests/test_schema_contract.py tests/test_reeving.py tests/test_vessel_motion_schema.py --no-cov -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(schema): rules, conditions, rope EA and hoisting speed (11.1.0)`.

### Task 3: Rules validation

**Files:**
- Create: `src/crane_statics/rules/__init__.py`, `rules/validation.py`
- Modify: `tests/test_architecture.py` (add `"rules"` to `PURE_PACKAGES`)
- Test: `tests/test_rules_validation.py`

**Interfaces:**
- Produces: `validate_rules_document(doc: CraneDocument) -> None` raising `RulesValidationError(ValueError)` with a one-line message; called from `core/io.py::load_document` after `normalize_document` when `doc.rules` is set.

- [ ] **Step 1: Write the failing tests:** `crane_class` given under DNV; missing `crane_class` under ABS; `heavy_lift` with an `offboard` condition; heavy lift with `|accel_z| = 0.07*9.81` passes and `0.0701*9.81` raises, same for `accel_x` and `accel_y`; offboard condition missing `v_in_m_s`, `v_t_m_s` or `significant_wave_height_m`; offboard with any payload hoist lacking `max_hoisting_speed_m_s` or rope EA, or a boom hoist lacking EA; an onboard-only condition set validates with no EA or speed (Review Focus 1); `hook_height_override_m` outside the hoist's reachable heights.
- [ ] **Step 2: Run** `pytest tests/test_rules_validation.py tests/test_architecture.py --no-cov -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `validate_rules_document` and `RulesValidationError`; hook-height bounds come from `calculation.rope_mass.derive_hook_geometry`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(rules): document validation for ABS/DNV profiles`.

---

## Phase 2: Rules package (pure functions)

### Task 4: Hook stiffness by virtual work

**Files:**
- Create: `src/crane_statics/rules/stiffness.py`
- Modify: `calculation/rope_mass.py` (expose the reeved length of a hoist at given node positions with the hook at a given tackle length; reuse `compute_reeved_length_m`, `active_hook_positions`)
- Test: `tests/test_rules_stiffness.py`

**Interfaces:**
- Produces: `hook_stiffness_kN_per_m(terms: Sequence[StiffnessTerm]) -> float` where `StiffnessTerm(tension_per_hook_kN: float, reeved_length_m: float, ea_kN: float)`; `payload_hoist_stiffness_terms(doc, point: AnalysisPoint, hoist_id: str, tackle_length_m: float) -> list[StiffnessTerm]` (active hoist term from `1/falls` and its reeved length including the winch run; boom-hoist term from `point.sensitivity_rope_tensions["BH"]`); `worst_case_tackle_length_m() -> float` returns `0.0`.
- Consumes: Task 2 `Rope.axial_stiffness_kN`; `AnalysisPoint` from `calculation/results.py`.

- [ ] **Step 1: Write the failing tests:** `hook_stiffness_kN_per_m([StiffnessTerm(0.5,100,100000)]) == 4000`; adding `StiffnessTerm(0.5,50,200000)` gives `3200`; agreement with `tests.rules_reference.hook_stiffness`; on the GT283 example (give EA values in the test through `model_copy`) the stiffness at tackle length 0 is greater than at the lowest hook height; a missing EA raises `RulesValidationError`.
- [ ] **Step 2: Run** `pytest tests/test_rules_stiffness.py --no-cov -q`. Expected: FAIL.
- [ ] **Step 3: Implement** with C = 1 / Σ(t²·L/EA); falls come from the hook segment `mult` (dead end included), reeved length from `compute_reeved_length_m`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(rules): vertical hook stiffness from rope EA/L`.

### Task 5: Invertible dynamic factors

**Files:**
- Create: `src/crane_statics/rules/types.py`, `rules/factors.py`
- Test: `tests/test_rules_factors.py`

**Interfaces:**
- Produces in `types.py`: `ProvenanceRecord(quantity: str, value: float, unit: str, clause: str, formula: str, inputs: Mapping[str, float], source: Literal["computed","override"])`.
- Produces in `factors.py` (all implement `calculation.dynamic_factor.DynamicFactor`, frozen dataclasses; `extra_mass_t` is the suspended rope mass added to `hook_mass_t` before amplification):
  `LinearFactor(value: float, extra_mass_t: float = 0.0)`;
  `AbsOnboardFactor(a_v_g: float, extra_mass_t: float = 0.0, lower: float = 1.1, upper: float = 1.33)`;
  `RelativeVelocityFactor(stiffness_kN_m: float, v_r_m_s: float, extra_mass_t: float = 0.0)` (ψ = 1 + v_r·√(K/(W·g)));
  `MaxFactor(parts: tuple[DynamicFactor, ...])` whose `payload_t` is the minimum of the parts' (each part is increasing in W, so the inverse of a maximum is the minimum of inverses);
  `OverrideFactor(value: float)` is `ConstantDynamicFactor`, reused.

- [ ] **Step 1: Write the failing tests:** for each class `payload_t(hook_force_kN(p, h, g), h, g) == approx(p)` over payloads 0, 50, 300, 1200 t (round trip); values against the oracle (`AbsOnboardFactor(0).hook_force_kN` at LL = 1000 kN equals `1000*1.181429`; cap and floor at LL 100 and 2000 kN; `RelativeVelocityFactor(5000, 1.3)` at W = 1000 kN gives ψ = 1.928098); `MaxFactor((AbsOnboardFactor(0), RelativeVelocityFactor(5000, 0.0)))` equals onboard; DNV floor via `MaxFactor((LinearFactor(1.26), RelativeVelocityFactor(...)))`; zero payload and zero hook mass give `hook_force_kN == 0` without raising (Review Focus 2); `extra_mass_t` raises the force by `extra * ψ * g`.
- [ ] **Step 2: Run** `pytest tests/test_rules_factors.py --no-cov -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the classes. `RelativeVelocityFactor.payload_t` solves F = W + b√W with b = v_r·√(K/g) in closed form (√W = (−b + √(b²+4F))/2). `AbsOnboardFactor` inverts piecewise over the cap, quadratic and floor regions; all are monotone increasing.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(rules): invertible ABS/DNV dynamic factors`.

### Task 6: ABS profile

**Files:**
- Create: `src/crane_statics/rules/abs_profile.py`, `rules/foundation.py`
- Test: `tests/test_rules_abs_profile.py`

**Interfaces:**
- Produces in `types.py` (add): `CaseSpec(name: str, wind_speed_m_s: float, vessel_motion: VesselMotion)`; `LateralSpec(accel_fraction_x: float, accel_fraction_y: float, incline_deg: float, wind_area_m2: float, wind_cd: float, min_fraction: float)`; `FoundationFactors(live_factor: Callable[[float], float], dead_factor: float)` (argument is LL in kN); `LiftSetup(factor: DynamicFactor, lateral: LateralSpec, foundation: FoundationFactors, retaining_live_factor: float, records: tuple[ProvenanceRecord, ...], warnings: tuple[str, ...])`.
- Produces in `abs_profile.py`: `class AbsProfile` with `cases(doc, cond: ConditionSpec) -> tuple[CaseSpec, ...]` (one case, "In-service"; heel/trim raised to Table 5A minimums only as a warning), and `lift_setup(doc, cond, hoist_id, mode, stiffness_kN_m, suspended_rope_mass_t, chart_max_load_t) -> LiftSetup`.
- Produces in `foundation.py`: `abs_pedestal_factor(ll_kN: float, crane_class: str) -> float`.
- Behaviour: onboard heavy lift → `LinearFactor(1.1 + a_v_g)`; offshore onboard → `AbsOnboardFactor(a_v_g)`; offboard → `MaxFactor((AbsOnboardFactor(a_v_g), RelativeVelocityFactor(K, v_r)))` with v_r = v_h + √(v_in² + v_t²); `a_v_g = |accel_z|/9.81`; `lateral.min_fraction = 0.02`, `incline_deg = √(roll² + pitch²)` (ABS 5.21), `accel_fraction_* = |accel|/9.81`; `retaining_live_factor = 3.75`; a manual `daf` replaces `factor` and adds an `override` record; a hoisting speed below `v_hmin` adds a warning.

- [ ] **Step 1: Write the failing tests:** factor values against the oracle (offshore onboard LL 1000 kN → 1.181429; heavy lift a_v = 0.05 g → 1.15; offboard with K 5000, v_h 0.5, v_in 0.8, v_t 0.6 → 2.070883); `foundation.live_factor(1000)` → 1.31 for offshore, `(3000)` → 1.0 for heavy lift; `lateral.min_fraction == 0.02`; override record present and its value wins when `hoist.hook_daf` is set while the computed record is also kept; the `v_hmin` warning at Hsig 2 m with v_h 0.15.
- [ ] **Step 2: Run** `pytest tests/test_rules_abs_profile.py --no-cov -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `AbsProfile` and `abs_pedestal_factor`; every record carries clause and page from the spec table.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(rules): ABS profile`.

### Task 7: DNV profile

**Files:**
- Create: `src/crane_statics/rules/dnv_profile.py`
- Modify: `rules/foundation.py` (add `dnv_sf1(swl_kN: float) -> float`)
- Test: `tests/test_rules_dnv_profile.py`

**Interfaces:**
- Produces: `class DnvProfile` with `cases(doc, cond) -> tuple[CaseSpec, CaseSpec]` (Case I: wind 0, `vessel_motion` with roll/pitch as entered and all accelerations zero; Case II: wind per condition, roll/pitch ×1.5, accelerations zero) and `lift_setup(...)` with the same signature as Task 6.
- Behaviour: `factor = MaxFactor((LinearFactor(psi_floor(chart_max_load_kN)), RelativeVelocityFactor(K, v_r)))` for offboard; onboard uses the floor only (ψ = floor); v_r = max(0.5·v_L, VH) + √(v_in² + v_t²), VH = 0.1·(Hs + 1); suspended rope mass is in `extra_mass_t`; `foundation.dead_factor = dnv_sf1(swl)` and `live_factor = lambda _: dnv_sf1(swl)` only when `rules.cabin_above_slewing_bearing`, otherwise 1.0; `retaining_live_factor = 1.0`; `lateral` carries only `incline_deg` and the load wind area and Cd (C = 1.2 containers or 1.0 other, as entered), `min_fraction = 0.0`; a speed below VH yields a warning noting the shaded-region note is deferred.

- [ ] **Step 1: Write the failing tests:** Case II heel/trim equals 1.5 × Case I; both cases have zero accelerations; Case I wind is 0; ψ at W 1000 kN, K 5000, v_l 0.5, v_in 0.8, v_t 0.6, Hs 2 → 1.928098; ψ never below the floor (W 2000 kN → 1.3, W 6000 kN → 1.1); SF1 1.3 below 2500 kN and 1.1 above, 1.0 without the cabin flag; `v_h` warning case.
- [ ] **Step 2: Run** `pytest tests/test_rules_dnv_profile.py --no-cov -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `DnvProfile`, `dnv_sf1`, plus `rules/__init__.py::profile_for(rules: RulesSpec) -> AbsProfile | DnvProfile`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(rules): DNV profile`.

---

## Phase 3: Core integration

### Task 8: Conditions, cases and chart selection plumbing

**Files:**
- Modify: `core/load_condition.py`, `core/sweep.py` (`run_mode_sweep` ~100-352), `core/governing_case.py` (49-104), `core/limit_auto_set.py` (~111), `core/chart_cache.py` (`ChartJob`, `ChartKey`, `plan_chart_jobs`)
- Test: `tests/test_load_condition.py` (extend), `tests/test_chart_cache.py` (extend), `tests/test_sweep_modes.py` (extend)

**Interfaces:**
- Produces: `LoadCondition(name, wind_speed_m_s, vessel_motion, spec: Optional[ConditionSpec] = None, case: Optional[CaseSpec] = None)`; `load_conditions(doc: CraneDocument) -> tuple[LoadCondition, ...]` (legacy: `(default_load_condition(doc),)`; with rules: one per `ConditionSpec` x profile case); `run_mode_sweep(..., condition_name: Optional[str] = None)`; `ChartJob(hoist_id, mode, condition)` and `ChartKey` including the condition name.
- `default_load_condition` keeps its signature and behaviour.

- [ ] **Step 1: Write the failing tests:** legacy `load_conditions(doc)` has one element equal to `default_load_condition`; a DNV two-condition document yields four elements named `"<condition>/Case I"` etc.; `ChartKey` differs between two conditions of one hoist (Review Focus 5); `run_mode_sweep` on a legacy document with `condition_name=None` returns the golden-identical payload; sweep for an unknown condition raises `KeyError` naming it.
- [ ] **Step 2: Run** `pytest tests/test_load_condition.py tests/test_chart_cache.py tests/test_sweep_modes.py --no-cov -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the signatures above; per case the sweep uses `case.wind_speed_m_s` and `case.vessel_motion` instead of the document environment; the chart's capacity is the minimum over the condition's cases.
- [ ] **Step 4: Run** the same command plus `tests/test_governing_case.py tests/test_sweep_envelope.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(core): load conditions with per-case sweeps`.

### Task 9: Per-point dynamic factor in the sweep

**Files:**
- Modify: `core/sweep.py` (`_capacity`/`_envelope`, ~163-217), `core/governing_case.py` (104), `core/limit_auto_set.py` (77-129), `core/analysis_services.py` (190-208, 504)
- Create: `core/lift_factor.py`
- Test: `tests/test_lift_factor.py`

**Interfaces:**
- Produces: `factor_for_point(doc: CraneDocument, condition: LoadCondition, hoist_id: str, mode: HoistAnalysisMode, point: AnalysisPoint, boom_angle_deg: float) -> LiftSetup` (legacy documents return a `LiftSetup` whose factor is `ConstantDynamicFactor(hoist.hook_daf)`). It builds the stiffness terms (Task 4), reads `hook_height_override_m`, and calls the profile.
- Consumes: `envelope_capacity_case(..., hook_daf=<DynamicFactor>)` already accepts a factor object (`DynamicFactorLike`); no `calculation/` signature changes in this task.

- [ ] **Step 1: Write the failing tests:** legacy document: `factor_for_point(...).factor` is `ConstantDynamicFactor(hoist.hook_daf)`; ABS offboard document: the sweep's capacity at one outreach equals the oracle value (payload from inverting the oracle ψ at the limiting hook force) within 1e-3 relative; `hook_height_override_m` changes C and lowers ψ versus the worst case; manual `daf` equals the legacy capacity and the `LiftSetup.records` hold both a computed and an override record.
- [ ] **Step 2: Run** `pytest tests/test_lift_factor.py --no-cov -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `factor_for_point` and call it in the sweep per angle, governing-case and auto-limit paths, so every consumer of `hook_daf` gets the same factor.
- [ ] **Step 4: Run** `pytest tests/test_lift_factor.py tests/test_chart_envelope.py tests/test_sweep_modes.py tests/test_governing_case.py tests/test_dynamic_factor.py --no-cov -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(core): per-outreach dynamic factor from the rules profile`.

### Task 10: Suspended rope in the live load

**Files:**
- Modify: `calculation/rope_mass.py` (`rope_mass_at_nodes` 153), `calculation/solver/crane_solver.py` (`_angle_invariants` 674-715), `calculation/engine.py` (`compute_analysis_point` 539)
- Create: `rules/suspended.py`
- Test: `tests/test_rules_suspended.py`

**Interfaces:**
- Produces: `rope_mass_at_nodes(doc_dict, positions, effective_mult=None, *, exclude_hoist_segment: Optional[str] = None)` (new keyword; default behaviour unchanged); `suspended_rope_mass_t(doc_dict, hoist_id, positions, effective_mult=None) -> float` in `rules/suspended.py` (mass of the hook-segment rope from the support node to the hook: linear mass × segment length × mult).
- `compute_analysis_point(..., amplified_rope_hoist_id: Optional[str] = None)` skips that rope segment's dead mass when set (set only by the rules path from Task 9).

- [ ] **Step 1: Write the failing tests:** legacy call without the keyword gives the golden node masses; with the keyword the last segment's mass is absent from the nodes and equals `suspended_rope_mass_t`; total rope mass is conserved (dead + suspended); split-block falls override changes the suspended mass with `mult`.
- [ ] **Step 2: Run** `pytest tests/test_rules_suspended.py tests/test_rope_mass.py --no-cov -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the keyword and helper; wire `factor_for_point` (Task 9) to pass `suspended_rope_mass_t` as `extra_mass_t` and the sweep to pass `amplified_rope_hoist_id`.
- [ ] **Step 4: Run** the same command plus `tests/test_vessel_frame_engine.py`. Expected: PASS (goldens untouched).
- [ ] **Step 5: Commit** `feat(calc): suspended rope counted in the amplified live load`.

### Task 11: Live-load lateral loads (design note, then implementation)

**Files:**
- Modify: `docs/superpowers/specs/2026-11-08-abs-dnv-crane-loads-design.md` (append section "Lateral live-load model")
- Modify: `calculation/solver/crane_solver.py` (off-lead lateral at the support node, ~376-446), `calculation/engine.py` (`_augment_point_with_out_of_plane_loads` 458, `compute_analysis_point`), `calculation/results.py`, `core/lead_channels.py`, `core/chart_envelope.py` (`lead_points` 372, `envelope_capacity_case` 767)
- Test: `tests/test_live_load_lateral.py`

**Interfaces:**
- Produces `calculation.results.HookLateral(fraction_x: float, fraction_y: float, constant_x_kN: float, constant_y_kN: float, min_fraction: float)`: lateral hook load = `fraction * H + constant`, magnitude floored at `min_fraction * H`; constants hold wind on the suspended load (P·A with P = 0.5·rho·Cd·V² from the existing wind helper, ABS 5.19.3 / DNV 4.2.3.3), fractions hold `a/g` and `sin(incline)` (ABS 5.17 `HL_LL = VDL·a_h`, 5.21 `HL_SIA`). `compute_analysis_point(..., hook_lateral: Optional[HookLateral] = None)`; `None` reproduces today's behaviour bit for bit. `calculation/` knows nothing of ABS or DNV.

- [ ] **Step 1: Design note.** Append the section to the spec: how `HookLateral` composes with the off-lead and side-lead channels (it is an extra lateral force at the support node using the same unit-response mechanism), how the sign/direction is maximised across the four wind axes already enumerated by `candidate_wind_directions`, and where the `min_fraction` floor acts in the envelope superposition. Content must state the chosen formulas and show one worked example reproducing `abs_list_trim_load(1000, 5, 2) = 93.85 kN`. Commit the note before coding.
- [ ] **Step 2: Write the failing tests:** `hook_lateral=None` leaves the GT283 golden reactions unchanged; a pure `incline_deg` of 5.385° at H = 1000 kN adds a lateral of 93.85 kN (±0.01) at the support node; wind constant is independent of H; the floor: with all fractions zero and `min_fraction = 0.02`, lateral is `0.02 * H` and reactions grow linearly in H; the lateral direction chosen is the one with the largest demand.
- [ ] **Step 3: Run** `pytest tests/test_live_load_lateral.py --no-cov -q`. Expected: FAIL.
- [ ] **Step 4: Implement** `HookLateral` and its plumbing (probe set and superposition in `chart_envelope` treat it as one more lead channel); fill it from `LiftSetup.lateral` in Task 9's path. Run the test file plus `tests/test_vessel_frame_engine.py tests/test_chart_envelope.py tests/test_sweep_envelope.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(calc): live-load lateral loads on the hook`.

### Task 12: Foundation, slewing-bearing and retaining-component loads

**Files:**
- Modify: `calculation/allowable.py` (`allowable_hook_load` 87, `_magnitude_candidate` 39), `calculation/capacity.py`, `calculation/engine.py` (`compute_allowable_load` 723, `compute_omnidirectional_allowable_load` 745), `core/limit_factory.py`, `core/analysis_services.py` (`compute_result_rows` 318), `core/results.py`
- Test: `tests/test_foundation_factors.py`

**Interfaces:**
- Produces: `calculation.allowable.DemandScale(live: Callable[[float], float], dead: float = 1.0)` (argument: live load LL in kN); `allowable_hook_load(..., demand_scale: Optional[Mapping[str, DemandScale]] = None)` keyed by connection id (`"platform_base"`); demand = `dead * baseline + live(LL) * sensitivity * H`; any non-`None` scale takes the `solve_capacity_limit_kN` bisection path (monotone for PF, see spec). `core/limit_factory.py` adds limit ids `platform_base_retaining_<component>` (same components as `platform_base`) evaluated with `DemandScale(live=lambda _: 3.75, dead=1.0)`. `ResultRow.kind` gains `"factored"` rows labelled "Platform Base (ABS PF)" / "(DNV SF1)" / "Retaining".
- LL passed to the scale is the unamplified live load: payload + hook + suspended rope, in kN.

- [ ] **Step 1: Write the failing tests:** `demand_scale=None` equals today's capacity; with `DemandScale(live=lambda ll: 1.2)` a linear limit's capacity equals `(limit - baseline) / (1.2 * s)`; with the oracle's ABS PF the capacity solves the monotone equation (check demand at the returned H equals the limit within 1e-6); 3.75 retaining capacity for `platform_base_Fz`; DNV SF1 scales dead and live terms; reported rows include "factored" rows only when a profile is active.
- [ ] **Step 2: Run** `pytest tests/test_foundation_factors.py --no-cov -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the signatures above; pass `LiftSetup.foundation` and `retaining_live_factor` from `factor_for_point`.
- [ ] **Step 4: Run** the same command plus `tests/test_allowable_load_limits.py tests/test_min_bearing_line_load.py tests/test_limit_factors.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(calc): pedestal, slewing-bearing and retaining-component load factors`.

---

## Phase 4: Provenance, UI, docs, acceptance

### Task 13: Provenance in sweep results and CSV

**Files:**
- Modify: `core/sweep.py` (payload dict ~347-352), `core/sweep_cache.py`, `qml_app/viewmodels/chart_vm.py` (`_SweepWorker` 106, `_curve_points` 1136, `exportCsv` 1312-1340)
- Test: `tests/test_chart_view_model.py` (extend), `tests/test_sweep_modes.py` (extend)

**Interfaces:**
- Produces: sweep payload gains `provenance: list[tuple[float, tuple[ProvenanceRecord, ...], tuple[str, ...]]]` (outreach, records, warnings) and `condition: str`; legacy payload gains `provenance == []`. CSV header becomes `series, outreach_m, load_t` for legacy documents (unchanged) and adds `condition, factor, clause, source, warnings` when `provenance` is non-empty.

- [ ] **Step 1: Write the failing tests:** legacy export is byte-identical to today's; a rules document export has the extra columns and a `computed` or `override` source per capacity row; `exportCsv` still refuses while partial.
- [ ] **Step 2: Run** the two test files with `--no-cov -q`. Expected: FAIL.
- [ ] **Step 3: Implement** carrying `LiftSetup.records/warnings` per angle into the payload; extend `exportCsv`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(chart): clause trail in sweep payload and CSV export`.

### Task 14: Condition selector and details view

**Files:**
- Modify: `qml_app/viewmodels/chart_vm.py`, `qml_app/qml/LoadChartWorkspace.qml`, `qml_app/models/report_rows.py`, `presentation/formatters.py`
- Test: `tests/test_chart_view_model.py` (extend), `tests/test_qml_shell.py` (extend)

**Interfaces:**
- Produces: `ChartViewModel.conditionNames` (`QStringList`, empty for legacy documents), `ChartViewModel.currentCondition` with setter that re-plans chart jobs (Task 8), `ChartViewModel.provenanceRows` (`QVariantList` of dicts with `quantity, value, unit, clause, formula, source, warnings`). Use the `qml-ui-development` skill for the QML.

- [ ] **Step 1: Write the failing tests:** legacy document hides the selector (`conditionNames == []`); a two-condition document lists both and switching changes `curve_points` without reusing the other cache entry; `provenanceRows` for a hovered or selected outreach lists the dynamic-factor record with its clause.
- [ ] **Step 2: Run** the two files with `--no-cov -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the view-model properties and the QML selector and details panel.
- [ ] **Step 4: Run** the same command, then take a headless screenshot with the `run-app` skill to confirm the selector and panel render. Expected: PASS and a usable screenshot.
- [ ] **Step 5: Commit** `feat(ui): condition selector and calculation details`.

### Task 15: Documentation

**Files:**
- Create: `docs/adr/0004-rules-profiles-keep-the-core-class-free.md`
- Modify: `README.md` (Document Lifecycle, References), `CONTEXT-EXTENDED.md` (version line), `CONTEXT-CORE.md` (add Rules profile, Condition)

- [ ] **Step 1:** Write the ADR (Status, Date, Context, Decision, Consequences: profiles in `rules/`, closed-form inverse factors, `HookLateral` and `DemandScale` as the only core hooks, rope-only stiffness deviation, DNV acceleration handling).
- [ ] **Step 2:** Update README and CONTEXT files: schema `11.1.0`, `rules`/`conditions` YAML example copied from `tests/test_rules_schema.py`, the stale `5.12.0` line.
- [ ] **Step 3: Run** `.venv/Scripts/python.exe -m pre_commit run --all-files`. Expected: all hooks pass.
- [ ] **Step 4: Commit** `docs: ADR-0004 and rules profile documentation`.

### Task 16: Acceptance run against the signed-off cases

**Files:**
- Create: `tests/test_rules_acceptance.py`, `examples/crane_input_GT283_dnv.yaml`, `examples/crane_input_GT283_abs.yaml`

**Interfaces:**
- Consumes: everything above and `tests/rules_reference.py`.

- [ ] **Step 1: Write the tests:** for each reference case (ABS onboard, ABS offboard, ABS heavy lift, DNV Case I, DNV Case II, ψ-floor ranges, PF clamps, SF1, 3.75x), build the example document with the case's inputs, run `run_mode_sweep`, and assert the payload at the reference outreach equals the oracle value within 1e-3 relative. Add a test that all three legacy examples reproduce their goldens.
- [ ] **Step 2: Run** `pytest tests/test_rules_acceptance.py --no-cov -q`. Expected: FAIL until the example files exist and the pipeline is complete; fix findings in the owning task's files.
- [ ] **Step 3:** Run the full suite `.venv/Scripts/python.exe -m pytest -n auto --dist loadfile` and pre-commit. Expected: all green, coverage at or above 75%.
- [ ] **Step 4: Commit** `test: ABS/DNV acceptance against the independent oracle`.
