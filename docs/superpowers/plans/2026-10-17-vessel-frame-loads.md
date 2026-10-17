# Vessel-Frame Loads Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drive structure and payload loads from vessel-frame accelerations, vessel roll/pitch (gravity tilt) and crane slewing angle, with constant wind and no waterline, while the scene stays in the crane frame.

**Architecture:** A new pure module `core/vessel_frame.py` turns vessel inputs into a crane-frame load acceleration (`CraneFrameMotion`). The engine resolves it once per analysis and feeds the existing ax/ay/az/pitch/roll channels; the solver's scalar-gravity sites are changed to use the resulting load vector so tilt loads payload and structure consistently. Schema major 6 → 7 removes wind-profile/sea-level fields.

**Tech Stack:** Python 3.13, pydantic, pytest, Qt Quick/QML (PySide6), JSON Schema.

**Spec:** `docs/superpowers/specs/2026-10-17-vessel-frame-loads-design.md`

## Global Constraints

- Intrinsic rotation `R = Rz(α)·Ry(β)·Rx(γ)` (Tait–Bryan z-y-x); α = yaw (irrelevant for gravity), β = pitch, γ = roll.
- Vessel axes: x forward, y port, z up. Pitch positive bow-down; roll positive to starboard.
- Gravity in vessel frame: `g·(sinβ, −sinγ·cosβ, −cosγ·cosβ)`; `g` = `abs(environment.gravity_m_s2)`.
- Load acceleration `k_v = g_v − a_v`; rotate by `−crane_slewing_angle` about z to get `k_c`; equivalent acceleration `a_eq = (0,0,−g) − k_c`.
- All new inputs are exact signed values; no ± envelope for accelerations, angles or angular accelerations. Wind-direction enumeration is unchanged.
- Zero angles/accelerations must reproduce today's results exactly.
- Wind speed is constant with height (`max_wind_speed_m_s`). Removed: `wind_profile_exponent`, `wind_reference_height_m_asl`, `mean_sealevel_z_m`. `air_density_kg_m3` stays.
- Waterline removed from the scene. Hook-height default (unauthored) = crane-frame z = 0.
- Authored schema major version 7 (`AUTHORED_SCHEMA_VERSION = "7.0.0"`), schema file `crane-statics-v7.schema.json`.
- Angular-acceleration reference point (`reference_x_m`, `reference_z_m`) stays in crane-frame coordinates.
- Run `pytest` from the repo root; project hooks run black, flake8, mypy and the architecture boundary tests on commit — `core/` and `calculation/` must stay Qt-free.

## Review Focus

- Combined roll + pitch + slew produces the same load vector magnitude as `g` (gravity vector stays unit-consistent): tested in Task 1.
- Slew of ±90° / 180° swaps/negates x and y consistently for accelerations and for angular accelerations: Task 1.
- Zero-everything scene reproduces the pre-change numbers (regression guard): Task 4.
- Idle hook, support-compensation and rope masses feel tilt, not only the boom/leg mass points: Task 4.
- Old v6 files (with `wind_profile_exponent` etc.) are rejected with the unsupported-version message, not a confusing validation error: Task 2.
- Negative accelerations round-trip through load/save (old validators forced `abs`/`>=0`): Task 2.

---

### Task 1: Pure vessel-frame transform

**Files:**
- Create: `src/crane_statics/core/vessel_frame.py`
- Test: `tests/test_vessel_frame.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class VesselInputs:
      accel_x_m_s2: float = 0.0   # vessel frame, gravity excluded
      accel_y_m_s2: float = 0.0
      accel_z_m_s2: float = 0.0
      roll_deg: float = 0.0
      pitch_deg: float = 0.0
      slew_deg: float = 0.0
      roll_accel_rad_s2: float = 0.0   # about vessel x
      pitch_accel_rad_s2: float = 0.0  # about vessel y

  @dataclass(frozen=True)
  class CraneFrameMotion:
      load_accel: tuple[float, float, float]   # k_c, m/s²; force on mass m = m*load_accel
      accel_x_m_s2: float                      # a_eq components, crane frame
      accel_y_m_s2: float
      accel_z_m_s2: float
      pitch_accel_rad_s2: float                # about crane y
      roll_accel_rad_s2: float                 # about crane x

  def gravity_in_vessel_frame(g: float, roll_deg: float, pitch_deg: float) -> tuple[float, float, float]
  def crane_frame_motion(g: float, inputs: VesselInputs) -> CraneFrameMotion
  ```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_vessel_frame.py
import math

import pytest

from crane_statics.core.vessel_frame import (
    VesselInputs,
    crane_frame_motion,
    gravity_in_vessel_frame,
)

G = 9.81


def test_level_vessel_gravity_is_straight_down():
    gx, gy, gz = gravity_in_vessel_frame(G, 0.0, 0.0)
    assert (gx, gy, gz) == pytest.approx((0.0, 0.0, -G))


