# ADR-0002 — `core/drawn_loads.py` is the single definition of the load model

- **Status**: accepted
- **Date**: 2026-08-27

## Context

The crane's in-plane load model — self weight, hook and payload weight, wind profile,
X/Z D'Alembert inertia, rope interface forces, and the reactions between bodies — was
implemented twice.

Once in the solver (`calculation/engine.py`, `calculation/solver/crane_solver.py`),
which assembles it to solve for tensions and reactions. And once inside the Qt
renderer, `CraneSceneRenderer`, as a family of `_collect_*` methods over a hand-synced
shadow copy of `SceneState`, so the scene could draw arrows.

The Equilibrium Check verified the renderer's copy, not the solver's. So the report
that exists to catch a wrong load model was checking the second implementation of it
against itself, and the two copies had already drifted. Worse, the vectors crossed
back into pure `core/` as anonymous 6-tuples `(origin_xy, fx, fz, QColor, label,
tooltip)`, decoded positionally in `AnalysisPresenter`, where one branch stringified a
`QColor` into a report label. Qt was in `core`'s interface in every sense except the
import that `tests/test_architecture.py` checks for.

## Decision

`core/drawn_loads.py` is the one definition of what a load is. It is pure Python:

```python
build_body_loads(
    document_dict, *, hoist, conditions, node_positions,
    analysis_point=None, body_filter=None,
) -> BodyLoads
```

`BodyLoads` holds named categories of frozen `LoadVector(world_x, world_z, fx_kN,
fz_kN, category, label, detail)` and `LoadMoment(world_x, world_z, moment_kNm,
entity_id, label, detail)`. World coordinates and named fields — no colour, no
tooltip text, no scene projection.

**The scene draws the load model; it does not own it.** `core/scene_build.py` calls
`build_body_loads` and projects and styles what comes back. `CraneSceneRenderer`
computes nothing: it shows the published `SceneFrame`. The Equilibrium Check and the
Load Summary read the same values, through the same interface, as the arrows on
screen.

**Scope is the X/Z plane, stated in the interface.** Lateral acceleration
(`accel_y_m_s2`), roll acceleration, side lead and Y-axis wind produce purely
out-of-plane forces in the solver — `engine.py::_build_split_support_reactions`
routes them into `fy` alone, never into X/Z equilibrium. They are therefore
deliberately *absent* from `LoadConditions` rather than accepted and silently
dropped. A caller passing them would be making an error the type system should
catch, not a request the module should ignore.

## Consequences

- An equilibrium mismatch is a bug in one module. The class of defect where the
  drawn arrows and the checked sum disagree cannot occur, because they are the same
  values.
- Statics assertions are plain calls on values: no `QGuiApplication`, no
  `MockCanvas`, no `SessionState`, no `SceneViewModel`. The tests that used to reach
  into renderer privates (`canvas._kin`, `renderer._boom_angle_deg`) became public
  calls.
- Two `Protocol`s (`DrawnLoadProvider`, `RendererReportingContract`) and one adapter
  (`RendererDrawnLoadProvider`) went away. Each had exactly one implementor — a
  hypothetical seam, not a real one — and production and the acceptance suite entered
  it by different routes, which is how the drift stayed invisible.
- Adding a load type means one edit, in a module with no Qt dependency, and it shows
  up in the scene, the Equilibrium Check and the Load Summary at once.
- **The rule this records**: a new force or moment is defined in `core/drawn_loads.py`
  and nowhere else. If the renderer needs something about a load, it goes in the
  returned value or in the `SceneFrame` — not into a `_collect_*` method on the
  renderer. `tests/test_architecture.py` guards import direction only, so this part
  is written down rather than executable.
