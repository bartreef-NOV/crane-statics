"""Write the Crane Statics validation workbook (plain .xlsx, live formulas, no macros).

Sheets, in order (``layout.SHEETS``): Conventions, Inputs, Geometry, Loads, Statics,
OutOfPlane, Results, Checks. Addresses come only from ``layout``; each sheet has its own writer
module (``build_inputs``, ``build_geometry``, ``build_loads``, ``build_statics``,
``build_oop``, ``build_results``, ``build_checks``, ``conventions``).
"""

from __future__ import annotations

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
from .layout import DEFAULT_LAYOUT, Layout
from .reference import SceneCase


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
    wb.save(Path(out))
