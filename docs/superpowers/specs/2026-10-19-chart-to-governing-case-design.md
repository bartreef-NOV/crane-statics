# Load chart → governing case in the Scene

## Intent
Users want to see *why* a design limit governs. Today they must guess input
combinations (wind direction, slew angle, offlead/sidelead, pitch, acceleration
directions, vessel attitude) to reproduce the worst case. From the Load Chart
they should be able to point at a series, right-click, and land in the Scene
with exactly the inputs and results that produce that limit.

## Behaviour (as decided with the user)
- Trigger: right-click on a point of a series in the Load Chart. The point is the
  hovered/scrubbed one (existing hover/pin in `QuickChartPlot.qml`), at the
  nearest outreach on that series.
- Menu entry (in the existing `chartMenu`) switches to the Scene tab.
- The Scene shows the governing case: all inputs set to the worst-case values,
  hook load set so the component load equals the design limit of that
  component/series at that outreach, outreach/boom angle at the chosen point.
  Results (rope and connection rows, scene frame) are those of that case.
- Reversible: before applying, the current Scene inputs are saved. A
  **Restore my inputs** button restores them.
- A label "Governing case: *limit name* at *outreach*" is shown while the scene
  still equals the governing case. On the first user edit of any input the label
  disappears; the Restore button stays until the user restores or loads another
  document / leaves the session.

## Goals
- One right-click from chart point to Scene governing case.
- Scene numbers match the chart value (same engine, no second implementation of
  the worst-case search).

## Non-goals
- Showing the governing case for every point at once; comparing cases.
- Persisting the saved inputs in the document.
- Changing the chart's streamed point format.

## Anti-goals
- A Scene whose results disagree with the chart point it was opened from.
- Silently losing the user's own Scene inputs.

## Constraints (from the codebase)
- Layering: domain packages stay Qt-free; view models orchestrate; see
  `tests/test_architecture.py`.
- A chart point is only `[outreach, load_t]`; the governing case is found
  analytically in `core/chart_envelope.py` (`_evaluate`, `_slew_harmonics`,
  `lead_points`) and discarded. `AllowableCapacity` has `governing_limit_id`
  but `governing_wind_direction` is set to None by `envelope_capacity`.
- Scene state is `SceneState` per hoist in `core/session_model.py`; setters in
  `scene_vm.py` clamp vessel motion and order matters.
- Tab switch is `workspaceTabs.currentIndex` in `Main.qml`; no programmatic
  chart→scene switch exists.
- Hook modes: normal/split chart mode per hoist (`chart_mode`).

## Decided by the user
- Restore-my-inputs behaviour as above.
- Entry point is the right-click context menu.

## Also decided by the user (review round)
- `SceneState` gets a continuous wind angle so the worst wind angle can be held
  exactly (replaces the discrete direction as the source of truth).
- Vessel motion: the case uses the full vessel-motion limits, as the chart does
  (the chart has no motion-off toggle). Users zero the motion manually after the jump.
- Applying the case sets `tackle_length_m` to the value the load curve used.
- Magnitude limits (resultant, radial force, radial moment, bearing line load):
  the chart value is the capacity of a real evaluated case (`best` in
  `_magnitude_capacity`), so track its argmax `(lead, case, cos, sin, corner)`
  and apply it. The chart value is a deliberate conservative bound: the argmax
  slew sits on a 360-gon circumscribing the slew ellipse (stretch 1/cos(pi/360),
  ~1.00004), so the Scene result may differ from the chart by up to ~0.1 %
  (Scene slightly higher). Accepted by the user; tests use that tolerance for
  these four limits. Fallback if tracking proves hard: disable the menu entry
  for these four.

## Builder's call (author's guesses, user has not agreed)
- Snapshot only on first apply (a second apply keeps the original); cleared on
  document load or hoist change. Restore also restores the hook-load auto flag.
  Programmatic writes by the apply slot must not clear the label.
- Hook load set to the limit with auto off. New `showSceneRequested` signal
  drives `workspaceTabs.currentIndex` in `Main.qml`.
- Combined curve tie-break: first limit key. Unlimited/non-responsive limits:
  entry disabled. Split/normal follows the mode the chart job used.
- Re-evaluate the governing case on demand for (hoist, mode, outreach, limit)
  when the menu entry is used, rather than carrying case data on every streamed
  point. Extend the envelope evaluation to return the argmax case (a small
  value object: scene-state fields plus governing limit id) and expose a pure
  function in `core/`.
- Right-clicking the combined capacity curve resolves to the limit with the
  lowest load at that outreach.
- Apply the case through one new scene view-model slot that writes
  `SceneState` directly and reloads, not through the individual setters
  (avoids clamp-order issues); hook load auto mode turned off.
- Saved inputs live in the scene view model (in memory, one snapshot per hoist).

## Left to the builder
- Exact value-object shape, slot names, banner/button QML layout (native Fusion
  styling per the qml-ui-development skill).
- Handling of limits with no responsive case (menu entry disabled).
- Tests: pure-function test that the on-demand case reproduces the chart point
  value; view-model test for apply/restore/label-clearing.
