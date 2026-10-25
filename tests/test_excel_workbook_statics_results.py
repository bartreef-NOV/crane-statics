"""Excel workbook: the Statics solves and the in-plane Results rows."""

import dataclasses
import math
from pathlib import Path
from typing import Any, Callable

import pytest

from scripts.excel_workbook import layout
from scripts.excel_workbook.build import build_workbook
from scripts.excel_workbook.reference import CASES

from tests.excel_workbook_helpers import (
    INPLANE_REQUIRED,
    LAYOUT,
    LOAD_TOL,
    TIGHT,
    _Book,
    _app_inplane,
    _assert_book_clean,
    _assert_no_errors,
    _assert_oop_matches_engine,
    _assert_results_show_message,
    _assert_statics_match_solver,
    _collapse_rear_leg,
    _collapse_rear_leg_doc,
    _golden,
    _model,
    _solver_statics,
    _workbook_results,
)


@pytest.mark.parametrize("name", ["base", "inplane_wind_accel", "idle_hoist"])
def test_inplane_results_match_golden(case_book: Callable[[str], "_Book"], name: str) -> None:
    book = case_book(name)
    _assert_no_errors(book, layout.RESULTS)
    _assert_no_errors(book, layout.STATICS)
    got = _workbook_results(book, LAYOUT, _model())
    golden = _golden()["cases"][name]["app_results"]
    assert INPLANE_REQUIRED <= set(LAYOUT.result_rows)
    assert {k for k in golden if k.startswith("tension.")} == {
        k for k in got if k.startswith("tension.")
    }
    for key, value in got.items():
        assert key in golden, key
        assert math.isclose(value, golden[key], abs_tol=LOAD_TOL), (name, key, value, golden[key])
    assert book(LAYOUT.statics_cell("statics_status", "ok")) == 1
    assert book(LAYOUT.results_cell("results_status", "message")) == "OK"
    _assert_statics_match_solver(book, LAYOUT, _solver_statics(CASES[name]), name)
    _assert_book_clean(book, layout.OUT_OF_PLANE, layout.CHECKS)
    _assert_oop_matches_engine(book, LAYOUT, _model(), CASES[name], name)


def test_singular_matrix_sets_flag_not_errors(tmp_path: Path) -> None:
    # The app: is_ill_conditioned (|det| / prod(row norms) <= 1e-12) holds, so _run_statics
    # records the reason and returns {}, and there is no point.
    assert _solver_statics(CASES["base"], _collapse_rear_leg_doc) == {}
    assert _app_inplane(CASES["base"], _collapse_rear_leg_doc) is None
    model = _model()
    _collapse_rear_leg(model)
    path = tmp_path / "singular.xlsx"
    build_workbook(model, CASES["base"], path, TIGHT)
    book = _assert_results_show_message(path, TIGHT, "singular")
    assert book(TIGHT.statics_flag("leg_system")) == 1
    assert book(TIGHT.statics_flag("boom_system")) == 0
    assert book(TIGHT.check("singular_matrix")) == 1
    assert book(TIGHT.total_issues_addr) == 1


def test_no_solve_rope_shows_message(tmp_path: Path) -> None:
    def mutate(doc: dict[str, Any]) -> None:
        for rope in doc["ropes"]:
            rope["tension_mode"] = "fixed"

    assert _app_inplane(CASES["base"], mutate) is None
    model = _model()
    mutate(model)
    path = tmp_path / "no_solve.xlsx"
    build_workbook(model, CASES["base"], path, TIGHT)
    book = _assert_results_show_message(path, TIGHT, "solve rope")
    assert book(TIGHT.check("no_solve_rope")) == 1
    assert book(TIGHT.statics_flag("boom_system")) == 1


@pytest.mark.parametrize("name", ["inplane_wind_accel", "outofplane_wind_roll_sidelead"])
def test_spare_rows_do_not_change_results(tmp_path: Path, name: str) -> None:
    big = layout.Layout(
        layout.Capacities(mass_points=55, wind_areas=45, nodes=95, segments=70, ropes=11, hoists=12)
    )
    model = _model()
    got = {}
    for tag, lay in (("tight", TIGHT), ("big", big)):
        path = tmp_path / f"{tag}.xlsx"
        build_workbook(model, CASES[name], path, lay)
        book = _Book(path)
        _assert_book_clean(book, layout.OUT_OF_PLANE, layout.RESULTS, layout.CHECKS)
        got[tag] = _workbook_results(book, lay, model)
        got[tag].update({k: book(lay.statics_value(k)) for k in layout.STATICS_UNKNOWNS})
        for group in lay.oop.groups:
            for comp in ("mx", "mz"):
                got[tag][f"{group}.{comp}"] = book(lay.oop.moment(group, comp))
        for key in ("fy_kN", "mx_kNm"):
            got[tag][key] = book(lay.oop.cell("platform", key))
        assert book(lay.total_issues_addr) == 0
    assert set(got["tight"]) == set(got["big"])
    for key, value in got["tight"].items():
        assert math.isclose(value, got["big"][key], rel_tol=0.0, abs_tol=1e-9), key


def test_wind_zero_and_idle_hoist_zero_tension(tmp_path: Path) -> None:
    # Scene hoist with zero hook load, no wind, and an idle hoist (SH) whose rope has no
    # segment: the app reports MH = 0 and SH = its block weight over one part (not 0).
    case = dataclasses.replace(CASES["base"], hook_load_kN=0.0, wind_speed_m_s=0.0)

    def mutate(doc: dict[str, Any]) -> None:
        next(r for r in doc["ropes"] if r["id"] == "SH__rope")["segments"] = []

    want = _app_inplane(case, mutate)
    assert want is not None
    model = _model()
    mutate(model)
    path = tmp_path / "zero.xlsx"
    build_workbook(model, case, path, TIGHT)
    _assert_no_errors(path, layout.RESULTS)
    book = _Book(path)
    got = _workbook_results(book, TIGHT, model)
    assert got["tension.MH"] == 0 and want["tension.MH"] == 0
    assert want["tension.SH"] > 1.0
    assert set(got) == set(want)
    for key, value in want.items():
        assert math.isclose(got[key], value, abs_tol=LOAD_TOL), (key, got[key], value)
    _assert_statics_match_solver(book, TIGHT, _solver_statics(case, mutate), "zero")
