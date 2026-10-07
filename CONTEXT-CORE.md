# Domain Vocabulary (Core)

Essential terms for understanding the codebase structure. For the complete vocabulary, see `CONTEXT-EXTENDED.md`.

## Core Concepts

**Authored document** — the JSON a user writes; validated against the `crane-statics` schema.

**Normalized document** — an authored document after filling defaults and generating derived nodes. This is the `CraneDocument` every module sees.

**Body** — a rigid part of the crane: `platform`, `boom`, `front_leg`, `rear_leg`. Carries nodes and mass points.

**Node** — a named point on a body (e.g., `boom_heel`, `rear_top`). Referenced by ropes and hoists via id.

**Rope** — a load path with segments. A rope with `tension_mode="solve"` is a *boom-hoist* rope whose tension is an unknown.

**Hoist** — a lifting device with hook mass, falls, DAF, and contractual points (load/outreach duties).

**Session** — the loaded document plus changes since load. Held by pure `core/session_model.py::SessionModel`.

**Scene state** — the operator's inputs for one hoist: boom angle, hook load, tackle length, offlead, sidelead, wind, accelerations, and crane slew on the vessel.

**Vessel attitude** — static heel and trim, saved in the document; with slew it tilts gravity in the crane frame. Load charts are the worst case over slew. The Scene may try its own heel and trim without saving them.

**Scene frame** — `core/scene_frame.py::SceneFrame`: immutable description of what the canvas shows (nodes, ropes, forces, labels, hit targets, mapping).

**Drawn load** — one force or moment in the load model, with value, position, category, label. Defined once in `core/drawn_loads.py`.

**Analysis point** — `calculation/engine.py::AnalysisPoint`: full linear response at one boom angle. Baseline + sensitivities per kN hook and lateral force.
