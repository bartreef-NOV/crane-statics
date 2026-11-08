from typing import Any

from crane_statics.core.results import ResultRow
from crane_statics.presentation.formatters import ResultRowFormatter


def _row(**kwargs: Any) -> ResultRow:
    base: dict[str, Any] = dict(name="Row", kind="rope", entity_id="r1", demand_kN=10.0)
    base.update(kwargs)
    return ResultRow(**base)


def test_row_without_limit_is_clickable():
    row = _row(limit_kN=None)
    assert ResultRowFormatter.is_clickable(row)
    assert ResultRowFormatter.result_rows_to_dicts([row])[0]["clickable"]


def test_row_with_limit_is_clickable():
    assert ResultRowFormatter.is_clickable(_row(limit_kN=100.0, utilization_pct=10.0))


def test_group_header_is_not_clickable():
    assert not ResultRowFormatter.is_clickable(_row(is_group_header=True))


def test_row_without_entity_is_not_clickable():
    assert not ResultRowFormatter.is_clickable(_row(entity_id=None))


def test_row_of_other_kind_is_not_clickable():
    assert not ResultRowFormatter.is_clickable(_row(kind="other"))


def test_factored_row_is_not_clickable_and_says_what_it_is():
    row = _row(
        name="Platform Base (ABS PF) / Fz",
        kind="factored",
        entity_id="platform_base",
        component="Fz",
        limit_kN=100.0,
        utilization_pct=50.0,
    )
    item = ResultRowFormatter.result_rows_to_dicts([row])[0]
    assert item["clickable"] is False
    assert item["tooltip"].startswith("Factored demand")
    assert item["utilization"] == "50%"
    plain = ResultRowFormatter.result_rows_to_dicts([_row(kind="connection", component="Fz")])[0]
    assert "Factored" not in plain["tooltip"]
