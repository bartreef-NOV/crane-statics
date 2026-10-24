# Plan: Port crane_statics from Python to C++ (Qt 6)

## Context
The app is ~16k lines of Python plus 34 QML files. The goal is a C++ rewrite. Decisions:
- Python stays as the reference oracle during the port and is retired after parity.
- The existing QML is reused.
- Stack: Qt 6 + CMake + vcpkg (Eigen, yaml-cpp, nlohmann/json plus a JSON-schema validator, Qt Test or GoogleTest).

The codebase is already layered for this: `core/`, `calculation/` and `data/` have no Qt imports, and Qt lives only in `qml_app/`. Numpy is used only for two small linear solves in `calculation/solver/crane_solver.py` (~lines 755-809, a 3x3 and a 6x6 system). `core/chart_envelope.py` (the load-chart envelope) also uses vectorised numpy array arithmetic for ranking candidate cases; a plain loop or Eigen arrays will do in C++. Test expectations are asserted inline, so golden data must be generated from Python first.

## Approach: bottom-up, parity-gated, one layer at a time
Python remains the oracle. Each layer is accepted only when it matches Python output on shared fixtures.

### Phase 0 - Scaffolding and golden data
- Add `cpp/` with CMake presets, `vcpkg.json`, a `crane_core` static library, a `crane_app` executable and a `tests/` target.
- Write a Python script (under `tools/`, not `src/`) that runs each example in `examples/*.yaml` (22689, 13778_retracted, GT283) through the solver and exports golden JSON: inputs, solver outputs, scene frames, drawn loads and model-health results. Check the output into `cpp/tests/golden/`.
- Reuse `schemas/crane-statics-v9.schema.json` as the shared contract; C++ validates documents against it.

### Phase 1 - data + io (`data/`, `core/io.py`)
- Port `data/authored_models.py` and `data/models.py` to C++ structs with explicit validation and normalization (pydantic has no C++ equivalent). Keep the v9 major-version gate from `core/io.py`.
- YAML via yaml-cpp, JSON via nlohmann/json. Watch the YAML 1.1 int ambiguity fixed in commit 3f140f1.
- Gate: all example YAMLs load and re-serialize; schema validation passes; invalid-document cases from `tests/` behave the same.

### Phase 2 - calculation
- Port `calculation/` (engine, solver/crane_solver, kinematics, capacity, rope_mass, `vessel_frame` - the pure vessel/crane-frame transform, ADR-0003, port it first as the engine imports it). Replace `np.linalg.solve` with Eigen and map `LinAlgError` to a singular-matrix check.
- Gate: solver outputs match golden JSON within a stated tolerance; port the ~121 `test_acceptance.py` cases as parameterized tests.

### Phase 3 - core (no Qt)
- Port order: `drawn_loads` (single source of loads per ADR-0002) -> `scene_frame` / `scene_build` -> `session_model` -> `document_edit`, `model_health`, `limit_auto_set`, `vessel_envelope`, `lead_channels`, `chart_envelope`, `sweep`, `analysis_*`. The three envelope modules are pure and must precede `sweep`.
- Keep `SessionModel` pure with named change events (ADR-0001); Qt signals are added only at the QObject boundary.
- Port `presentation/formatters.py` alongside.
- Gate: scene frames and drawn loads match golden JSON; port `test_document_edit`, `test_scene_frame`, `test_model_health`, and an include-rule check equivalent to `test_architecture`.

### Phase 4 - qml_app
- Port `SessionState`, `scene_renderer` and the four view models (`appVm`, `modelVm`, `sceneVm`, `chartVm`) to C++ `QObject`s with `Q_PROPERTY`, signals and slots. Port `DictListModel` and `RecordTableModel` to `QAbstractListModel` / `QAbstractTableModel`. Register them via `setContextProperty` as in `app.py:71-74`.
- Reuse the 34 QML files and `design/` unchanged; fix only API mismatches. Follow the `qml-ui-development` skill for conventions and the `run-app` skill for verification.
- Gate: port `test_qml_shell` and the view-model tests; the app launches and screenshots of the Scene, Load Chart and Model workspaces match Python.

### Phase 5 - cutover
- Run both implementations on all fixtures in CI, then delete `src/crane_statics/`, update CLAUDE.md and README, and drop Python tooling.

## Critical files (Python sources to port)
- `src/crane_statics/calculation/solver/crane_solver.py`, `calculation/engine.py`
- `src/crane_statics/data/models.py`, `data/authored_models.py`, `core/io.py`
- `src/crane_statics/core/{drawn_loads,scene_build,scene_frame,session_model,document_edit}.py`
- `src/crane_statics/qml_app/{app,session}.py`, `qml_app/viewmodels/*`, `qml_app/models/*`

## Risks
- Floating-point drift between numpy and Eigen: fix tolerances up front.
- Pydantic validation semantics are implicit: derive cases from `tests/` and the schema.
- Expectations are inline in tests, so the Phase 0 golden export is the main safety net.
- The large view models (`scene_vm` 859 lines, `model_vm` 845 lines) are the biggest UI-layer effort.

## Verification
- Per phase: C++ tests against `cpp/tests/golden/` pass, and the Python suite still passes (`pytest`).
- End to end: `cmake --preset default && cmake --build`, then `ctest`; launch the app and compare screenshots of the three workspaces to Python.
