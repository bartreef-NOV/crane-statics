"""The Checks sheet: one live count per input check (0 = OK) and a total."""

from __future__ import annotations

from collections.abc import Mapping

from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import PatternFill
from openpyxl.worksheet.worksheet import Worksheet

from . import styles
from .layout import (
    CHECK_DESCRIPTIONS,
    CHECKS_HEADER_ROW,
    CHECKS_TOTAL_ROW,
    FIXED_NODE_POINTS,
    Layout,
)
from .sheet_writers import local

_ID_TABLES = ("mass_points", "wind_areas", "nodes", "ropes", "hoists")
#: Tables whose ids are referenced elsewhere. Mass-point and wind-area ids are labels only
#: (the app accepts duplicates there), so ``duplicate_ids`` skips them.
_UNIQUE_ID_TABLES = ("nodes", "ropes", "hoists")
_BAD_FILL = PatternFill("solid", fgColor="F8CBAD")


def _active(lay: Layout, table: str) -> str:
    return f"({lay.col_range(table, 'active')}=1)"


def _missing(lay: Layout, target: str, refs: str) -> str:
    """Array term: 1 where ``refs`` names no active row of table ``target``."""
    return (
        f"(COUNTIFS({lay.col_range(target, 'id')},{refs},"
        f"{lay.col_range(target, 'active')},1)=0)"
    )


def _sp(*factors: str) -> str:
    return "SUMPRODUCT(" + "*".join(factors) + ")"


def invalid_value_terms(lay: Layout) -> list[str]:
    """SUMPRODUCT terms of the ``invalid_values`` check, one per table column with a fixed set
    of allowed values.

    A typo in such a cell would silently drop the row (every formula compares against the
    exact choices), so: ``active`` must be blank, 0 or 1 on every row; on active rows, every
    other 1/0 column must be blank, 0 or 1, and every list column (body, frame, role) one of
    its choices.
    """
    terms = []
    for name, table in lay.tables.items():
        active = lay.col_range(name, "active")
        terms.append(_sp(f'1*({active}<>"")', f"({active}<>0)", f"({active}<>1)"))
        for f in table.fields:
            col = lay.col_range(name, f.key)
            if f.key == "active":
                continue
            if f.kind == "flag":
                terms.append(_sp(f"1*({active}=1)", f'({col}<>"")', f"({col}<>0)", f"({col}<>1)"))
            elif f.choices:
                terms.append(_sp(f"1*({active}=1)", *(f'({col}<>"{c}")' for c in f.choices)))
    return terms


def mirror_pairs(lay: Layout) -> list[tuple[str, int, str]]:
    """``(Inputs active range, capacity, mirror active range)`` for every sheet table that has
    one row per Inputs row (Geometry, Loads, OutOfPlane, Results)."""
    mirrors = {
        "mass_points": [lay.loads_col_range("mass_loads", "active")]
        + [lay.oop.col_range("oop_masses", "active")],
        "wind_areas": [lay.loads_col_range("wind_loads", "active")]
        + [lay.oop.col_range("oop_winds", "active")],
        "nodes": [
            lay.geo_col_range("node_positions", "active"),
            lay.loads_col_range("node_loads", "active"),
            lay.oop.col_range("oop_lumped", "active"),
        ],
        "segments": [lay.loads_col_range("segment_loads", "active")],
        "ropes": [lay.loads_col_range("rope_tensions", "active")],
        "hoists": [
            lay.loads_col_range("hoist_ropes", "active"),
            lay.results_tables["tensions"].col_range("active"),
        ],
    }
    return [
        (lay.col_range(name, "active"), lay.tables[name].capacity, mirror)
        for name in lay.tables
        for mirror in mirrors[name]
    ]


def mirror_formula(lay: Layout) -> str:
    """``mirror``: rows inserted into or deleted from an Inputs table (its range no longer has
    ``capacity`` rows), or a row-wise sheet whose Active column no longer copies Inputs."""
    terms = [
        f"IFERROR(1*(ROWS({src})<>{cap})+1*(SUM({src})<>SUM({mirror})),1)"
        for src, cap, mirror in mirror_pairs(lay)
    ]
    return "=" + "+".join(terms)


