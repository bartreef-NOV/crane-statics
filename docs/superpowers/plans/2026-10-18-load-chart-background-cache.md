# Load Chart Background Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switching hoist or mode in the Load Chart shows a cached chart instantly or draws the curve progressively, while the other charts compute quietly in the background.

**Architecture:** `core/sweep.py` gets a per-(hoist, mode) sweep with a batch callback; a new Qt-free `core/chart_cache.py` holds the fingerprinted LRU cache and the job planner; `ChartViewModel` renders the wanted chart from the cache and runs one background `QThread` job at a time from a priority queue. `run_capacity_sweep` keeps its signature and result.

**Tech Stack:** Python 3.11, PyQt6 (QThread, signals), pytest, pydantic models (`CraneDocument`).

**Spec:** `docs/superpowers/specs/2026-10-18-load-chart-background-cache-design.md`

## Global Constraints

- `core/` stays Qt-free (`tests/test_architecture.py`); Qt thread glue lives in `qml_app/viewmodels/chart_vm.py`. Run the `domain-boundary-reviewer` agent after Task 4.
- `run_capacity_sweep` signature and result structure unchanged; `drawBlocking` keeps working (tests use it).
- No separate process or process pool; no persistence of the cache across sessions.
- The cache key is `(hoist_id, mode, outreach_step, fingerprint)`; the fingerprint covers document content, enabled limits and limit display names. A stale chart shown after an edit is a failure; an unnecessary recomputation is not.
- Cache bound: 48 entries, least recently used.
- Queue order: visible (hoist, mode); the other mode of that hoist if splittable; then the other payload hoists in `payload_hoist_ids()` order (normal, then split if splittable). One worker at a time. Clicking an unfinished chart jumps the queue; the running background job is cancelled (`requestInterruption`/`SweepCancelled`) and requeued after it.
- Only the visible job streams points into the UI; background jobs only fill the cache.
- Commit steps below are to be executed only if the user has asked for commits in this session; otherwise leave the work uncommitted.
- Test commands use the project venv: `.venv/Scripts/python.exe -m pytest ... --no-cov`.

## Review Focus

- Hoist switched while a sweep runs: the new hoist's chart is shown, never the old one's (Task 3 and 4 tests).
- Edit while background jobs run: results of the old fingerprint are neither displayed nor stored; the visible chart recomputes (Task 4).
- Document replaced or app shut down while a worker runs: no crash, nothing stale displayed (Task 4).
- Split mode on a hoist that is not splittable or lacks split parameters: no job, or an empty cached chart, never an exception (Tasks 1, 2, 3).
- A fine step (0.1 m, hundreds of points): updates arrive in batches, not one signal per point (Tasks 1, 4).

---

### Task 1: Per-mode sweep with batch callback

**Files:**
- Modify: `src/crane_statics/core/sweep.py` (extract the per-mode body of `run_capacity_sweep`)
- Test: `tests/test_sweep_modes.py` (create)

**Interfaces:**
- Produces:
  ```python
  def run_mode_sweep(
      doc: CraneDocument, hoist_id: str, mode_name: str, enabled_limits: dict,
      outreach_step: float, limit_display_names: dict,
      progress: Optional[Callable[[str], None]] = None,
      should_cancel: Optional[Callable[[], bool]] = None,
      on_points: Optional[Callable[[list[tuple[float, float]]], None]] = None,
      batch_points: int = 20,
  ) -> Optional[dict[str, Any]]
  ```
  Returns today's per-mode payload (`curve_data`, `contractual_results`, `limit_series`, `n_points`), or `None` when the mode does not apply: `"split"` on a hoist without `splitable_block`, `split_hook_mass_t` or `split_falls`. `on_points` receives the finite `(outreach, load_t)` pairs in ascending outreach, in lists of at most `batch_points`, and the concatenation of all batches equals `curve_data`.

