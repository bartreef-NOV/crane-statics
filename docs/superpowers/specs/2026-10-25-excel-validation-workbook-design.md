# Excel validation workbook — design

## Intent

Give people who do not run Crane Statics a standalone Excel workbook that
reproduces the numbers the app's Scene view shows, so they can check the app
independently (validation) and see how the numbers arise (insight).

Reviewers must be able to trace any result back to inputs through visible,
live formulas. Auditability beats compactness.

## Goals

- A single hand-built **template** `.xlsx`: users type in their own crane data.
  It is not an exporter and the app does not generate it.
- Reproduce, for one operating state at a time:
  - **Hoist rope tensions** (per hoist, as in the Scene results table).
  - **Main support reactions**: heel point, rear hinge, front hinge, upper
    hinge, platform base (Fx, Fz, M, and the out-of-plane components the app
    reports for them).
- Include **out-of-plane effects**: Y wind, vessel roll, sidelead, Y
  accelerations, roll acceleration and the left/right reaction split, as well
  as in-plane loads (weight, hook load, in-plane wind, accelerations, pitch,
  vessel attitude, offlead, rope self-weight).
- Ship with the **22689 example** (`examples/crane_input_22689.yaml`)
  pre-filled as a worked case users can copy.
- Match the app's results for 22689 to within rounding.
- **Generic with spare rows**: every variable-length list is a fixed-size table
  with an `Active` (1/0) column, so cranes with more or fewer items than 22689
  fit without editing formulas.

## Non-goals

- Load-chart / envelope computation, "Auto" load capacity solving.
- Utilisation / limit columns (limits would be plain inputs; not provided).
- Free-body view and per-body load filtering.
- The Load Overview incremental-contribution breakdown, Equilibrium Check and
  Load Summary reports (the user chose "main reactions and rope tensions").
