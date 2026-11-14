# Crane Statics

[![CI](https://github.com/bartreef-NOV/crane-statics/actions/workflows/ci.yml/badge.svg)](https://github.com/bartreef-NOV/crane-statics/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000)](https://github.com/psf/black)
[![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue)](https://mypy-lang.org/)
[![Latest release](https://img.shields.io/github/v/release/bartreef-NOV/crane-statics)](https://github.com/bartreef-NOV/crane-statics/releases)

A Qt Quick/QML desktop application for loading, editing, analyzing, and validating fixed-topology 2D crane models authored in YAML.

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
crane-statics path/to/crane_model.yaml

# Or via Python module
python -m crane_statics path/to/crane_model.yaml
```

### Windows Executable

Tagged releases (`v*`) publish `crane-statics-<tag>-windows-x64.zip` on the GitHub Releases
page: unzip it and run `crane-statics.exe` (no Python needed). The build is unsigned, so
Windows SmartScreen or antivirus software may warn about it.

To build it locally:

```bash
pip install -e ".[build]"
pyinstaller packaging/crane-statics.spec --noconfirm
# -> dist/crane-statics/crane-statics.exe
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
├── calculation/       # Statics solver and response computations (standard-neutral)
├── rules/             # ABS and DNV profiles: dynamic factors, cases, foundation factors, provenance
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

Authored input (YAML) is strict `crane-statics` schema version `13.0.0` (`src/crane_statics/schemas/crane-statics-v13.schema.json`).

13.0.0 moves each payload hoist's `daf`, `offlead_deg` and `sidelead_deg` into `conditions.<name>.hoists.<id>`. `conditions` is now always required and `rules` is optional. Load-chart points carry `conditions: [...]`, naming the conditions they apply to. The top-level `environment.max_wind_speed_m_s` and `vessel_motion` are removed; each condition has its own `wind_speed_m_s` and `vessel_motion`. Convert v12 files with `PYTHONPATH=src python scripts/migrate_authored_v13.py <files>` (v12 files are rejected otherwise). 12.0.0 had renamed `hook_mass_t` to `lower_block_mass_t`.

Each hoist is self-contained: its `reeving` lists the rope path from the winch outwards, and an entry with `body` and coordinates defines a sheave or winch that belongs to that hoist (`boom` nodes use `u_m`/`w_m`, the others `x_m`/`z_m`). A hoist-local node `winch` in hoist `MH` becomes runtime node `mh_winch`. The last reeving entry is the support node the hook hangs from. Entries without coordinates pass through a node already defined (`boom_heel`, or a shared node under a body's `nodes`). Delete a hoist block to remove the hoist and its sheaves; copy one and rename its key to add a hoist.

Defaults apply for gravity and air density (and, per condition, vessel motion). Body sections (`boom`, `rear_leg`, `front_leg`, `platform`) and their `mass_points`, `wind_areas` and `nodes` may be omitted when empty. The schema includes coordinate-frame examples and descriptions for schema-aware editors. See `examples/` for complete files.

### ABS/DNV rules

Every document defines `conditions`, a map of named lift conditions. Each condition holds the wind speed, the vessel motion and a `hoists` map of the payload hoists usable under it. A hoist entry carries `offlead_deg`, `sidelead_deg` and an optional `daf`. A hoist is usable only if a condition lists it and its load-chart points name that condition (each listed condition needs at least one point naming it; the boom hoist `BH` is never listed). An optional `rules` section selects the certifying standard (ABS or DNV) and enables `lift: offboard`. Each hoist may carry `rope` (`ea_kN`, or elastic modulus and metallic area) and `max_hoisting_speed_m_s`. This excerpt is from `examples/crane_input_GT283_abs.yaml`:

```yaml
model_definition:
  rules: {standard: ABS, crane_class: offshore}   # or DNV
  conditions:
    onboard_sea:
      wind_speed_m_s: 20.0
      vessel_motion: {accel_x_m_s2: 0.3, accel_y_m_s2: 0.4, accel_z_m_s2: 0.5, roll_deg: 2.0, pitch_deg: 1.0}
      hoists:
        MH: {offlead_deg: 1.0, sidelead_deg: 2.5}   # daf omitted: derived from the standard
        AH: {offlead_deg: 2.0, sidelead_deg: 4.5}
    offboard_supply:
      lift: offboard
      wind_speed_m_s: 15.0
      significant_wave_height_m: 1.5
      # v_in_m_s, v_t_m_s ... as below
      hoists:
        MH: {offlead_deg: 1.0, sidelead_deg: 2.5}
  hoists:
    MH:
      # reeving, lower_block_mass_t, falls ... as usual
      rope: {ea_kN: 40000.0}
      max_hoisting_speed_m_s: 0.25
      load_chart:
      - outreach_m: 16.0
        load_t: 1000.0
        conditions: [onboard_sea, offboard_supply]
      - outreach_m: 25.0
        load_t: 1000.0
        conditions: [onboard_sea, offboard_supply]
```

Without `rules` every condition is onboard and the standard is not applied. A minimal rules-less document uses one `default` condition (this is the shape of `examples/crane_input_GT283.yaml`):

```yaml
model_definition:
  conditions:
    default:
      wind_speed_m_s: 20.0
      hoists:
        MH: {offlead_deg: 1.0, sidelead_deg: 2.5, daf: 1.1}
  hoists:
    MH:
      # reeving, lower_block_mass_t, falls ... as usual
      load_chart:
      - {outreach_m: 16.0, load_t: 1000.0, conditions: [default]}
      - {outreach_m: 25.0, load_t: 1000.0, conditions: [default]}
```

- Dynamic factor (`daf`, per hoist per condition): with `rules`, an omitted `daf` is derived from the standard and a given value is a manual override that the results flag; without `rules`, an omitted `daf` is 1.0.
- Offboard lifts need `significant_wave_height_m`, `v_in_m_s` and `v_t_m_s`. For ABS, `v_in_m_s` and `v_t_m_s` are the standard's `v_d` and `v_c` in `v_r = v_h + sqrt(v_d^2 + v_c^2)`; for DNV they are `Vin` and `Vt` in `VR = 0.5*VL + sqrt(Vin^2 + Vt^2)`. The Hs-based default velocities are not used.
- The hook stiffness is rope-only (boom hoist and active hoist as series EA/L), which is conservative. See [ADR-0004](docs/adr/0004-rules-profiles-keep-the-core-class-free.md) for the decision and its known limitations.
- The Model > Conditions tab lists, adds, duplicates, deletes and edits the conditions and each condition's per-hoist off-lead, side-lead and DAF. The Offboard group stays visible for onboard conditions so the wave height and velocities can be entered before switching the lift to offboard.
- The Load Chart workspace has a condition selector. Each condition has its own chart, and the Scene follows the selected condition and case.
- The Calculation details panel lists, for the inspected chart point, each factor with its value, inputs, formula, clause, whether it was computed or overridden, and any warnings.
- The chart CSV export of a rules chart adds the columns `condition`, `case`, `factor`, `unit`, `inputs`, `formula`, `clause`, `source`, `warnings` after `series,outreach_m,load_t`, one row per factor of each capacity point.

### Load Path
1. YAML file loaded from disk
2. `normalize_document()` fills in defaults, adds derived nodes, canonical connections
3. Pydantic validation enforces strict rules
4. SessionState initialized from normalized document
5. UI workspaces hydrated from session state

### Save Path
1. Session state synchronized back into document
2. `document_to_authored_form()` removes derived fields, connections, topology-controlled fields
3. Clean YAML written to disk (no internal machinery exposed)

## Features

- Document creation, opening, saving, and close-with-unsaved-changes protection
- Strict YAML validation and normalized fixed-topology crane documents
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

- `src/crane_statics/schemas/crane-statics-v13.schema.json` - Authored JSON schema (Draft 2020-12), generated from `crane_statics.data.authored_models` via `python -m crane_statics.schemas.generate_schema`
- ABS, *Requirements for Certification of Lifting Appliances*, January 2026. Part 2-2: 9.3 (p.52-54), 5.15 (p.46), 5.13.5(c) (p.46), 5.17 (p.47-48), 5.19 (p.49-50), 5.21 (p.50-51), 11 (p.56-57)
- DNV-ST-0378, *Offshore and platform lifting appliances*, July 2019, amended October 2021: 4.1.3.2 (p.54), 4.2.2.1 (p.57), 4.2.3.2 and 4.2.3.3 (p.58), 8.2.2.1 (p.90), 8.2.2.2 (p.91), 8.2.2.4 (p.91)

## License

Proprietary