def test_pitch_bow_down_gives_forward_gravity_component():
    gx, gy, gz = gravity_in_vessel_frame(G, 0.0, 10.0)
    assert gx == pytest.approx(G * math.sin(math.radians(10.0)))
    assert gy == pytest.approx(0.0)
    assert gz == pytest.approx(-G * math.cos(math.radians(10.0)))


def test_roll_to_starboard_gives_gravity_toward_starboard_negative_y():
    gx, gy, gz = gravity_in_vessel_frame(G, 10.0, 0.0)
    assert gx == pytest.approx(0.0)
    assert gy == pytest.approx(-G * math.sin(math.radians(10.0)))
    assert gz == pytest.approx(-G * math.cos(math.radians(10.0)))


def test_gravity_magnitude_is_preserved_for_combined_angles():
    gx, gy, gz = gravity_in_vessel_frame(G, 7.0, -12.0)
    assert math.sqrt(gx**2 + gy**2 + gz**2) == pytest.approx(G)


def test_zero_inputs_give_zero_equivalent_motion():
    m = crane_frame_motion(G, VesselInputs())
    assert m.load_accel == pytest.approx((0.0, 0.0, -G))
    assert (m.accel_x_m_s2, m.accel_y_m_s2, m.accel_z_m_s2) == pytest.approx((0.0, 0.0, 0.0))
    assert m.pitch_accel_rad_s2 == pytest.approx(0.0)
    assert m.roll_accel_rad_s2 == pytest.approx(0.0)


def test_level_acceleration_matches_legacy_convention():
    # Legacy: Fx = -m*ax, Fz = -m*(g + az)
    m = crane_frame_motion(G, VesselInputs(accel_x_m_s2=1.5, accel_z_m_s2=0.4))
    assert m.load_accel == pytest.approx((-1.5, 0.0, -(G + 0.4)))
    assert (m.accel_x_m_s2, m.accel_z_m_s2) == pytest.approx((1.5, 0.4))


def test_slew_90_maps_vessel_x_acceleration_to_negative_crane_y():
    m = crane_frame_motion(G, VesselInputs(accel_x_m_s2=1.0, slew_deg=90.0))
    assert m.accel_x_m_s2 == pytest.approx(0.0, abs=1e-12)
    assert m.accel_y_m_s2 == pytest.approx(-1.0)


def test_slew_90_maps_vessel_pitch_tilt_to_crane_y_gravity():
    m = crane_frame_motion(G, VesselInputs(pitch_deg=10.0, slew_deg=90.0))
    s = math.sin(math.radians(10.0))
    # vessel-frame g_x = G*s; crane y = -vessel x
    assert m.load_accel[0] == pytest.approx(0.0, abs=1e-12)
    assert m.load_accel[1] == pytest.approx(-G * s)


def test_slew_180_negates_horizontal_components():
    a = crane_frame_motion(G, VesselInputs(accel_x_m_s2=1.0, accel_y_m_s2=2.0))
    b = crane_frame_motion(G, VesselInputs(accel_x_m_s2=1.0, accel_y_m_s2=2.0, slew_deg=180.0))
    assert b.accel_x_m_s2 == pytest.approx(-a.accel_x_m_s2)
    assert b.accel_y_m_s2 == pytest.approx(-a.accel_y_m_s2)
    assert b.accel_z_m_s2 == pytest.approx(a.accel_z_m_s2)


