"""The dynamic factor (and the rest of the lift setup) of one chart point.

A legacy document has one constant factor per hoist, its authored ``hook_daf``. On a rules
document the profile builds it per condition case, hoist, analysis mode and boom angle: an
offboard lift's factor depends on the vertical hook stiffness, which changes with outreach.
Every consumer of the factor (sweep, governing case, Auto-Set, the Scene) goes through
``factor_for_point`` or the per-run cache ``LiftFactors``, so they all use the same one.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import replace
from typing import Any, Hashable, Optional, cast

from ..calculation.dynamic_factor import ConstantDynamicFactor
from ..calculation.engine import AnalysisPoint, CraneCalculator
from ..calculation.rope_mass import hook_support_node_id
from ..calculation.solver.kinematics import KinematicsAdapter
from ..data.models import CraneDocument, Hoist
from ..rules import RulesValidationError, profile_for
from ..rules.stiffness import (
    hook_stiffness_kN_per_m,
    payload_hoist_stiffness_terms,
    worst_case_tackle_length_m,
)
from ..rules.types import FoundationFactors, LateralSpec, LiftSetup
from .analysis_cases import HoistAnalysisMode
from .load_condition import LoadCondition

#: The suspended rope joins the live load in a later step; until then it is not counted.
SUSPENDED_ROPE_MASS_T = 0.0

# A legacy document has no live-load lateral, no foundation factor and no retaining factor.
_NEUTRAL_LATERAL = LateralSpec(
    accel_fraction_x=0.0,
    accel_fraction_y=0.0,
    incline_deg=0.0,
    wind_area_m2=0.0,
    wind_cd=1.0,
    min_fraction=0.0,
)


def _unit_factor(_live_load_kN: float) -> float:
    return 1.0


_NEUTRAL_FOUNDATION = FoundationFactors(live_factor=_unit_factor, dead_factor=1.0)


def _hoist(doc: CraneDocument, hoist_id: str) -> Hoist:
    hoist = next((h for h in doc.hoists if h.id == hoist_id), None)
    if hoist is None:
        raise RulesValidationError(f"hoists.{hoist_id}: not defined")
    return hoist


def legacy_lift_setup(hoist: Hoist) -> LiftSetup:
    """The setup of a document without rules: the authored constant factor, nothing else."""
    return LiftSetup(
        factor=ConstantDynamicFactor(hoist.hook_daf),
        lateral=_NEUTRAL_LATERAL,
        foundation=_NEUTRAL_FOUNDATION,
        retaining_live_factor=1.0,
        records=(),
        warnings=(),
    )


def needs_stiffness(condition: LoadCondition) -> bool:
    """Whether the condition's factor depends on the hook stiffness (offboard lifts only)."""
    return condition.spec is not None and condition.spec.lift == "offboard"


def chart_max_load_t(mode: HoistAnalysisMode) -> float:
    """The curve's maximum rated load: the largest contractual (rated) point load, else 0."""
    return max((float(cp.load_t) for cp in mode.contractual_points), default=0.0)


def stiffness_tackle_length_m(
    doc: CraneDocument,
    condition: LoadCondition,
    hoist_id: str,
    boom_angle_deg: float,
    kinematics: Optional[KinematicsAdapter] = None,
    doc_dict: Optional[dict[str, Any]] = None,
) -> float:
    """The hook's payout below its sheave at which the stiffness is evaluated.

    Without ``hook_height_override_m`` that is the worst case, the hook at its sheave
    (``worst_case_tackle_length_m``). With it, the hook hangs at that absolute height:
    ``max(0, z_support - hook_height)``, ``z_support`` being the height of the node the
    hook hangs from at ``boom_angle_deg``. A sheave below the override height leaves no
    payout (clamped to 0, as ``rope_mass.hook_positions_at_height`` clamps the hook).
    """
    override = None if condition.spec is None else condition.spec.hook_height_override_m
    if override is None:
        return worst_case_tackle_length_m()
    data = doc.model_dump() if doc_dict is None else doc_dict
    kin = KinematicsAdapter(data) if kinematics is None else kinematics
    positions = kin.compute_all_node_positions(float(boom_angle_deg))
    support = positions.get(hook_support_node_id(data, hoist_id))
    if support is None:
        raise RulesValidationError(
            f"hoists.{hoist_id}: hook support node unresolved at {boom_angle_deg:g} deg"
        )
    return max(0.0, float(support["z"]) - float(override))


