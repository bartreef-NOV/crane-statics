# Load Chart Incremental Limits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After a design-limit edit the load chart evaluates only the changed or added limit; probe solves and unchanged limits' results are reused.

**Architecture:** A Qt-free compute cache (probe sets per boom angle, per-limit capacities per angle) is passed into `run_mode_sweep`, which derives the combined capacity as the lowest per-limit capacity. `ChartViewModel` owns the cache and hands each worker the right scope.

**Tech Stack:** Python 3.11, PyQt6, pytest, pydantic (`CraneDocument`).

**Spec:** `docs/superpowers/specs/2026-10-18-load-chart-incremental-limits-design.md`

## Global Constraints

- `core/` stays Qt-free (`tests/test_architecture.py`); the cache lives in `core/`, thread glue in `qml_app/viewmodels/chart_vm.py`.
- `run_capacity_sweep` and `run_mode_sweep` keep their results and signatures except for one new optional keyword argument `compute_scope` on `run_mode_sweep`; without it behaviour is unchanged.
- No process pool or other parallelism; no change to capacity physics.
- Results with the cache must equal results without it exactly (same floats), for cold and warm caches.
- A document change (model, vessel motion, wind, hoist data) must never reuse old probes; contractual-point edits and limit/display-name edits must not invalidate probes.
- Cache bound: probe sets 4096 entries, limit results 200000 entries, least recently used (the builder measures the real in-memory size of a `ProbeSet` and reports it; adjust only if 4096 sets exceed about 200 MB).
- Only one sweep job runs at a time; never mutate or clear a cache in place while a worker may be using it (replace the object instead).
- Commit steps: the user asked for the subagent-driven workflow on a feature branch in place; commit on the branch with explicit file paths only, never `git add -A`.
- The working tree may contain unrelated uncommitted edits; never touch, stage or revert files outside the task.
- Test commands use the project venv: `.venv/Scripts/python.exe -m pytest ... --no-cov`.

## Review Focus

- Warm-cache result equals the uncached result when one limit is changed, added or removed, with several limits including ones that do not respond to hook load and magnitude limits (Task 2).
- No enabled limits, or all limit values blank/zero: unlimited capacity, empty curve, no exception, same as today (Task 2).
- A document edit (vessel motion, wind speed, hoist data) rebuilds probes; a contractual-point edit and a limit edit do not (Tasks 1 and 3).
- Memory is bounded when many angles or modes are swept; the oldest entries are evicted (Task 1).
- Toggling a limit value back reuses its cached per-angle results; two limits sharing an entity but with different components are cached separately (Tasks 1 and 2).

---

### Task 1: Compute cache

**Files:**
- Create: `src/crane_statics/core/sweep_cache.py`
- Test: `tests/test_sweep_cache.py` (create)

**Interfaces:**
- Consumes: `CraneDocument`; `ProbeSet` (`core/chart_envelope.py`).
- Produces:
  ```python
  def compute_fingerprint(doc: CraneDocument) -> str
  # SHA-256 of doc.model_dump_json() with every hoist's contractual_points and
  # split_contractual_points excluded.
  LimitSignature = tuple[str, tuple[tuple[str, float], ...]]   # (limit id, sorted (component, value))
  def limit_signature(limit_id: str, components: dict) -> LimitSignature
  class LimitResult(NamedTuple): load_t: float; load_kN: float; responsive: bool
  class ComputeScope:                      # one (fingerprint, hoist, mode)
      def probes(self, angle: float, build: Callable[[], Optional[ProbeSet]]) -> Optional[ProbeSet]
      def limit_result(self, angle: float, signature: LimitSignature,
                       compute: Callable[[], LimitResult]) -> LimitResult
  class ComputeCache:
      def __init__(self, max_probe_sets: int = 4096, max_limit_results: int = 200000) -> None
      def scope(self, fingerprint: str, hoist_id: str, mode: str) -> ComputeScope
      def clear(self) -> None
      def probe_count(self) -> int
  ```
  Angles are keyed as `round(float(angle), 10)`. A `None` build result is cached. `build`/`compute` run only on a miss, outside any lock held across the call.

