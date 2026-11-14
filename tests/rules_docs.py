"""Rules documents built from the GT283 example, for core tests of conditions and cases."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import pytest

from crane_statics.core import governing_case, lift_factor, limit_auto_set, sweep
from crane_statics.data import normalize_document
from crane_statics.data.models import (
    ConditionHoist,
    ConditionSpec,
    CraneDocument,
    RulesSpec,
    VesselMotion,
)
from tests.authored_helpers import example_path, read_yaml, v13

#: The GT283 example (schema v13).
GT283 = example_path("crane_input_GT283.yaml")
MOTION = VesselMotion(
    accel_x_m_s2=0.8, roll_deg=4.0, pitch_deg=2.5, reference_x_m=3.0, reference_z_m=-2.0
)


def load_v13(path: Path) -> CraneDocument:
    """The authored file at ``path``, normalized (a v12 file is migrated first; the
    shipped examples are v13)."""
    return normalize_document(v13(read_yaml(path)))


def _copied(hoists: dict[str, ConditionHoist]) -> dict[str, ConditionHoist]:
    """Deep copies of condition hoist entries: no two conditions may share one."""
    return {hid: entry.model_copy(deep=True) for hid, entry in hoists.items()}


def first_settings(doc: CraneDocument, hoist_id: str) -> Optional[ConditionHoist]:
    """``hoist_id``'s entry in ``doc``'s first condition (``iter_hoist_analysis_modes``
    takes it); None when that condition does not list the hoist."""
    first = next(iter(doc.conditions.values()))
    return first.hoists.get(hoist_id)


def with_condition(
    doc: CraneDocument, name: str, hoists: dict[str, ConditionHoist]
) -> CraneDocument:
    """``doc`` with one more condition ``name``: a copy of its first condition (wind,
    vessel motion and the rest) that lists only ``hoists``."""
    first = next(iter(doc.conditions.values()))
    added = first.model_copy(deep=True, update={"name": name, "hoists": _copied(hoists)})
    return doc.model_copy(update={"conditions": {**doc.conditions, name: added}})


def listing_example_hoists(doc: CraneDocument, condition: ConditionSpec) -> ConditionSpec:
    """``condition`` listing (copies of) ``doc``'s first-condition hoist settings when it
    lists none itself: a condition built in a test has no hoist usable otherwise."""
    if condition.hoists:
        return condition
    first = next(iter(doc.conditions.values()))
    return condition.model_copy(update={"hoists": _copied(first.hoists)})


def gale(name: str = "gale", wind: float = 30.0, motion: VesselMotion = MOTION) -> ConditionSpec:
    return ConditionSpec(name=name, wind_speed_m_s=wind, vessel_motion=motion)


def rules_doc(standard: Literal["ABS", "DNV"], *conditions: ConditionSpec) -> CraneDocument:
    """GT283 under ``standard`` with ``conditions``; the environment holds runtime dummies.

    A condition listing no hoists gets GT283's own hoist settings (its migrated ``default``
    condition: lead limits, the authored DAFs, which are manual overrides under rules, and
    the contractual points).
    """
    doc = load_v13(GT283)
    hoists = doc.conditions["default"].hoists
    listed = [
        c if c.hoists else c.model_copy(update={"hoists": _copied(hoists)}) for c in conditions
    ]
    # The dummies a rules document carries at runtime: no analysis may read them.
    env = doc.environment.model_copy(
        update={"max_wind_speed_m_s": 20.0, "vessel_motion": VesselMotion()}
    )
    return doc.model_copy(
        update={
            "rules": RulesSpec(
                standard=standard, crane_class="offshore" if standard == "ABS" else None
            ),
            "conditions": {c.name: c for c in listed},
            "environment": env,
        }
    )


def without_suspended_rope(doc: CraneDocument) -> CraneDocument:
    """``doc`` with massless payload-hoist ropes (the boom hoist keeps its rope mass).

    A rules run counts the suspended (hook-segment) rope in the amplified live load, a legacy
    run as dead load. Without payload-rope mass both are the same, so a rules run equals its
    ``legacy_equivalent`` exactly; ``tests/test_rules_suspended.py`` covers the rope itself.
    """
    hoists = [
        h if h.support_node_id is None else h.model_copy(update={"linear_mass_kg_m": 0.0})
        for h in doc.hoists
    ]
    return doc.model_copy(update={"hoists": hoists})


def legacy_equivalent(doc: CraneDocument, wind: float, motion: VesselMotion) -> CraneDocument:
    """``doc`` without rules, one condition at ``wind`` and ``motion``.

    The condition takes the hoist settings of ``doc``'s first condition (an authored DAF is
    the constant factor, 1.0 without one); the environment carries the same values.
    """
    first = next(iter(doc.conditions.values()))
    condition = ConditionSpec(
        name="default", wind_speed_m_s=wind, vessel_motion=motion, hoists=_copied(first.hoists)
    )
    env = doc.environment.model_copy(update={"max_wind_speed_m_s": wind, "vessel_motion": motion})
    return doc.model_copy(
        update={"rules": None, "conditions": {"default": condition}, "environment": env}
    )


def without_live_lateral(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch the live-load lateral (``lift_factor.hook_lateral``) off in the chart consumers.

    A rules run puts the vessel-motion, incline, load-wind and minimum side load on the
    hook (spec section 9); its ``legacy_equivalent`` has none of them. Tests that check the
    condition plumbing against the legacy run switch it off; the lateral itself is covered
    by ``tests/test_live_load_lateral.py``.
    """
    for module in (sweep, governing_case, limit_auto_set):
        monkeypatch.setattr(module, "hook_lateral", lambda *_args, **_kwargs: None)


def without_foundation_factors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch the pedestal and retaining-component demand scales off (Task 12).

    A rules run checks platform-base limits against the factored demand (ABS PF, DNV
    SF1); its ``legacy_equivalent`` has no factors. Tests that compare the two switch them
    off; ``tests/test_foundation_factors.py`` covers the factors themselves.
    """
    monkeypatch.setattr(lift_factor.LiftFactors, "demand_scales", lambda *_a, **_k: None)