def stiffness_point(
    calc: CraneCalculator, hoist_id: str, boom_angle_deg: float
) -> Optional[AnalysisPoint]:
    """The point the hook stiffness reads its rope sensitivities from.

    The hoist is the active one, with no lead (so the boom-hoist sensitivity is the
    vertical hook load's alone), on a level vessel without wind or motion (sensitivities
    do not depend on them), and with its authored reeving: the stiffness ignores split
    blocks (``rules.stiffness.payload_hoist_stiffness_terms``), so no split overrides.
    """
    return calc.compute_analysis_point(
        float(boom_angle_deg),
        0.0,
        hoist_id,
        wind_speed_m_s=0.0,
        wind_angle_deg=0.0,
        accel_x_m_s2=0.0,
        accel_y_m_s2=0.0,
        accel_z_m_s2=0.0,
        pitch_accel_rad_s2=0.0,
        roll_accel_rad_s2=0.0,
        offlead_deg=0.0,
        sidelead_deg=0.0,
        hoist_runtime_overrides=None,
        crane_slewing_angle_deg=0.0,
        vessel_roll_deg=0.0,
        vessel_pitch_deg=0.0,
    )


def _profile_setup(
    doc: CraneDocument,
    condition: LoadCondition,
    hoist_id: str,
    mode: HoistAnalysisMode,
    stiffness_kN_m: float,
) -> LiftSetup:
    assert doc.rules is not None and condition.spec is not None
    setup = profile_for(doc.rules).lift_setup(
        doc,
        condition.spec,
        hoist_id,
        mode,
        stiffness_kN_m,
        SUSPENDED_ROPE_MASS_T,
        chart_max_load_t(mode),
        case=condition.case,
    )
    notes: list[str] = []
    if not mode.contractual_points:
        notes.append(
            f"hoists.{hoist_id} ({mode.name}): no contractual points, so the curve's maximum "
            "rated load is taken as 0 t (hook mass only) for the representative live load, "
            "the DNV psi floor and SF1"
        )
    if needs_stiffness(condition) and mode.runtime_overrides:
        notes.append(
            f"hoists.{hoist_id} ({mode.name}): the hook stiffness uses the authored reeving "
            "(falls and support node), not the split block"
        )
    if not notes:
        return setup
    return replace(setup, warnings=(*setup.warnings, *notes))


def factor_for_point(
    doc: CraneDocument,
    condition: LoadCondition,
    hoist_id: str,
    mode: HoistAnalysisMode,
    point: Optional[AnalysisPoint],
    boom_angle_deg: float,
) -> LiftSetup:
    """The lift setup of ``hoist_id`` in ``mode`` at ``boom_angle_deg`` under ``condition``.

    A legacy condition (``spec`` None) gives ``ConstantDynamicFactor(hoist.hook_daf)``
    with neutral lateral and foundation settings and no records. A rules condition calls
    its profile's ``lift_setup`` with the condition case (DNV Case II has its own
    incline). For an offboard lift the vertical hook stiffness comes from ``point``
    (see ``stiffness_point``; required then, unused otherwise) with the hook at
    ``stiffness_tackle_length_m``. The suspended rope is not counted yet (0 t).
    The same computation as ``LiftFactors.setup``, uncached.
    """
    return LiftFactors(doc, None).setup(condition, hoist_id, mode, boom_angle_deg, point=point)


def _angle_key(angle: float) -> float:
    return round(float(angle), 10)


class _Lru(OrderedDict[Hashable, Any]):
    """A dict that keeps at most ``limit`` entries (None: unbounded), dropping the oldest."""

    def __init__(self, limit: Optional[int]) -> None:
        super().__init__()
        self._limit = limit

    def put(self, key: Hashable, value: Any) -> None:
        self[key] = value
        self.move_to_end(key)
        if self._limit is not None:
            while len(self) > self._limit:
                self.popitem(last=False)


