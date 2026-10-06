"""Statics on a heeled/trimmed vessel: tilted gravity in the slewing crane frame.

Heel and trim rotate gravity; the crane's slew decides how much of that tilt
lies in the luffing plane (``lateral_x``) and how much across it
(``lateral_y``). The hook hangs plumb, so the hook load tilts with it.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from crane_statics.calculation.engine import CraneCalculator
from crane_statics.calculation.point_composition import with_crane_gravity
from crane_statics.calculation.vessel_attitude import VesselAttitude, crane_frame_gravity
from crane_statics.core import drawn_loads as dl
from crane_statics.core.io import load_document
from tests.test_acceptance import scene_inputs

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"
HEEL, TRIM = 3.0, 1.0
IN_PLANE_ENTITIES = ("heel_point", "rear_hinge", "front_hinge", "upper_hinge")
SPLIT_GROUPS = (
    ("heel_point", "heel_left", "heel_right"),
    ("front_hinge", "front_leg_left", "front_leg_right"),
    ("rear_hinge", "rear_leg_left", "rear_leg_right"),
)
QUIET: dict[str, Any] = dict(
    wind_speed_m_s=0.0,
    wind_direction="+X",
    accel_x_m_s2=0.0,
    accel_y_m_s2=0.0,
    accel_z_m_s2=0.0,
    pitch_accel_rad_s2=0.0,
    roll_accel_rad_s2=0.0,
    offlead_deg=0.0,
    sidelead_deg=0.0,
)


@pytest.fixture
def document():
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    return load_document(EXAMPLE)


def _tilted(doc, heel_deg: float = HEEL, trim_deg: float = TRIM):
    tilted = doc.model_copy(deep=True)
    tilted.environment.vessel_motion.heel_deg = heel_deg
    tilted.environment.vessel_motion.trim_deg = trim_deg
    return tilted


def _point(doc, *, angle: float = 45.0, hoist_id: str = "MH", **kwargs: Any):
    inputs = dict(QUIET)
    inputs.update(kwargs)
    point = CraneCalculator(doc).compute_analysis_point(angle, 0.0, hoist_id, **inputs)
    assert point is not None
    return point


def _gravity(slew_deg: float, heel_deg: float = HEEL, trim_deg: float = TRIM):
    return crane_frame_gravity(VesselAttitude(heel_deg, trim_deg), slew_deg)


def _assert_maps_close(actual: dict, expected: dict, path: str = "") -> None:
    assert set(actual) == set(expected), path
    for key, value in expected.items():
        if isinstance(value, dict):
            _assert_maps_close(actual[key], value, f"{path}.{key}")
        else:
            assert actual[key] == pytest.approx(value, rel=1e-9, abs=1e-6), f"{path}.{key}"


class TestWholeCraneBalance:
    @pytest.mark.parametrize("slew_deg", [0.0, 40.0, 135.0, 260.0])
    def test_ground_reaction_carries_the_tilted_weight_and_hook_load(self, document, slew_deg):
        weight_kN = _point(document).baseline_reactions["platform_base"]["Fz"]
        g = _gravity(slew_deg)

        point = _point(_tilted(document), slew_deg=slew_deg)
        base = point.baseline_reactions["platform_base"]
        sens = point.sensitivity_reactions["platform_base"]

        assert base["Fz"] == pytest.approx(weight_kN * g.vertical, rel=1e-9)
        assert base["Fx"] == pytest.approx(-weight_kN * g.lateral_x, rel=1e-9)
        assert base["Fy"] == pytest.approx(-weight_kN * g.lateral_y, rel=1e-9)
        assert sens["Fz"] == pytest.approx(g.vertical, rel=1e-9)
        assert sens["Fx"] == pytest.approx(-g.lateral_x, rel=1e-9)
        assert sens["Fy"] == pytest.approx(-g.lateral_y, rel=1e-9)

    def test_hook_lateral_adds_to_offlead(self, document):
        g = _gravity(70.0)
        offlead = 2.0

        point = _point(_tilted(document), slew_deg=70.0, offlead_deg=offlead)

        assert point.sensitivity_reactions["platform_base"]["Fx"] == pytest.approx(
            -(g.lateral_x + math.sin(math.radians(offlead))), rel=1e-9
        )


class TestTrimOverTheBowIsAnInPlaneAcceleration:
    def test_in_plane_baseline_matches_the_equivalent_acceleration(self, document):
        # Accelerations act on structure and rope only, so drop the idle hook blocks.
        for hoist in document.hoists:
            if hoist.id != "MH":
                hoist.hook_mass_t = 0.0
        g_abs = abs(float(document.environment.gravity_m_s2))
        theta = math.radians(4.0)

        tilted = _point(_tilted(document, 0.0, 4.0), slew_deg=0.0)
        accelerated = _point(
            document,
            accel_x_m_s2=-g_abs * math.sin(theta),
            accel_z_m_s2=-g_abs * (1.0 - math.cos(theta)),
        )

        assert tilted.baseline_rope_tensions["boom_hoist"] == pytest.approx(
            accelerated.baseline_rope_tensions["boom_hoist"], rel=1e-9
        )
        for entity in IN_PLANE_ENTITIES:
            for component in ("Fx", "Fz"):
                assert tilted.baseline_reactions[entity][component] == pytest.approx(
                    accelerated.baseline_reactions[entity][component], rel=1e-9, abs=1e-6
                ), f"{entity}.{component}"
        for component in ("Fx", "Fz", "My"):
            assert tilted.baseline_reactions["platform_base"][component] == pytest.approx(
                accelerated.baseline_reactions["platform_base"][component], rel=1e-9, abs=1e-6
            ), component


class TestSplitSupportsFollowTheTilt:
    @pytest.mark.parametrize("slew_deg", [0.0, 40.0, 200.0])
    def test_left_and_right_pins_sum_to_the_in_plane_total(self, document, slew_deg):
        point = _point(_tilted(document), slew_deg=slew_deg, offlead_deg=1.5, sidelead_deg=2.0)

        for maps in (point.baseline_reactions, point.sensitivity_reactions):
            for total, left, right in SPLIT_GROUPS:
                for component in ("Fx", "Fz"):
                    assert maps[left][component] + maps[right][component] == pytest.approx(
                        maps[total][component], rel=1e-9, abs=1e-6
                    ), f"{left}+{right} vs {total}.{component}"

    def test_mirroring_heel_and_slew_swaps_left_and_right(self, document):
        for body in document.bodies:
            for mass_point in body.mass_points:
                mass_point.y_m = 0.0
                if mass_point.local_y_m is not None:
                    mass_point.local_y_m = 0.0

        point = _point(_tilted(document, HEEL, TRIM), slew_deg=40.0)
        mirror = _point(_tilted(document, -HEEL, TRIM), slew_deg=320.0)

        for entity in IN_PLANE_ENTITIES:
            _assert_maps_close(mirror.baseline_reactions[entity], point.baseline_reactions[entity])
        for _total, left, right in SPLIT_GROUPS:
            _assert_maps_close(mirror.baseline_reactions[left], point.baseline_reactions[right])
            _assert_maps_close(
                mirror.sensitivity_reactions[left], point.sensitivity_reactions[right]
            )
        for maps_m, maps_p in (
            (mirror.baseline_reactions, point.baseline_reactions),
            (mirror.sensitivity_reactions, point.sensitivity_reactions),
        ):
            for component in ("Fy", "Mx"):
                assert maps_m["platform_base"][component] == pytest.approx(
                    -maps_p["platform_base"][component], rel=1e-9, abs=1e-6
                ), component


class TestComposition:
    def test_recomposing_to_another_slew_matches_a_direct_solve(self, document):
        tilted = _tilted(document)
        at_30 = _point(tilted, slew_deg=30.0, offlead_deg=1.0, sidelead_deg=2.0)
        at_210 = _point(tilted, slew_deg=210.0, offlead_deg=1.0, sidelead_deg=2.0)

        moved = with_crane_gravity(at_30, _gravity(210.0), slew_deg=210.0)

        assert moved.slew_deg == 210.0
        _assert_maps_close(moved.baseline_reactions, at_210.baseline_reactions)
        _assert_maps_close(moved.sensitivity_reactions, at_210.sensitivity_reactions)
        _assert_maps_close(moved.baseline_rope_tensions, at_210.baseline_rope_tensions)
        _assert_maps_close(moved.sensitivity_rope_tensions, at_210.sensitivity_rope_tensions)

    def test_composing_does_not_mutate_the_source_point(self, document):
        at_30 = _point(_tilted(document), slew_deg=30.0)
        before = at_30.baseline_reactions["heel_left"]["Fz"]

        with_crane_gravity(at_30, _gravity(120.0), slew_deg=120.0)

        assert at_30.baseline_reactions["heel_left"]["Fz"] == before

    def test_slew_has_no_effect_on_a_level_vessel(self, document):
        at_0 = _point(document, slew_deg=0.0)
        at_123 = _point(document, slew_deg=123.0)

        assert at_123.baseline_reactions == at_0.baseline_reactions
        assert at_123.sensitivity_reactions == at_0.sensitivity_reactions


class TestDrawnLoadsBalanceTheTiltedSolve:
    @pytest.mark.parametrize("slew_deg", [0.0, 75.0, 200.0])
    @pytest.mark.parametrize("hook_load_kN", [0.0, 5000.0])
    def test_every_free_body_closes(self, document, slew_deg, hook_load_kN):
        tilted = _tilted(document)
        tackle_m = 40.0
        point = CraneCalculator(tilted).compute_analysis_point(
            45.0, 0.0, "MH", tackle_length_m=tackle_m, slew_deg=slew_deg, **QUIET
        )
        assert point is not None
        conditions = {
            key: value
            for key, value in QUIET.items()
            if key not in {"accel_y_m_s2", "roll_accel_rad_s2", "sidelead_deg"}
        }
        inputs = scene_inputs(
            tilted,
            "MH",
            angle=45.0,
            analysis_point=point,
            tackle_length_m=tackle_m,
            hook_load_kN=hook_load_kN,
            slew_deg=slew_deg,
            **conditions,
        )
        positions = inputs.node_positions()
        refs = {
            "platform": "platform_base",
            "boom": "boom_heel",
            "rear_leg": "rear_base",
            "front_leg": "front_base",
        }
        for body, ref_node in refs.items():
            loads = inputs.body_loads(positions, body)
            vectors = loads.vectors(
                dl.GRAVITY,
                dl.ROPE_WEIGHT,
                dl.IDLE_HOOK_MASS,
                dl.HOOK_LOAD,
                dl.ROPE_INTERFACE,
                dl.REACTIONS,
            )
            sum_fx = sum(v.fx_kN for v in vectors)
            sum_fz = sum(v.fz_kN for v in vectors)
            x0, z0 = float(positions[ref_node]["x"]), float(positions[ref_node]["z"])
            sum_m = dl.sum_moment_about(vectors, loads.moments, x0, z0)

            assert abs(sum_fx) <= 1e-6, body
            assert abs(sum_fz) <= 1e-6, body
            assert abs(sum_m) <= 1e-5, body


def _scene_services(doc, **scene_state: Any):
    from crane_statics.core.analysis_presenter import AnalysisPresenter
    from crane_statics.core.analysis_services import (
        AnalysisCalculator,
        HoistStateService,
        KinematicsService,
    )
    from crane_statics.core.session_model import SessionModel

    session = SessionModel()
    session.set_document(doc)
    session.select_payload_hoist("MH")
    state = session.get_active_hoist_state()
    assert state is not None
    state.scene_state.boom_angle_deg = 45.0
    state.scene_state.tackle_length_m = 40.0
    for key, value in scene_state.items():
        setattr(state.scene_state, key, value)
    hoist_svc = HoistStateService(session)
    calculator = AnalysisCalculator(session, KinematicsService(session), hoist_svc)
    return calculator, AnalysisPresenter(session, calculator, hoist_svc)


class TestSceneAnalysisUsesTheSlew:
    def test_scene_state_starts_over_the_bow(self):
        from crane_statics.core.session_model import SceneState

        assert SceneState().slew_deg == 0.0

    def test_scene_point_is_solved_at_the_scene_slew(self, document):
        tilted = _tilted(document)
        calculator, _ = _scene_services(tilted, slew_deg=75.0)

        point = calculator.compute_analysis_point()

        assert point is not None
        assert point.slew_deg == 75.0
        assert point.crane_gravity == _gravity(75.0)

    def test_auto_load_follows_the_scene_slew(self, document):
        tilted = _tilted(document, heel_deg=5.0, trim_deg=0.0)
        over_bow, _ = _scene_services(tilted, slew_deg=0.0)
        over_side, _ = _scene_services(tilted, slew_deg=90.0)

        bow = over_bow.compute_auto_load()
        side = over_side.compute_auto_load()

        assert bow is not None and side is not None
        assert side.max_allowable_load_kN != pytest.approx(bow.max_allowable_load_kN)

    def test_contribution_overview_reconstructs_a_tilted_demand(self, document):
        tilted = _tilted(document)
        _, presenter = _scene_services(tilted, slew_deg=75.0, hook_load_kN=5000.0)
        row = {"kind": "connection", "entity_id": "heel_point", "component": "Fx"}

        overview = presenter.build_load_contribution_overview(row)

        assert overview is not None
        names = [term["name"] for term in overview["terms"]]
        assert "Vessel attitude" in names
        assert overview["delta_kN"] == pytest.approx(0.0, abs=1e-6)

    def test_contribution_overview_omits_the_attitude_term_when_level(self, document):
        _, presenter = _scene_services(document, hook_load_kN=5000.0)
        row = {"kind": "connection", "entity_id": "heel_point", "component": "Fx"}

        overview = presenter.build_load_contribution_overview(row)

        assert overview is not None
        assert "Vessel attitude" not in [term["name"] for term in overview["terms"]]


class TestDrawnLoadsFollowTheAnalysisPoint:
    def test_weights_are_drawn_at_the_slew_the_reactions_were_solved_at(self, document):
        tilted = _tilted(document)
        point = CraneCalculator(tilted).compute_analysis_point(
            45.0, 0.0, "MH", tackle_length_m=40.0, slew_deg=75.0, **QUIET
        )
        assert point is not None
        conditions = {
            key: value
            for key, value in QUIET.items()
            if key not in {"accel_y_m_s2", "roll_accel_rad_s2", "sidelead_deg"}
        }
        # The conditions name a different slew; the solved point is the authority.
        inputs = scene_inputs(
            tilted, "MH", angle=45.0, analysis_point=point, tackle_length_m=40.0, **conditions
        )
        positions = inputs.node_positions()
        loads = inputs.body_loads(positions, "boom")
        vectors = loads.vectors(
            dl.GRAVITY, dl.ROPE_WEIGHT, dl.IDLE_HOOK_MASS, dl.ROPE_INTERFACE, dl.REACTIONS
        )

        assert abs(sum(v.fx_kN for v in vectors)) <= 1e-6
        assert abs(sum(v.fz_kN for v in vectors)) <= 1e-6
