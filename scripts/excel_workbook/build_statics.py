"""The Statics sheet: the app's in-plane equilibrium solves, as visible matrix blocks.

Source: ``calculation/solver/crane_solver.py`` ``_run_statics``, solved once with the actual
loads (the app composes the same linear solve from a baseline and unit channels):

* boom -- ``A_boom [Hx, Hz, T_bh] = -[Fx, Fz, M]`` of the boom's known loads; the third
  column holds the solve-rope coefficients ``bh`` (Loads body totals) and the heel lever arm.
* leg frame -- ``A_af [R_rb_x, R_rb_z, R_fb_x, R_fb_z, R_top_x, R_top_z] = -(leg loads)``,
  the leg loads including ``T_bh x bh``; ``A_af`` holds 0/+-1 and the node coordinates.
* platform -- the resultant at the ground pin ``(r_g_x, r_g_z, m_g)``.

Each system is solved with ``MMULT(MINVERSE(A), b)`` written as a legacy array formula over
the whole output column (Excel 2016, and the ``formulas`` evaluator, need the full ref). The
app gives no result when ``np.linalg.solve`` raises; here a ``singular`` flag (relative
determinant <= ``SINGULAR_REL_TOL`` or MINVERSE failing) zeroes the solution and Results
shows a message.
"""

from __future__ import annotations

from openpyxl.worksheet.formula import ArrayFormula
from openpyxl.worksheet.worksheet import Worksheet

from . import styles
from .layout import (
    SINGULAR_REL_TOL,
    STATICS_NODES,
    STATICS_NOTES,
    SYSTEM_STATUS_FIELDS,
    Block,
    Layout,
    MatrixSystem,
    split,
)


def _local(address: str) -> str:
    return split(address)[1]


def _node(lay: Layout, node: str, axis: str) -> str:
    return lay.statics_cell("structure_nodes", f"{node}_{axis}_m")


def _status_formulas(lay: Layout) -> dict[str, str]:
    r = lay.col_range
    return {
        "solve_ropes": f'=COUNTIFS({r("ropes", "active")},1,{r("ropes", "role")},"solve")',
        "boom_singular": f"={lay.statics_flag('boom_system')}",
        "leg_singular": f"={lay.statics_flag('leg_system')}",
        "ok": (
            f"=IF(AND({lay.statics_cell('statics_status', 'solve_ropes')}>0,"
            f"{lay.statics_cell('statics_status', 'boom_singular')}=0,"
            f"{lay.statics_cell('statics_status', 'leg_singular')}=0),1,0)"
        ),
    }


def _node_formulas(lay: Layout) -> dict[str, str]:
    ids = lay.geo_col_range("node_positions", "id")
    out = {}
    for node in STATICS_NODES:
        for axis in ("x", "z"):
            col = lay.geo_col_range("node_positions", f"{axis}_m")
            out[f"{node}_{axis}_m"] = f'=IFERROR(INDEX({col},MATCH("{node}",{ids},0)),0)'
    return out


def _boom_matrix(lay: Layout) -> tuple[list[list[str | float]], list[str]]:
    bt = lay.body_total
    hx, hz = _node(lay, "boom_heel", "x"), _node(lay, "boom_heel", "z")
    a: list[list[str | float]] = [
        [1.0, 0.0, f"={bt('boom', 'bh_fx')}"],
        [0.0, 1.0, f"={bt('boom', 'bh_fz')}"],
        [f"=-{hz}", f"={hx}", f"={bt('boom', 'bh_m')}"],
    ]
    b = [f"=-{bt('boom', key)}" for key in ("fx", "fz", "m")]
    return a, b


def _leg_matrix(lay: Layout) -> tuple[list[list[str | float]], list[str]]:
    n = lambda node, axis: _node(lay, node, axis)  # noqa: E731
    a: list[list[str | float]] = [
        [1.0, 0.0, 0.0, 0.0, -1.0, 0.0],
        [0.0, 1.0, 0.0, 0.0, 0.0, -1.0],
        [
            f"=-{n('rear_base', 'z')}",
            f"={n('rear_base', 'x')}",
            0.0,
            0.0,
            f"={n('rear_top', 'z')}",
            f"=-{n('rear_top', 'x')}",
        ],
        [0.0, 0.0, 1.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0, 0.0, 1.0],
        [
            0.0,
            0.0,
            f"=-{n('front_base', 'z')}",
            f"={n('front_base', 'x')}",
            f"=-{n('front_top', 'z')}",
            f"={n('front_top', 'x')}",
        ],
    ]
    b = [
        f"=-{lay.statics_cell('leg_loads', f'{leg}_{comp}')}"
        for leg in ("rear", "front")
        for comp in ("fx", "fz", "m")
    ]
    return a, b


