"""Excel workbook: the Loads sheet against the app's solver and drawn loads."""

import math
from pathlib import Path
from typing import Any, Callable

import pytest

from crane_statics.calculation.rope_mass import rope_mass_at_nodes
from scripts.excel_workbook import layout
from scripts.excel_workbook.build import build_workbook
from scripts.excel_workbook.reference import CASES, YAML_PATH, app_results

from tests.excel_workbook_helpers import (
    LAYOUT,
    LOAD_TOL,
    TIGHT,
    _Book,
    _assert_body_totals_match_solver,
    _assert_no_errors,
    _build,
    _build_case,
    _drawn_category_sums,
    _model,
    _rename_node,
    _solver_loads,
    _wind_case,
)


@pytest.mark.parametrize("name", ["base", "inplane_wind_accel", "idle_hoist"])
def test_total_loads_match_drawn_loads(case_book: Callable[[str], "_Book"], name: str) -> None:
    case = CASES[name]
    book = case_book(name)
    drawn, t_bh = _drawn_category_sums(case)
    for body in layout.BODIES:
        known = {"fx": 0.0, "fz": 0.0, "m": 0.0}
        for cat in layout.LOAD_CATEGORIES:
            for comp in ("fx", "fz", "m"):
                got = book(LAYOUT.body_total(body, f"{cat}_{comp}"))
                want = drawn[body][cat][comp]
                if cat == "rope":
                    # The Scene draws the solved boom-hoist tension too; the workbook
                    # lists it as coefficients (bh_*) for Statics.
                    got += t_bh * book(LAYOUT.body_total(body, f"bh_{comp}"))
                assert math.isclose(got, want, abs_tol=LOAD_TOL), (name, body, cat, comp)
                known[comp] += book(LAYOUT.body_total(body, f"{cat}_{comp}"))
        for comp in ("fx", "fz", "m"):
            assert math.isclose(book(LAYOUT.body_total(body, comp)), known[comp], abs_tol=1e-6)
    ld, bh, _ = _solver_loads(case)
    _assert_body_totals_match_solver(book, LAYOUT, ld, bh, name)
    # Rope tensions of the fixed ropes are the Scene's rope rows.
    results = app_results(YAML_PATH, case)
    for i, hoist in enumerate(_model()["hoists"], start=1):
        row = next(
            k for k, r in enumerate(_model()["ropes"], start=1) if r["id"] == hoist["rope_id"]
        )
        got = book(LAYOUT.loads_addr("rope_tensions", "tension_kN", row))
        want = 0.0 if hoist["id"] == "BH" else results[f"tension.{hoist['id']}"]
        assert math.isclose(got, want, abs_tol=1e-9), (name, hoist["id"])


@pytest.mark.parametrize("name", ["base", "idle_hoist"])
def test_rope_weight_reeved_and_spooled(tmp_path: Path, name: str) -> None:
    case = CASES[name]
    # The spool node is found by its flag, not by "winch" in its id: rename one drum.
    model = _model()
    _rename_node(model, "mh_winch", "mh_drum")
    book = _Book(_build(tmp_path, model, case=name))
    _ld, _bh, app = _solver_loads(case)
    expected = rope_mass_at_nodes(app["doc"], app["positions"])
    seen = set()
    for i, node in enumerate(model["nodes"], start=1):
        app_id = "mh_winch" if node["id"] == "mh_drum" else node["id"]
        entry = expected.get(app_id)
        for key in ("reeved_t", "spooled_t"):
            got = book(LAYOUT.loads_addr("node_loads", key, i))
            want = 0.0 if entry is None else getattr(entry, key)
            assert math.isclose(got, want, abs_tol=1e-9), (name, node["id"], key, got, want)
        if entry is not None:
            seen.add(app_id)
    assert seen == set(expected)
    assert expected["mh_winch"].spooled_t > 1.0
    assert book(LAYOUT.loads_addr("hoist_ropes", "spool_node_id", 1)) == "mh_drum"


