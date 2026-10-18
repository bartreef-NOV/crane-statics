# Load chart: per-(hoist, mode) jobs, a result cache and background precompute

## Intent
Switching hoist or mode in the Load Chart should show something at once. Charts already seen appear instantly from memory; charts not yet seen fill in progressively. The user prefers instant charts, accepts that a first computation cannot be instant, and finds streaming partial results acceptable.

Today (commit 714a27f, `qml_app/viewmodels/chart_vm.py`):
- One `_SweepWorker` runs `run_capacity_sweep` for the selected hoist and computes the normal and the split mode together. Switching normal/split only re-renders `_last_result`, so it is instant, but every redraw pays for both modes up front.
- Selecting another hoist calls `reload()`, which empties `_last_result` and marks the chart stale. A 250 ms timer then runs a full sweep. Nothing is stored per hoist, so switching back recomputes.
- Race (existing bug): hoist selection does not bump `_generation`. If a sweep is running when the hoist changes, `_on_sweep_finished` renders the old hoist's result under the new hoist and clears the stale flag; the new hoist is never swept.

## Decided (by the user)
- Compute the other hoists and the split mode quietly in the background, not only on demand.
- Partial results should stream into the visible chart while it is being computed.
- A background computation may use a core and make the UI slightly less smooth for now. A separate process may come later; do not build it now, but do not make it harder.
- Charts already computed are kept and reused when switching back.

## Goals
- Revisiting a computed (hoist, mode) shows its chart with no sweep.
- A not-yet-computed visible chart draws its curve progressively, low outreach to high, and the axes do not jump as batches arrive.
- The visible (hoist, mode) is computed first; clicking an unfinished one makes it jump the queue.
- No stale result is ever shown as current: the race above is gone.
- Results are identical to today's `run_capacity_sweep` output for the same inputs.

## Non-goals / anti-goals
- No change to capacity physics or to `run_capacity_sweep`'s result structure and signature: its tests and `drawBlocking` keep working.
- No separate process or process pool now.
- No persistence of cached charts across sessions or documents.
- Anti-goal: a cached chart shown after an edit that should have invalidated it. A recomputation that is not needed is cheap; a stale chart is a failure.

## Constraints and facts found
- `core/` is toolkit-neutral (Qt-free) and `tests/test_architecture.py` enforces layering; the job queue, cache and batching logic that need no Qt belong in `core/`, the QThread glue in `qml_app/`. Run the `domain-boundary-reviewer` agent after the change.
- `run_capacity_sweep` builds its closures per call and walks `mode_outreach_grid` in ascending order: stage 1 evaluates the contractual points, stage 2 the curve. `_envelope` already caches per (angle, mode); modes share no solves because their overrides differ, so splitting per mode loses no work.
- The cooperative cancel (`should_cancel`, `SweepCancelled`) already exists and is checked per outreach.
- The sweep runs on a Python thread and shares the GIL with the UI thread. Yield between batches to keep the UI usable; measure before concluding it is a problem.
- `get_calculator(doc)` caches `CraneCalculator` by `id(document)` and never evicts (`calculation/engine.py`, `_CALCULATOR_CACHE`). Each `draw()` deep-copies the document, so every sweep today leaks a document copy and a calculator; background jobs would multiply this. Jobs must construct `CraneCalculator(doc)` directly or release it when done. Note `get_calculator` is also used by other callers; do not change its behaviour for them without checking.
- A sweep reads the document content, the enabled limits (`_enabled_limits()`, which come from `model.design_limits`, not the document), the outreach step, the limit display names, the hoist and the mode. Document edits are signalled by `content_changed`/`document_changed`; the chart's `_generation` counter is bumped by both.
- Performance reference: the 22689 example at 0.1 m steps takes about 9 s for the normal mode; at 1 m steps about 1 s for both modes. Streaming matters most for fine steps.

## Design (builder's starting point; items marked "call" are the author's choices, not the user's)
1. **Per-mode sweep in `core/sweep.py`** (call). Extract the per-mode body of `run_capacity_sweep` into a public function that computes one (hoist, mode) and takes an optional batch callback delivering finite `(outreach, load_t)` points as they are computed. `run_capacity_sweep` composes it for normal and split and returns exactly today's structure. Contractual results (stage 1) may be delivered before the curve.
2. **Cache** (call). Keyed by (hoist id, mode, outreach step, input fingerprint). The fingerprint covers everything a sweep reads: document content (`model_dump` serialised and hashed), the enabled limits, the limit display names. A changed fingerprint makes old entries unreachable, so undo returns to a cached chart and no generation bookkeeping can leave a stale one. Bound the cache (call: a few dozen entries, least-recently-used); entries are small point lists. A coarser option, flushing everything on `content_changed`, is acceptable if hashing proves costly; builder to measure.
3. **Job queue** (call). Jobs are (hoist, mode). Order: the visible (hoist, mode); then the other mode of the visible hoist if splittable; then the other payload hoists in list order. One worker at a time. Selecting or changing mode to an uncomputed job makes it first: the running background job is cancelled through the existing cancel and requeued, losing its partial work. A job whose result is already cached is never queued. Hoists that are not payload hoists are never charted (`model.payload_hoist_ids()`); split is only for splittable hoists (`model.is_splitable_hoist`).
4. **Streaming** (call). The visible job's batches are appended to the displayed curve (`curvePoints`, `chartUpdated`). Axis ranges for a chart still being computed come from the hoist's outreach limits, not from the points so far. Background jobs deliver nothing until finished; they only fill the cache. Batch size or interval: builder's choice, with the aim of a handful of UI updates per second, not one per point.
5. **Invalidation and the debounce** (call). Edits keep the current behaviour: the displayed chart is marked stale and the 250 ms timer restarts the visible job; the background queue restarts behind it with the new fingerprint. Switching hoist or mode does not go through `reload()`'s clearing of results any more; it selects a cache entry.
6. **Race fix** (call). A finished job is stored under its own key; it is displayed only if its key is the currently wanted one. No result is rendered under a different hoist, mode or fingerprint.
7. **Shutdown.** `shutdown()` must still stop the worker cleanly before the event loop exits.

## Left to the builder
- Class names and file layout beyond the Qt-free/Qt split above.
- Batch size and update rate; cache bound; hash function; queue data structure.
- How the QML shows "computing" per chart (existing `busy`/`statusText` properties may be extended). No visual redesign is asked for.
- Whether `drawBlocking` runs through the same path (it must keep working for tests).

## Verification
- Tests: cache hit returns without calling the sweep; a content edit, a limit change or a step change misses; undo hits; the stale-hoist race (select another hoist while a sweep runs) shows the right hoist's chart; job ordering and priority jumps; cancelled background job is requeued, not lost; streamed points concatenate to the final curve.
- `run_capacity_sweep` output unchanged on the example documents (existing sweep tests).
- Run the app (`run-app` skill) and screenshot the Load Chart for a splittable and a non-splittable crane: switch hoists back and forth, confirm no recomputation on return and visible progressive drawing at a fine step (for example 0.1 m on the 22689 example).
- `.venv/Scripts/python.exe -m pre_commit run --all-files` passes.