- [ ] **Step 1: Write failing tests** in `tests/test_sweep_modes.py` using `examples/crane_input_22689.yaml`, hoist `MH`, step 5.0:
  - `test_mode_payload_equals_the_combined_sweep`: `run_mode_sweep(..., "normal", ...)["curve_data"] == run_capacity_sweep(...)["modes"]["normal"]["curve_data"]`, and the same for `"split"` when the example has it (skip otherwise).
  - `test_batches_concatenate_to_the_curve`: collect batches with `batch_points=4`; assert every batch has `len <= 4`, more than one batch, and `sum(batches, []) == payload["curve_data"]`.
  - `test_inapplicable_split_returns_none`: set `hoist.splitable_block = False` on a loaded document; `run_mode_sweep(..., "split", ...) is None`.
  - `test_cancel_raises`: `should_cancel=lambda: True` raises `SweepCancelled`.
  - `test_sweep_does_not_grow_the_calculator_cache`: `len(crane_statics.calculation.engine._CALCULATOR_CACHE)` is unchanged after a `run_mode_sweep` call.

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_sweep_modes.py --no-cov -q`. Expected: FAIL (`run_mode_sweep` missing).

- [ ] **Step 3: Implement `run_mode_sweep`** in `core/sweep.py`: the existing per-mode logic moves into it; build the calculator with `CraneCalculator(doc)` instead of `get_calculator(doc)` (that cache never evicts, so every sweep leaked a document copy). Flush a batch whenever `batch_points` finite points are pending and once more at the end of the curve loop. Rewrite `run_capacity_sweep` to call it for `"normal"` and, under today's condition (`splitable_block` and both split parameters not `None`), for `"split"`, building the same result dict (`hoist`, `modes`, `n_points`, `n_points_by_mode`).

- [ ] **Step 4: Run** `.venv/Scripts/python.exe -m pytest tests/test_sweep_modes.py tests/test_sweep_envelope.py tests/test_chart_view_model.py --no-cov -q`. Expected: all pass.

- [ ] **Step 5: Commit** `git add src/crane_statics/core/sweep.py tests/test_sweep_modes.py && git commit -m "Sweep: per-mode entry point with batch callback"`

---

### Task 2: Chart cache, fingerprint and job planner

**Files:**
- Create: `src/crane_statics/core/chart_cache.py`
- Test: `tests/test_chart_cache.py` (create)

**Interfaces:**
- Consumes: `CraneDocument` (`model_dump_json`).
- Produces:
  ```python
  class ChartJob(NamedTuple): hoist_id: str; mode: str
  class ChartKey(NamedTuple): hoist_id: str; mode: str; outreach_step: float; fingerprint: str
  def chart_fingerprint(doc: CraneDocument, enabled_limits: dict, limit_display_names: dict) -> str
  def empty_payload() -> dict[str, Any]   # curve_data [], contractual_results [], limit_series [], n_points 0
  class ChartCache:
      def __init__(self, max_entries: int = 48) -> None
      def get(self, key: ChartKey) -> Optional[dict[str, Any]]   # marks most recently used
      def put(self, key: ChartKey, payload: dict[str, Any]) -> None
      def clear(self) -> None
      def __len__(self) -> int
  def plan_chart_jobs(
      visible: ChartJob, hoist_ids: Sequence[str], is_splitable: Callable[[str], bool]
  ) -> list[ChartJob]
  ```

- [ ] **Step 1: Write failing tests** in `tests/test_chart_cache.py`:
  - `test_fingerprint_changes_with_document_limits_and_names_and_restores_on_undo`: edit a contractual point, then restore it; fingerprints are different, then equal again. Different `enabled_limits` and different `limit_display_names` give different fingerprints.
  - `test_cache_is_lru_with_bound`: `ChartCache(max_entries=2)`; put a, b; get a; put c; `get(b) is None`, `get(a)` and `get(c)` present.
  - `test_plan_orders_visible_then_other_mode_then_other_hoists`: hoists `["A","B","C"]`, `B` splittable only, visible `ChartJob("B","normal")` → `[B/normal, B/split, A/normal, C/normal]`; visible `ChartJob("B","split")` → `[B/split, B/normal, A/normal, C/normal]`.
  - `test_plan_never_plans_split_for_a_non_splittable_hoist`, and `test_plan_has_no_duplicates`.

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_chart_cache.py --no-cov -q`. Expected: FAIL (module missing).

