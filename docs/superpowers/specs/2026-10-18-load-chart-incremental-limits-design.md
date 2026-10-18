# Load chart: incremental recomputation after a limit edit

## Intent
The user changes design limits (rope and connection limits) very often and watches the load chart redraw. Today every limit edit recomputes the whole sweep, although about 80% of a sweep is the per-boom-angle probe solves (`build_probes`), which do not depend on the limits at all, and the limit evaluation (`envelope_capacity`) is run once for all limits plus once per limit for the limit series. After a limit edit only the changed or added limit should be evaluated; the Capacity and Contractual series follow from it.

## Decided (by the user)
- Changing, adding or removing a limit must not recompute everything: only the affected limit is (re)evaluated, and the Capacity and Contractual series are updated from the results.
- The user asked whether to compute charts in a background thread. Sweeps already run on a worker thread (see the background-cache design). Further parallelism (a process pool) is a possible later step, not part of this work.
- The user skipped design questions; choices below are the author's calls.

## Goals
- A limit edit (value, enable/disable, auto-set) on a chart whose document is unchanged performs no probe solves and evaluates only the changed limit; unchanged limits' per-angle results are reused.
- A contractual-point edit performs no probe solves for angles already computed (it adds at most the new contractual outreach angle).
- Results are identical to a full recomputation (same curve, limit series, contractual verdicts) for the same inputs.
- Memory stays bounded.

## Non-goals / anti-goals
- No process pool or other parallelism in this work. No change to capacity physics. `run_capacity_sweep` and `run_mode_sweep` keep their results; the new cache is an optional argument.
- Anti-goal: a stale probe or limit result used after a document edit that affects it (model, vessel motion, wind, hoist data).

## Constraints and facts found
- `build_probes(calc, hoist_id, angle, wind_speed, overrides, vessel=)` depends on the document, hoist, mode overrides and angle; not on limits, limit display names or the contractual points. `envelope_capacity(calc, probes, limits, ...)` evaluates each (limit, component) independently with a single-limit dict and keeps the lowest, so the combined capacity of N limits equals the lowest of the N single-limit capacities.
- In `run_mode_sweep` (`core/sweep.py`) the combined capacity, the limit-series responsiveness test (`_affects_hook_load`) and the per-limit series capacities are computed separately per angle; with N > 1 limits that is N + 1 envelope evaluations per angle.
- A `ProbeSet` pickles to about 9.5 KB (about 30 KB in memory is a safe estimate): 1349 angles (0.1 m step) is roughly 40 MB per (hoist, mode); a step of 1 m is negligible. The cache must be bounded, with the builder measuring the true size.
- `core/` stays Qt-free (`tests/test_architecture.py`). Only one sweep job runs at a time (`ChartViewModel`), so a cache scope is touched by one thread at a time; the view model must not mutate or clear a cache in place while a worker may use it.
- The chart result cache (`core/chart_cache.py`, keyed by a fingerprint of document, limits and display names) stays as is; this work adds a compute cache beneath it.

## Design (author's calls)
1. **Compute cache** (`core/sweep_cache.py`). Keyed by a *compute fingerprint* of the document with the hoists' contractual points excluded, plus hoist id and mode name; inside a scope, probes are keyed by rounded boom angle (so different outreach steps share work) and limit results by (angle, limit signature). Bounded by total entries, least recently used. `None` probe results are cached too.
2. **Per-limit evaluation in `run_mode_sweep`.** Per angle: probes from the cache; for each enabled limit its single-limit capacity and responsiveness from the cache or computed once; the combined capacity is the lowest of the limit capacities (an unlimited capacity when no limit applies); the limit series come from the same per-limit values. The cache is an optional argument; without it behaviour and results are unchanged.
3. **View model.** `ChartViewModel` owns one compute cache, passes the right scope to each worker, and replaces (not clears) it when the document changes while no worker can still be using the old one.

## Left to the builder
- Names and file layout beyond the above; entry bounds; the in-memory size measurement; the limit-signature representation.

## Verification
- Equality tests: results with the cache (cold, warm, after adding/removing/changing one limit) equal results without it, on the example documents, with several limits including ones that do not respond to the hook load and magnitude limits.
- Counting tests: a limit edit through the view model makes zero `build_probes` calls and one limit evaluation per angle; a document edit rebuilds.
- Timing, back to back with the previous code: the 22689 example at a 0.1 m step after changing one limit of several (report before/after).
- `pre_commit` passes; full suite has only the two known `test_acceptance` failures.
