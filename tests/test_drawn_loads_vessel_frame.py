"""Drawn loads follow the crane-frame load vector the solver applies.

Gravity arrows show the tilted crane-frame gravity ``m*g_c``; the Inertia category carries
only the vessel accelerations ``-m*a_c`` rotated into the crane frame
(``calculation.vessel_frame.crane_frame_motion``), so Gravity + Inertia = m*k_c in plane --
exactly the load the solver applies to every mass, including idle hook blocks and the
split-block support mass.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from crane_statics.core import drawn_loads as dl
from crane_statics.core import load_document
from tests.test_acceptance import SceneHarness

EXAMPLES = Path(__file__).parent.parent / "examples"
EXAMPLE_NAMES = ("crane_input_22689", "crane_input_13778_retracted", "crane_input_GT283")
G = 9.81  # every example document authors gravity_m_s2 = 9.81

TILTED_SLEWED = dict(
    vessel_pitch_deg=8.0,
    vessel_roll_deg=5.0,
    crane_slewing_angle_deg=30.0,
    accel_x_m_s2=0.4,
    accel_z_m_s2=0.3,
)
WITH_ANGULAR = dict(TILTED_SLEWED, pitch_accel_rad_s2=0.02, roll_accel_rad_s2=-0.015)


def _harness(name: str, hoist_id: str | None = None, **scene) -> SceneHarness:
    doc = load_document(EXAMPLES / f"{name}.yaml")
    harness = SceneHarness(doc, hoist_id or doc.hoists[0].id)
    harness.apply(boom_angle_deg=45.0, **scene)
    return harness


def _failing(report: dict) -> list[str]:
    return [s["message"] for s in report["sections"] if not s["passed"]]


@pytest.mark.parametrize("scene", [TILTED_SLEWED, WITH_ANGULAR], ids=["tilt-slew", "angular"])
@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_equilibrium_check_passes_with_tilt_and_slew(name: str, scene: dict) -> None:
    report = _harness(name, **scene).report()
    assert report["available"] is True
    assert report["passed"] is True, (name, _failing(report))


@pytest.mark.parametrize("name", ("crane_input_22689", "crane_input_13778_retracted"))
def test_equilibrium_check_passes_with_tilt_in_split_mode(name: str) -> None:
    """The split-block support mass feels the tilt too."""
    harness = _harness(name, "MH")
    harness.vm.setHookMode("split")
    assert harness.state.split_mode_active is True
    harness.apply(**WITH_ANGULAR)
    report = harness.report()
    assert report["passed"] is True, (name, _failing(report))


def test_pitch_ten_degrees_tilts_gravity_plus_inertia() -> None:
    """Whole crane, only vessel_pitch_deg = 10: Gravity + Inertia + Idle hook = M*k_c.

    M is read from the GT283 YAML: body mass points 770.5 t plus the idle AH (7.0 t) and
    trolley (7.7 t) hook blocks; the active MH hook block (50 t) is part of the hook load
    and is excluded. k_c = (g sin10, -g cos10) for a bow-down pitch of 10 deg.
    """
    harness = _harness("crane_input_GT283", "MH", vessel_pitch_deg=10.0)
    doc_dict = harness.inputs.document_dict
    assert doc_dict is not None
    mass_points_t = sum(
        float(mp.get("mass_t", 0.0)) for body in doc_dict["bodies"] for mp in body["mass_points"]
    )
    assert mass_points_t == pytest.approx(770.5, abs=1e-9)
    total_t = 770.5 + 7.0 + 7.7

    loads = harness.loads("none")
    vectors = loads.vectors(dl.GRAVITY, dl.INERTIA, dl.IDLE_HOOK_MASS)
    sum_fx = sum(v.fx_kN for v in vectors)
    sum_fz = sum(v.fz_kN for v in vectors)
    beta = math.radians(10.0)
    assert sum_fx == pytest.approx(total_t * G * math.sin(beta), rel=1e-9)  # 1337.57 kN
    assert sum_fz == pytest.approx(-total_t * G * math.cos(beta), rel=1e-9)  # -7585.64 kN

    # The tilt lives in the Gravity arrows; a pure tilt draws no Inertia.
    assert loads.category(dl.INERTIA) == ()
    gravity = loads.vectors(dl.GRAVITY, dl.IDLE_HOOK_MASS)
    assert sum(v.fx_kN for v in gravity) == pytest.approx(total_t * G * math.sin(beta), rel=1e-9)
    assert sum(v.fz_kN for v in gravity) == pytest.approx(-total_t * G * math.cos(beta), rel=1e-9)

    # Rope self-weight carries its own gravity + inertia: tilted by the same 10 deg.
    rope = loads.vectors(dl.ROPE_WEIGHT)
    assert rope
    rope_fx = sum(v.fx_kN for v in rope)
    rope_fz = sum(v.fz_kN for v in rope)
    assert rope_fx / -rope_fz == pytest.approx(math.tan(beta), rel=1e-9)


def test_idle_hook_blocks_carry_inertia() -> None:
    """Level vessel, accel_x = 1: each idle hook block gets an Inertia arrow -m*ax."""
    harness = _harness("crane_input_GT283", "MH", accel_x_m_s2=1.0)
    loads = harness.loads("none")
    positions = harness.inputs.node_positions()
    doc_dict = harness.inputs.document_dict
    assert doc_dict is not None
    by_id = {h["id"]: h for h in doc_dict["hoists"]}
    inertia = loads.category(dl.INERTIA)
    for hoist_id, mass_t in (("AH", 7.0), ("trolley", 7.7)):
        node = positions[by_id[hoist_id]["load_node_id"]]
        at_hook = [
            v
            for v in inertia
            if v.world_x == pytest.approx(node["x"]) and v.world_z == pytest.approx(node["z"])
        ]
        assert [v.fx_kN for v in at_hook] == [pytest.approx(-mass_t)], hoist_id
        assert at_hook[0].fz_kN == pytest.approx(0.0, abs=1e-12)
    active_node = positions[by_id["MH"]["load_node_id"]]
    assert not [
        v
        for v in inertia
        if v.world_x == pytest.approx(active_node["x"])
        and v.world_z == pytest.approx(active_node["z"])
    ]


def test_conditions_carry_tilted_gravity_and_vessel_accelerations() -> None:
    """Pitch 10 deg, no accelerations: g_c = (g sin10, -g cos10), a_c = 0 (hand values)."""
    harness = _harness("crane_input_GT283", "MH", vessel_pitch_deg=10.0)
    conditions = harness.inputs.conditions
    beta = math.radians(10.0)
    assert conditions.gravity_x_m_s2 == pytest.approx(G * math.sin(beta), rel=1e-12)
    assert conditions.gravity_z_m_s2 == pytest.approx(-G * math.cos(beta), rel=1e-12)
    assert conditions.accel_x_m_s2 == 0.0
    assert conditions.accel_z_m_s2 == 0.0
    assert conditions.pitch_accel_rad_s2 == 0.0


GT283_MASS_POINTS_T = 770.5
GT283_TOTAL_T = 770.5 + 7.0 + 7.7  # mass points + idle AH and trolley hook blocks


def _sums(vectors) -> tuple[float, float]:
    return sum(v.fx_kN for v in vectors), sum(v.fz_kN for v in vectors)


def test_pure_pitch_draws_tilted_gravity_and_no_inertia() -> None:
    loads = _harness("crane_input_GT283", "MH", vessel_pitch_deg=10.0).loads("none")
    beta = math.radians(10.0)
    inertia_fx, inertia_fz = _sums(loads.category(dl.INERTIA))
    assert inertia_fx == pytest.approx(0.0, abs=1e-9)
    assert inertia_fz == pytest.approx(0.0, abs=1e-9)
    fx, fz = _sums(loads.category(dl.GRAVITY))
    assert fx == pytest.approx(GT283_MASS_POINTS_T * G * math.sin(beta), rel=1e-9)  # 1312.5
    assert fz == pytest.approx(-GT283_MASS_POINTS_T * G * math.cos(beta), rel=1e-9)  # -7443.7
    fx, fz = _sums(loads.vectors(dl.GRAVITY, dl.IDLE_HOOK_MASS))
    assert fx == pytest.approx(GT283_TOTAL_T * G * math.sin(beta), rel=1e-9)  # 1337.57
    assert fz == pytest.approx(-GT283_TOTAL_T * G * math.cos(beta), rel=1e-9)  # -7585.64


def test_pitch_with_slew_ninety_draws_no_out_of_plane_gravity() -> None:
    """Slew 90: the pitch's forward gravity component points along crane -y, not drawn."""
    loads = _harness(
        "crane_input_GT283", "MH", vessel_pitch_deg=10.0, crane_slewing_angle_deg=90.0
    ).loads("none")
    beta = math.radians(10.0)
    fx, fz = _sums(loads.vectors(dl.GRAVITY, dl.IDLE_HOOK_MASS))
    assert fx == pytest.approx(0.0, abs=1e-9)
    assert fz == pytest.approx(-GT283_TOTAL_T * G * math.cos(beta), rel=1e-9)
    assert _sums(loads.category(dl.INERTIA)) == pytest.approx((0.0, 0.0), abs=1e-9)


