# ADR-0003 — Heel and trim tilt gravity; load charts are a worst case over slew

- **Status**: accepted
- **Date**: 2026-10-06

## Context

The crane is mounted on a vessel. A static heel or trim tilts gravity relative to the
deck, and the slewing crane sees a different tilt at every slew angle. The solver is
planar (the boom's luffing plane, X/Z) with an out-of-plane support split. Before this
decision, gravity was hard-coded as −Z everywhere.

## Decision

**Frames and signs.** These are defined once, in `calculation/vessel_attitude.py`.

- Vessel frame: x forward, y to port, z up. Heel + is starboard down; trim + is bow
  down (ZYX order).
- Slew is measured from the bow and is + clockwise seen from above.
- Crane frame: X along the boom, Y to the boom's left, Z up.
- Gravity seen by the crane is the unit vector `crane_frame_gravity(attitude, slew)`:
  - `lateral_x = sinθ·cosψ + sinφ·cosθ·sinψ` lies in the luffing plane, + toward the
    boom tip.
  - `lateral_y = sinθ·sinψ − sinφ·cosθ·cosψ` lies across it.
  - `vertical = cosφ·cosθ` does not depend on slew.

**Heel and trim are a design condition.** They are saved in the document as
`model_definition.vessel_motion.heel_deg` / `trim_deg` (schema 6.1, |angle| ≤ 30°).
Slew is a Scene operating input (`SceneState.slew_deg`) and is not saved.
`vessel_motion` accelerations stay in the crane frame, as before.

**Weights tilt; rope tensions do not.** The hook hangs plumb, so a rope carries the
full hook weight whatever the tilt.

- In `crane_solver._accumulate_loads`, every weight is split into its vertical and
  lateral parts. This covers mass points, rope lumps, idle hook blocks (their lateral
  part acts at their sheave) and the split compensation mass.
- The active hook load's vertical part acts at the hook. Its lateral part enters at
  the sheave through the existing offlead unit, and across the plane through the
  sidelead unit, which now also acts at the sheave.

**Slew is composed, not solved.**

- The vertical fraction is solved into every basis channel.
- The lateral fractions get per-unit channels on the `AnalysisPoint`:
  - `gravity_lateral_x_unit_*` in the luffing plane
  - `gravity_lateral_y_unit_reactions` across it, in the support split
- `point_composition.with_crane_gravity` moves a point to any slew as a weighted sum
  of maps.
- A level vessel skips the extra channels and reproduces the old results exactly
  (`tests/test_level_attitude_goldens.py`).

**Load charts are rated for any slew.**

- A chart point, a contractual verdict and a rope or connection auto-set case is the
  worst over the wind directions and over `envelope_slew_angles`. That is a 15° grid
  anchored on the worst in-plane slew ψ*, so ψ* and ψ* + 90/180/270° are sampled
  exactly.
- Between samples, a response that is linear in the tilt is under-estimated by at
  most R·(1 − cos 7.5°) of its tilt sensitivity, where R is the tilt's sine.
- The chart's x-axis stays crane-frame outreach of the sheave, so contractual points
  remain comparable with the level chart.

**The Scene shows one slew; the chart shows the envelope.** The scene solves and
draws at `SceneState.slew_deg`. Drawn weights use the analysis point's own
`crane_gravity`, so the Equilibrium Check closes by construction.

## Consequences

- Charts on a tilted vessel cost about 3–4× a level chart: one solve per wind
  direction, then 24 compositions and limit inversions. The bearing line load is
  inverted in closed form to keep that affordable.
- The out-of-plane split remains the simplified pass it was:
  - every support group sees every body's masses
  - in-plane forces at a Y offset add no yaw moment

  Tilted gravity inherits both simplifications.
- Not modelled: load-induced heel (no hydrostatics), the crane's position on deck
  (irrelevant to a uniform field), and vessel-frame accelerations.
- Files saved with a non-zero heel or trim need a 6.1-aware build. A level attitude
  is omitted on save, so those files stay readable by 6.0 builds.
