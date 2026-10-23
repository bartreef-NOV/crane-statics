"""A limit's required factor: the runtime margin applied to its capacity."""

from __future__ import annotations

import pytest

from crane_statics.core.session_model import DesignLimit


def test_allowable_is_capacity_divided_by_the_factor():
    limit = DesignLimit(
        id="x", kind="rope", entity_id="r", component="T", max_kN=300.0, required_factor=1.5
    )

    assert limit.allowable_kN == pytest.approx(200.0)


def test_default_factor_leaves_the_capacity_unchanged():
    limit = DesignLimit(id="x", kind="rope", entity_id="r", component="T", max_kN=300.0)

    assert limit.required_factor == 1.0
    assert limit.allowable_kN == 300.0


def test_limit_without_capacity_has_no_allowable_value():
    assert DesignLimit(id="x", kind="rope", entity_id="r", component="T").allowable_kN is None