def test_level_surge_keeps_nominal_gravity_and_draws_vessel_inertia() -> None:
    loads = _harness("crane_input_GT283", "MH", accel_x_m_s2=0.4).loads("none")
    fx, fz = _sums(loads.vectors(dl.GRAVITY, dl.IDLE_HOOK_MASS))
    assert fx == 0.0
    assert fz == pytest.approx(-GT283_TOTAL_T * G, rel=1e-12)
    fx, fz = _sums(loads.category(dl.INERTIA))
    assert fx == pytest.approx(-GT283_TOTAL_T * 0.4, rel=1e-9)  # -314.08 kN
    assert fz == pytest.approx(0.0, abs=1e-9)


def test_surge_at_slew_ninety_leaves_the_plane() -> None:
    loads = _harness(
        "crane_input_GT283", "MH", accel_x_m_s2=0.4, crane_slewing_angle_deg=90.0
    ).loads("none")
    fx, fz = _sums(loads.category(dl.INERTIA))
    assert fx == pytest.approx(0.0, abs=1e-9)
    assert fz == pytest.approx(0.0, abs=1e-9)


def test_slew_ninety_swaps_roll_accel_into_pitch() -> None:
    """Slew 90: vessel roll accel 0.1 -> crane pitch accel -0.1; vessel ax 1 leaves X-Z."""
    harness = _harness(
        "crane_input_GT283",
        "MH",
        crane_slewing_angle_deg=90.0,
        roll_accel_rad_s2=0.1,
        accel_x_m_s2=1.0,
    )
    conditions = harness.inputs.conditions
    assert conditions.pitch_accel_rad_s2 == pytest.approx(-0.1, abs=1e-12)
    assert conditions.accel_x_m_s2 == pytest.approx(0.0, abs=1e-12)
    assert conditions.accel_z_m_s2 == pytest.approx(0.0, abs=1e-12)


def test_level_unslewed_conditions_keep_the_raw_accelerations() -> None:
    harness = _harness(
        "crane_input_GT283", "MH", accel_x_m_s2=0.4, accel_z_m_s2=0.3, pitch_accel_rad_s2=0.02
    )
    conditions = harness.inputs.conditions
    # (-g - (-g - az)) may round in the last bit; the engine resolves the same way.
    assert conditions.accel_x_m_s2 == pytest.approx(0.4, rel=1e-14)
    assert conditions.accel_z_m_s2 == pytest.approx(0.3, rel=1e-14)
    assert conditions.pitch_accel_rad_s2 == pytest.approx(0.02, rel=1e-14)
