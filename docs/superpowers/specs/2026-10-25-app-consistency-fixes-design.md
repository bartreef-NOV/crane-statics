# App consistency fixes — design

## Intent

Building the Excel validation workbook (see
`2026-10-25-excel-validation-workbook-design.md`) exposed places where the app's
reactions and wind loads are inconsistent. The workbook copied them to match the app.
Fix the app, then make the workbook follow.

## Decided by the user

- **Reaction convention:** a reaction is the force the support exerts on the crane.
- **+Y points to port** (left, looking along +x, the outreach direction).
- **Boom wind areas** (`area_w_m2` = X wind, `area_v_m2` = Y wind) are the areas the
  wind sees. Only X wind scales with |sin(boom angle)|; Y wind on the boom is unscaled.
- In scope: fixes 1-5 below and the workbook follow-up. Out of scope: name-based
  solver rules, arrow-vs-solver differences that cannot occur in authored documents.
- Order: user commits their uncommitted v11 work on `main` first; then the app fixes;
  then rebase and fix the workbook branch `excel-validation-workbook`
  (worktree `C:\Users\ReefB\Desktop\crane_statics-xlsx`, HEAD 67ca296); the user then
  opens the workbook in real Excel.

## Fixes

1. **Platform-base signs.** `platform_base` Fy and Mx (`calculation/engine.py`
   `_augment_point_with_out_of_plane_loads`, ~681-703, fed by `_out_of_plane_variants`)
   are the sums of the *applied* loads. Negate them so they are support-on-crane, like
   Fz, Fx, My. Check every consumer of the sign: `core/demand_extraction.py`
   (`fradial`, `mradial`, min/max bearing line load), `engine.py` ~223-262 and ~910-990,
   limits, chart envelope, tables, arrows.
2. **Left/right swap.** `_out_of_plane_variants` (~618-621) computes `0.5*total -/+ M/width`
   with M the moment of the applied loads; the side that gets `0.5*total - M/width`
   is the +Y side (a mass at +Y loads it more), and the code names that side `*_right`.
   +Y is port (left), so the names are swapped. Swap the two lines for `heel`,
   `front_leg`, `rear_leg`. Verify arrow anchors and table labels
   (`presentation/formatters.py` 116-174) agree.
3. **Wind scaling.** Remove `boom_proj` on `area_v_m2` (`engine.py:432`). Keep sin θ on
   X-wind boom areas in `crane_solver.py` (~499-503, every boom-body area). Make
   `core/drawn_loads.py:558-559` scale every boom-body X area (today only boom-local).
4. **Near-singular matrices.** The boom 3x3 and leg 6x6 solves (`_run_statics`) fail only
   on an exactly singular matrix; near-singular gives huge numbers. Fail with a clear
   error when |det|/prod(row norms) <= 1e-12 (the workbook's threshold).
5. **No solve rope.** `compute_analysis_point` returns None and the Scene shows nothing.
   Show a message saying no rope has `tension_mode == "solve"`.

## Workbook follow-up

- Update formulas for fixes 1-3 (Results/OutOfPlane/Loads), regenerate
  `tests/golden/22689_workbook_cases.json` and
  `docs/crane-statics-validation-22689.xlsx`, update the guide
  (`docs/excel-validation-workbook.md`, "Known limits and deliberate app parity") and
  `reference.py` docstring (sign conventions, dependency list).
- Add checks: bearing diameter > 0 (app rejects it, `models.py:322`); `boom_local` on a
  non-boom body; a row inserted first or last in a table.
- Heel boom-axial/normal rows (6 keys) stay omitted (name-based heel axis, deferred).
- Re-run the four-case acceptance (0.01 kN / 0.01 kNm) against the fixed app.

## Non-goals

- Name-based rules: "winch" node id, heel-axis node list, `__hook__<id>`, `BH__rope` vs
  `boom_hoist`, `_T` chart suffix.
- Arrow-vs-solver differences (`falls` vs multipliers, hook-load clamp, shared ropes).
- Split-block mode, deeper hanging-node chains, outreach-to-angle in the workbook.
- The pre-existing failing `test_chart_menu_edits_contractual_points_at_the_cursor`.

## Anti-goals

- Fixing signs in one place and leaving a consumer (limits, bearing loads, arrows,
  tables, saved results) silently inverted.
- Changing any in-plane number: only Fy/Mx at platform base, the left/right pairs, and
  Y-wind boom loads may change.

## My calls (from the builder check; not user decisions)

- **Saved data:** `examples/` holds no stored reactions, so no schema bump or migration.
  Only `tests/golden/gt283_*.json` (and the workbook golden) store Fy/Mx/left-right
  values: regenerate them and review the diff. Any other stored result found while
  working is reported, not migrated.
- **Wind:** the `drawn_loads` change only affects arrow length for boom-body X areas that
  are not boom-local; solver results do not change. The "only Y-wind, platform-base and
  left/right numbers may change" anti-goal is about solver results.
- **Source of truth for left/right:** the reaction values from `_out_of_plane_variants`.
  Arrow anchors and table labels must follow them; the builder checks each and fixes the
  one that disagrees physically (+Y = port = left).
- **Consumers (fix 1):** keep the physical meaning of `fradial`, `mradial` and bearing line
  loads unchanged. Where a consumer depended on the old sign, adapt it so its output stays
  the same; flag each case in the plan.
- **Near-singular (fix 4):** hard failure with a clear message at 1e-12; confirm all
  `examples/*.yaml` and golden cases still solve. Catch it where the exact-singular error
  is already caught.
- **No solve rope (fix 5):** confirm `None` has no other cause; if it does, give each cause
  its own message. Place the text where existing Scene messages live; test it.
- **Workbook verification:** with the `formulas` library as before (no LibreOffice); the
  user checks in real Excel afterwards.
- **Sequencing:** assume the v11 commit has landed; re-find the line numbers in this
  document by symbol, not number.

## Left to the builder

- Error type/wording for fixes 4-5 (follow existing validation/error patterns).
- Tests: pin sign, left/right, and wind scaling with hand-computed cases.
- Whether saved/golden files elsewhere in `tests/` need regenerating.
