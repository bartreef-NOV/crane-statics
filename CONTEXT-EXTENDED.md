# Domain Vocabulary (Extended Reference)

Complete domain vocabulary. For quick reference, see `CONTEXT-CORE.md`.

The terms this codebase is built out of. Modules are named after these concepts, not
after mechanism: `core/drawn_loads.py`, `core/scene_build.py`, `core/session_model.py`
— not `LoadHelper`, `FrameManager`, `StateHandler`. If you introduce a concept that
isn't here, add it here first; if you find yourself needing a word that isn't defined,
that is usually the sign a module is named after its mechanism.

Architecture vocabulary (**module**, **interface**, **depth**, **seam**, **adapter**,
**leverage**, **locality**) lives in `.claude/skills/codebase-design/SKILL.md`.
Decisions that should not be re-litigated live in [docs/adr/](docs/adr/).

---

## The document

**Authored document** — the JSON a user writes and saves, validated against the
strict `crane-statics` schema (currently `5.12.0`, in `src/crane_statics/schemas/`).
It is allowed to be terse: omitted defaults, omitted empty arrays, no derived nodes.
`data/models.py::document_to_authored_form` converts back to it for saving, so a
load/save round-trip must not invent content.

**Normalized document** — an authored document after `normalize_document()`: defaults
filled in, derived nodes generated, canonical connections generated, bodies in
canonical order. This is the `CraneDocument` every other module sees. Nothing
downstream of `data/` should have to ask whether a field was authored or defaulted.

**Body** — a rigid part of the crane: `platform`, `boom`, `front_leg`, `rear_leg`.
Carries nodes and mass points. The canonical order matters to the solver's assembly.

**Node** — a named point in world coordinates on a body (`boom_heel`, `rear_top`,
`platform_front`). Rope segments and hoists refer to nodes by id, so a node id is
part of the document's contract.

**Rope** — a load path through a sequence of segments. A rope whose `tension_mode` is
`"solve"` is a *boom-hoist* rope: its tension is an unknown the solver finds.

**Hoist** — a rope operated as a lifting device, with hook mass, falls, DAF and
contractual points. A **payload hoist** is one whose rope is *not* in solve mode
(`data/models.py::payload_hoist_ids`) — the ones a user picks between in the scene.
The distinction matters because a solve-mode hoist has no payload to set.

**Connection** — a canonical joint (`heel_point`, `front_hinge`, `rear_hinge`,
`upper_hinge`, `platform_base`) where reactions are reported.

**Contractual point** — an authored `(load_t, outreach_m)` duty the crane is sold
against, optionally labelled. A hoist carries a normal set and, when splitable, a
separate split set. Selecting one drives both geometry and hook load.

---

## Session and scene state

**Session** — the loaded document plus everything the user has changed since. Held by
the pure `core/session_model.py::SessionModel`: document, path, dirty flag, selected
hoist, per-hoist state, derived design limits, and a named change-event registry.

**Scene state** — `SessionModel`'s `SceneState`: what the operator has dialled in for
one hoist. Boom angle, hook load, tackle length, offlead, sidelead, wind speed and
direction, the three linear plus two angular accelerations, and the crane's slew.
This is the *input* to everything drawn and everything solved.

**Scene attitude** — the heel and trim the Scene solves and draws at
(`SessionModel.scene_attitude()`). It follows the document's vessel attitude until
edited in the Scene, then holds `scene_attitude_override` for every hoist until reset,
a document loads, or the Model is edited to match it. Never saved; `scene_document()`
and `scene_document_dict()` carry it into the Scene's solve and drawing.

**Hoist state** — `HoistState`: one hoist's scene state plus its UI-adjacent state —
split mode flag, chart mode, selected contractual index, cached sweep data.

**Design limit** — an allowable force on a rope or connection component, with
optional min and max in kN and enable flags. Derived from the document by
`core/limit_factory.py` and adjustable per session. Charts draw them; the capacity
calculation checks against them.

**Split mode** — a splitable hook block operated as two blocks: different falls,
different hook mass, and its own contractual point set. Only meaningful when the
hoist declares `splitable_block`.

---

## Geometry and loads

**Outreach** — horizontal distance from the crane's reference to the load node. The
user drives either boom angle or outreach; `calculation/solver/kinematics.py` maps
between them, and not every outreach is reachable.

**Tackle length** — rope length from the sheave to the hook, i.e. how far the hook
hangs. Bounded by the hoist's hook-travel limits.

**Offlead / sidelead** — the angle by which the hoist rope departs from vertical, in
plane (offlead) and out of plane (sidelead).

