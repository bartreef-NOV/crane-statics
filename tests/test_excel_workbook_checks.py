"""Excel workbook: the Checks sheet counts input problems."""

from pathlib import Path

from openpyxl import load_workbook

from tests.excel_workbook_helpers import LAYOUT, _Book, _build, _model


def test_overflow_check_trips(tmp_path: Path) -> None:
    model = _model()
    capacity = LAYOUT.tables["segments"].capacity
    extra = capacity + 1 - sum(len(r["segments"]) for r in model["ropes"])
    seg = model["ropes"][0]["segments"][0]
    model["ropes"][0]["segments"].extend(dict(seg) for _ in range(extra))
    path = _build(tmp_path, model)
    book = _Book(path)
    assert book(LAYOUT.tables["segments"].overflow_addr) == 1
    assert book(LAYOUT.check("overflow")) == 1
    assert book(LAYOUT.total_issues_addr) > 0
    assert book(LAYOUT.addr("segments", "active", capacity)) == 1


def test_overflow_check_counts_rows_typed_below_a_table(tmp_path: Path) -> None:
    path = _build(tmp_path)
    wb = load_workbook(path)
    sheet, coord = LAYOUT.tables["nodes"].guard_addr("id").replace("$", "").split("!")
    wb[sheet][coord] = "typed_below_the_table"
    wb.save(path)
    assert _Book(path)(LAYOUT.check("overflow")) == 1


def test_duplicate_id_check(tmp_path: Path) -> None:
    model = _model()
    model["nodes"].append(dict(model["nodes"][3]))
    assert _Book(_build(tmp_path, model))(LAYOUT.check("duplicate_ids")) > 0


def test_missing_node_reference_check(tmp_path: Path) -> None:
    model = _model()
    model["ropes"][0]["segments"][0]["to_node_id"] = "no_such_node"
    assert _Book(_build(tmp_path, model))(LAYOUT.check("node_references")) == 1


def test_inactive_node_reference_check(tmp_path: Path) -> None:
    path = _build(tmp_path)
    ids = [n["id"] for n in _model()["nodes"]]
    wb = load_workbook(path)
    row = ids.index("mh_aframe_sheave_1") + 1
    sheet, coord = LAYOUT.addr("nodes", "active", row).replace("$", "").split("!")
    wb[sheet][coord] = 0
    wb.save(path)
    # Two MH segments touch the deactivated sheave.
    assert _Book(path)(LAYOUT.check("node_references")) == 2


def test_two_solve_ropes_check(tmp_path: Path) -> None:
    model = _model()
    next(r for r in model["ropes"] if r["id"] == "MH__rope")["tension_mode"] = "solve"
    book = _Book(_build(tmp_path, model))
    assert book(LAYOUT.check("multiple_solve_ropes")) == 1
    assert book(LAYOUT.check("no_solve_rope")) == 0


def test_hoist_rope_without_active_segments_check(tmp_path: Path) -> None:
    model = _model()
    next(r for r in model["ropes"] if r["id"] == "SH__rope")["segments"] = []
    assert _Book(_build(tmp_path, model))(LAYOUT.check("hoist_without_segments")) == 1


def test_hanging_chain_check(tmp_path: Path) -> None:
    model = _model()
    parent = next(n for n in model["nodes"] if n["frame"] == "hanging")
    child = dict(parent, id="chained_hook", below_node_id=parent["id"])
    model["nodes"].append(child)
    assert _Book(_build(tmp_path, model))(LAYOUT.check("hanging_chain")) == 1
