"""Excel workbook smoke tests on the other example cranes (GT283, 13778): the workbook built
from a crane's own YAML matches the app for that crane."""

import math
from pathlib import Path

import pytest

from scripts.excel_workbook import layout
from scripts.excel_workbook.build import build_workbook
from scripts.excel_workbook.reference import REPO_ROOT, app_results, expanded_model

from tests.excel_workbook_helpers import (
    ACCEPT_TOL,
    EXPECTED_OMISSIONS,
    OTHER_CRANES,
    _assert_book_clean,
    _Book,
    _workbook_results,
    fit_layout,
)

BEARING_ROWS = {
    "reaction.platform_base.max_bearing_line_load",
    "reaction.platform_base.min_bearing_line_load",
}


@pytest.mark.parametrize("yaml_name", sorted(OTHER_CRANES))
def test_other_crane_matches_app(tmp_path: Path, yaml_name: str) -> None:
    yaml_path = REPO_ROOT / "examples" / yaml_name
    case = OTHER_CRANES[yaml_name]
    model = expanded_model(yaml_path)
    lay = fit_layout(model)
    path = tmp_path / "crane.xlsx"
    build_workbook(model, case, path, lay)
    book = _Book(path)
    _assert_book_clean(book, *layout.SHEETS)
    assert book(lay.total_issues_addr) == 0
    assert book(lay.results_cell("results_status", "message")) == "OK"
    want = app_results(yaml_path, case)
    got = _workbook_results(book, lay, model)
    assert set(want) - set(got) == EXPECTED_OMISSIONS, yaml_name
    # Without a bearing diameter the app drops the bearing rows; the workbook shows n/a.
    extra = set(got) - set(want)
    no_diameter = model["structure"]["slewing_bearing_diameter_m"] is None
    assert extra == (BEARING_ROWS if no_diameter else set()), extra
    for key in extra:
        assert isinstance(got[key], str) and "diameter" in got[key], (key, got[key])
    for key, value in want.items():
        if key in got:
            assert math.isclose(got[key], value, rel_tol=0.0, abs_tol=ACCEPT_TOL), (
                yaml_name,
                key,
                got[key],
                value,
            )