**Analysis point** — `calculation/engine.py::AnalysisPoint`: the full linear response
of the crane at one boom angle and outreach. A baseline at zero hook load, plus
sensitivities per kN of hook and per kN of lateral force. Everything downstream —
demands, capacity, charts, reports — is that response evaluated at an actual load,
which is why the solve happens once per geometry and not once per query.

**Drawn load** — one force or moment in the crane's in-plane load model, as a value:
world position, kN components, category, label, detail. Defined once, in
`core/drawn_loads.py`. This module is the *single* definition of the load model — the
scene draws it and the Equilibrium Check verifies it, so a mismatch is a bug in one
place rather than a divergence between two (see
[ADR-0002](docs/adr/0002-drawn-loads-own-the-load-model.md)).

**Load conditions** — the in-plane subset of scene state that produces drawn loads:
gravity, wind profile, and X/Z D'Alembert inertia. Lateral acceleration, roll
acceleration, sidelead and Y-axis wind are deliberately *absent*: they produce only
out-of-plane forces, so they have no drawable vector and no effect on in-plane
equilibrium.

**Vessel attitude** — the static heel (+ starboard down) and trim (+ bow down) of the
vessel, in `environment.vessel_motion`. *Vessel heel* is unrelated to `boom_heel`, the
boom's pivot node, or to the renderer's `heel_world`. The Scene may try its own (see
*Scene attitude*); load charts always use the document's.

**Slew** — the crane's rotation on the vessel, in degrees from the bow, + toward
starboard (`SceneState.slew_deg`). It only matters when the vessel is not level.

**Crane-frame gravity** — `vessel_attitude.CraneFrameGravity`: the unit gravity
direction the slewed crane sees. `lateral_x` lies in the luffing plane, `lateral_y`
across it, and `vertical` is the rest. An analysis point records the gravity it was
composed at.

**Slew envelope** — the slew samples a load chart is the worst case over
(`envelope_slew_angles`). Charts, contractual verdicts and auto-set use it; the Scene
shows one slew (see [ADR-0003](docs/adr/0003-vessel-attitude-and-slew-envelope.md)).

**Free body** — one body isolated with the loads acting on it, including the
reactions from its neighbours: `platform`, `boom`, `front_leg`, `rear_leg`, or
`none` for the whole crane. Selecting one filters both what the scene draws and what
the Equilibrium Check sums.

**Reaction group** — the set of forces a support carries, accumulated about that
support's own origin. Groups are `heel`, `front_leg`, `rear_leg`, `platform_base`;
each has its own moment reference, which is why accumulation is per group.

**Equilibrium check** — the report that sums the drawn loads for the selected free
body and shows the residual. It is a check on the load model, so it must read the
same values the scene draws.

---

## The scene

**Scene frame** — `core/scene_frame.py::SceneFrame`: an immutable value describing
everything the canvas shows, in *scene* coordinates. Nodes, rope segments,
structural members, markers, force arrows, moments, labels, guides, hit targets,
boom axes, fit rect, mapping, status, revision. Colours are hex strings, not Qt
types, so the frame travels to QML unchanged.

**Scene mapping** — the world↔scene coordinate transform carried on the frame.
`to_scene` projects; the renderer's `scene_to_world` inverts it for hit-testing.

**Building the frame** — `core/scene_build.py::build_scene_frame(SceneInputs) ->
SceneFrame`, pure. One value in, one value out, no ordering for a caller to know.
It projects and styles the loads that `drawn_loads` computed; it does not recompute
them.

**Showing the frame** — `qml_app/scene/scene_renderer.py::CraneSceneRenderer`. Its
whole interface is `show(frame)` plus the three `SceneCanvasContract` properties
(`scene_to_world`, `map_scale`, `heel_world`). It holds view-owned state only —
viewport fit and the cached mapping. A new need is met by putting the value in the
frame, not by widening the renderer.

**Hit target** — a frame-carried segment the pointer can grab, tagged with what it
drags: `boom_angle`, `outreach`, `tackle_length`.

**Drag gesture** — `qml_app/scene/scene_drag.py::SceneDrag`: press, move, release as
a value. It reads geometry from a `SceneCanvasContract` and *returns* the `DragEdit`
the pointer position implies; it never writes scene state itself. That is what makes
clamping, alt-snap and the heel-relative angle testable against a stub canvas.

**Session state (Qt)** — `qml_app/session.py::SessionState`: six `pyqtSignal`s plus
the `SessionModel` the view models read and write directly. It is the seam between
the pure session and Qt, and nothing more — see
[ADR-0001](docs/adr/0001-session-state-is-the-signal-seam.md).
