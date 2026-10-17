# Load chart: worst case over slew, wind direction and vessel-motion signs

## Intent
The load chart must report the lowest allowable load of a fully revolving crane. Capacity is the minimum over:
- every crane slewing angle, 0-360 degrees;
- wind from any direction relative to the crane, 0-360 degrees, at the Model's maximum wind speed;
- both signs of the hoist's authored offlead and sidelead angles (`hook.offlead_deg`, `hook.sidelead_deg`), as Auto-Set does (`iter_wind_lead_directional_cases`);
- both signs of each of seven vessel motion limits: surge, sway, heave (m/s^2), roll, pitch (rad/s^2), roll angle, pitch angle (deg).

It must also be fast. Today (commit of this session) the chart enumerates the 128 sign combinations, each with 4 axis-aligned wind cases, through full solves; GT283 with all seven limits set takes about 0.5 s per outreach point.

## Decided (by the user)
- The crane is always fully revolving. The chart is the worst case over slew 0-360.
- Wind acts from any direction relative to the crane (worst case over all 360), replacing the four axis-aligned wind cases (+X, -X, +Y, -Y).
- Model vessel motion values are ± limits; the chart takes the worst case over both signs. Scene inputs are clamped to those limits and never affect the chart.
- Vessel input names: surge, sway, heave, roll, pitch, roll angle, pitch angle.

## Goals
- Chart result equals brute-force enumeration (all sign combinations x fine slew grid x fine wind grid) to within the scan resolution, verified by a test on the example documents.
- A full chart draw is dramatically faster than now (target: well under the current 0.5 s per outreach point with all limits set; builder to measure and report).
- No change to Scene analysis results for a given set of Scene inputs.

## Non-goals / anti-goals
- No new solver physics. The out-of-plane pass keeps its current scope (see CONTEXT-EXTENDED.md): hinge totals, rope tensions and member loads stay in-plane. Do not change that here.
- Auto-Set (`limit_auto_set.py`) keeps its behaviour; reuse its lead composition (`_compose_lead_channel_point`) rather than duplicating it.
- A faster chart that silently reports a higher (unsafe) capacity than brute force is a failure, even if it is quick.

## Constraints and facts found
- The in-plane solve is exactly linear in its load channels (dead, hook, offlead, accel x, accel z, pitch accel, wind); `compose_unit_basis_point` already composes signed channels. Wind force scales with speed squared, so it is exact only at the speed the basis was built at. No tension-only or iterative nonlinearity exists in the in-plane solve (`crane_solver.py`).
- Slew affects results only by rotating the vessel-frame horizontal load (kx, ky) and the (roll, pitch) angular accelerations into the crane frame (`calculation/vessel_frame.py`). Geometry is independent of slew. Gravity tilt is nonlinear in the angles but is converted to crane-frame load components first.
- Today the basis is rebuilt on every `compute_analysis_point` call (no cache). Profile: basis build ~64%, out-of-plane pass ~32%, composing ~3%.
- The out-of-plane pass (`_augment_point_with_out_of_plane_loads`) is called 3 times per point; the hook-0 and hook-1 calls give identical moments, Fy and Mx. The sidelead unit is motion-independent. All of it is affine in crane-frame (accel x, y, z, pitch, roll accel, sidelead) and in wind per axis.
- It uses `compute_all_node_positions` without `active_hook_positions`, so hook-related z differs slightly from the in-plane solve. Keep or fix this deliberately, and say which.
- Flipping a y-type input (sway, roll, roll angle) leaves in-plane results unchanged and flips lateral results, exactly only if all mass points have zero y offset.
- `split_wind_speed_components` (engine.py) gives axis speed components for the four directions only; the wind model treats X and Y with separate areas. Generalising to an arbitrary angle by components is the intended approach; the builder must confirm how the per-axis forces scale for non-axis angles and keep the axis cases identical to today.
- Limits are of two kinds: linear in a single response (rope T, Fx, Fz, Fy, M, My, Mx, boom axial/normal), and magnitude-based (resultant, fradial, mradial, bearing line load, which uses a bisection solver in `capacity.py`).
- Existing behaviour to preserve: per-limit series are only produced when a limit responds to hook load (`_affects_hook_load`); contractual outreaches are computed in stage 1 and again in stage 2; split mode has its own overrides.

