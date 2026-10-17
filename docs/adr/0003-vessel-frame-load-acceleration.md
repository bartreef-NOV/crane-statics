# ADR-0003 — One vessel-frame transform produces the crane-frame load acceleration

- **Status**: accepted
- **Date**: 2026-10-17

## Context

The solver treated gravity as a scalar acting along crane-frame -z, and vessel motion
as separate X/Z/Y accelerations and pitch/roll angular accelerations added on top.
There was no way to say the vessel is rolled or pitched, or that the crane is slewed
relative to the vessel, so tilt could not change the direction of gravity on the crane.
Wind carried a height profile and a mean sea level reference, and the scene drew a
waterline, none of which the load model needed. Accelerations were entered as a +/-
envelope, and the roll sign convention on the legacy Y path was left-handed.

## Decision

`calculation/vessel_frame.py` is a pure transform, `crane_frame_motion(g, VesselInputs) ->
CraneFrameMotion`. Vessel axes are x forward, y port, z up; pitch is positive
bow-down, roll positive to starboard, orientation `Rz(yaw)·Ry(pitch)·Rx(roll)`.
It forms the load acceleration `k_v = g_v − a_v` in the vessel frame, rotates it by
−slew about z into the crane frame, and returns the equivalent crane-frame
acceleration `a_eq = (0,0,−g) − k_c`. That feeds the solver's existing
ax/ay/az/pitch/roll channels. `drawn_loads` (via
`AnalysisCalculator.drawn_load_conditions()`) gets the same motion split for drawing:
the Gravity arrows show the in-plane part of the tilted gravity `m·g_c` (`gravity_crane`),
and Inertia carries only the vessel accelerations `−m·a_c` rotated by −slew
(`accel_crane`) plus the pitch-acceleration lever terms. A pure tilt therefore draws a
tilted Gravity arrow and no Inertia; `g_c − a_c = k_c`, so the totals equal what the
solver applies and the Equilibrium Check holds under tilt and slew. Roll and pitch angular accelerations
rotate with slew as one right-handed vector; roll acceleration is right-handed about +x.

Other decisions in the same change:

- Wind is constant: no height profile, no mean sea level.
- Inputs are exact and signed. There is no +/- envelope for accelerations or angles.
  Wind direction enumeration is unchanged.
- The waterline is removed from the scene.
- Idle hooks, support compensation and rope masses all feel the load vector, in the
  in-plane solve and in the out-of-plane (split-support) pass. Reported idle rope
  tension carries heave.

## Consequences

- Authored schema major is 7. v6 files are rejected; there is no migration.
- The solver's scalar-gravity sites are replaced by the equivalent accelerations.
  Scene state gains vessel roll, pitch and crane slewing angle.
- `vessel_frame` is a Qt-free leaf of the pure core and joins the C++ port list.
- Known gaps:
  - `drawn_loads` selects idle-hook masses differently from the solver for boom-hoist
    ropes and runtime overrides.
  - The hook load direction is not recomputed from the resultant load; offlead and
    sidelead remain user-entered.
