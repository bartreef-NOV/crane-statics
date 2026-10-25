# Crane Statics validation workbook

`docs/crane-statics-validation-22689.xlsx` is a plain Excel workbook. It has no macros and
every result is a live formula. It reproduces the numbers the Crane Statics **Scene view**
shows for one operating state:

- the rope tension of every hoist;
- the support reactions of the heel point, the front, rear and upper hinges and the
  platform base, in-plane and out-of-plane, including the heel left/right split and the
  platform bearing line loads.

The workbook is for engineers who do not run the app. Use it to check the app
independently and to see how each number arises. It comes filled in with crane 22689
(`examples/crane_input_22689.yaml`) at the `base` scene state. You can type in another
crane or another operating state.

The workbook needs Excel 2016 or later. It uses no dynamic-array functions; the two matrix
solves are legacy array formulas (`MMULT(MINVERSE(A), b)`). The file has no cached values
and is flagged `fullCalcOnLoad`, so Excel recalculates everything when you open it. If
Excel is set to manual calculation, press F9. If Excel opens the file in Protected View
(for example after a download), the cells show no values until you click **Enable
Editing**, because the file stores formulas only and Excel recalculates them once editing is
enabled.

Cell colours: yellow = input (type here), blue = formula (do not edit), grey = generator
marker (key rows), red = guard row (keep blank).

## Sheets, in calculation order

| Sheet | What it holds |
|---|---|
| Conventions | Units, axes, angles, wind, offlead/sidelead, rope roles, reaction signs, out-of-plane pass, statics, table rules. Each line cites the app source it was copied from. |
| Inputs | The only sheet you type on: environment, structure points, scene state, then six tables (mass points, wind areas, nodes, rope segments, ropes, hoists). |
| Geometry | The boom rotation, the active hook position and the vessel-to-crane frame motion (gravity components, `k = g - a`, rotated accelerations). One row per Inputs node gives the final x/z. |
| Loads | In-plane loads per row: mass weight and inertia, X wind, rope tensions, segment forces, rope self-weight (reeved and spooled), hook load and offlead, idle hook blocks. Then the per-body totals for boom, rear leg, front leg and platform. The solve rope appears as coefficients per kN of its tension (`bh_*`). |
| Statics | The boom 3x3 solve `[Hx, Hz, T_bh]`, the leg-frame 6x6 solve and the platform resultant. Each system shows A, b, the raw `MMULT(MINVERSE)` column, the "x used" column (0 if singular), row norms, det, rel_det and the singular flag. |
| OutOfPlane | Y loads from masses, lumped rope and hook masses, Y wind and sidelead. Moments about the heel, front base, rear base and platform heel. The left/right split (left = +Y = port: `0.5 total - M / boom width`; right: `+ M`), then platform Fy and Mx as support reactions. |
| Results | Status (`OK` or the reason there are no results), the rope tension per hoist, and one row per reaction component keyed `reaction.<entity>.<component>`, with units and the formula source. |
| Checks | One live count per input check (0 = OK) and the total in C3. Counts above 0 turn red. Below the list: overflow per table and the fixed structure nodes present. |

## Filling in Inputs

You type the **expanded** model, meaning the runtime nodes and rope segments the app builds
from the authored YAML, not the YAML itself. The workbook does only the simple geometry.

### Single values

- **Environment:** gravity is typed signed, as authored (-9.81); the magnitude is used.
  Then air density, and the vessel motion reference x and z, which are the lever-arm origin
  for pitch and roll accelerations. Max wind speed is information only.
- **Structure points and widths:**
  - boom width, which is the heel left/right spacing used by the out-of-plane split;
  - slewing bearing diameter, which is optional (blank hides the bearing line-load rows);
  - x and z of the boom heel, upper hinge, rear hinge, front hinge and platform base.
- **Scene state:** see "Changing the scene state" below.

### Tables (common rules)

Every table has a fixed number of rows: 40 mass points, 40 wind areas, 80 nodes,
60 segments, 8 ropes and 8 hoists.

