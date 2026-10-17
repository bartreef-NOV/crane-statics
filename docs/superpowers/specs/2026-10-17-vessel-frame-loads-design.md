# Vessel-Frame Loads: Design

Date: 2026-10-17. Status: draft for review.

## Goal

Let the operator describe vessel state (accelerations, roll, pitch) and crane orientation on the
vessel (slewing angle). Derive gravity in the crane frame from roll and pitch. The scene and
solver stay in the crane coordinate system.

## Decisions (agreed)

- Inputs live in scene state (per hoist). The authored document's `vessel_motion` holds defaults.
  This is a schema major version bump with example migration.
- All new inputs are exact signed values. There is no ± envelope for accelerations, angles or
  angular accelerations. Wind-direction enumeration is unchanged.
- Existing `pitch_angular_accel_rad_s2` / `roll_angular_accel_rad_s2` and the rotation reference
  point stay, as exact signed values.
- Wind is a constant profile: `max_wind_speed_m_s` applies at every height. Remove
  `wind_profile_exponent`, `wind_reference_height_m_asl` and `mean_sealevel_z_m`.
- The waterline is removed from the scene.

## Inputs

| Input | Frame | Notes |
|---|---|---|
| `ax, ay, az` (m/s²) | vessel | excludes gravity |
| `vessel_roll_angle` | about vessel x (γ) | positive to starboard |
| `vessel_pitch_angle` | about vessel y (β) | positive bow-down |
| `crane_slewing_angle` | about vessel z | crane frame relative to vessel frame |

Vessel axes: x forward, y port, z up. (Convention to confirm in review.)

## Frame transform: `core/vessel_frame.py` (pure, no Qt)

1. R = Rz(α)·Ry(β)·Rx(γ), intrinsic z-y-x, vessel to world. Yaw α does not affect gravity.
2. Gravity in vessel frame: `g_v = Rᵀ·(0,0,-g) = g·(sinβ, -sinγ·cosβ, -cosγ·cosβ)`.
3. Load acceleration in vessel frame: `k_v = g_v − a_v`; force on a mass is `m·k_v`.
4. Rotate by −`crane_slewing_angle` about z to get `k_c` in the crane frame.
5. Return the equivalent crane-frame acceleration triple relative to the nominal `(0,0,-g)`:
   `a_eq = (0,0,-g) − k_c`. Its components feed the existing ax/ay/az channels, so zero angles
   and zero acceleration reproduce today's results exactly.

## Solver

- `crane_solver.py`: replace ± sign enumeration for accel_x/accel_z/pitch with signed values
  scaled by the basis. Y channels (engine.py `accel_y`, roll) get the same treatment.
- Sites that use scalar `gravity_abs` (idle hook mass ~545, component weight ~635, idle mass
  ~646, rope mass ~667) must use the tilted load vector, otherwise tilt would load the payload
  but not the structure.
- Wind: drop the power-law term in `_wind_fx`; force uses `max_wind_speed_m_s` directly.

## Scene

Crane frame unchanged. Remove `SceneWaterline`, `SceneFrame.set_waterline`,
`SceneBuilder._draw_waterline`, the `waterline` frame field, and the renderer item. Gravity
arrows show the in-plane component of `m·k_c`.

## Data / schema

- `data/models.py`, `data/authored_models.py`: new `vessel_motion` fields (roll, pitch, slew,
  vessel-frame accelerations); remove wind-profile and sea-level fields; major version bump and
  migration in `core/io.py`; regenerate JSON Schema; migrate `examples/`.
- Hook-height default: unauthored means crane-frame z = 0 (previously the waterline).
- Offlead/sidelead remain user-entered rope angles in the crane frame; the hook force is
  `m·k_c` applied through the rope. The rope direction is not recomputed from the resultant.

## Testing

- Rotation matrix against hand-computed cases (roll only, pitch only, combined).
- Zero angles and accelerations reproduce current results exactly.
- Slew 90° swaps the x/y effects of vessel ax/ay.
- Structure weight and payload weight tilt consistently.
- Migration golden test and schema round-trip.
- Scene build has no waterline; QML renderer tests updated.

## Out of scope

Recomputing rope direction from the load resultant, wind-profile options, ± envelopes for the
new inputs.

## Docs

Update `CONTEXT-*.md` vocabulary and `docs/cpp-port-plan.md` where they mention the removed
fields.