def test_wind_zero_speed_gives_zero(tmp_path: Path) -> None:
    case = _wind_case("+X", 0.0)
    path = _build_case(tmp_path, case)
    _assert_no_errors(path)
    book = _Book(path)
    for i in range(1, TIGHT.loads_tables["wind_loads"].capacity + 1):
        assert book(TIGHT.loads_addr("wind_loads", "fx", i)) == 0
    for body in layout.BODIES:
        for comp in ("fx", "fz", "m"):
            assert book(TIGHT.body_total(body, f"wind_{comp}")) == 0
    ld, bh, _ = _solver_loads(case)
    _assert_body_totals_match_solver(book, TIGHT, ld, bh, "zero wind")


@pytest.mark.parametrize("direction", ["+X", "-X", "+Y", "-Y"])
def test_wind_direction_signs(tmp_path: Path, direction: str) -> None:
    case = _wind_case(direction)
    book = _Book(_build_case(tmp_path, case))
    drawn, _t_bh = _drawn_category_sums(case)
    sign = {"+X": 1.0, "-X": -1.0}.get(direction, 0.0)
    assert book(TIGHT.loads_cell("load_scene", "wind_sign")) == sign
    for body in layout.BODIES:
        for comp in ("fx", "fz", "m"):
            got = book(TIGHT.body_total(body, f"wind_{comp}"))
            assert math.isclose(got, drawn[body]["wind"][comp], abs_tol=LOAD_TOL), (body, comp)
    boom_fx = book(TIGHT.body_total("boom", "wind_fx"))
    platform_fx = book(TIGHT.body_total("platform", "wind_fx"))
    if sign:
        assert boom_fx * sign > 1.0 and platform_fx * sign > 1.0
    else:
        assert boom_fx == 0 and platform_fx == 0
    ld, bh, _ = _solver_loads(case)
    _assert_body_totals_match_solver(book, TIGHT, ld, bh, direction)


def test_loads_spare_rows_are_zero_without_errors(case_book: Callable[[str], "_Book"]) -> None:
    book = case_book("base")
    values = _assert_no_errors(book)
    model = _model()
    used = {
        "mass_loads": sum(len(b["mass_points"]) for b in model["bodies"]),
        "wind_loads": sum(len(b["wind_areas"]) for b in model["bodies"]),
        "rope_tensions": len(model["ropes"]),
        "hoist_ropes": len(model["hoists"]),
        "segment_loads": sum(len(r["segments"]) for r in model["ropes"]),
        "node_loads": len(model["nodes"]),
    }
    for name, n_used in used.items():
        table = LAYOUT.loads_tables[name]
        assert table.capacity > n_used, name
        for i in range(n_used + 1, table.capacity + 1):
            for f in table.fields:
                got = values[LAYOUT.loads_addr(name, f.key, i).replace("$", "").split("!")[1]]
                if f.kind == "text":
                    assert got is None, (name, i, f.key, got)
                else:
                    assert got == 0, (name, i, f.key, got)
    assert book(LAYOUT.total_issues_addr) == 0


def test_zero_length_segment_and_hoist_without_segments(tmp_path: Path) -> None:
    def mutate(doc: dict[str, Any]) -> None:
        ropes = {r["id"]: r for r in doc["ropes"]}
        ropes["SH__rope"]["segments"] = []
        seg = ropes["WH__rope"]["segments"][3]
        seg["to_node_id"] = seg["from_node_id"]

    model = _model()
    mutate(model)
    case = CASES["base"]
    path = tmp_path / "zero.xlsx"
    build_workbook(model, case, path, TIGHT)
    _assert_no_errors(path)
    book = _Book(path)
    assert book(TIGHT.check("hoist_without_segments")) == 1
    seg_row = 1 + sum(len(r["segments"]) for r in model["ropes"][:1]) + 3
    assert model["ropes"][1]["id"] == "WH__rope"
    for key in ("length_m", "ux", "uz", "fx", "fz", "half_mass_t"):
        assert book(TIGHT.loads_addr("segment_loads", key, seg_row)) == 0, key
    sh_row = next(i for i, h in enumerate(model["hoists"], start=1) if h["id"] == "SH")
    for key in ("reeved_m", "spooled_m", "spooled_t"):
        assert book(TIGHT.loads_addr("hoist_ropes", key, sh_row)) == 0, key
    ld, bh, _ = _solver_loads(case, mutate)
    _assert_body_totals_match_solver(book, TIGHT, ld, bh, "zero-length")