- **Never insert or delete rows** inside a table or above one. Use the spare rows (set
  Active = 1 and fill the row), or regenerate with larger capacities. The calculation sheets
  have one formula row per Inputs row, and an inserted or deleted row breaks that link; the
  `mirror` check fires if it happens, including for a row inserted above the first data row
  or just above the guard row.
- **Active (column A):** 1 = row in use, 0 = spare. A spare row must have Active = 0 and
  every other cell blank; spare rows change no result. Setting Active = 0 on a used row
  removes it from the calculation without deleting it.
- **Guard row:** below each table there is a red guard row. Keep it blank. Anything typed
  there counts as overflow on Checks. If you need more rows, regenerate the workbook with
  larger capacities (`--capacity`, see "Regenerating").
- **List columns** (Active, Body, Frame, Role, Spool node, wind direction) have a dropdown,
  and Excel rejects other values typed into them. A value pasted in can bypass that, so the
  `invalid_values` check also counts any value outside the list. A typo such as `Boom `
  (trailing space) would otherwise drop the row from the calculation silently.
- **Ids:** Excel matches ids case-insensitively and treats `*`, `?` and `~` as wildcards.
  Keep ids unique ignoring case, and free of those three characters.
- **Unused coordinates:** leave them blank, for example the u/v/w of a global mass point or
  the x/z of a hanging node.
- **Body:** `boom`, `rear_leg`, `front_leg` or `platform`. This decides which body's
  equilibrium a row loads.

### Mass points

Columns: Active, Id, Body, Frame, Mass [t], then u, v, w [m] or x, y, z [m].

- Frame `boom_local`: u runs along the boom from the heel, w is normal to it (positive
  toward +z at a 0 degree boom), and v is lateral. Use this frame only for body `boom`
  (the `boom_local_non_boom` check flags it on another body).
- Frame `global`: x, y, z in the crane frame.
- y (or v) is used only by the out-of-plane pass.

### Wind areas

Columns: Active, Id, Body, Frame, Cd, Area for X wind [m^2], Area for Y wind [m^2], then
u, w or x, z.

There is no lateral coordinate: wind acts at y = 0. Force = 0.5 rho Cd A V^2 / 1000 kN.
For X wind, the areas of body `boom` are scaled by |sin(boom angle)| (the boom's projection
seen along x). Y wind uses every area in full at any boom angle.

### Nodes

Columns: Active, Id, Body, Frame, x, z, u, w, Hangs below node, Hanging drop [m],
Spool node (1/0).

- **Frame `global`:** type x and z.
- **Frame `boom_local`:** type u and w along and normal to the boom from the heel. The
  global position is computed at the scene boom angle. Use it only for body `boom` (the
  `boom_local_non_boom` check flags it on another body).
- **Frame `hanging`:** a hook block. Type `Hangs below node` (the sheave it hangs from)
  and `Hanging drop`, which is how far an idle hook hangs below that sheave (blank counts
  as 1 m, the app default). The scene hoist's hook ignores the drop and hangs the scene
  tackle length below its support node. Only one level of hanging is resolved.
- **Spool node = 1:** marks the node that holds the hoist's rope not reeved, usually the
  winch drum. The spooled mass (total rope length minus the reeved length, times the linear
  mass) is placed there. The app instead looks for a node id containing "winch" on the
  hoist's rope; the flag replaces that name rule.
- **Fixed structure nodes:** these nine ids must exist and be active: `boom_heel`,
  `platform_heel`, `rear_top`, `front_top`, `rear_base`, `platform_rear`, `front_base`,
  `platform_front` and `platform_base`. Their x and z are formulas linking to the structure
  points, so do not type over them.

### Rope segments (reeving)

Columns: Active, Rope id, From node, To node, Parts (multiplier).

Each segment is a straight rope run between two nodes. Its multiplier is the number of rope
parts in that run. The force on each end node is `T x unit vector x mult` (the from end
pulled toward the to end, and the opposite at the to end). Rope self-weight is length x
mult x linear mass, split half to each end.

