# Conditions UI, rules examples, calculation-details fix, lower-block rename — design

Date: 2026-11-09. Four independent pieces of work, planned together.

## 1. Calculation details panel: hover/click does nothing

**Symptom (user report):** the chart's "Calculation details" panel shows
"Hover or click a point on the capacity curve to see how its factors were
obtained." and never fills in.

**What the code does today** (read, not yet run):
- `QuickChartPlot.qml` `nearestPoint()` snaps to the closest *sampled* curve point or
  contractual marker within 28 px; the MouseArea sets `hoveredPoint` on move and
  `pinnedPoint` on left click.
- `LoadChartWorkspace.qml` forwards `pinnedPoint || hoveredPoint` to
  `chartVm.inspectChartPoint()`, which calls `setDetailOutreach()` for curve points
  (those with a string `seriesId`), then `_refresh_details()` looks the outreach up in
  `self._provenance`.
- `_provenance` comes from the sweep payload (`sweep.py` ~L496:
  `[(x, *trail_by_outreach[x]) for x in curve_outreach if x in trail_by_outreach]`),
  is emptied while a chart streams (`_show_stream`) and on `_clear_display`.
- The panel is only visible for rules documents (`chartVm.conditionNames.length > 0`).

**Suspects, in order** (the cause is not yet known; do not fix blind):
1. `_provenance` is empty for the displayed chart: the exact-float `x in trail_by_outreach`
   filter drops points, or the cached/streamed payload path never fills it.
2. The inspected point never reaches the view model (binding/identity issue in
   `inspectedPoint`, or hover is lost because points are sparse and the 28 px radius
   misses the line between samples).
3. Rows are produced but not rendered (ScrollView/GroupBox sizing).

**Goal:** a working panel, found by reproducing it in the real app (`run-app` skill) with
`examples/crane_input_GT283_abs.yaml` and `..._dnv.yaml`, then fixing the root cause with a
regression test. If the behaviour is by design for some inputs (e.g. non-rules documents
hide the panel), say so in the UI text rather than showing a dead hint.
**Non-goal:** redesigning the panel's content.
Use superpowers:systematic-debugging.

## 2. New rules examples

- `examples/crane_input_22689_abs.yaml` — ABS variant of `crane_input_22689.yaml`.
- `examples/crane_input_13778_retracted_dnv.yaml` — DNV variant of
  `crane_input_13778_retracted.yaml`.

Model on `crane_input_GT283_abs.yaml` / `_dnv.yaml`: add `rules:` and `conditions:` to
`model_definition` (ABS: `{standard: ABS, crane_class: offshore}`, DNV:
`{standard: DNV, cabin_above_slewing_bearing: true}`), keeping the structure, masses and hoists
of the base file. **My call:** each file gets an `onboard_sea` and an `offboard_*` condition like
the GT283 examples, with the same placeholder environment values, since the real values
for these cranes are not available. The new examples must load, validate against the schema and
produce a chart; add them to whatever test enumerates `examples/`.
Mark the invented condition values in a YAML comment as illustrative.
**Found while planning:** neither base file has `rope.ea_kN` (needed by any rules run) or
`max_hoisting_speed_m_s` (needed by `offboard` conditions); `validate_rules_document`
rejects the file without them. Fill in only what validation demands, with values copied from
the GT283 rules examples, also marked illustrative. The condition fields to edit in part 3
also include `load_drag_coefficient` and `hook_height_override_m`.

## 3. Conditions editable in the UI

Today conditions (`model_definition.conditions`, e.g. `offboard_hs1`: `lift`, `wind_speed_m_s`,
`vessel_motion{...}`, `significant_wave_height_m`, `v_in_m_s`, `v_t_m_s`, `load_wind_area_m2`)
exist only in YAML; the Environment panel shows a note instead (`EnvironmentPanel.qml`,
`environmentFromConditions` in `document_forms.py`).

**Agreed (user, in conversation):** a **Conditions** panel with a list of conditions
(add, duplicate, rename, delete) and a form for the selected one covering every condition field above.
It replaces the note in the Environment panel for rules documents.

**Constraints:**
- Edits go through the existing document-edit path (`core/document_edit.py`,
  `authored_form.py`, `ModelViewModel`) so undo, dirty state and chart staleness behave like
  other model edits. Follow the `qml-ui-development` skill and the layering rules (no domain
  logic in view models; `tests/test_architecture.py`).
- Fields that are only meaningful for some `lift` values (wave height, v_in, v_t for
  `offboard`) are shown only for those; validation reuses the authored-model rules.
- Condition names are unique, non-empty, and used by the chart's condition selector; renaming or
  deleting the one currently charted must not leave a dangling selection
  (`ChartViewModel._refresh_conditions` already handles disappearance).
- A document with no `rules` block keeps the existing Environment fields.

**Left to the builder:** exact panel placement (new tab vs section of the Model workspace),
how a rules document is created from a non-rules one (assumed out of scope: the panel is shown
only when `rules` is present), and the form layout.
**Non-goal:** editing `rules` (standard, crane class) in the UI.

## 4. Rename `hook_mass_t` → `lower_block_mass_t`

The authored-file field and the internal model fields mean the mass of the lower block
(hook block / load block) and are confused with the hook load. Rename everywhere:
authored models (`authored_models.py`, including `split.hook_mass_t`), `authored_form.py`,
`data/normalize/authored.py`, `data/models.py` (`hook_mass_t`, `split_hook_mass_t`), calculation,
core, rules, QML (`HoistDialog.qml`, `HoistsPanel.qml`), formatters, the JSON Schema
(`schemas/crane-statics-v11.schema.json`, generated), all `examples/*.yaml`, the Excel
workbook scripts, README, and tests.

**Constraint:** this changes the authored-document contract, so it is a breaking schema
change: **11.1.0 → 12.0.0**, a new `crane-statics-v12.schema.json` (generated), and
`AUTHORED_SCHEMA_MAJOR_VERSION` updated (use the `schema-contract-reviewer` agent).
**My call:** follow the repo's precedent (10.0.0 "refactor hook attributes", 11.0.0) — the
loader rejects other majors (`core/io.py`), so there is **no migration**; all examples and
test fixtures are rewritten to 12.0.0. Old v11 files must be renamed by hand (or by
find-and-replace); the version error message should say so.
Do it as a mechanical rename in its own commit, **first**, so parts 1–3 build on the new names.
Do not rename unrelated `hook_*` names (hook load, hook position).

## Calls settled without asking (all mine, overridable)

- Examples: GT283 condition values are kept verbatim, marked illustrative. "Produces a chart"
  means a non-empty chart that loads without errors; the details panel working on them is
  covered by part 1's fix, not by part 2's tests. If a condition leaves a chart empty, adjust
  the value minimally and note it in a YAML comment.
- Conditions form: `vessel_motion` is the fixed set of scalars shown in the example
  (accel x/y/z, roll/pitch angle, roll/pitch angular accel, reference x/z); `lift` is the enum
  the authored models define (read it there). Changing `lift` keeps the now-hidden fields
  in the document rather than clearing them. Units follow the Environment panel's labels.
- Zero conditions: a rules document must keep at least one; deleting the last is disabled.
- Branching: one branch, four commits in the order below; the rename lands and passes
  pre-commit before the rest.

## Order and verification

Order: 4 (rename), 1 (bug), 2 (examples), 3 (UI). Each: tests plus
`pre_commit run --all-files`; parts 1 and 3 are also checked in the running app with the
`run-app` skill.