- [ ] **Step 3: Implement** the module. Fingerprint: SHA-256 of `doc.model_dump_json()` plus `json.dumps` of the two dicts with `sort_keys=True, default=repr`, hex digest. `ChartCache` uses an `OrderedDict`.

- [ ] **Step 4: Run** the tests and `.venv/Scripts/python.exe -m pytest tests/test_architecture.py --no-cov -q`. Expected: pass.

- [ ] **Step 5: Commit** `git add src/crane_statics/core/chart_cache.py tests/test_chart_cache.py && git commit -m "Chart cache, fingerprint and job planner"`

---

### Task 3: View model renders from the cache (synchronous path)

**Files:**
- Modify: `src/crane_statics/qml_app/viewmodels/chart_vm.py`
- Test: `tests/test_chart_view_model.py` (add a class `TestChartCaching`)

**Interfaces:**
- Consumes: `run_mode_sweep`, `ChartCache`, `ChartKey`, `ChartJob`, `chart_fingerprint`, `empty_payload` (Tasks 1, 2).
- Produces: `ChartViewModel._cache: ChartCache`; `_wanted_job() -> Optional[ChartJob]`; `_wanted_key() -> Optional[ChartKey]` (fingerprint recomputed only when `_generation` changed since the last computation); `_render_payload(payload: dict)` (the body of today's `_render_active_mode` taking the payload as argument). `_last_result` and `_on_sweep_finished` are replaced by the cache. `drawBlocking()` computes the wanted chart if it is not cached, stores it (`None` from `run_mode_sweep` is stored as `empty_payload()`), and renders it.

- [ ] **Step 1: Write failing tests** in `TestChartCaching`, patching `crane_statics.qml_app.viewmodels.chart_vm.run_mode_sweep` with a wrapper that counts calls and delegates:
  - `test_switching_back_to_a_computed_chart_does_not_sweep`: `drawBlocking()`, select another hoist, `drawBlocking()`, select the first hoist again; assert the call count is 2 and `curvePoints` equals the first chart's (skip if the example has one payload hoist).
  - `test_mode_switch_after_both_modes_computed_does_not_sweep` for a splittable hoist (skip otherwise).
  - `test_a_limit_edit_misses_and_restoring_it_hits`: `setLimitEnabled`/`setLimitMax` change, `drawBlocking()` → one more call; restore the value, `drawBlocking()` → no further call.
  - `test_outreach_step_change_misses_the_cache`.
  - `test_switching_hoist_clears_the_displayed_chart_until_available`: after selecting an uncached hoist, `curvePoints == []` and `stale is True`.
  - `test_result_is_never_rendered_under_another_hoist`: call `drawBlocking()` for hoist A, select B without drawing; `curvePoints` is empty, not A's.

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_chart_view_model.py --no-cov -q`. Expected: new tests FAIL.

- [ ] **Step 3: Implement** the cache-backed `draw`/`drawBlocking`/`reload`/`setChartMode`: `reload()` no longer discards results; it renders the wanted payload if cached (stale False) or clears the displayed series (stale True). `_on_content_changed` and `_on_document_changed` still bump `_generation`; `_on_document_changed` also clears the cache. Keep every existing public slot and property name.

- [ ] **Step 4: Run** `.venv/Scripts/python.exe -m pytest tests/test_chart_view_model.py tests/test_acceptance.py --no-cov -q`. Expected: only the two known `test_acceptance.py` failures (`..._handles_unavailable_analysis`) remain.

- [ ] **Step 5: Commit** `git add src/crane_statics/qml_app/viewmodels/chart_vm.py tests/test_chart_view_model.py && git commit -m "Chart view model: cache-backed display"`

---

### Task 4: Background job queue and streaming

**Files:**
- Modify: `src/crane_statics/qml_app/viewmodels/chart_vm.py`
- Test: `tests/test_chart_background.py` (create)

**Interfaces:**
- Consumes: Task 3's `_cache`, `_wanted_job`, `_wanted_key`, `_render_payload`; Task 2's `plan_chart_jobs`.
- Produces:
  ```python
  class _SweepWorker(QThread):          # one (hoist, mode) job
      pointsReady = pyqtSignal(object)  # list[tuple[float, float]]
      progress = pyqtSignal(str)
      finishedWith = pyqtSignal(object) # dict (empty_payload() if run_mode_sweep returned None)
      failed = pyqtSignal(str)
      cancelled = pyqtSignal()
      def __init__(self, doc, job: ChartJob, enabled_limits: dict,
                   outreach_step: float, limit_display_names: dict) -> None
  ```
  View model internals: a queue of `ChartJob`, at most one running `(job, key, worker)`, `_pump()` (start the next uncached job if none is running), `_prioritize(job)`. A job's key is computed from its own deep-copied document and the limits at start; a finished job is stored under that key only if `_generation` is unchanged since it started, and rendered only if its key equals `_wanted_key()`. `busy` is true while the wanted chart is not yet complete.

- [ ] **Step 1: Write failing tests** in `tests/test_chart_background.py`. Patch `chart_vm.run_mode_sweep` with a recording fake that delegates to the real function, except in the controllable tests where it emits points through `on_points`, then waits on a `threading.Event` while polling `should_cancel` (raising `SweepCancelled`). Use a helper `wait_until(predicate, timeout=30.0)` that loops `QCoreApplication.processEvents()` with a short sleep. Example `22689`, step 5.0:
  - `test_draw_fills_the_cache_for_every_planned_job`: after `draw()` and waiting for idle, `_cache` holds every job from `plan_chart_jobs`, the first recorded call is the visible job.
  - `test_switching_back_does_not_resweep_after_background_fill`.
  - `test_selecting_an_unfinished_chart_jumps_the_queue`: block the first job, select another hoist; the blocked job is cancelled and recorded again after the selected one.
  - `test_hoist_switch_during_a_sweep_shows_the_new_hoist` (the stale-hoist race): after idle, `curvePoints` equals the new hoist's `run_mode_sweep` curve.
  - `test_edit_during_background_discards_old_fingerprint_results`: change a limit while jobs run; no entry with the old fingerprint is added after the edit, and the visible chart ends up matching a fresh sweep.
  - `test_streaming_grows_the_visible_curve`: with the controllable fake releasing batches one at a time, `len(curvePoints)` increases between releases and ends equal to the final payload's curve; `chartUpdated` fires at most `n_batches + 2` times.
  - `test_background_jobs_do_not_touch_the_displayed_chart`.
  - `test_document_replaced_while_running_is_safe` and `test_shutdown_stops_a_running_background_job` (no thread left running, no exception).
  - `test_non_splittable_hoist_gets_no_split_job`.

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_chart_background.py --no-cov -q`. Expected: FAIL.

- [ ] **Step 3: Implement the worker and scheduler.** `draw()` computes the fingerprint, rebuilds the queue from `plan_chart_jobs(...)` minus cached keys, and pumps. `setChartMode`/`selectHoist`/`reload` render from cache or call `_prioritize`. Partial points append to `_curve_points` and emit `chartUpdated` only for the wanted running job. While a chart is partial, `axisRanges` takes x from the hoist's `outreach_min_m`/`outreach_max_m` and pins `yMin` to 0, so the axes do not jump. Failure of a background job marks nothing stale and is logged. `shutdown()` interrupts and waits for the running worker.

- [ ] **Step 4: Run** `.venv/Scripts/python.exe -m pytest tests/test_chart_background.py tests/test_chart_view_model.py tests/test_acceptance.py --no-cov -q`. Expected: only the two known `test_acceptance.py` failures remain.

- [ ] **Step 5: Verify in the app** with the `run-app` skill: screenshot the Load Chart for the 22689 example at step 0.1; switch hoists back and forth and confirm the return is immediate and the first draw is progressive. Run the `domain-boundary-reviewer` agent on the diff.

- [ ] **Step 6: Run** the full suite `.venv/Scripts/python.exe -m pytest --no-cov -q -m "slow or not slow"` and `.venv/Scripts/python.exe -m pre_commit run --all-files`. Expected: only the two known failures; all hooks pass.

- [ ] **Step 7: Commit** `git add src/crane_statics/qml_app/viewmodels/chart_vm.py tests/test_chart_background.py && git commit -m "Chart: background jobs, priority queue and streaming"`