- [ ] **Step 1: Write failing tests** in `tests/test_sweep_cache.py`:
  - `test_compute_fingerprint_ignores_contractual_points_only`: editing a contractual point (normal and split) keeps the fingerprint; changing `doc.environment.max_wind_speed_m_s` or a vessel motion value changes it. Use `examples/crane_input_22689.yaml`.
  - `test_probes_are_built_once_per_angle_and_none_is_cached`: a counting `build` is called once for two requests of the same angle, and once for an angle whose build returns `None`.
  - `test_scopes_are_independent`: the same angle in two different fingerprints/hoists/modes builds twice.
  - `test_probe_bound_evicts_least_recently_used`: `ComputeCache(max_probe_sets=2)`, request angles a, b, a, c; then b is rebuilt, a is not.
  - `test_limit_results_are_cached_per_signature`: two signatures at one angle compute separately; the same signature once; `limit_signature("rope", {"T": 5.0})` differs from `limit_signature("rope", {"T": 6.0})` and from `limit_signature("rope", {"Fx": 5.0})`, and is independent of dict order.
  - `test_limit_bound_evicts`: `ComputeCache(max_limit_results=2)`.

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_sweep_cache.py --no-cov -q`. Expected: FAIL (module missing).

- [ ] **Step 3: Implement** the module (`OrderedDict` per kind with entry counters shared across scopes; scopes are light views on the cache). Use `doc.model_dump_json(exclude={"hoists": {"__all__": {"contractual_points", "split_contractual_points"}}})` for the fingerprint, verified by the first test. Measure `sys.getsizeof`-deep or `pickle` size of a real `ProbeSet` (22689 example, one mid-range angle) and record it in the report.

- [ ] **Step 4: Run** the tests and `.venv/Scripts/python.exe -m pytest tests/test_architecture.py --no-cov -q`. Expected: pass.

- [ ] **Step 5: Commit** `git add src/crane_statics/core/sweep_cache.py tests/test_sweep_cache.py && git commit -m "Sweep compute cache"`

---

### Task 2: Per-limit evaluation through the cache

**Files:**
- Modify: `src/crane_statics/core/sweep.py` (`run_mode_sweep`)
- Test: `tests/test_sweep_incremental.py` (create)

**Interfaces:**
- Consumes: `ComputeScope`, `LimitResult`, `limit_signature` (Task 1); `build_probes`, `envelope_capacity`, `lead_points` (`core/chart_envelope.py`).
- Produces: `run_mode_sweep(..., compute_scope: Optional[ComputeScope] = None)` (new last keyword argument). With or without a scope, the returned payload is identical to today's. Per angle the sweep: gets probes via `compute_scope.probes(angle, build)` (or builds them directly); for each enabled limit gets a `LimitResult` (single-limit `envelope_capacity` load in t and kN, plus `responsive` = the existing any-lead-point `_affects_hook_load` test) via `compute_scope.limit_result` (or computes it); the combined capacity is the result with the lowest `load_kN`; when no limit is enabled or none applies it is the unlimited capacity (`envelope_capacity` with the empty limit dict, as today). `limit_series` points come from the same `LimitResult`s; the `cap if len(enabled_limits) == 1` shortcut disappears because the combined capacity is then the single result.

- [ ] **Step 1: Write failing tests** in `tests/test_sweep_incremental.py` (example `crane_input_22689.yaml`, hoist `MH`, step 5.0, vessel limits set as in `tests/test_sweep_envelope.py`, wind 20 m/s; build limit dicts from the document's rope and connection entities, choosing values that make several limits bind; include one limit that does not respond to the hook load and one magnitude limit such as `platform_base` `max_bearing_line_load`):
  - `test_scope_does_not_change_results_cold_and_warm`: payload without scope == payload with a fresh scope == payload with the same (warm) scope, for the normal mode and, if available, the split mode (compare `curve_data`, `limit_series`, `n_points` and the contractual results' allowables and statuses).
  - `test_changing_adding_removing_one_limit_equals_a_full_recompute`: with a warm scope, change one limit's value, add one, remove one, disable all; each result equals the same sweep without a scope.
  - `test_warm_scope_makes_no_probe_solves_and_one_evaluation_per_limit_angle`: patch `crane_statics.core.sweep.build_probes` and `crane_statics.core.sweep.envelope_capacity` with counting wrappers; after warming, changing one limit's value gives 0 `build_probes` calls and exactly one single-limit `envelope_capacity` call per swept angle for that limit (plus the empty-dict fallback calls only where today's code makes them).
  - `test_no_enabled_limits_gives_an_unlimited_empty_curve`: `{}` and a limit with value `None`/`0` give `n_points == 0`, no exception, same with and without scope.
  - `test_toggling_a_value_back_reuses_the_cached_results`: change a limit and change it back; the second return makes 0 evaluations.
  - `test_same_entity_different_components_are_separate`: two components of one entity at different values give different cached results and a correct combined result.

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_sweep_incremental.py --no-cov -q`. Expected: FAIL (`compute_scope` unknown).