def input_check_formulas(
    lay: Layout, overflow_range: str, fixed_count_range: str
) -> dict[str, str]:
    """Formulas for the input checks of ``layout.CHECK_DESCRIPTIONS``."""
    r = lay.col_range
    duplicates = [
        _sp(
            _active(lay, t),
            f"({r(t, 'id')}<>\"\")",
            f"(COUNTIFS({r(t, 'id')},{r(t, 'id')},{r(t, 'active')},1)>1)",
        )
        for t in _UNIQUE_ID_TABLES
    ]
    blanks = [_sp(_active(lay, t), f"({r(t, 'id')}=\"\")") for t in _ID_TABLES]
    blanks.append(_sp(_active(lay, "segments"), f"({r('segments', 'rope_id')}=\"\")"))
    node_refs = [
        _sp(_active(lay, "segments"), _missing(lay, "nodes", r("segments", "from_node_id"))),
        _sp(_active(lay, "segments"), _missing(lay, "nodes", r("segments", "to_node_id"))),
        _sp(_active(lay, "hoists"), _missing(lay, "nodes", r("hoists", "load_node_id"))),
        _sp(
            _active(lay, "hoists"),
            f"({r('hoists', 'support_node_id')}<>\"\")",
            _missing(lay, "nodes", r("hoists", "support_node_id")),
        ),
        _sp(
            _active(lay, "nodes"),
            f"({r('nodes', 'frame')}=\"hanging\")",
            _missing(lay, "nodes", r("nodes", "below_node_id")),
        ),
    ]
    rope_refs = [
        _sp(_active(lay, "segments"), _missing(lay, "ropes", r("segments", "rope_id"))),
        _sp(_active(lay, "hoists"), _missing(lay, "ropes", r("hoists", "rope_id"))),
    ]
    solve_count = f"COUNTIFS({r('ropes', 'active')},1,{r('ropes', 'role')},\"solve\")"
    hoist = lay.cell("scene", "hoist_id")
    wind = lay.cell("scene", "wind_direction")
    diameter = lay.cell("structure", "slewing_bearing_diameter_m")
    hoist_keys = lay.loads_col_range("hoist_ropes", "id_key")
    hoist_rope = f'IFERROR(INDEX({r("hoists", "rope_id")},MATCH({hoist}&"",{hoist_keys},0)),"")'
    return {
        "overflow": f"=SUM({overflow_range})",
        "duplicate_ids": "=" + "+".join(duplicates),
        "blank_ids": "=" + "+".join(blanks),
        "node_references": "=" + "+".join(node_refs),
        "rope_references": "=" + "+".join(rope_refs),
        "hoist_without_segments": "="
        + _sp(
            _active(lay, "hoists"),
            f"(COUNTIFS({r('segments', 'rope_id')},{r('hoists', 'rope_id')},"
            f"{r('segments', 'active')},1)=0)",
        ),
        "multiple_solve_ropes": f"=MAX(0,{solve_count}-1)",
        "no_solve_rope": f"=IF({solve_count}=0,1,0)",
        "scene_hoist": (
            f"=IF(COUNTIFS({r('hoists', 'id')},{hoist},{r('hoists', 'active')},1)=0,1,"
            f"IF(COUNTIFS({r('ropes', 'id')},{hoist_rope},{r('ropes', 'active')},1,"
            f"{r('ropes', 'role')},\"fixed\")=0,1,0))"
        ),
        "wind_direction": (f'=IF(OR({wind}="+X",{wind}="-X",{wind}="+Y",{wind}="-Y"),0,1)'),
        "fixed_nodes_missing": f"=COUNTIF({fixed_count_range},0)",
        "hanging_chain": "="
        + _sp(
            _active(lay, "nodes"),
            f"({r('nodes', 'frame')}=\"hanging\")",
            f"(COUNTIFS({r('nodes', 'id')},{r('nodes', 'below_node_id')},"
            f"{r('nodes', 'frame')},\"hanging\",{r('nodes', 'active')},1)>0)",
        ),
        "invalid_values": "=" + "+".join(invalid_value_terms(lay)),
        "mirror": mirror_formula(lay),
        "invalid_bearing_diameter": (
            f'=IF({diameter}="",0,IF(ISNUMBER({diameter}),IF({diameter}>0,0,1),1))'
        ),
    }


