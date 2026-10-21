# Load Chart Live Series Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** While a load chart is (re)computed, show all its series (capacity, every limit series) as they arrive, and show the contractual points: grey until the sweep has decided pass or fail, then green or red.

**Architecture:** `run_mode_sweep` gets two optional callbacks (contractual verdicts after stage 1; per-limit points next to each curve batch) and a pure `limit_series_layout` helper; `_SweepWorker` forwards them as signals; `ChartViewModel` keeps the streamed limit series and the markers during streaming instead of emptying them, and the QML plot draws pending markers grey.

**Tech Stack:** Python 3.11, PyQt6/QML, pytest.

**Spec:** agreed in chat (no spec file); the agreed design is under "Design" below.

## Design (agreed with the user in chat)

- Contractual points appear as grey markers from the start of a draw, taken from the document's contractual points of the wanted mode. When stage 1 finishes (normally well under a second) each turns green or red. They are never decided before the capacity at their outreach is known.
- The pending colour changes from orange to a neutral grey (the legend entry as well).
- Each limit's points stream in together with the capacity curve and show as they arrive.
- A limit keeps its colour from the first batch to the finished chart: colours are assigned by position among ALL enabled limits in display order (rank, then label), not among the limits that end up with points.
- Axis behaviour while computing is unchanged: x from the hoist's outreach range, y from the capacity curve so far; limit series never stretch y (existing tests).
- Only the visible chart streams; background jobs, the cache, export gating (`chartComplete`) and the final payload replacing the stream at the end are unchanged.

## Global Constraints

- `core/` stays Qt-free (`tests/test_architecture.py`); Qt signals live in `qml_app/viewmodels/chart_vm.py`.
- `run_capacity_sweep` / `run_mode_sweep` results and signatures keep working: the two new keyword arguments of `run_mode_sweep` are optional and without them behaviour is unchanged. The payload structure is unchanged.
- No new test may rely on sleeps; use the deterministic gates and `wait_until` helpers of `tests/test_chart_background.py`.
- Commit steps: commit on a feature branch with explicit file paths only, never `git add -A`; the working tree may hold unrelated uncommitted edits (`.gitignore`, `CLAUDE.md`) that must not be staged.
- Test commands use the project venv: `.venv/Scripts/python.exe -m pytest ... --no-cov`.

## Review Focus

- Split mode shows the split mode's contractual points (not the normal ones) while streaming, and a mode without contractual points shows no markers and no error (Task 2).
- Switching hoist or mode, an edit, or a cancel mid-stream leaves no series or markers of the previous job on screen (Task 2).
- A chart served from the cache (no streaming) renders exactly as before, with the new colour rule (Task 2).
- The contractual callback fires before any curve batch, and an empty or failed stage 1 yields pending markers, not a crash (Task 1).
- A limit with no points in the middle of the order does not shift the colours of the others between the stream and the finished chart (Tasks 1 and 2).

---

### Task 1: Sweep callbacks and series layout

**Files:**
- Modify: `src/crane_statics/core/sweep.py` (`run_mode_sweep`)
- Test: `tests/test_sweep_live.py` (create)

**Interfaces:**
- Produces:
  ```python
  def limit_series_layout(
      doc: CraneDocument, hoist_id: str, enabled_limits: dict, limit_display_names: dict
  ) -> list[tuple[str, str, int]]
  # (limit id, display label, rank) for EVERY enabled limit, in display order (rank, then label),
  # exactly the rank and label rules run_mode_sweep applies to its limit_series today.
  def run_mode_sweep(..., on_contractual: Optional[Callable[[list[tuple[Any, Optional[float], Optional[bool]]]], None]] = None,
                     on_limit_points: Optional[Callable[[dict[str, list[tuple[float, float]]]], None]] = None) -> Optional[dict]
  ```
  `on_contractual` is called once, right after stage 1, with the same `(contractual point, allowable load t or None, passed or None)` tuples that end up in `contractual_results` (a copy; not called when the mode does not apply or has no contractual points). `on_limit_points` is called each time `on_points` flushes a batch, with `{limit id: [(outreach, load_t), ...]}` for the limits that gained points since the previous call (never an empty dict); per limit the concatenation of all batches equals that limit's final `limit_series` points. The final `limit_series` assembly uses `limit_series_layout` (no duplicated rank/label logic).