def test_angular_accelerations_rotate_with_slew():
    m0 = crane_frame_motion(G, VesselInputs(roll_accel_rad_s2=0.1, pitch_accel_rad_s2=0.2))
    assert (m0.roll_accel_rad_s2, m0.pitch_accel_rad_s2) == pytest.approx((0.1, 0.2))
    m90 = crane_frame_motion(
        G, VesselInputs(roll_accel_rad_s2=0.1, pitch_accel_rad_s2=0.2, slew_deg=90.0)
    )
    assert m90.roll_accel_rad_s2 == pytest.approx(0.2)
    assert m90.pitch_accel_rad_s2 == pytest.approx(-0.1)
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_vessel_frame.py -v`
Expected: FAIL (`ModuleNotFoundError: crane_statics.core.vessel_frame`).

- [ ] **Step 3: Implement**

```python
# src/crane_statics/core/vessel_frame.py
"""Vessel-frame motion → crane-frame load acceleration (pure, Qt-free).

Vessel axes: x forward, y port, z up. Pitch is positive bow-down, roll positive to
starboard. R = Rz(yaw)·Ry(pitch)·Rx(roll) (intrinsic z-y-x) maps vessel → world, so
gravity in the vessel frame is Rᵀ·(0, 0, -g); yaw drops out. The crane frame is the vessel
frame rotated about z by the slewing angle.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class VesselInputs:
    accel_x_m_s2: float = 0.0
    accel_y_m_s2: float = 0.0
    accel_z_m_s2: float = 0.0
    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    slew_deg: float = 0.0
    roll_accel_rad_s2: float = 0.0
    pitch_accel_rad_s2: float = 0.0


@dataclass(frozen=True)
class CraneFrameMotion:
    load_accel: tuple[float, float, float]
    accel_x_m_s2: float
    accel_y_m_s2: float
    accel_z_m_s2: float
    pitch_accel_rad_s2: float
    roll_accel_rad_s2: float


def gravity_in_vessel_frame(g: float, roll_deg: float, pitch_deg: float) -> tuple[float, float, float]:
    """Return gravity (m/s²) in the vessel frame for a positive magnitude ``g``."""
    roll = math.radians(roll_deg)
    pitch = math.radians(pitch_deg)
    return (
        g * math.sin(pitch),
        -g * math.sin(roll) * math.cos(pitch),
        -g * math.cos(roll) * math.cos(pitch),
    )


def _vessel_to_crane(x: float, y: float, slew_deg: float) -> tuple[float, float]:
    """Rotate a horizontal vessel-frame vector by -slew about z."""
    s = math.radians(slew_deg)
    return (
        math.cos(s) * x + math.sin(s) * y,
        -math.sin(s) * x + math.cos(s) * y,
    )


def crane_frame_motion(g: float, inputs: VesselInputs) -> CraneFrameMotion:
    """Resolve vessel inputs into the crane-frame load acceleration and equivalent motion."""
    gx, gy, gz = gravity_in_vessel_frame(g, inputs.roll_deg, inputs.pitch_deg)
    kx_v = gx - inputs.accel_x_m_s2
    ky_v = gy - inputs.accel_y_m_s2
    kz = gz - inputs.accel_z_m_s2
    kx, ky = _vessel_to_crane(kx_v, ky_v, inputs.slew_deg)
    roll_c, pitch_c = _vessel_to_crane(
        inputs.roll_accel_rad_s2, inputs.pitch_accel_rad_s2, inputs.slew_deg
    )
    return CraneFrameMotion(
        load_accel=(kx, ky, kz),
        accel_x_m_s2=-kx,
        accel_y_m_s2=-ky,
        accel_z_m_s2=-g - kz,
        pitch_accel_rad_s2=pitch_c,
        roll_accel_rad_s2=roll_c,
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_vessel_frame.py tests/test_architecture.py -v`
Expected: PASS (module is Qt-free, so the architecture test is unaffected).

- [ ] **Step 5: Commit**

```bash
git add src/crane_statics/core/vessel_frame.py tests/test_vessel_frame.py
git commit -m "Add pure vessel-frame to crane-frame load transform"
```

---

### Task 2: Schema v7, runtime model, and example migration

Removes wind-profile/sea-level fields, adds signed vessel-frame `vessel_motion` with roll, pitch and slew defaults, bumps the schema major version, and updates every fixture that mentions the removed fields.

**Files:**
- Modify: `src/crane_statics/data/authored_models.py` (`AUTHORED_SCHEMA_MAJOR_VERSION` line 26, `AUTHORED_SCHEMA_VERSION` line 27, `AuthoredVesselMotion` ~65, `AuthoredEnvironment` ~79, hook-height description ~530, example dict ~574-582)
- Modify: `src/crane_statics/data/models.py` (`VesselMotion` 85, `Environment` 108, `DEFAULT_VESSEL_MOTION` 27, normalization ~801-818 and ~1146-1190, ~1313-1320, ~1726, ~2068-2103)
- Modify: `src/crane_statics/core/io.py` (only if it hard-codes `v6`; check with `grep -n "v6\|crane-statics-v" src/crane_statics/core/io.py src/crane_statics/schemas/generate_schema.py`)
- Rename/regenerate: `src/crane_statics/schemas/crane-statics-v6.schema.json` → `crane-statics-v7.schema.json` (via `generate_schema.py`)
- Modify: `examples/*.yaml` (three files; lines 7-9 hold the removed fields)
- Modify tests: `tests/test_acceptance.py` (~206-208, ~610-612), `tests/test_document_io_formats.py` (~20-22), `tests/test_reeving.py` (~22-24), `tests/test_schema_contract.py`
- Test: `tests/test_vessel_motion_schema.py` (new)

**Interfaces:**
- Produces: authored `vessel_motion` keys (all default 0, signed): `accel_x_m_s2`, `accel_y_m_s2`, `accel_z_m_s2` (vessel frame, gravity excluded), `roll_deg`, `pitch_deg`, `crane_slewing_angle_deg`, `pitch_angular_accel_rad_s2`, `roll_angular_accel_rad_s2`, `reference_x_m`, `reference_z_m`. Runtime `VesselMotion` has the same field names. `Environment` no longer has `wind_reference_height_m_asl`, `wind_profile_exponent`, `mean_sealevel_z_m`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_vessel_motion_schema.py
import pytest
from pydantic import ValidationError

from crane_statics.data.authored_models import (
    AUTHORED_SCHEMA_MAJOR_VERSION,
    AuthoredEnvironment,
    AuthoredVesselMotion,
)
from crane_statics.data.models import Environment, VesselMotion


def test_schema_major_is_7():
    assert AUTHORED_SCHEMA_MAJOR_VERSION == 7


def test_authored_vessel_motion_accepts_signed_values_and_angles():
    vm = AuthoredVesselMotion(
        accel_x_m_s2=-1.2, roll_deg=-4.0, pitch_deg=3.0, crane_slewing_angle_deg=-90.0
    )
    assert vm.accel_x_m_s2 == -1.2
    assert vm.crane_slewing_angle_deg == -90.0


def test_authored_environment_rejects_removed_wind_fields():
    with pytest.raises(ValidationError):
        AuthoredEnvironment(max_wind_speed_m_s=20.0, wind_profile_exponent=0.143)
    with pytest.raises(ValidationError):
        AuthoredEnvironment(max_wind_speed_m_s=20.0, mean_sealevel_z_m=-35.0)


def test_runtime_models_have_signed_motion_and_no_wind_profile():
    vm = VesselMotion(accel_z_m_s2=-0.5, roll_deg=2.0)
    assert vm.accel_z_m_s2 == -0.5
    env = Environment()
    for removed in ("wind_profile_exponent", "wind_reference_height_m_asl", "mean_sealevel_z_m"):
        assert not hasattr(env, removed)
```

Also add to `tests/test_document_io_formats.py` a test that loading a document whose `schema.version` is `6.0.0` raises the existing "Unsupported authored schema version" error (reuse the module's existing fixture-builder; set `schema.version = "6.0.0"`), and a save/load round-trip test with `accel_x_m_s2: -1.0` and `roll_deg: -3.0` asserting both survive.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_vessel_motion_schema.py -v`
Expected: FAIL (major is 6, fields missing).

- [ ] **Step 3: Implement**

1. `authored_models.py`: set major 7 / version `"7.0.0"`. Replace `AuthoredVesselMotion` body with signed fields (drop every `ge=0`) plus `roll_deg`, `pitch_deg`, `crane_slewing_angle_deg` (default 0.0) and keep `reference_x_m`, `reference_z_m`; update the docstring to "vessel-frame accelerations (gravity excluded), roll/pitch, crane slewing angle". Delete `wind_profile_exponent`, `wind_reference_height_m_asl`, `mean_sealevel_z_m` from `AuthoredEnvironment` and fix its docstring; change the hook-height description (~530) to "Omit to default to crane-frame z = 0." Update the example dict (~574-582) and bump its `schema.version`.
2. `models.py`: `VesselMotion` — add `roll_deg`, `pitch_deg`, `crane_slewing_angle_deg`; delete `validate_non_negative`. `Environment` — delete the three fields and shrink `validate_positive` to `air_density_kg_m3` only. `DEFAULT_VESSEL_MOTION` — add the three angle keys. In the normalization code (~1146-1190) remove the `abs(...)` wrappers around accelerations and the three removed environment keys, and pass the three angle keys through with `float(...)`. In the lines ~801-818 and ~1726 and ~2103 replace the `mean_sealevel_z_m` fallback for the design hook height with `0.0`. Delete the removed fields from the export path (~2090-2095) and make the export emit `vessel_motion` keys from `DEFAULT_VESSEL_MOTION` (so the new angle keys are written).
3. `grep -rn "wind_profile\|mean_sealevel\|wind_reference" src examples tests` and remove every remaining authored/runtime occurrence in these files; the in-scope remainders are handled in later tasks: `core/drawn_loads.py` and `core/scene_build.py` (Task 3/6), `calculation/*` (Task 3), `presentation/formatters.py`, `qml_app/contracts.py`, `qml_app/viewmodels/model_vm.py`, `qml_app/qml/EnvironmentPanel.qml` (Task 6).
4. `examples/*.yaml`: delete the three removed keys; set `schema.version` to `7.0.0`; add nothing else (new fields default to 0).
5. Regenerate the schema: `python -m crane_statics.schemas.generate_schema` (see `schemas/generate_schema.py` for its exact CLI), `git rm` the v6 file, add the v7 file, and fix any path/name constant that still says v6 (`grep -rn "v6" src tests pyproject.toml`).
6. Update the three test fixtures listed above to drop the removed keys and use `"7.0.0"`.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_vessel_motion_schema.py tests/test_schema_contract.py tests/test_document_io_formats.py -v`
Expected: PASS. (Other suites may still fail until Tasks 3-6; do not touch them yet.)
Then use the `schema-contract-reviewer` agent on the diff.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Schema v7: signed vessel-frame motion with roll/pitch/slew, drop wind profile and sea level"
```

---

### Task 3: Constant wind profile

**Files:**
- Modify: `src/crane_statics/calculation/solver/crane_solver.py` (`_accumulate_loads`: remove `wind_ref_h`, `msl_z`, `wind_exp` ~421-423; replace `_wind_fx` ~448-455)
- Modify: `src/crane_statics/calculation/engine.py` (`_build_split_support_reactions` ~358-382: remove `z_ref`, `exp`, `msl`, `h_asl`, `v_eff`)
- Modify: `src/crane_statics/core/drawn_loads.py` (~516-518 and its use)
- Test: `tests/test_constant_wind.py`

**Interfaces:** Consumes `max_wind_speed_m_s`; the wind force on an area is `0.5·ρ·Cd·A·v²/1000` kN independent of height.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_constant_wind.py
from pathlib import Path

import pytest

from crane_statics.calculation.engine import KinematicsAdapter  # same import engine.py uses
from crane_statics.calculation.solver import crane_solver
from crane_statics.core import load_document
from crane_statics.data.models import WindArea

EXAMPLES = Path(__file__).parent.parent / "examples"


def _wind_fx_total(z_m: float) -> float:
    doc = load_document(EXAMPLES / "crane_input_GT283.yaml")
    for body in doc.bodies:
        body.wind_areas = []
        if body.id == "rear_leg":
            body.wind_areas = [
                WindArea(id="w", area_w_m2=10.0, area_v_m2=0.0, cd=1.2, x_m=0.0, z_m=z_m)
            ]
    d = doc.model_dump()
    positions = KinematicsAdapter(d).compute_all_node_positions(45.0)
    node_pos = {n: (float(v["x"]), float(v["z"])) for n, v in positions.items()}
    body_map = {n["id"]: n.get("body", "") for n in d["nodes"]}
    windy, _ = crane_solver._accumulate_loads(
        d, node_pos, body_map, "MH", 0.0, 20.0, 0.0, 0.0, boom_angle_deg=45.0
    )
    calm, _ = crane_solver._accumulate_loads(
        d, node_pos, body_map, "MH", 0.0, 0.0, 0.0, 0.0, boom_angle_deg=45.0
    )
    return sum(windy[b]["Fx"] - calm[b]["Fx"] for b in windy)


def test_wind_force_is_independent_of_height():
    expected = 0.5 * 1.225 * 1.2 * 10.0 * 20.0**2 / 1000.0
    assert _wind_fx_total(10.0) == pytest.approx(expected)
    assert _wind_fx_total(60.0) == pytest.approx(expected)
```

If `KinematicsAdapter` is not importable from `engine`, copy the import line `engine.py` uses (`grep -n "KinematicsAdapter" src/crane_statics/calculation/engine.py`). Add a second test for the Y path: call `CraneCalculator._build_split_support_reactions` with `wind_y_m_s=20.0` for the two documents (z = 10 and 60) and assert the returned total lateral force (third tuple element) is equal.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_constant_wind.py -v` — Expected: FAIL (power law still applies).

- [ ] **Step 3: Implement**

In `_accumulate_loads`:

```python
    def _wind_fx(area: float, cd: float, is_boom_body: bool) -> float:
        eff_area = area * boom_scale if is_boom_body else area
        return float(wind_sign * 0.5 * air_density * v_mag**2 * cd * eff_area / 1000.0)
```

update both call sites to drop the `wcz` argument (the moment arm `-wcz * fx` stays). In `engine._build_split_support_reactions` use `v_eff = wind_mag`. In `drawn_loads.py` replace the power-law speed with the constant speed (read the surrounding method first and keep its force-arrow semantics).

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_constant_wind.py tests/test_scene_frame.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Apply wind speed at a constant value over height"
```

---

### Task 4: Engine and solver use the crane-frame load vector

**Files:**
- Modify: `src/crane_statics/calculation/solver/crane_solver.py` (`_accumulate_loads`: idle hook ~646, support-comp weight ~635, signature; `inertia_force` stays)
- Modify: `src/crane_statics/calculation/engine.py` (`compute_analysis_point` signature ~520-535 and body ~550-640; `_build_split_support_reactions` ~283-340; sweep wrapper ~846-872)
- Modify: `src/crane_statics/calculation/solver/crane_solver.py` (`compose_scalar_envelope_unit_basis_point` removal)
- Test: `tests/test_vessel_frame_engine.py`

**Interfaces:**
- Consumes: `crane_frame_motion`, `VesselInputs` (Task 1).
- Produces: `CraneCalculator.compute_analysis_point` (and the wrappers that forward motion kwargs — `grep -n accel_x_m_s2 src/crane_statics/calculation/engine.py`) accept optional `vessel_roll_deg`, `vessel_pitch_deg`, `crane_slewing_angle_deg` (default `None` → document `vessel_motion`). The existing `accel_*_m_s2` / `*_accel_rad_s2` kwargs now mean **vessel-frame** values.
- Internal contract: `crane_solver._accumulate_loads(..., accel_x_m_s2, accel_z_m_s2, pitch_rad_s2)` and `build_directional_response_basis` keep their signatures but receive **equivalent crane-frame** values (`CraneFrameMotion.accel_x_m_s2`, `accel_z_m_s2`, `pitch_accel_rad_s2`), so the channel basis is unchanged.

- [ ] **Step 0: Record golden numbers (before any edit in this task)**

On the commit that finished Task 3, run once from the repo root (script lives outside the repo; `python -I`) and commit `tests/golden/gt283_mh_45deg.json`:

```python
import json
from pathlib import Path
from crane_statics.calculation.engine import CraneCalculator
from crane_statics.core import load_document

doc = load_document(Path("examples/crane_input_GT283.yaml"))
p = CraneCalculator(doc).compute_analysis_point(
    "MH", 45.0, wind_speed_m_s=10.0, wind_direction="+X",
    accel_x_m_s2=0.5, accel_z_m_s2=0.3, pitch_accel_rad_s2=0.01,
)
Path("tests/golden").mkdir(exist_ok=True)
Path("tests/golden/gt283_mh_45deg.json").write_text(
    json.dumps({"baseline": p.baseline_reactions, "sensitivity": p.sensitivity_reactions},
               indent=1, sort_keys=True)
)
```

The inputs are level (no tilt, slew 0), so this golden must survive Task 4 unchanged.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_vessel_frame_engine.py
import json
import math
from pathlib import Path

import pytest

from crane_statics.calculation.engine import CraneCalculator
from crane_statics.calculation.solver import crane_solver
from crane_statics.core import load_document

ROOT = Path(__file__).parent.parent
G = 9.81


@pytest.fixture(scope="module")
def calc():
    return CraneCalculator(load_document(ROOT / "examples" / "crane_input_GT283.yaml"))


def _flat(reactions):
    return {(e, k): v for e, comps in reactions.items() for k, v in comps.items()}


def test_level_vessel_inputs_reproduce_golden(calc):
    p = calc.compute_analysis_point(
        "MH", 45.0, wind_speed_m_s=10.0, wind_direction="+X",
        accel_x_m_s2=0.5, accel_z_m_s2=0.3, pitch_accel_rad_s2=0.01,
        vessel_roll_deg=0.0, vessel_pitch_deg=0.0, crane_slewing_angle_deg=0.0,
    )
    golden = json.loads((ROOT / "tests/golden/gt283_mh_45deg.json").read_text())
    assert _flat(p.baseline_reactions) == pytest.approx(_flat(golden["baseline"]))
    assert _flat(p.sensitivity_reactions) == pytest.approx(_flat(golden["sensitivity"]))


def test_pitch_equals_equivalent_level_acceleration(calc):
    beta = math.radians(10.0)
    tilted = calc.compute_analysis_point("MH", 45.0, wind_speed_m_s=0.0, vessel_pitch_deg=10.0)
    equiv = calc.compute_analysis_point(
        "MH", 45.0, wind_speed_m_s=0.0,
        accel_x_m_s2=-G * math.sin(beta), accel_z_m_s2=-G * (1.0 - math.cos(beta)),
    )
    assert _flat(tilted.baseline_reactions) == pytest.approx(_flat(equiv.baseline_reactions))


def test_tilt_loads_every_mass_including_idle_hook(calc):
    """Sum of body Fx under pitch beta == |sum of body Fz| at level * sin(beta).

    Holds only if every mass (mass points, idle hook mass, support-comp mass, rope mass) feels
    the tilt; a mass left on the scalar-gravity path breaks the identity.
    """
    d = calc._doc_dict
    positions = calc._kinematics.compute_all_node_positions(45.0)
    node_pos = {n: (float(v["x"]), float(v["z"])) for n, v in positions.items()}
    body_map = {n["id"]: n.get("body", "") for n in d["nodes"]}
    beta = math.radians(10.0)
    level, _ = crane_solver._accumulate_loads(
        d, node_pos, body_map, "MH", 0.0, 0.0, 0.0, 0.0, boom_angle_deg=45.0
    )
    tilted, _ = crane_solver._accumulate_loads(
        d, node_pos, body_map, "MH", 0.0, 0.0,
        -G * math.sin(beta), -G * (1.0 - math.cos(beta)), boom_angle_deg=45.0,
    )
    total_fz_level = sum(b["Fz"] for b in level.values())
    total_fx_tilted = sum(b["Fx"] for b in tilted.values())
    assert total_fx_tilted == pytest.approx(abs(total_fz_level) * math.sin(beta))


def test_slew_90_moves_vessel_ax_out_of_the_xz_solve(calc):
    level = calc.compute_analysis_point("MH", 45.0, wind_speed_m_s=0.0)
    at0 = calc.compute_analysis_point("MH", 45.0, wind_speed_m_s=0.0, accel_x_m_s2=1.0)
    at90 = calc.compute_analysis_point(
        "MH", 45.0, wind_speed_m_s=0.0, accel_x_m_s2=1.0, crane_slewing_angle_deg=90.0
    )
    assert _flat(at90.baseline_reactions) == pytest.approx(_flat(level.baseline_reactions))
    assert _flat(at0.baseline_reactions) != pytest.approx(_flat(level.baseline_reactions))
```

`test_tilt_loads_every_mass_including_idle_hook` is the guard for the scalar-gravity sites: it fails until the idle-hook, support-comp and rope-mass sites route through `inertia_force`. Add a fifth test asserting that with `crane_slewing_angle_deg=90` and `accel_x_m_s2=1.0` the split-support left/right reactions differ from the level case (copy the accessor `tests/test_split_support_compensation.py` uses to read split results).

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_vessel_frame_engine.py -v` — Expected: FAIL (unknown kwargs).

- [ ] **Step 3: Implement**

1. `engine.py` — `compute_analysis_point` and the sweep wrapper (~846-872): add the three kwargs. After resolving the document defaults (`vm.accel_x_m_s2` etc., plus `vm.roll_deg`, `vm.pitch_deg`, `vm.crane_slewing_angle_deg`), call
   ```python
   motion = crane_frame_motion(abs(float(env.gravity_m_s2)), VesselInputs(
       accel_x_m_s2=accel_x_ref, accel_y_m_s2=accel_y_ref, accel_z_m_s2=accel_z_ref,
       roll_deg=roll_deg, pitch_deg=pitch_deg, slew_deg=slew_deg,
       roll_accel_rad_s2=roll_ref, pitch_accel_rad_s2=pitch_ref))
   ```
   and pass `motion.accel_x_m_s2`, `motion.accel_z_m_s2`, `motion.pitch_accel_rad_s2` to `build_directional_response_basis`, and `motion.accel_y_m_s2`, `motion.roll_accel_rad_s2`, `motion.load_accel` to `_augment_point_with_split_supports` → `_build_split_support_reactions` (add a `load_accel` parameter). Always compose with signs (`_explicit_env` branch): delete the `else` branch, the `_explicit_env` flag and the import of `compose_scalar_envelope_unit_basis_point`.
2. `_build_split_support_reactions`: replace `fz_weight = -mass*gravity_abs` and the `fy_acc` term by `fy = mass*(load_accel_y - roll_accel*(zw - roll_ref_z)*(-1) ...)` — keep the existing sign convention: `ay_pt = accel_y + roll_accel*(zw - roll_ref_z)`; `fy_acc = -m*ay_pt`, `fz_weight = -m*(gravity_abs + accel_z)`, `fx = -m*accel_x` (all equivalent crane-frame values from `motion`), so `load_accel` itself is not needed there — drop that parameter and pass the equivalent values. The support-comp `fz_comp` becomes `-comp_mass_t * (gravity_abs + accel_z)` with `fx = -comp_mass_t * accel_x`, `fy = -comp_mass_t * accel_y`.
3. `crane_solver._accumulate_loads`: at the support-comp site (~635) and idle-hook site (~646) replace `fz = -m*gravity_abs` by `fx, fz = inertia_force(m, x, z, accel_x_m_s2, accel_z_m_s2, pitch_rad_s2, ref_x, ref_z, gravity)` and add `ld_fx[b] += fx`, `ld_m[b] += x*fz - z*fx`, using the same moment form as the mass loop. Keep the `bh_*` coefficient bookkeeping untouched.
4. Delete `compose_scalar_envelope_unit_basis_point` from `crane_solver.py` and its re-export in `solver/__init__.py` if present. `governing_signs` stays (it now always carries the exact signs).
5. Update all call sites that build engine kwargs from `SceneState`: `grep -rn "accel_x_m_s2=" src/crane_statics/core/*.py` — `analysis_services.py` (~251, ~492), `analysis_presenter.py` (~227-307: `zero_env`/`inertia_env` dicts; put the three new kwargs in `inertia_env` from `sc`, zeros in `zero_env`), `limit_auto_set.py`, `sweep.py`. Pass `vessel_roll_deg=sc.vessel_roll_deg`, `vessel_pitch_deg=sc.vessel_pitch_deg`, `crane_slewing_angle_deg=sc.crane_slewing_angle_deg` wherever the accelerations are passed (SceneState fields are added in Task 5; do both tasks before running the whole suite).

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_vessel_frame_engine.py tests/test_acceptance.py tests/test_pinned_support_moment.py tests/test_split_support_compensation.py -v`
Expected: PASS, including the legacy-regression test.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Drive engine loads from the crane-frame load vector; tilt loads payload and structure"
```

---

### Task 5: Scene state and defaults

**Files:**
- Modify: `src/crane_statics/core/session_model.py` (`SceneState` 18-33; `set_document` ~123-135)
- Modify: `src/crane_statics/qml_app/viewmodels/scene_vm.py`, `qml_app/qml/SceneControlRail.qml`, `qml_app/qml/EnvironmentPanel.qml`, `qml_app/contracts.py`, `qml_app/viewmodels/model_vm.py`, `presentation/formatters.py` (labels)
- Test: `tests/test_scene_view_model.py` (extend), `tests/test_app_view_model.py` (extend)

**Interfaces:**
- Produces: `SceneState.vessel_roll_deg`, `vessel_pitch_deg`, `crane_slewing_angle_deg` (floats, default 0.0). Accelerations in `SceneState` are now vessel-frame signed. `set_document` seeds all scene fields from `vessel_motion`.
- Consumes: runtime `VesselMotion` (Task 2).

- [ ] **Step 1: Write failing tests** — in `tests/test_scene_view_model.py`: setting the three new properties through the view model updates `SceneState`, emits the existing change signal and triggers re-analysis; negative accelerations are accepted (no clamping). In `tests/test_app_view_model.py`: loading a document whose `vessel_motion` has `roll_deg: 3`, `crane_slewing_angle_deg: 90`, `accel_x_m_s2: -1` seeds those values into every hoist's scene state. Follow the existing patterns in those files for fixture/signal assertions.

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_scene_view_model.py tests/test_app_view_model.py -v`; Expected: FAIL.

- [ ] **Step 3: Implement**
  - Add the three fields to `SceneState`; in `set_document` seed them with `float(vessel_motion.roll_deg)` etc. and drop any `abs()`.
  - View model: expose the three new properties the same way `accel_x` is exposed (read `scene_vm.py` to copy the property/setter/notify pattern and the QML-invokable setter); remove any clamping of accelerations to ≥ 0.
  - QML: add three numeric fields (Roll °, Pitch °, Slew °) to the vessel-motion group in `SceneControlRail.qml`, using the existing numeric-field component, `Metrics`/`Typography` tokens and label style (invoke the `qml-ui-development` skill before editing). Relabel the acceleration fields "Vessel ax/ay/az (excl. gravity)".
  - `EnvironmentPanel.qml`, `contracts.py`, `model_vm.py`, `formatters.py`: delete the wind exponent / reference height / mean sea level fields and labels; add the three angle defaults to the vessel-motion editing group if the panel lists `vessel_motion` keys (match how `accel_x_m_s2` appears there).

- [ ] **Step 4: Run to verify pass** — `pytest tests/test_scene_view_model.py tests/test_app_view_model.py tests/test_qml_shell.py tests/test_document_edit.py -v`; Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Add vessel roll, pitch and crane slewing angle to scene state and UI"
```

---

### Task 6: Remove the waterline from the scene

**Files:**
- Modify: `src/crane_statics/core/scene_frame.py` (`SceneWaterline` ~102, `waterline` field ~229, init ~260, `set_waterline` ~634, build ~688)
- Modify: `src/crane_statics/core/scene_build.py` (`_draw_waterline` ~728, call ~417, set ~442, comment ~411)
- Modify: `src/crane_statics/qml_app/adapters/scene_adapter.py` (~37, ~66)
- Modify: `src/crane_statics/qml_app/qml/scene/QuickSceneCanvas.qml` (~19-24, ~191-203, ~393-394)
- Test: `tests/test_scene_frame.py`, `tests/test_scene_adapters.py`

- [ ] **Step 1: Write failing tests** — in `tests/test_scene_frame.py` assert a built frame has no `waterline` attribute (`not hasattr(frame, "waterline")`) and the frame still fits the node pins; in `tests/test_scene_adapters.py` assert the adapted frame dict has no `"waterline"` key.

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_scene_frame.py tests/test_scene_adapters.py -v`; Expected: FAIL.

- [ ] **Step 3: Implement** — delete the items listed above. In `QuickSceneCanvas.qml` remove the `waterline` property, `mslLabelText`/`mslLabelY`, the two waterline items (fill + line) and the label item; confirm with `grep -n "waterline\|msl" ...QuickSceneCanvas.qml` that nothing references them. Update the fit-rect comment in `scene_build.py` (decorative extents no longer include the waterline fill). Update `qml_app/contracts.py` protocols if they list `waterline`. Use the `domain-boundary-reviewer` agent on this diff because it spans `core/` and `qml_app/`.

- [ ] **Step 4: Run to verify pass** — `pytest -q` (full suite); Expected: PASS.
Then run the app headlessly with the `run-app` skill and screenshot the Scene workspace to confirm no waterline and that the new fields appear.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Remove waterline from the scene"
```

---

### Task 7: Docs and final verification

**Files:**
- Modify: `CONTEXT-CORE.md`, `CONTEXT-EXTENDED.md` (scene-state definition line 21 of CONTEXT-CORE: add roll, pitch, slewing angle; add a "Vessel frame / crane frame" entry; remove sea level / wind profile terms)
- Modify: `docs/cpp-port-plan.md` (mentions of removed fields; add `vessel_frame` to the port list)
- Create: `docs/adr/0003-vessel-frame-load-acceleration.md` (decision: single transform producing an equivalent crane-frame acceleration; constant wind; exact signed inputs)

- [ ] **Step 1:** `grep -rniE "sea.?level|wind profile|power.?law|waterline" CONTEXT*.md docs README.md` and update or delete each hit.
- [ ] **Step 2:** Write the ADR (context, decision, consequences) in the style of `docs/adr/0002-*.md`.
- [ ] **Step 3:** Run the full verification: `pytest -q`, then `black --check`, `flake8` and `mypy` the same way the pre-commit hooks do.
- [ ] **Step 4:** Commit.

```bash
git add -A
git commit -m "Document vessel-frame load model"
```