The parts at the hook (the number the hook load is divided by) is the sum of the
multipliers of the rope's active segments that touch the hook node. The hoist's Falls
column is not used.

**Worked example (22689).** In the YAML each reeving point carries `parts:` (default 1).
The segment *into* a point takes that point's parts, and the last segment into the hook
takes the hoist's `falls`.

| Rope (hoist) | Segments: from -> to (mult) | Parts at hook |
|---|---|---|
| `MH__rope` (MH, fixed) | mh_winch -> mh_aframe_sheave_1 (2); mh_aframe_sheave_1 -> mh_aframe_sheave_2 (2); mh_aframe_sheave_2 -> mh_boom_sheave_3 (2); mh_boom_sheave_3 -> mh_boom_sheave_4 (2); mh_boom_sheave_4 -> `__hook__MH` (20) | 20 |
| `WH__rope` (WH, fixed) | wh_winch -> wh_aframe_sheave_1 -> wh_aframe_sheave_2 -> wh_boom_sheave_3 -> wh_boom_sheave_4, all (1); wh_boom_sheave_4 -> `__hook__WH` (4) | 4 |
| `SH__rope` (SH, fixed) | sh_winch -> sh_boom_sheave_1 (1); sh_boom_sheave_1 -> sh_boom_sheave_2 (1); sh_boom_sheave_2 -> `__hook__SH` (1) | 1 |
| `BH__rope` (BH, solve) | bh_winch -> bh_aframe_sheave_1 (2); bh_aframe_sheave_1 -> bh_aframe_sheave_2 (2); bh_aframe_sheave_2 -> bh_boom_sheave_3 (24) | 24 at bh_boom_sheave_3 |

In the base case the MH hook load is 6500 kN, so each MH part carries 6500 / 20 = 325 kN.
That is the `tension.MH` row. BH has no hook: its tension (770.2 kN in the base case) is
solved by the boom equilibrium, and its 24-part run pulls the boom sheave toward the A-frame.

To get the multipliers from a drawing, count the rope parts between each pair of consecutive
sheave sets. A run reeved n times between two blocks is one segment with mult n. The hook
block's falls go on the segment from the last sheave into the hook node.

### Ropes

Columns: Active, Id, Role.

- **Role `solve`:** the boom-hoist rope. Its tension is an unknown of the boom solve.
  Exactly one active solve rope is required.
- **Role `fixed`:** a hoist rope whose tension follows from the hook.

The rope's linear mass and length are typed on the hoist row.

### Hoists

Columns: Active, Id, Rope id, Hook node, Support node, Falls, Hook block mass [t],
Hook DAF, Offlead and Sidelead (document defaults), Rope linear mass [kg/m],
Total rope length (incl. spooled) [m], Max hook travel, Lowest hook height, Splitable block,
Split falls, Split hook mass.

- **Hook node:** the hanging hook node. For the boom hoist, give its boom sheave
  (`bh_boom_sheave_3`), and leave Support node and Falls blank.
- **Support node:** the sheave the hook hangs below. The hook's own `Hangs below node`
  takes precedence for the hook position. The sidelead force acts at this node.
- **Columns the calculation uses:** Rope id, Hook node, Support node, Hook block mass, Rope
  linear mass and Total rope length.
- **Information only:** Falls, Hook DAF, the offlead/sidelead defaults (the scene values
  are used), Max hook travel, Lowest hook height and the three split columns.