## Found: the chart ignores offlead and sidelead today
`run_capacity_sweep` calls `compute_analysis_point` without `offlead_deg`/`sidelead_deg`, and `compute_allowable_load` never applies the lead sensitivity channels (`offlead_lateral_unit_*`, `sidelead_lateral_unit_reactions`); only Auto-Set scales them by sin(lead angle) in `_compose_lead_channel_point`. `iter_wind_directional_cases` is documented as "wind-direction-only cases for chart sweeps", so this may have been deliberate, but the user expects the chart to account for sidelead, so it is treated as a gap. The examples author nonzero leads (e.g. GT283 MH: offlead 1.0, sidelead 2.5), so chart capacities will drop slightly for them. The lead channels are linear in the hook load, so they compose cheaply on the cached basis. Update the example-based chart tests that pin capacities.

## Suggested approach (builder may improve)
1. Cache one basis per (boom angle, hoist, runtime overrides, tackle): unit channels plus the precomputed out-of-plane unit channels and sidelead unit. Compose each case arithmetically.
2. Treat slew and wind direction as continuous parameters: for linear limits use the closed form (response = B0 + P cos(slew) + Q sin(slew), maximum B0 + sqrt(P^2+Q^2)), and pick the worst sign pattern from the sign of each weight; for magnitude-based limits, scan slew and wind angle on a fixed grid with vectorised numpy and refine around the worst.
3. Drop the redundant out-of-plane call; reuse stage-1 contractual results in stage 2.
4. Keep the old brute-force path available to tests as the reference.

## Decided by me (check these)
- (User decided) The Model's slewing angle is removed: the `crane_slewing_angle_deg` field leaves `AuthoredVesselMotion` and `VesselMotion`, and the Model "Crane Orientation" group goes. The slewing angle stays a Scene-only input (Geometry group), starting at 0. Removing a field from a model with `extra="forbid"` is a breaking schema change, so this bumps the authored schema to major version 8 (new `crane-statics-v8.schema.json`, update examples, README and tests that pin 7). `core/io.py` has no migration, so v7 files that contain the field are rejected; none of the bundled examples do.
- Wind speed is the Model maximum wind speed at every direction; the existing "wind <= threshold -> single case" behaviour is kept.

- Safety direction: the fast path may be conservative (lower capacity than brute force, within about 0.5%) but must never report higher capacity. Tests assert a one-sided bound plus the 0.5% tolerance. The worst case over slew and wind angle is a joint maximum over both angles, not two independent ones.
- A zero Model limit contributes a single sign and is skipped. Roll and pitch angle signs are applied to the crane-frame load components (the gravity tilt), as `crane_frame_motion` does today.
- The worst sign pattern is chosen per limit (each limit has its own worst case); the chart takes the minimum over limits. The per-limit series keep their current meaning; which pattern governs is not reported.
- If any mass point has a nonzero y offset, the sway/roll mirror shortcut is not used: enumerate those signs (or fall back to the brute-force path). Never assume the mirror.
- (User decided: option A) Wind at angle theta uses per-axis components: Fx from area_w with (V cos theta)^2, Fy from area_v with (V sin theta)^2, each keeping its sign. The four axis cases give exactly today's numbers. Between the axes the force is smaller than the axis value; for linear limits the worst case is therefore still on an axis, so the gain is mostly for the magnitude-based limits.
- Sidelead moment arm fix (user raised it): `_build_out_of_plane_reactions` applies the sidelead force at `hoist.load_node_id`, which is the hook node, taken from raw kinematics (a placeholder 1 m below the sheave). The rope transmits the load to the crane at the supporting sheave (`hoist.support_node_id`), and the in-plane offlead response is already applied at the sheave. Apply the sidelead force at the support node. Do not use `active_hook_positions` for this. The support-compensation mass already uses the support node. This changes Scene results when sidelead is nonzero (Mx and left/right split shift by Fy times the drop over the support width), so update tests that pin those numbers deliberately. The chart now includes sidelead (next item), so it changes too.
- Performance target: at least 10x faster than the current sweep on GT283 with all seven limits nonzero (benchmark: `examples/crane_input_GT283.yaml`, hoist MH, 2 m outreach step, one limit enabled; measured at 3.7 s for the current approach), and no slower than today with all limits zero.

## Left to the builder
Scan resolution and refinement strategy; where the cache lives and how it is invalidated when the document changes; whether to fix the hook-position inconsistency in the out-of-plane pass; test tolerances.