def _leg_load_formulas(lay: Layout) -> dict[str, str]:
    t_bh = lay.statics_value("t_bh")
    out = {}
    for leg, body in (("rear", "rear_leg"), ("front", "front_leg")):
        for comp in ("fx", "fz", "m"):
            out[f"{leg}_{comp}"] = (
                f"={lay.body_total(body, comp)}+{t_bh}*{lay.body_total(body, f'bh_{comp}')}"
            )
    return out


def _platform_formulas(lay: Layout) -> dict[str, str]:
    v = lay.statics_value
    me = lambda key: lay.statics_cell("platform", key)  # noqa: E731
    n = lambda node, axis: _node(lay, node, axis)  # noqa: E731
    out = {
        f"load_{comp}": (
            f"={lay.body_total('platform', comp)}"
            f"+{v('t_bh')}*{lay.body_total('platform', f'bh_{comp}')}"
        )
        for comp in ("fx", "fz", "m")
    }
    # x (-Fz) - z (-Fx) of each support force the boom and legs put on the platform.
    lever = "+".join(
        f"{n(node, 'x')}*(-{v(fz)})-{n(node, 'z')}*(-{v(fx)})"
        for node, fx, fz in (
            ("platform_heel", "h_x", "h_z"),
            ("platform_rear", "r_rb_x", "r_rb_z"),
            ("platform_front", "r_fb_x", "r_fb_z"),
        )
    )
    out.update(
        {
            "plat_fx": f"={me('load_fx')}-{v('h_x')}-{v('r_rb_x')}-{v('r_fb_x')}",
            "plat_fz": f"={me('load_fz')}-{v('h_z')}-{v('r_rb_z')}-{v('r_fb_z')}",
            "plat_m": f"={me('load_m')}+{lever}",
            "r_g_x": f"=-{me('plat_fx')}",
            "r_g_z": f"=-{me('plat_fz')}",
            "m_g": f"=-{me('plat_m')}",
        }
    )
    return out


def _leg_axis_formulas(lay: Layout) -> dict[str, str]:
    n = lambda node, axis: _node(lay, node, axis)  # noqa: E731
    me = lambda key: lay.statics_cell("leg_axes", key)  # noqa: E731
    out = {}
    for leg, base, top in (("rear", "rear_base", "rear_top"), ("front", "front_base", "front_top")):
        dx = f"({n(top, 'x')}-{n(base, 'x')})"
        dz = f"({n(top, 'z')}-{n(base, 'z')})"
        ok = me(f"{leg}_axis_ok")
        out[f"{leg}_len_m"] = f"=SQRT({dx}^2+{dz}^2)"
        out[f"{leg}_axis_ok"] = f"=IF({me(f'{leg}_len_m')}>1E-12,1,0)"
        out[f"{leg}_ux"] = f"=IF({ok}=1,{dx}/{me(f'{leg}_len_m')},0)"
        out[f"{leg}_uz"] = f"=IF({ok}=1,{dz}/{me(f'{leg}_len_m')},0)"
    return out


def _write_block(ws: Worksheet, block: Block, formulas: dict[str, str]) -> None:
    ws[f"A{block.title_row}"] = block.title
    ws[f"A{block.title_row}"].font = styles.SECTION_FONT
    for f in block.fields:
        row = block.row(f.key)
        ws[f"A{row}"] = f.header
        styles.put(ws, f"B{row}", formulas[f.key])
        ws[f"C{row}"] = f.unit or None
        ws[f"D{row}"] = f.key + (f"  -- {f.note}" if f.note else "")
        ws[f"D{row}"].font = styles.KEY_FONT