- **Idle hoists:** every active hoist other than the scene hoist is idle. Its rope carries
  hook block mass x (|g| + az') / parts at the hook, and its block hangs at its hanging drop.

## Changing the scene state

Edit the **Scene state** block on Inputs:

- the hook-loaded hoist id (it must be an active hoist with a fixed rope);
- boom angle (deg, from +x toward +z);
- hook load in kN, which is (payload + hook block) x DAF x g; the workbook takes the kN
  value directly;
- tackle length (support sheave to hook);
- offlead and sidelead (deg);
- wind speed and direction (+X, -X, +Y or -Y; pick it from the dropdown. Typed by hand,
  `+X` or `-Y` is read by Excel as a formula and shows `#NAME?`; type a leading apostrophe,
  `'+X`, to enter it as text);
- vessel accelerations ax, ay, az;
- pitch and roll angular accelerations;
- vessel roll (positive to starboard) and pitch (positive bow-down);
- crane slewing angle.

The accelerations, roll and pitch are vessel-frame values, as the Scene takes them. The
workbook rotates them into the crane frame by the slewing angle.

The repository has four reference states (`scripts/excel_workbook/reference.py` `CASES`):
`base`, `inplane_wind_accel`, `outofplane_wind_roll_sidelead` and `idle_hoist`. To write
the workbook already set to one of them, see "Regenerating".

## Reading Checks

Every count must be 0. The total is in C3, and its status reads `OK` or `CHECK INPUTS`.

| Check | Counts |
|---|---|
| `overflow` | Rows that did not fit a table when the workbook was generated, plus anything typed in a guard row. |
| `mirror` | An Inputs table whose rows were inserted or deleted (its range no longer has the generated number of rows, or a row was inserted above its first data row or between its last data row and the guard row, so the key row and the guard row are no longer capacity + 1 rows apart), or a calculation sheet (Geometry, Loads, OutOfPlane, Results) whose Active column no longer copies the Inputs rows. |
| `duplicate_ids` | Active node, rope or hoist rows whose id is used by another active row of the same table. Mass-point and wind-area ids are labels only and may repeat, as in the app. |
| `blank_ids` | Active rows with a blank id, and segments with a blank rope id. |
| `invalid_values` | Active cells that are not blank, 0 or 1; and on active rows, a 1/0 column (Spool node, Splitable block) that is not 0/1, or a Body, Frame or Role that is not one of its list choices. |
| `boom_local_non_boom` | Active mass-point, wind-area or node rows with frame `boom_local` on a body other than `boom`. The app ignores u/v/w on such a row and uses x/z, while the workbook would rotate it with the boom. |
| `node_references` | Segment ends, hoist hook and support nodes, and hanging nodes' parents that name a missing or inactive node. |
| `rope_references` | Segments or hoists naming a missing or inactive rope. |
| `hoist_without_segments` | Active hoists whose rope has no active segment. |
| `multiple_solve_ropes` | Active solve ropes beyond the first. |
| `no_solve_rope` | 1 if no active rope has role solve. The app shows no results then, and Results shows a message. |
| `scene_hoist` | 1 if the scene hoist is not an active hoist with an active fixed rope. |
| `wind_direction` | 1 if the scene wind direction is not +X, -X, +Y or -Y. The app treats other text as +X. |
| `fixed_nodes_missing` | Fixed structure node ids with no active node row. |
| `hanging_chain` | Hanging nodes whose parent is itself hanging. Only one level is resolved. |
| `singular_matrix` | Singular Statics systems (boom 3x3, leg frame 6x6). The boom one is singular when there is no solve rope. |
| `zero_boom_width` | 1 if the boom width is not > 0. The out-of-plane split divides by it, so Results shows a message. |
| `invalid_bearing_diameter` | 1 if the slewing bearing diameter is typed but is not a number > 0 (the app rejects 0 or less). Blank is allowed and shows the bearing rows as n/a. The cell also has a validation that rejects a typed value other than a number > 0; a pasted value can bypass it, which this check catches. |

When Statics has no solution (no solve rope, or a singular matrix) or the boom width is not
> 0, every Results value shows the reason as text, because the app shows no results in that
case. A Results status other than `OK` always comes with a non-zero check. The other checks
do not blank Results, so with a non-zero total the numbers may be wrong even when the status
reads `OK`.

## Sign conventions

These are copied from the Conventions sheet, which also cites the source of each line.

- **Units:** m, t, kN, kNm, and deg for inputs. Weight = mass x |g|.
- **Axes:**
  - x is horizontal in the boom plane, positive toward the boom tip (outreach);
  - z is up;
  - y is lateral, completing a right-handed frame: +y points to port (left, looking
    along +x).
  - The crane frame is the vessel frame (x forward, y port, z up) rotated about z by the
    slewing angle.
  - In-plane moments are about +y, with M = x Fz - z Fx.
- **Boom:**
  - The boom angle is measured at the heel, from +x toward +z.
  - Boom-local to global: x = x_heel + u cos theta - w sin theta, and
    z = z_heel + u sin theta + w cos theta.
  - Hanging nodes hang straight down.
- **Vessel:**
  - Pitch is positive bow-down and roll positive to starboard.
  - Gravity in the vessel frame is g (sin pitch, -sin roll cos pitch, -cos roll cos pitch).
  - The load acceleration is k = g - a.
  - Mass load: Fx = -m (ax' + pitch' dz), Fz = -m (|g| + az' - pitch' dx) and
    Fy = -m (ay' - roll' dz), with dx and dz measured from the vessel motion reference.
- **Wind:** the direction is where the wind blows toward, so +X wind pushes in +x. X wind
  on body `boom` areas is scaled by |sin(boom angle)|; Y wind is not scaled.
- **Hook:**
  - The hook load acts at the hook node in -z.
  - Offlead adds sin(offlead) x hook load in +x at the node the hook hangs from.
  - Sidelead adds sin(sidelead) x hook load in +y at the scene hoist's support node, at its
    position before the tackle moves the hook.
- **Reactions:**
  - Every reported reaction is the force (or moment) the support exerts on the crane,
    opposing the applied loads: weight gives positive Fz, and a +X vessel acceleration
    gives positive Fx. This includes platform base Fy and Mx: a +Y wind gives negative Fy,
    and Mx = -(applied Mx about the platform heel).
  - Pinned supports (heel, hinges) carry no moment.
  - Left/right: `heel_left` is the +Y (port) side. heel_left = 0.5 total - M / boom width
    and heel_right = 0.5 total + M / boom width. Fz uses Mx, Fx uses Mz, and M is the
    moment of the applied loads about the heel, including the platform masses. A mass at
    +Y loads `heel_left`.

## Comparing with the app

1. Open the same crane YAML in Crane Statics and go to the Scene view.
2. Select the same hook-loaded hoist and set the same scene state: boom angle, hook load,
   tackle length, offlead/sidelead, wind, accelerations, vessel roll/pitch and slew.
3. Compare the Scene results table with the Results sheet:
   - each rope row matches the tension of the hoist that owns the rope;
   - each connection row and component matches the `reaction.<entity>.<component>` row.
4. Differences should be no more than 0.01 kN, 0.01 kNm or 0.01 kN/m (rounding). For a larger
   difference, first check that Checks is 0, then follow the chain Inputs -> Geometry ->
   Loads -> Statics -> OutOfPlane -> Results.

## Known limits and deliberate app parity

a. **Split-block mode is unsupported.** The Splitable block, Split falls and Split hook mass
   columns are typed for information only and ignored. Only the app's normal (non-split)
   mode is reproduced.

b. **Verification was not done in Excel.** The workbook was verified by recalculating it with
   the Python `formulas` library, not in Excel itself. On four 22689 cases (`base`,
   `inplane_wind_accel`, `outofplane_wind_roll_sidelead` and `idle_hoist`), every result
   the workbook produces matched the app within 0.01 kN / 0.01 kNm (0.01 kN/m for the
   bearing line loads). The largest difference measured was about 1e-6. No formula cell
   evaluated to an error value. The row insertions that the `mirror` check catches were
   simulated by moving every formula reference the way Excel does, not made in Excel.
   Please open the workbook in Excel 2016 or later and compare the Results with the app
   before relying on it.

c. **A hoist with no active rope segments still shows a tension.** It reports its hook block
   weight over one part, hook mass x (|g| + az') / 1, not zero, because the app's parts
   count defaults to 1. The `hoist_without_segments` check flags this case.

d. **Not provided:** the `boom_axial` and `boom_normal` rows of `heel_point`, `heel_left`
   and `heel_right`. The app takes that axis from a name-based list of boom sheave node ids.
   All other rows of the app's results table are provided. Hinge Fy rows and the
   front/rear leg left/right splits are not shown in the app's Scene table. The OutOfPlane
   sheet does compute the leg splits.

e. **Geometry limits:**
   - Only one level of hanging nodes (`hanging_chain` check).
   - No outreach-to-angle conversion: type the boom angle.
   - The hook load is typed in kN; there is no payload-in-tonnes input.

f. **Singular statics.** A Statics system counts as singular when |det A| / (product of the
   row norms of A) <= 1e-12, or when MINVERSE fails; the app uses the same test and shows
   why no results are available. When a matrix is singular, the raw
   `MMULT(MINVERSE(A), b)` column on Statics shows `#NUM!`. That is the only place an error
   value can appear: the "x used" column and everything downstream stay numeric, and Results
   shows a message.

g. **Other differences and parity choices.** None of these affects 22689.
   - The spool node is chosen by its flag, not by "winch" in the node id.
   - If several active hoists share one rope, the workbook takes the idle tension from the
     first of them and the app's solver from the last. Authored documents do not produce
     shared ropes.
   - The hook load is not clamped at 0. The solver does not clamp it either; only the
     Scene arrows do.
   - The Scene arrows apply the hoist's Falls to the hook segment. The results table,
     which the workbook matches, uses the segment multipliers. The two agree when Falls
     equals the multiplier of the hook segment.
   - Ids are matched case-insensitively by Excel and case-sensitively by the app. Ids are
     compared as text, so a numeric id (a hoist called 7) works.
   - If two active hoists share one rope, the rope's segments take the linear mass of both
     hoist rows (Loads sums them), so its self-weight is doubled. Give each hoist its own
     rope.

## Regenerating (developers)

The workbook is written by a script. Nobody edits it by hand. You need the dev tooling:
`openpyxl` and `formulas` are in the `dev` extra of `pyproject.toml`
(`pip install -e .[dev]`). From the repository root:

```
python -m scripts.excel_workbook.build examples/crane_input_22689.yaml docs/crane-statics-validation-22689.xlsx
python -m scripts.excel_workbook.build <crane.yaml> <out.xlsx> --case idle_hoist
python -m scripts.excel_workbook.build <crane.yaml> <out.xlsx> --capacity nodes=120 --capacity segments=90
```

- The YAML is expanded with the app's own `normalize_document`
  (`scripts/excel_workbook/reference.py` `expanded_model`).
- The scene state is a `CASES` entry; the default is the first, `base`.
- The cases use 22689's hoist ids. For another crane, edit the scene block on Inputs
  afterwards, otherwise `scene_hoist` flags it.
- Table capacities default to `layout.Capacities` (40 mass points, 40 wind areas, 80 nodes,
  60 segments, 8 ropes, 8 hoists). Change them with `--capacity TABLE=N`, which can be
  repeated; TABLE is one of `mass_points`, `wind_areas`, `nodes`, `segments`, `ropes` and
  `hoists`. Rows beyond capacity are not written and are counted by the `overflow` check.

The golden app values are `tests/golden/22689_workbook_cases.json`. To regenerate them, run
`python -m scripts.excel_workbook.reference`. The tests are in `tests/test_excel_workbook_*.py`, with shared helpers in
`tests/excel_workbook_helpers.py`. In `tests/test_excel_workbook_acceptance_delivery.py`,
`test_all_four_cases_within_tolerance` and `test_no_error_values_anywhere` are the
acceptance tests, and `test_delivered_workbook_is_up_to_date` checks that the committed
`.xlsx` matches the generator. `tests/test_excel_workbook_other_cranes.py` builds the
workbook for the GT283 and 13778 examples and compares it with the app for those cranes.

In a git worktree whose virtual environment has another checkout installed in editable mode,
set `PYTHONPATH=src` when running these commands by hand, so that this checkout's
`crane_statics` is the one imported. pytest already sets `pythonpath = ["src"]`.
