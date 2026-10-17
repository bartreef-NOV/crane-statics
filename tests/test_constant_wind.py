from pathlib import Path

import pytest

from crane_statics.calculation.engine import AnalysisPoint, CraneCalculator
from crane_statics.calculation.solver import crane_solver
from crane_statics.calculation.solver.kinematics import KinematicsAdapter
from crane_statics.core import load_document
from crane_statics.data.models import WindArea

EXAMPLES = Path(__file__).parent.parent / "examples"
EXPECTED = (
    0.5
    * load_document(EXAMPLES / "crane_input_GT283.yaml").environment.air_density_kg_m3
    * 1.2
    * 10.0
    * 20.0**2
    / 1000.0
)


def _doc_with_wind_at(z_m: float):
    doc = load_document(EXAMPLES / "crane_input_GT283.yaml")
    for body in doc.bodies:
        body.wind_areas = []
        if body.id == "rear_leg":
            body.wind_areas = [
                WindArea(id="w", area_w_m2=10.0, area_v_m2=10.0, cd=1.2, x_m=0.0, z_m=z_m)
            ]
    return doc


def _wind_fx_total(z_m: float) -> float:
    doc = _doc_with_wind_at(z_m)
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
    return float(sum(windy[b]["Fx"] - calm[b]["Fx"] for b in windy))


def _wind_fy_total(z_m: float) -> float:
    calc = CraneCalculator(_doc_with_wind_at(z_m))
    point = AnalysisPoint(
        boom_angle_deg=45.0,
        outreach_m=0.0,
        baseline_rope_tensions={},
        baseline_reactions={},
        sensitivity_rope_tensions={},
        sensitivity_reactions={},
    )

    def _fy(wind: float) -> float:
        return calc._build_out_of_plane_reactions(point, "MH", 45.0, 0.0, wind, 0.0, 0.0, 0.0)[2]

    return _fy(20.0) - _fy(0.0)


def test_wind_force_is_independent_of_height():
    assert _wind_fx_total(10.0) == pytest.approx(EXPECTED)
    assert _wind_fx_total(60.0) == pytest.approx(EXPECTED)


def test_lateral_wind_force_is_independent_of_height():
    assert _wind_fy_total(10.0) == pytest.approx(EXPECTED)
    assert _wind_fy_total(60.0) == pytest.approx(EXPECTED)
