"""Excel workbook: the Geometry sheet against the app's kinematics and vessel frame."""

import math
from pathlib import Path
from typing import Callable

import pytest

from crane_statics.calculation.rope_mass import active_hook_positions
from crane_statics.calculation.solver.kinematics import KinematicsAdapter
from crane_statics.calculation.vessel_frame import VesselInputs, crane_frame_motion
from crane_statics.core.io import load_document
from scripts.excel_workbook import layout
from scripts.excel_workbook.build import build_workbook
from scripts.excel_workbook.recalc import recalculate
from scripts.excel_workbook.reference import CASES, YAML_PATH

from tests.excel_workbook_helpers import CASE_NAMES, LAYOUT, _Book, _model


@pytest.mark.parametrize("name", sorted(CASE_NAMES))
def test_node_positions_match_kinematics(case_book: Callable[[str], "_Book"], name: str) -> None:
    case = CASES[name]
    book = case_book(name)
    doc = load_document(YAML_PATH).model_dump()
    expected = active_hook_positions(
        doc,
        case.hoist_id,
        KinematicsAdapter(doc).compute_all_node_positions(case.boom_angle_deg),
        case.tackle_length_m,
    )
    model = _model()
    assert len(model["nodes"]) == 29
    for i, node in enumerate(model["nodes"], start=1):
        assert book(LAYOUT.geo_addr("node_positions", "id", i)) == node["id"]
        assert book(LAYOUT.geo_addr("node_positions", "active", i)) == 1
        for axis in ("x", "z"):
            got = book(LAYOUT.geo_addr("node_positions", f"{axis}_m", i))
            want = expected[node["id"]][axis]
            assert math.isclose(got, want, rel_tol=0.0, abs_tol=1e-9), (name, node["id"], axis)


@pytest.mark.parametrize("name", sorted(CASE_NAMES))
def test_frame_motion_matches_vessel_frame(case_book: Callable[[str], "_Book"], name: str) -> None:
    case = CASES[name]
    book = case_book(name)
    model = _model()
    motion = crane_frame_motion(
        abs(model["environment"]["gravity_m_s2"]),
        VesselInputs(
            accel_x_m_s2=case.accel_x_m_s2,
            accel_y_m_s2=case.accel_y_m_s2,
            accel_z_m_s2=case.accel_z_m_s2,
            roll_deg=case.vessel_roll_deg,
            pitch_deg=case.vessel_pitch_deg,
            slew_deg=case.crane_slewing_angle_deg,
            roll_accel_rad_s2=case.roll_accel_rad_s2,
            pitch_accel_rad_s2=case.pitch_accel_rad_s2,
        ),
    )
    expected = {
        "gx": motion.gravity_crane[0],
        "gy": motion.gravity_crane[1],
        "gz": motion.gravity_crane[2],
        "ax": motion.accel_crane[0],
        "ay": motion.accel_crane[1],
        "az": motion.accel_crane[2],
        "kx": motion.load_accel[0],
        "ky": motion.load_accel[1],
        "kz": motion.load_accel[2],
        "solver_ax": motion.accel_x_m_s2,
        "solver_ay": motion.accel_y_m_s2,
        "solver_az": motion.accel_z_m_s2,
        "pitch_accel_crane": motion.pitch_accel_rad_s2,
        "roll_accel_crane": motion.roll_accel_rad_s2,
    }
    for key, want in expected.items():
        got = book(LAYOUT.geo_cell("frame_motion", key))
        assert math.isclose(got, want, rel_tol=0.0, abs_tol=1e-9), (name, key, got, want)
    # k = g - a holds in the crane frame.
    for axis in "xyz":
        k = book(LAYOUT.geo_cell("frame_motion", f"k{axis}"))
        g = book(LAYOUT.geo_cell("frame_motion", f"g{axis}"))
        a = book(LAYOUT.geo_cell("frame_motion", f"a{axis}"))
        assert math.isclose(k, g - a, abs_tol=1e-12)


def test_geometry_spare_rows_are_zero_without_errors(tmp_path: Path) -> None:
    lay = layout.Layout(layout.Capacities(nodes=40))
    path = tmp_path / "spare.xlsx"
    build_workbook(_model(), CASES["base"], path, lay)
    values = recalculate(path)["Geometry"]
    table = lay.geo_tables["node_positions"]
    for i in range(30, 41):
        for key in table.keys:
            sheet, coord = lay.geo_addr("node_positions", key, i).replace("$", "").split("!")
            got = values[coord]
            assert not (isinstance(got, str) and got.startswith("#")), (i, key, got)
            if key not in ("id", "frame"):
                assert got == 0, (i, key, got)
    for cell_values in values.values():
        assert not (isinstance(cell_values, str) and cell_values.startswith("#"))
    assert _Book(path)(lay.total_issues_addr) == 0
