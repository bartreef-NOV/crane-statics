"""Excel workbook: the OutOfPlane sheet and the out-of-plane Results rows."""

import dataclasses
import math
from pathlib import Path
from typing import Callable

import pytest

from crane_statics.core.io import load_document
from scripts.excel_workbook import layout
from scripts.excel_workbook.build import build_workbook
from scripts.excel_workbook.reference import CASES, YAML_PATH

from tests.excel_workbook_helpers import (
    INPLANE_REQUIRED,
    LAYOUT,
    LOAD_TOL,
    OOP_REQUIRED,
    TIGHT,
    _Book,
    _app_inplane,
    _assert_book_clean,
    _assert_oop_matches_engine,
    _assert_statics_match_solver,
    _build_case,
    _golden,
    _model,
    _solver_statics,
    _workbook_results,
)


def test_outofplane_results_match_golden(case_book: Callable[[str], "_Book"]) -> None:
    name = "outofplane_wind_roll_sidelead"
    book = case_book(name)
    _assert_book_clean(book, layout.STATICS, layout.OUT_OF_PLANE, layout.RESULTS, layout.CHECKS)
    got = _workbook_results(book, LAYOUT, _model())
    golden = _golden()["cases"][name]["app_results"]
    assert INPLANE_REQUIRED | OOP_REQUIRED <= set(LAYOUT.result_rows)
    for key, value in got.items():
        assert key in golden, key
        assert math.isclose(value, golden[key], abs_tol=LOAD_TOL), (name, key, value, golden[key])
    # The case loads the left/right split and the platform out of plane.
    assert abs(got["reaction.heel_left.fz"] - got["reaction.heel_right.fz"]) > 1000.0
    assert abs(got["reaction.heel_left.fx"] - got["reaction.heel_right.fx"]) > 1000.0
    # Support reaction: the platform pushes back against the +Y wind, roll and sidelead.
    assert got["reaction.platform_base.fy"] < -100.0
    assert book(LAYOUT.results_cell("results_status", "message")) == "OK"
    assert book(LAYOUT.total_issues_addr) == 0
    _assert_statics_match_solver(book, LAYOUT, _solver_statics(CASES[name]), name)
    _assert_oop_matches_engine(book, LAYOUT, _model(), CASES[name], name)


def test_zero_boom_width_is_flagged(tmp_path: Path) -> None:
    from crane_statics.calculation.engine import CraneCalculator

    case = CASES["outofplane_wind_roll_sidelead"]
    # The app rejects a document with boom width 0; past validation the engine's split
    # raises and compute_analysis_point gives no point (no results at all).
    doc = load_document(YAML_PATH)
    doc.support_widths.boom_width_m = 0.0
    kwargs = dataclasses.asdict(case)
    hoist_id = kwargs.pop("hoist_id")
    angle, hook = kwargs.pop("boom_angle_deg"), kwargs.pop("hook_load_kN")
    assert CraneCalculator(doc).compute_analysis_point(angle, hook, hoist_id, **kwargs) is None

    model = _model()
    model["structure"]["boom_width_m"] = 0.0
    path = tmp_path / "zero_width.xlsx"
    build_workbook(model, case, path, TIGHT)
    book = _Book(path)
    _assert_book_clean(book, layout.OUT_OF_PLANE, layout.RESULTS, layout.CHECKS)
    assert book(TIGHT.check("zero_boom_width")) == 1
    assert book(TIGHT.total_issues_addr) == 1
    assert book(TIGHT.statics_cell("statics_status", "ok")) == 1
    message = book(TIGHT.results_cell("results_status", "message"))
    assert isinstance(message, str) and "boom width" in message.lower(), message
    for entity, component in TIGHT.result_rows:
        assert isinstance(book(TIGHT.result_cell(entity, component)), str), (entity, component)
    for i in range(1, len(model["hoists"]) + 1):
        assert isinstance(book(TIGHT.results_addr("tensions", "tension_kN", i)), str), i


@pytest.mark.parametrize("direction", ["+Y", "-Y"])
def test_wind_y_direction_signs(tmp_path: Path, direction: str) -> None:
    # Y wind alone: no motion, no sidelead; the platform Fy is the wind force.
    case = dataclasses.replace(CASES["base"], wind_speed_m_s=15.1, wind_direction=direction)
    path = _build_case(tmp_path, case)
    book = _Book(path)
    _assert_book_clean(book, layout.OUT_OF_PLANE, layout.RESULTS, layout.CHECKS)
    sign = 1.0 if direction == "+Y" else -1.0
    assert book(TIGHT.oop.cell("oop_scene", "wind_y_sign")) == sign
    for body in layout.BODIES:
        assert book(TIGHT.body_total(body, "wind_fx")) == 0
    want = _app_inplane(case)
    assert want is not None
    got = _workbook_results(book, TIGHT, _model())
    assert set(got) == set(want)
    for key, value in want.items():
        assert math.isclose(got[key], value, abs_tol=LOAD_TOL), (direction, key, got[key], value)
    # Support reactions oppose the wind: Fy against it, Mx = -(applied -z Fy) = +z Fy_wind.
    assert got["reaction.platform_base.fy"] * sign < -10.0
    assert got["reaction.platform_base.mx"] * sign > 100.0
    wind = sum(
        book(TIGHT.oop.addr("oop_winds", "fy_kN", i))
        for i in range(1, TIGHT.oop.tables["oop_winds"].capacity + 1)
    )
    assert math.isclose(wind, -got["reaction.platform_base.fy"], abs_tol=1e-9)
    _assert_oop_matches_engine(book, TIGHT, _model(), case, direction)


def test_blank_bearing_diameter_hides_bearing_rows(tmp_path: Path) -> None:
    from crane_statics.calculation.engine import CraneCalculator
    from crane_statics.core.demand_extraction import extract_connection_component_response

    case = CASES["outofplane_wind_roll_sidelead"]
    kwargs = dataclasses.asdict(case)
    hoist_id = kwargs.pop("hoist_id")
    angle, hook = kwargs.pop("boom_angle_deg"), kwargs.pop("hook_load_kN")
    calc = CraneCalculator(load_document(YAML_PATH))
    pt = calc.compute_analysis_point(angle, hook, hoist_id, **kwargs)
    bearing = ("max_bearing_line_load", "min_bearing_line_load")
    for comp in bearing:
        # The app drops the row when the document has no diameter.
        assert extract_connection_component_response(pt, hook, "platform_base", comp, None) is None

    model = _model()
    model["structure"]["slewing_bearing_diameter_m"] = None
    path = tmp_path / "no_diameter.xlsx"
    build_workbook(model, case, path, TIGHT)
    book = _Book(path)
    _assert_book_clean(book, layout.OUT_OF_PLANE, layout.RESULTS, layout.CHECKS)
    assert book(TIGHT.total_issues_addr) == 0
    for comp in bearing:
        value = book(TIGHT.result_cell("platform_base", comp))
        assert isinstance(value, str) and "diameter" in value, value
    golden = _golden()["cases"]["outofplane_wind_roll_sidelead"]["app_results"]
    for comp in ("fradial", "mradial", "fy", "mx"):
        got = book(TIGHT.result_cell("platform_base", comp))
        assert math.isclose(got, golden[f"reaction.platform_base.{comp}"], abs_tol=LOAD_TOL)
