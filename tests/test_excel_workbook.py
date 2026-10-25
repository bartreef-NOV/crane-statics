"""Tests for the Excel validation workbook tooling."""

import math
from pathlib import Path

import numpy as np
from openpyxl import Workbook
from openpyxl.worksheet.formula import ArrayFormula

from scripts.excel_workbook.recalc import recalculate


def _num(value: float | str | None) -> float:
    assert isinstance(value, float), value
    return value


def test_recalculate_supports_minverse_mmult(tmp_path: Path) -> None:
    matrix = [[4.0, -2.0, 1.0], [3.0, 6.0, -4.0], [2.0, 1.0, 8.0]]
    vector = [12.0, -25.0, 32.0]
    wb = Workbook()
    ws = wb.active
    ws.title = "Solve"
    for r, row in enumerate(matrix, start=1):
        for c, value in enumerate(row, start=1):
            ws.cell(row=r, column=c, value=value)
        ws.cell(row=r, column=5, value=vector[r - 1])
    ws["G1"] = ArrayFormula("G1:G3", "=MMULT(MINVERSE(A1:C3),E1:E3)")
    path = tmp_path / "solve.xlsx"
    wb.save(path)

    values = recalculate(path)["Solve"]

    expected = np.linalg.solve(np.array(matrix), np.array(vector))
    got = [values["G1"], values["G2"], values["G3"]]
    assert np.allclose(got, expected, rtol=0, atol=1e-9)


def test_recalculate_reads_sumproduct_if_index_match(tmp_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Fn"
    for i, (key, val) in enumerate([(1, 10.0), (2, 20.0), (3, 30.0)], start=1):
        ws.cell(row=i, column=1, value=key)
        ws.cell(row=i, column=2, value=val)
    ws["D1"] = "=SUMPRODUCT(A1:A3,B1:B3)"
    ws["D2"] = '=IF(B1>5,"big","small")'
    ws["D3"] = "=INDEX(B1:B3,MATCH(2,A1:A3,0))"
    ws["D4"] = "=ABS(-3.5)"
    ws["D5"] = "=SQRT(16)"
    ws["D6"] = "=SIN(0.5)"
    ws["D7"] = "=COS(0.5)"
    ws["D8"] = "=ATAN2(1,2)"
    path = tmp_path / "fn.xlsx"
    wb.save(path)

    values = recalculate(path)["Fn"]

    assert values["D1"] == 140.0
    assert values["D2"] == "big"
    assert values["D3"] == 20.0
    assert values["D4"] == 3.5
    assert values["D5"] == 4.0
    assert math.isclose(_num(values["D6"]), math.sin(0.5), abs_tol=1e-12)
    assert math.isclose(_num(values["D7"]), math.cos(0.5), abs_tol=1e-12)
    # Excel ATAN2(x, y) takes x first.
    assert math.isclose(_num(values["D8"]), math.atan2(2, 1), abs_tol=1e-12)


def test_recalculate_extra_functions(tmp_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Extra"
    for i, (k, v) in enumerate([("a", 1.0), ("b", 2.0), ("a", 4.0)], start=1):
        ws.cell(row=i, column=1, value=k)
        ws.cell(row=i, column=2, value=v)
    formulas = {
        "D1": ("=RADIANS(180)", math.pi),
        "D2": ("=DEGREES(PI())", 180.0),
        "D3": ("=ACOS(0.5)", math.acos(0.5)),
        "D4": ("=ATAN(1)", math.atan(1)),
        "D5": ("=MAX(B1:B3)", 4.0),
        "D6": ("=MIN(B1:B3)", 1.0),
        "D7": ("=SUM(B1:B3)", 7.0),
        "D8": ('=SUMIF(A1:A3,"a",B1:B3)', 5.0),
        "D9": ('=SUMIFS(B1:B3,A1:A3,"a",B1:B3,">1")', 4.0),
        "D10": ("=SQRT(3^2+4^2)", 5.0),
    }
    for cell, (formula, _) in formulas.items():
        ws[cell] = formula
    path = tmp_path / "extra.xlsx"
    wb.save(path)

    values = recalculate(path)["Extra"]

    for cell, (_, expected) in formulas.items():
        assert math.isclose(_num(values[cell]), expected, abs_tol=1e-12), cell