class LiftFactors:
    """``factor_for_point`` for one analysis run, each value computed once.

    The setup is cached per (condition case, hoist, mode, boom angle); a factor that does
    not depend on the stiffness (legacy, onboard) is cached without the angle. The
    stiffness point (one solve) and the stiffness itself are cached per hoist and angle
    (and tackle length), so the cases and conditions of a run share them. ``calc`` is any
    calculator of ``doc`` (the stiffness point does not read the environment); None when
    every stiffness point is supplied. ``max_entries`` bounds each cache (None: a run's
    caches grow with its angles). The caches assume ``doc`` is not edited meanwhile.
    """

    def __init__(
        self,
        doc: CraneDocument,
        calc: Optional[CraneCalculator],
        max_entries: Optional[int] = None,
    ) -> None:
        self._doc = doc
        self._calc = calc
        self._doc_dict: Optional[dict[str, Any]] = None
        self._kin: Optional[KinematicsAdapter] = None
        self._setups = _Lru(max_entries)
        self._points = _Lru(max_entries)
        self._stiffness = _Lru(max_entries)

    def _kinematics(self) -> tuple[dict[str, Any], KinematicsAdapter]:
        if self._doc_dict is None or self._kin is None:
            self._doc_dict = self._doc.model_dump()
            self._kin = KinematicsAdapter(self._doc_dict)
        return self._doc_dict, self._kin

    def _point(self, hoist_id: str, angle: float) -> Optional[AnalysisPoint]:
        key = (hoist_id, _angle_key(angle))
        if key not in self._points:
            if self._calc is None:
                raise RulesValidationError(
                    f"hoists.{hoist_id}: no analysis point for the hook stiffness at "
                    f"{angle:g} deg"
                )
            self._points.put(key, stiffness_point(self._calc, hoist_id, angle))
        return cast(Optional[AnalysisPoint], self._points[key])

    def _stiffness_kN_m(self, condition: LoadCondition, hoist_id: str, angle: float) -> float:
        doc_dict, kin = self._kinematics()
        tackle_m = stiffness_tackle_length_m(
            self._doc, condition, hoist_id, angle, kinematics=kin, doc_dict=doc_dict
        )
        key = (hoist_id, _angle_key(angle), round(tackle_m, 10))
        if key not in self._stiffness:
            point = self._point(hoist_id, angle)
            if point is None:
                raise RulesValidationError(
                    f"hoists.{hoist_id}: the hook stiffness point does not solve at "
                    f"{angle:g} deg"
                )
            self._stiffness.put(
                key,
                hook_stiffness_kN_per_m(
                    payload_hoist_stiffness_terms(self._doc, point, hoist_id, tackle_m)
                ),
            )
        return float(self._stiffness[key])

    def setup(
        self,
        condition: LoadCondition,
        hoist_id: str,
        mode: HoistAnalysisMode,
        angle: float,
        zero_probe: Optional[AnalysisPoint] = None,
        *,
        point: Optional[AnalysisPoint] = None,
    ) -> LiftSetup:
        """``factor_for_point(doc, condition, hoist_id, mode, <stiffness point>, angle)``.

        ``point`` is the stiffness point at ``angle`` when the caller has it. ``zero_probe``
        (``chart_envelope.ProbeSet.zero`` at ``angle``) saves its solve: in a mode without
        runtime overrides it is that same solve.
        """
        per_angle = needs_stiffness(condition)
        if per_angle:
            seed = point
            if seed is None and zero_probe is not None and not mode.runtime_overrides:
                seed = zero_probe
            point_key = (hoist_id, _angle_key(angle))
            if seed is not None and point_key not in self._points:
                self._points.put(point_key, seed)
        key = (condition.name, hoist_id, mode.name, _angle_key(angle) if per_angle else None)
        setup = cast(Optional[LiftSetup], self._setups.get(key))
        if setup is None:
            if condition.spec is None:
                setup = legacy_lift_setup(_hoist(self._doc, hoist_id))
            else:
                stiffness = self._stiffness_kN_m(condition, hoist_id, angle) if per_angle else 0.0
                setup = _profile_setup(self._doc, condition, hoist_id, mode, stiffness)
            self._setups.put(key, setup)
        return setup