- [ ] **Step 3: Implement** the restructure in `run_mode_sweep`; keep `_envelope`'s per-call cache for the contractual stage working through the same scope. Stage 1 (contractual) and stage 2 share the per-angle results.

- [ ] **Step 4: Run** `.venv/Scripts/python.exe -m pytest tests/test_sweep_incremental.py tests/test_sweep_modes.py tests/test_sweep_envelope.py tests/test_chart_view_model.py --no-cov -q` and `.venv/Scripts/python.exe -m pytest tests/test_sweep_envelope.py -m slow --no-cov -q`. Expected: all pass (the slow benchmark threshold must still hold).

- [ ] **Step 5: Commit** `git add src/crane_statics/core/sweep.py tests/test_sweep_incremental.py && git commit -m "Sweep: per-limit evaluation through a compute cache"`

---

### Task 3: View model uses the compute cache

**Files:**
- Modify: `src/crane_statics/qml_app/viewmodels/chart_vm.py`
- Test: `tests/test_chart_incremental.py` (create)

**Interfaces:**
- Consumes: `ComputeCache`, `compute_fingerprint` (Task 1); `run_mode_sweep(..., compute_scope=...)` (Task 2); the existing `_start`, `_job_key`, `_SweepWorker`, `_on_document_changed`, `shutdown`.
- Produces: `ChartViewModel._compute_cache: ComputeCache`. `_start` computes `compute_fingerprint(doc_copy)` on the GUI thread, takes `self._compute_cache.scope(fingerprint, job.hoist_id, job.mode)` and passes it to the worker, which forwards it as `compute_scope`. On `_on_document_changed` the cache object is replaced by a new `ComputeCache()` after running workers are cancelled (never cleared in place).

- [ ] **Step 1: Write failing tests** in `tests/test_chart_incremental.py` (reuse the patching/waiting helpers from `tests/test_chart_background.py`; patch `crane_statics.core.sweep.build_probes` and `.envelope_capacity` with counters):
  - `test_a_limit_edit_makes_no_probe_solves`: complete a draw, reset the counters, change a limit via `setLimitMax`/`setLimitEnabled`, wait for the redraw; 0 `build_probes` calls, the chart equals a fresh uncached `run_mode_sweep` of the new limits.
  - `test_a_contractual_edit_makes_no_new_probe_solves_for_known_angles`: after a draw, `addContractualPoint` at an outreach on the grid; 0 `build_probes` calls; at an outreach off the grid, probe calls only for the new angle.
  - `test_a_document_edit_rebuilds_probes`: change `doc.environment.max_wind_speed_m_s` (mark content changed); `build_probes` is called again.
  - `test_document_replaced_gets_a_new_cache`: after `set_document` of another document the old cache object is not reused (`vm._compute_cache` is a different object) and the first draw solves probes.
  - `test_background_precompute_still_fills_the_result_cache`: the existing queue behaviour is unchanged (every planned job is cached).

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_chart_incremental.py --no-cov -q`. Expected: FAIL.

- [ ] **Step 3: Implement** the wiring (worker receives the scope; no logic duplicated in the view model).

- [ ] **Step 4: Run** `.venv/Scripts/python.exe -m pytest tests/test_chart_incremental.py tests/test_chart_background.py tests/test_chart_view_model.py tests/test_qml_shell.py --no-cov -q`, then the full suite `.venv/Scripts/python.exe -m pytest --no-cov -q -m "slow or not slow"` and `.venv/Scripts/python.exe -m pre_commit run --all-files`. Expected: only the two known `test_acceptance.py` failures; all hooks pass.

- [ ] **Step 5: Measure** back to back (same session): the 22689 example at a 0.1 m step with several limits enabled, time of the first draw and of a redraw after changing one limit, with this branch against the commit before Task 1 (use a `git archive` copy of that commit on `PYTHONPATH`, not a stash). Write a throwaway script outside the repo: time `run_mode_sweep` without a scope, then with a fresh `ComputeScope` (first draw), then again after changing one limit (redraw); `scripts/profile_chart.py` calls `run_capacity_sweep` without a scope and cannot show the redraw gain. Report the numbers and the memory used by the caches in the task report; do not commit the script.

- [ ] **Step 6: Commit** `git add src/crane_statics/qml_app/viewmodels/chart_vm.py tests/test_chart_incremental.py && git commit -m "Chart: reuse probe and limit results after a limit edit"`