def _write_system(
    ws: Worksheet, system: MatrixSystem, a: list[list[str | float]], b: list[str]
) -> None:
    ws[f"A{system.title_row}"] = system.title + "  --  A x = b"
    ws[f"A{system.title_row}"].font = styles.SECTION_FONT
    headers = {"A": "Equation"}
    for j, f in enumerate(system.unknowns, start=1):
        headers[system.matrix_column(j)] = f"A: coefficient of {f.key}"
    headers[system.rhs_column] = "b (right-hand side) [kN or kNm]"
    headers[system.name_column] = "Unknown x"
    headers[system.raw_column] = "MMULT(MINVERSE(A), b)"
    headers[system.x_column] = "x used (0 if singular)"
    headers[system.norm_column] = "Row norm |A_i|"
    for col, text in headers.items():
        cell = ws[f"{col}{system.header_row}"]
        cell.value = text
        cell.font = styles.HEADER_FONT
        cell.fill = styles.HEADER_FILL
    singular = system.status_addr("singular")
    for i, equation in enumerate(system.equations, start=1):
        row = system.first_row + i - 1
        unknown = system.unknowns[i - 1]
        ws[f"A{row}"] = equation
        for j in range(1, system.n + 1):
            styles.put(ws, _local(system.a_addr(i, j)), a[i - 1][j - 1], styles.GENERATED_FILL)
        styles.put(ws, _local(system.b_addr(i)), b[i - 1])
        ws[f"{system.name_column}{row}"] = f"{unknown.key}: {unknown.header} [{unknown.unit}]"
        styles.put(
            ws,
            _local(system.x_addr(unknown.key)),
            f"=IF({singular}=1,0,{system.raw_addr(unknown.key)})",
        )
        first, last = system.matrix_column(1), system.matrix_column(system.n)
        styles.put(ws, _local(system.norm_addr(i)), f"=SQRT(SUMSQ({first}{row}:{last}{row}))")
    raw = system.raw_range.replace("$", "")
    ws[raw.split(":")[0]] = ArrayFormula(
        raw, f"=MMULT(MINVERSE({system.a_range}),{system.b_range})"
    )
    ws[raw.split(":")[0]].fill = styles.FORMULA_FILL
    for k in range(system.first_row + 1, system.last_row + 1):
        ws[f"{system.raw_column}{k}"].fill = styles.FORMULA_FILL
    norms = f"${system.norm_column}${system.first_row}:${system.norm_column}${system.last_row}"
    status = {
        "det": f"=MDETERM({system.a_range})",
        "norm_product": f"=PRODUCT({norms})",
        "rel_det": (
            f"=IF({system.status_addr('norm_product')}>0,"
            f"ABS({system.status_addr('det')})/{system.status_addr('norm_product')},0)"
        ),
        "singular": (
            f"=IF(OR({system.status_addr('rel_det')}<={SINGULAR_REL_TOL:G},"
            f"ISERROR(SUM({system.raw_range}))),1,0)"
        ),
    }
    for f in SYSTEM_STATUS_FIELDS:
        row = system.status_row(f.key)
        ws[f"A{row}"] = f.header
        styles.put(ws, f"B{row}", status[f.key])
        ws[f"C{row}"] = f.unit or None
        ws[f"D{row}"] = f.key + (f"  -- {f.note}" if f.note else "")
        ws[f"D{row}"].font = styles.KEY_FONT


def statics_check_formulas(lay: Layout) -> dict[str, str]:
    """The ``singular_matrix`` check: the number of singular systems."""
    return {
        "singular_matrix": "=" + "+".join(lay.statics_flag(name) for name in lay.statics_systems),
    }


def write_statics(ws: Worksheet, lay: Layout) -> None:
    """Fill the Statics sheet (all formulas, driven by Loads and Geometry)."""
    ws["A1"] = "Statics -- boom and leg-frame equilibrium solves"
    ws["A1"].font = styles.TITLE_FONT
    for k, note in enumerate(STATICS_NOTES):
        ws[f"A{3 + k}"] = note
        ws[f"A{3 + k}"].font = styles.NOTE_FONT
    blocks = {
        "statics_status": _status_formulas(lay),
        "structure_nodes": _node_formulas(lay),
        "leg_loads": _leg_load_formulas(lay),
        "platform": _platform_formulas(lay),
        "leg_axes": _leg_axis_formulas(lay),
    }
    for name, block in lay.statics_blocks.items():
        _write_block(ws, block, blocks[name])
    matrices = {"boom_system": _boom_matrix(lay), "leg_system": _leg_matrix(lay)}
    for name, system in lay.statics_systems.items():
        _write_system(ws, system, *matrices[name])
    ws.column_dimensions["A"].width = 44
    for col in "BCDEFGHIJKL":
        ws.column_dimensions[col].width = 18
