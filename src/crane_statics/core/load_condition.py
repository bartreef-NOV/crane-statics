"""The environmental inputs one analysis runs under.

Every document names its conditions (``doc.conditions``). Without rules each condition is
one analysis case, at its own wind speed and vessel motion; with rules each yields the
in-service cases its standard defines (``rules.profile_for(doc.rules).cases``). Analyses
read their wind speed, vessel-motion limits and per-hoist settings through
``LoadCondition`` rather than from the document: the document environment's wind speed
and vessel motion are runtime placeholders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..data.models import ConditionHoist, ConditionSpec, CraneDocument, VesselMotion
from ..rules import profile_for
from ..rules.types import CaseSpec

#: The condition name the v13 migration gives a document without rules.
DEFAULT_CONDITION_NAME = "default"

_NO_CONDITION = "document has no load condition"


@dataclass(frozen=True)
class LoadCondition:
    """Wind speed and vessel-motion limits (± values) of one analysis case.

    ``spec`` is the condition the case belongs to. Without rules there is one case per
    condition, named after it, ``case`` None. On a rules document there is one per
    (condition, profile case), named ``"<condition>/<case>"``; ``case`` is the profile
    case its wind and vessel motion come from.
    """

    name: str
    wind_speed_m_s: float
    vessel_motion: VesselMotion
    spec: ConditionSpec
    case: Optional[CaseSpec] = None

    @property
    def condition_name(self) -> str:
        """The name of the condition this case belongs to."""
        return self.spec.name

    @property
    def is_rules_case(self) -> bool:
        """Whether a rules profile derived this case (its factor comes from the standard)."""
        return self.case is not None

    def usable_hoist_ids(self) -> tuple[str, ...]:
        """The payload hoists usable under this case's condition, in the condition's order."""
        return tuple(self.spec.hoists)

    def hoist_settings(self, hoist_id: str) -> ConditionHoist:
        """``hoist_id``'s lead limits, DAF and chart under this case's condition.

        Raises ``KeyError`` naming the condition and the hoist when the condition does not
        list the hoist.
        """
        settings = self.spec.hoists.get(hoist_id)
        if settings is None:
            raise KeyError(
                f"conditions.{self.condition_name}.hoists.{hoist_id}: hoist {hoist_id!r} is "
                f"not usable in condition {self.condition_name!r}"
            )
        return settings


def condition_names(doc: CraneDocument) -> tuple[str, ...]:
    """The document's condition names, in document order."""
    return tuple(doc.conditions)


def _cases_of(doc: CraneDocument, spec: ConditionSpec) -> tuple[LoadCondition, ...]:
    if doc.rules is None:
        return (
            LoadCondition(
                name=spec.name,
                wind_speed_m_s=float(spec.wind_speed_m_s),
                vessel_motion=spec.vessel_motion,
                spec=spec,
            ),
        )
    return tuple(
        LoadCondition(
            name=f"{spec.name}/{case.name}",
            wind_speed_m_s=float(case.wind_speed_m_s),
            vessel_motion=case.vessel_motion,
            spec=spec,
            case=case,
        )
        for case in profile_for(doc.rules).cases(doc, spec)
    )


def load_conditions(doc: CraneDocument) -> tuple[LoadCondition, ...]:
    """Every analysis case of the document: one per condition, per profile case with rules.

    Empty for a document without conditions.
    """
    return tuple(case for spec in doc.conditions.values() for case in _cases_of(doc, spec))


def condition_cases(doc: CraneDocument, condition_name: Optional[str]) -> tuple[LoadCondition, ...]:
    """The cases of the condition ``condition_name`` (None: the document's first one).

    A chart for one condition is the minimum over these. Raises ``KeyError`` naming an
    unknown condition, or when the document has no condition at all.
    """
    if condition_name is None:
        spec = next(iter(doc.conditions.values()), None)
        if spec is None:
            raise KeyError(_NO_CONDITION)
    else:
        spec = doc.conditions.get(condition_name)
        if spec is None:
            raise KeyError(f"unknown load condition {condition_name!r}")
    return _cases_of(doc, spec)


def scene_case(
    doc: CraneDocument, condition_name: Optional[str], case_name: Optional[str] = None
) -> LoadCondition:
    """The analysis case the Scene runs under: ``case_name`` of ``condition_name``.

    None names the first condition; a ``case_name`` of None takes the condition's most
    severe case, its last one (a condition without rules has one; profiles list their cases
    mildest first: ABS has one, DNV Case I then Case II, which adds the wind and 1.5 times
    the heel/trim). Raises ``KeyError`` naming an unknown condition or case, or when the
    document has no condition.
    """
    cases = condition_cases(doc, condition_name)
    if case_name is None:
        return cases[-1]
    for case in cases:
        if case.case is not None and case.case.name == case_name:
            return case
    raise KeyError(f"unknown load case {case_name!r} of condition {condition_name!r}")


def condition_document(doc: CraneDocument, condition: LoadCondition) -> CraneDocument:
    """``doc`` with the environment ``condition`` runs under, for the calculator.

    The calculation reads the wind speed, the vessel-motion defaults and the pitch/roll
    reference point from the document environment; those are placeholders, so a
    calculator for one case is built from this document instead. The copy is not
    re-validated: a case may have zero wind, which the environment validator rejects.
    """
    environment = doc.environment.model_copy(
        update={
            "max_wind_speed_m_s": float(condition.wind_speed_m_s),
            "vessel_motion": condition.vessel_motion,
        }
    )
    return doc.model_copy(update={"environment": environment})
