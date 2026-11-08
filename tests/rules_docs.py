"""Rules documents built from the GT283 example, for core tests of conditions and cases."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest

from crane_statics.core import governing_case, limit_auto_set, load_document, sweep
from crane_statics.data.models import ConditionSpec, CraneDocument, RulesSpec, VesselMotion

GT283 = Path(__file__).parent.parent / "examples" / "crane_input_GT283.yaml"
MOTION = VesselMotion(
    accel_x_m_s2=0.8, roll_deg=4.0, pitch_deg=2.5, reference_x_m=3.0, reference_z_m=-2.0
)


def gale(name: str = "gale", wind: float = 30.0, motion: VesselMotion = MOTION) -> ConditionSpec:
    return ConditionSpec(name=name, wind_speed_m_s=wind, vessel_motion=motion)


def rules_doc(standard: Literal["ABS", "DNV"], *conditions: ConditionSpec) -> CraneDocument:
    """GT283 under ``standard`` with ``conditions``; the environment holds runtime dummies."""
    doc = load_document(GT283)
    # The dummies a rules document carries at runtime: no analysis may read them.
    env = doc.environment.model_copy(
        update={"max_wind_speed_m_s": 20.0, "vessel_motion": VesselMotion()}
    )
    return doc.model_copy(
        update={
            "rules": RulesSpec(
                standard=standard, crane_class="offshore" if standard == "ABS" else None
            ),
            "conditions": {c.name: c for c in conditions},
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
    """``doc`` without rules, its environment at ``wind`` and ``motion``."""
    env = doc.environment.model_copy(update={"max_wind_speed_m_s": wind, "vessel_motion": motion})
    return doc.model_copy(update={"rules": None, "conditions": {}, "environment": env})


def without_live_lateral(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch the live-load lateral (``lift_factor.hook_lateral``) off in the chart consumers.

    A rules run puts the vessel-motion, incline, load-wind and minimum side load on the
    hook (spec section 9); its ``legacy_equivalent`` has none of them. Tests that check the
    condition plumbing against the legacy run switch it off; the lateral itself is covered
    by ``tests/test_live_load_lateral.py``.
    """
    for module in (sweep, governing_case, limit_auto_set):
        monkeypatch.setattr(module, "hook_lateral", lambda *_args, **_kwargs: None)