- [ ] **Step 1: Write failing tests** in `tests/test_sweep_live.py` (example `crane_input_22689.yaml`, hoist `MH`, step 5.0, several limits as in `tests/test_sweep_incremental.py`, at least one limit that yields no series points):
  - `test_layout_matches_the_final_series_order_and_labels`: `limit_series_layout(...)` lists every enabled limit; the final payload's `limit_series` rows are the layout rows with points, in the same relative order, with equal label and rank.
  - `test_on_contractual_fires_once_before_any_curve_batch`: record an event log from `on_contractual` and `on_points`; the first event is the contractual call and it carries the same verdicts as the payload's `contractual_results`.
  - `test_on_contractual_not_called_without_contractual_points`: a split mode or document without contractual points.
  - `test_limit_batches_concatenate_to_the_final_series`: with `batch_points=4`, per limit the concatenated batches equal the payload's series points; every dict is non-empty; calls coincide with `on_points` flushes (same count).
  - `test_callbacks_do_not_change_the_payload`: payload with callbacks == payload without.

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_sweep_live.py --no-cov -q`. Expected: FAIL.

- [ ] **Step 3: Implement** `limit_series_layout`, the two callbacks and the shared assembly in `core/sweep.py`.

- [ ] **Step 4: Run** `.venv/Scripts/python.exe -m pytest tests/test_sweep_live.py tests/test_sweep_modes.py tests/test_sweep_incremental.py tests/test_sweep_envelope.py tests/test_chart_view_model.py --no-cov -q`. Expected: pass.

- [ ] **Step 5: Commit** `git add src/crane_statics/core/sweep.py tests/test_sweep_live.py && git commit -m "Sweep: contractual and per-limit streaming callbacks"`

---

### Task 2: View model and plot show every series while computing

**Files:**
- Modify: `src/crane_statics/qml_app/viewmodels/chart_vm.py`, `src/crane_statics/qml_app/qml/QuickChartPlot.qml` (and `ChartLegend.qml` if it carries the pending colour)
- Test: `tests/test_chart_live.py` (create)

**Interfaces:**
- Consumes: `run_mode_sweep(..., on_contractual=, on_limit_points=)` and `limit_series_layout(doc, hoist_id, enabled_limits, limit_display_names)` (Task 1); the existing streaming machinery (`_SweepWorker.pointsReady`, `_stream_points`, `_show_stream`, `_on_worker_points`, `_after_job`, `_clear_display`, `_render_payload`).
- Produces: `_SweepWorker.contractualReady = pyqtSignal(object)` and `limitPointsReady = pyqtSignal(object)` (forwarding the callbacks, with `time.sleep(0)` after each emit like `pointsReady`); in the view model a stream state holding the streamed limit points per limit id and the stage-1 verdicts of the running job, reset whenever a job starts or the display is cleared; `_show_stream` renders the capacity curve, one series per limit that has points (id, label, colour, points; order and colour index from the layout over ALL enabled limits), and the markers: grey `pending` markers from the wanted mode's contractual points (`self._contractual_points()`) until the verdicts arrive, then `pass`/`fail`/`pending` from them; the contractual table model rows follow (pending first, then allowable and status), through a helper shared with `_render_payload`. `_render_payload` uses the same colour rule (position in the layout over all enabled limits). In QML the `pending` marker colour is a neutral grey from the palette (and the legend entry of pending markers).

- [ ] **Step 1: Write failing tests** in `tests/test_chart_live.py` (reuse the gated fake sweep, `wait_until`, fixtures and teardown style of `tests/test_chart_background.py`; the fake must be able to call `on_contractual` and `on_limit_points` at chosen moments):
  - `test_contractual_markers_are_grey_from_the_start_then_decided`: right after the draw starts and before the fake calls `on_contractual`, `vm.markers` has one `pending` marker per contractual point of the mode with the right outreach and load; after the call the statuses are `pass`/`fail` as delivered, and the contractual table rows show allowables.
  - `test_limit_series_stream_in_with_stable_colours`: two limits where the first yields no points; after a batch the shown series has the second limit with colour index 1 of the palette; the finished chart has the same colour for it.
  - `test_split_mode_streams_its_own_contractual_points`: select a splittable hoist, `setChartMode("split")`, hold the sweep; markers equal the split points; a mode without contractual points shows none.
  - `test_mid_stream_switch_leaves_nothing_behind`: switching hoist, switching mode, a content edit and `_cancel_all`/cancel each leave `limitSeries == []` and `markers` per the new wanted chart (not the old job's).
  - `test_cached_chart_renders_without_streaming`: a cached wanted chart renders as before (final payload markers/series; colour rule position among all enabled limits) and the fake sweep is not called.
  - `test_background_jobs_do_not_touch_series_or_markers` and `test_limit_series_do_not_stretch_the_partial_y_axis` (existing axis rule).
  - A QML-level check in `tests/test_qml_shell.py` style, or a source check if the shell cannot render: the pending marker colour in `QuickChartPlot.qml` is no longer `#ef6c00`; say which in the report.

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_chart_live.py --no-cov -q`. Expected: FAIL.

- [ ] **Step 3: Implement** the worker signals, the stream state, `_show_stream`/`_on_worker_*` handlers, the shared contractual-rows helper, the colour rule in `_render_payload`, and the QML colour change. Handlers apply the existing guards (`_stopped()`, `running.worker is worker`, `_running_is_wanted()`), and only emit `chartUpdated` for the wanted running job.

- [ ] **Step 4: Run** `.venv/Scripts/python.exe -m pytest tests/test_chart_live.py tests/test_chart_background.py tests/test_chart_incremental.py tests/test_chart_view_model.py tests/test_qml_shell.py --no-cov -q`, then the full suite `.venv/Scripts/python.exe -m pytest --no-cov -q -m "slow or not slow"` and `.venv/Scripts/python.exe -m pre_commit run --all-files`. Expected: only the two known `test_acceptance.py` failures; all hooks pass.

- [ ] **Step 5: Run the app** with the `run-app` skill on the 22689 example at a 0.1 m step and screenshot mid-draw (grey markers, limit series arriving, markers turning green/red) and after completion; save the screenshots outside the repo and say where.

- [ ] **Step 6: Commit** `git add src/crane_statics/qml_app/viewmodels/chart_vm.py src/crane_statics/qml_app/qml/QuickChartPlot.qml tests/test_chart_live.py` (plus `ChartLegend.qml` / `tests/test_qml_shell.py` if changed) and `git commit -m "Chart: show every series and the contractual points while computing"`
