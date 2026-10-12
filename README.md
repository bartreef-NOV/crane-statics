# Crane Statics

A Qt Quick/QML desktop application for loading, editing, analyzing, and validating fixed-topology 2D crane models authored in JSON.

## Application

The QML application is the only supported desktop front end. It provides Scene, Load Chart, and Model workspaces backed by shared document, calculation, and scene-rendering services.

## Quick Start

### Installation

```bash
# Clone or extract the project
cd crane_statics

# Install in development mode
pip install -e .

# Or install with development dependencies
pip install -e ".[dev]"
```

### Running the Application

```bash
# Console command
crane-statics path/to/crane_model.json

# Or via Python module
python -m crane_statics path/to/crane_model.json
```

### Running Tests

```bash
pytest tests/ -v
```

## Architecture

### Layer Structure

```
src/crane_statics/
├── core/              # Document/session lifecycle and analysis services
├── data/              # Pydantic models, normalization, and validation
├── calculation/       # Statics solver and response computations
├── presentation/      # Display and formatting layer for tables and labels
├── qml_app/           # Qt Quick application, view models, and QML resources
├── schemas/           # Included schema artifacts
└── __main__.py        # Canonical QML module launcher
```

### Key Design Decisions

1. **Pydantic for Data Contracts**: Strict validation and normalization built into the data layer
2. **Pure Session Model**: `core/session_model.py` holds all session state with named change events; `qml_app/session.py::SessionState` adds Qt signals and nothing else ([ADR-0001](docs/adr/0001-session-state-is-the-signal-seam.md))
3. **QML View Models**: QML workspaces communicate through focused Qt properties, signals, and slots
4. **One Load Model**: `core/drawn_loads.py` defines every force and moment; the scene draws it and the Equilibrium Check verifies it, from the same values ([ADR-0002](docs/adr/0002-drawn-loads-own-the-load-model.md))
5. **Declarative Rendering**: `core/scene_build.py::build_scene_frame` produces an immutable `SceneFrame` from pure inputs; the renderer shows it via `show(frame)`

The domain vocabulary these modules are named after is in [CONTEXT.md](CONTEXT.md);
decisions that should not be re-litigated are in [docs/adr/](docs/adr/).

## Document Lifecycle

Authored input (YAML or JSON) is strict `crane-statics` schema version `6.0.0`.

Each hoist is self-contained: its `reeving` lists the rope path from the winch outwards, and an entry with `body` and coordinates defines a sheave or winch that belongs to that hoist (`boom` nodes use `u_m`/`w_m`, the others `x_m`/`z_m`). A hoist-local node `winch` in hoist `MH` becomes runtime node `mh_winch`. The last reeving entry is the support node the hook hangs from. Entries without coordinates pass through a node already defined (`boom_heel`, or a shared node under a body's `nodes`). Delete a hoist block to remove the hoist and its sheaves; copy one and rename its key to add a hoist.

Defaults apply for gravity, air density and vessel motion. Body sections (`boom`, `rear_leg`, `front_leg`, `platform`) and their `mass_points`, `wind_areas` and `nodes` may be omitted when empty. The schema includes coordinate-frame examples and descriptions for schema-aware editors. See `examples/` for complete files.

### Load Path
1. JSON file loaded from disk
2. `normalize_document()` fills in defaults, adds derived nodes, canonical connections
3. Pydantic validation enforces strict rules
4. SessionState initialized from normalized document
5. UI workspaces hydrated from session state

### Save Path
1. Session state synchronized back into document
2. `document_to_authored_form()` removes derived fields, connections, topology-controlled fields
3. Clean JSON written to disk (no internal machinery exposed)

## Features

- Document creation, opening, saving, and close-with-unsaved-changes protection
- Strict JSON validation and normalized fixed-topology crane documents
- Interactive Scene workspace with geometry, loads, wind, free-body, results, reports, and tooltips
- Load Chart workspace with capacity sweeps, contractual points, design limits, auto-set limits, and CSV/PNG export
- Model workspace with structured editing, validation feedback, and health status
- Native Fusion styling with Follow System, Light, and Dark appearance choices

## Numeric Tolerance

For comparing floating-point results against reference outputs, a tolerance of **10^-6** is used unless explicitly stated otherwise.

## Example Model

An example crane model is provided at `examples/crane_input_22689.yaml` with:
- 4 hoists (MH, AH, SH, BH)
- Multiple contractual points
- Full environment and structural definition
- All required nodes, ropes, and bodies

## Development Notes

### Adding a New Test

Keep tests close to the owning layer: use `tests/test_qml_shell.py` for QML load and shell behavior, the focused view-model test modules for workspace state, and `tests/test_acceptance.py` for cross-layer engineering behavior.

### Adding Workspace Features

Keep QML declarative and route state changes through the owning view model. Add QML controls under `src/crane_statics/qml_app/qml/`, expose only the necessary Qt properties/signals/slots from `src/crane_statics/qml_app/viewmodels/`, and preserve the `crane_statics` core as UI-independent application logic.

## References

- `src/crane_statics/schemas/crane-statics-v6.schema.json` - Authored JSON schema (Draft 2020-12), generated from `crane_statics.data.authored_models` via `python -m crane_statics.schemas.generate_schema`

## License

Proprietary