def write_checks(
    ws: Worksheet, lay: Layout, extra_formulas: Mapping[str, str] | None = None
) -> None:
    """Write every check of ``layout.CHECK_DESCRIPTIONS``; later tasks pass their own formulas in
    ``extra_formulas`` (keyed like ``CHECK_DESCRIPTIONS``)."""
    ws["A1"] = "Checks -- every count must be 0"
    ws["A1"].font = styles.TITLE_FONT

    # Detail blocks below the check list: overflow per table, fixed nodes present.
    row = lay.checks_detail_row
    ws[f"A{row}"] = "Overflow per table"
    ws[f"A{row}"].font = styles.SECTION_FONT
    for col, text in zip("ABCD", ("Table", "Not written", "Typed in guard row", "Total")):
        ws[f"{col}{row + 1}"] = text
        ws[f"{col}{row + 1}"].font = styles.HEADER_FONT
    first = row + 2
    for i, table in enumerate(lay.tables.values()):
        rr = first + i
        ws[f"A{rr}"] = table.name
        styles.put(ws, f"B{rr}", f"={table.overflow_addr}")
        styles.put(ws, f"C{rr}", f"=COUNTA({table.guard_range})")
        styles.put(ws, f"D{rr}", f"=B{rr}+C{rr}")
    overflow_range = f"$D${first}:$D${first + len(lay.tables) - 1}"

    row = first + len(lay.tables) + 2
    ws[f"A{row}"] = "Fixed structure nodes (active rows with this id)"
    ws[f"A{row}"].font = styles.SECTION_FONT
    first = row + 1
    for i, node_id in enumerate(FIXED_NODE_POINTS):
        rr = first + i
        ws[f"A{rr}"] = node_id
        styles.put(
            ws,
            f"B{rr}",
            f"=COUNTIFS({lay.col_range('nodes', 'id')},A{rr},"
            f"{lay.col_range('nodes', 'active')},1)",
        )
    fixed_range = f"$B${first}:$B${first + len(FIXED_NODE_POINTS) - 1}"

    formulas = input_check_formulas(lay, overflow_range, fixed_range)
    formulas.update(extra_formulas or {})

    header = CHECKS_HEADER_ROW
    for col, text in zip("ABCD", ("Check", "Description", "Count", "Status")):
        ws[f"{col}{header}"] = text
        ws[f"{col}{header}"].font = styles.HEADER_FONT
        ws[f"{col}{header}"].fill = styles.HEADER_FILL
    for key, description in CHECK_DESCRIPTIONS.items():
        rr = lay.check_row(key)
        ws[f"A{rr}"] = key
        ws[f"B{rr}"] = description
        styles.put(ws, local(lay.check(key)), formulas[key])
        styles.put(ws, f"D{rr}", f'=IF(C{rr}=0,"OK","CHECK")')
    last = lay.check_row(list(CHECK_DESCRIPTIONS)[-1])
    total = local(lay.total_issues_addr)
    ws[f"B{CHECKS_TOTAL_ROW}"] = "Total issues"
    ws[f"B{CHECKS_TOTAL_ROW}"].font = styles.HEADER_FONT
    styles.put(ws, total, f"=SUM(C{header + 1}:C{last})")
    styles.put(ws, f"D{CHECKS_TOTAL_ROW}", f'=IF({total}=0,"OK","CHECK INPUTS")')
    bad = CellIsRule(operator="greaterThan", formula=["0"], fill=_BAD_FILL)
    ws.conditional_formatting.add(f"C{header + 1}:C{last}", bad)
    ws.conditional_formatting.add(total, bad)
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 90
    ws.column_dimensions["C"].width = 10
    ws.column_dimensions["D"].width = 16
