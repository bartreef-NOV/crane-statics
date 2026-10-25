"""Write the Crane Statics validation workbook (plain .xlsx, live formulas, no macros).

Sheets, in order (``layout.SHEETS``): Conventions, Inputs, Geometry, Loads, Statics,
OutOfPlane, Results, Checks. Addresses come only from ``layout``; each sheet has its own writer
module (``build_inputs``, ``build_geometry``, ``build_loads``, ``build_statics``,
``build_oop``, ``build_results``, ``build_checks``, ``conventions``).

Command line (from the repo root; in a worktree set ``PYTHONPATH=src``)::

    python -m scripts.excel_workbook.build examples/crane_input_22689.yaml out.xlsx
    python -m scripts.excel_workbook.build <yaml> <out.xlsx> --case idle_hoist
    python -m scripts.excel_workbook.build <yaml> <out.xlsx> --capacity nodes=120

The YAML is expanded with ``reference.expanded_model``; the scene state is a
``reference.CASES`` entry (default: the first, ``base``).
"""

from __future__ import annotations

import argparse
import dataclasses
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from openpyxl import Workbook

from . import layout
from .build_checks import write_checks
from .build_geometry import write_geometry
from .build_inputs import write_inputs
from .build_loads import write_loads
from .build_oop import oop_check_formulas, write_oop
from .build_results import write_results
from .build_statics import statics_check_formulas, write_statics
from .conventions import write_conventions
from .layout import DEFAULT_LAYOUT, Capacities, Layout
from .reference import CASES, SceneCase, expanded_model


def build_workbook(
    model: dict[str, Any], case: SceneCase, out: Path, lay: Layout = DEFAULT_LAYOUT
) -> None:
    """Write the workbook for ``model`` (``reference.expanded_model``) at scene ``case``.

    Rows beyond a table's capacity are not written; their number appears in the table's
    overflow cell and trips the ``overflow`` check.
    """
    wb = Workbook()
    wb.remove(wb.active)
    sheets = {name: wb.create_sheet(name) for name in layout.SHEETS}
    write_conventions(sheets[layout.CONVENTIONS])
    write_inputs(sheets[layout.INPUTS], lay, model, case)
    write_geometry(sheets[layout.GEOMETRY], lay)
    write_loads(sheets[layout.LOADS], lay)
    write_statics(sheets[layout.STATICS], lay)
    write_oop(sheets[layout.OUT_OF_PLANE], lay)
    write_results(sheets[layout.RESULTS], lay)
    write_checks(
        sheets[layout.CHECKS], lay, {**statics_check_formulas(lay), **oop_check_formulas(lay)}
    )
    # Formulas are written without cached values: Excel recalculates them on open.
    wb.calculation.fullCalcOnLoad = True
    wb.save(Path(out))


def _capacity(text: str) -> tuple[str, int]:
    """``"nodes=120"`` -> ``("nodes", 120)`` (a ``layout.Capacities`` field)."""
    names = [f.name for f in dataclasses.fields(Capacities)]
    table, _, count = text.partition("=")
    if table not in names or not count.isdigit() or int(count) < 1:
        raise argparse.ArgumentTypeError(
            f"expected TABLE=N with TABLE one of {', '.join(names)} and N >= 1, got {text!r}"
        )
    return table, int(count)


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m scripts.excel_workbook.build <yaml> <out.xlsx> [--case NAME]
    [--capacity TABLE=N ...]``."""
    parser = argparse.ArgumentParser(
        prog="python -m scripts.excel_workbook.build",
        description="Write the Crane Statics validation workbook for a crane YAML.",
    )
    parser.add_argument("yaml", type=Path, help="authored crane input YAML")
    parser.add_argument("out", type=Path, help="workbook to write (.xlsx)")
    parser.add_argument(
        "--case",
        choices=list(CASES),
        default=next(iter(CASES)),
        help="scene state typed on Inputs (default: %(default)s)",
    )
    parser.add_argument(
        "--capacity",
        type=_capacity,
        action="append",
        default=[],
        metavar="TABLE=N",
        help="rows of an Inputs table (repeatable), e.g. nodes=120; default: layout.Capacities",
    )
    args = parser.parse_args(argv)
    lay = Layout(Capacities(**dict(args.capacity))) if args.capacity else DEFAULT_LAYOUT
    build_workbook(expanded_model(args.yaml), CASES[args.case], args.out, lay)
    print(f"wrote {args.out} (scene case {args.case!r})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