- Bearing line loads and other post-processed connection rows, unless trivially
  derived (builder's call; list as optional).
- Display scaling of arrows, colours, NTS culling — cosmetic.
- Reimplementing the app's authored-to-runtime expansion in formulas.
- Making the workbook an app feature (no export button, no round trip).

## Anti-goals

- A workbook that only agrees with the app for 22689 because values are
  hard-coded or fitted. Formulas must be general.
- Formulas so entangled (mega-cells, hidden VBA, macros) that a reviewer cannot
  follow them. No macros; the file must be a plain `.xlsx`.
- Silent wrong answers when a user overflows a table, leaves an unused row
  active, or enters inconsistent data: prefer visible check cells.

## Inputs the user types (the "middle route", decided)

Users enter the **already-expanded** model, not the authored YAML form. The
workbook does the simple geometry only.

- Scalars: gravity, air density, wind speed and direction.
- Structure points: boom heel, upper hinge, rear hinge, front hinge; boom
  width; slewing bearing diameter (if needed by a reported row).
- Mass points per body (boom, platform, legs as needed): mass, position.
  Boom-local (u, w) or global (x, z) per row, with a type column.
- Wind areas per body: Cd, area(s), position, boom-local or global.
- Nodes: id, body, boom-local or global or hanging, coordinates.
- Rope segments: from-node, to-node, multiplier (parts), rope id, Active.
  Reeving is entered directly as segments with multipliers; the 22689 case is
  the worked example of how parts at a node become segment multipliers.
- Hoists: rope, support node, hook node, falls, hook mass, DAF, offlead,
  sidelead, rope linear mass, rope length, split-mode fields (if included),
  tension mode (fixed vs solved for the boom-hoist rope), active vs idle.
- Scene state: boom angle (or outreach), hook load (kN or payload t with DAF),
  tackle length, offlead, sidelead, wind speed/direction, accelerations
  ax/ay/az, pitch and roll acceleration, vessel roll and pitch, slew angle.

Simple geometry the workbook does itself: boom-local to global node positions
at the boom angle, hanging-node (hook) drop below the support node, optional
outreach-to-angle.

## What the workbook computes (from the code survey)

All linear 2D statics plus an out-of-plane pass; no iteration, no root-finding.
Because the problem is linear in the loads, the workbook solves **once** with
the actual loads rather than copying the app's baseline-plus-sensitivity
decomposition. Results must be identical.

Order of calculation (cite the Python for the formula source):

1. Vessel-to-crane frame: gravity components from vessel roll/pitch, slew
   rotation, `k = g - a` (`calculation/vessel_frame.py`).
2. Node positions (`calculation/solver/kinematics.py`).
3. Mass inertia forces and moments (`crane_solver.py` `inertia_force`, mass
   loop). Rope self-weight lumped at nodes, reeved vs spooled
   (`calculation/rope_mass.py`).
4. Wind force `0.5 rho Cd A V^2 / 1000`, boom area scaled by `|sin(theta)|`.
5. Rope segment forces: `T = hook_kN / n_parts` for the active fixed-tension
   rope, `m_hook (g + az) / n_parts` for idle ropes, `T * unit_vector * mult`
   at both ends; boom-hoist rope tension solved.
6. Hook force, offlead and split-block compensation.
7. Boom 3x3 solve for `[Hx, Hz, T_boom_hoist]`, leg-frame 6x6 solve, platform
   resultant (`_run_statics` in `crane_solver.py`).
8. Out-of-plane pass (`engine.py` `_augment_point_with_out_of_plane_loads` and
   neighbours): Y masses, Y wind, moments about heel / front base / rear base /
   platform heel, left/right reaction split `0.5 * total +/- M / width`,
   platform Fy and Mx.
9. Hook load from payload: `(payload_t + hook_mass_t) * DAF * g`.

Matrix solves use `MINVERSE`/`MMULT` on a clearly laid-out matrix block; a
singular matrix must show an explicit error flag, not `#VALUE!` noise.

## Constraints

- Plain `.xlsx`, no macros, opens in current desktop Excel; avoid dynamic-array
  functions if they would break older Excel (builder's call, state it).
- Fixed crane topology, as in the app: boom, rear leg, front leg, platform;
  named structure nodes. Name-based special cases in the solver (e.g. a node id
  containing "winch" holding unspooled rope; the `boom_hoist` rope channel) must
  be reproduced or replaced by explicit input columns, and documented.
- Units as in the app: tonnes, kN, m, kNm; gravity from the input.
- Sign and direction conventions must match the app and be documented on a
  conventions sheet (outreach positive x, wind sign, pitch sign, Y-wind and
  out-of-plane lever arms, reaction signs).

## Decisions by the user

- Purpose: independent validation and insight for people not running the app.
- Scope: main reactions and rope tensions; no utilisation, no free-body view,
  no load chart.
- Reference case: 22689.
- Single hand-built template; users type in their own data.
- Generic with spare rows (not sized to 22689).
- Input form: expanded nodes/segments with simple geometry done in the workbook.
- Include out-of-plane effects.
- Acceptance: workbook matches the app on four generated 22689 cases within
  0.01 kN (forces) and 0.01 kNm (moments): (1) base case, weight plus hook
  load; (2) in-plane wind with accelerations; (3) out-of-plane wind with roll
  and sidelead; (4) an idle-hoist case. The builder generates these reference
  results by running the app.

## My calls (not user decisions)

- Build it with a Python script (openpyxl) that writes live formulas, so the
  template is regenerable and testable; deliver the `.xlsx`. The generator
  script is a development tool, not an app feature.
- Verify by recalculating the workbook headlessly (e.g. LibreOffice) and
  comparing against the app's output for 22689 and the GT283 golden files in
  `tests/golden/`. There is **no golden file for 22689** today; the builder
  must produce one from the app (and say so).

## Answers from the builder check (my calls unless noted)

- **Expanded model for 22689:** the app's `normalize_document`
  (`data/models.py:1531`) turns the authored YAML into the expanded
  `CraneDocument`. Use it to produce the workbook's 22689 prefill; do not
  hand-derive it.
- **Name-based special cases:** replace with explicit input columns (a rope
  role column fixed/solve, and a "spool node" flag on the node that holds
  unspooled rope), rather than string matching. Translate 22689 via
  `normalize_document`. Search for any other name-based rules and report them.
- **Boom-hoist rope:** the rope with `tension_mode == "solve"` is the one whose
  tension is an unknown in the boom solve (`crane_solver.py:104`,
  `models.py:365`). Verify against the code how a document with no solve rope
  behaves and support both if the code does.
- **Deviating from this document:** allowed. If the code contradicts the
  survey, the source wins; report the difference. Reaction definitions come
  from the Scene view's reaction arrows and results rows (`core/drawn_loads.py`
  `reactions()`, `core/analysis_services.py` `compute_result_rows`).
- **Input checks:** a default set is enough: table overflow, duplicate ids,
  segments referencing missing or inactive nodes, a hoist whose rope has no
  active segments, more than one solve rope, singular matrix.
- **Excel versions:** Excel 2016 or later, no dynamic-array functions, so
  matrix blocks must work as ordinary or legacy array formulas. LibreOffice
  recalculation is a check, not proof of Excel behaviour; say so.

## Left to the builder

- Sheet layout and naming, table sizes (how many spare rows), colour coding of
  input vs formula cells, data validation.
- Whether to replicate the 3x3/6x6 solves with `MINVERSE` or closed-form.
- Whether to include optional rows (bearing line loads, axial/normal
  projections, resultant) beyond the required reactions and tensions.
- How split-block mode is handled: include if cheap, otherwise document as
  unsupported.
- Where the generator script and verification test live in the repo.

## Open points for the builder to flag

- Which extra cases need golden data from the app to validate (idle hoists,
  split mode, Y wind, roll).
- Any survey claim above that the code contradicts. The source wins over this
  document.
