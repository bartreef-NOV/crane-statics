"""The environmental inputs one analysis runs under.

A legacy document carries a single set of them (its ``environment``), so every analysis
runs under that one condition. A rules document names its conditions instead
(``doc.conditions``) and each one yields the in-service cases its standard defines
(``rules.profile_for(doc.rules).cases``). Analyses read their wind speed and vessel-motion
limits through ``LoadCondition`` rather than from the document: on a rules document the
document environment's wind speed and vessel motion are runtime placeholders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..data.models import ConditionSpec, CraneDocument, VesselMotion
from ..rules import profile_for
from ..rules.types import CaseSpec

DEFAULT_CONDITION_NAME = "default"


@dataclass(frozen=True)
class LoadCondition:
    """Wind speed and vessel-motion limits (± values) of one analysis case.

    A legacy document has one, ``spec`` and ``case`` None. On a rules document there is one
    per (condition, profile case), named ``"<condition>/<case>"``; ``spec`` is the
    condition and ``case`` the profile case its wind and vessel motion come from.
    """

    name: str
    wind_speed_m_s: float
    vessel_motion: VesselMotion
    spec: Optional[ConditionSpec] = None
    case: Optional[CaseSpec] = None

    @property
    def condition_name(self) -> str:
        """The name of the condition this case belongs to (its own name if legacy)."""
        return self.spec.name if self.spec is not None else self.name


def default_load_condition(doc: CraneDocument) -> LoadCondition:
    """The condition of the document's environment: what a legacy analysis uses."""
    return LoadCondition(
        name=DEFAULT_CONDITION_NAME,
        wind_speed_m_s=float(doc.environment.max_wind_speed_m_s),
        vessel_motion=doc.environment.vessel_motion,
    )


def condition_names(doc: CraneDocument) -> tuple[str, ...]:
    """The document's condition names, in document order (legacy: the default one)."""
    if doc.rules is None:
        return (DEFAULT_CONDITION_NAME,)
    return tuple(doc.conditions)


def _cases_of(doc: CraneDocument, spec: ConditionSpec) -> tuple[LoadCondition, ...]:
    assert doc.rules is not None
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
    """Every analysis case of the document: one per (condition, profile case) with rules."""
    if doc.rules is None:
        return (default_load_condition(doc),)
    return tuple(case for spec in doc.conditions.values() for case in _cases_of(doc, spec))


def condition_cases(doc: CraneDocument, condition_name: Optional[str]) -> tuple[LoadCondition, ...]:
    """The cases of the condition ``condition_name`` (None: the document's first one).

    A chart for one condition is the minimum over these. Raises ``KeyError`` naming an
    unknown condition.
    """
    if doc.rules is None:
        if condition_name not in (None, DEFAULT_CONDITION_NAME):
            raise KeyError(f"unknown load condition {condition_name!r}")
        return (default_load_condition(doc),)
    if condition_name is None:
        spec = next(iter(doc.conditions.values()), None)
        if spec is None:
            raise KeyError("the rules document has no load condition")
    else:
        spec = doc.conditions.get(condition_name)
        if spec is None:
            raise KeyError(f"unknown load condition {condition_name!r}")
    return _cases_of(doc, spec)


def scene_case(
    doc: CraneDocument, condition_name: Optional[str], case_name: Optional[str] = None
) -> LoadCondition:
    """The analysis case the Scene runs under: ``case_name`` of ``condition_name``.

    Legacy: the default condition (both names ignored). On a rules document None names the
    first condition; a ``case_name`` of None takes the profile's most severe case, its
    last one (profiles list their cases mildest first: ABS has one, DNV Case I then Case
    II, which adds the wind and 1.5 times the heel/trim). Raises ``KeyError`` naming an
    unknown condition or case.
    """
    if doc.rules is None:
        return default_load_condition(doc)
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
    reference point from the document environment; on a rules document those are
    placeholders, so a calculator for one case is built from this document instead. A
    legacy condition returns ``doc`` itself (the analysis is unchanged). The copy is not
    re-validated: a case may have zero wind, which the environment validator rejects.
    """
    if condition.spec is None:
        return doc
    environment = doc.environment.model_copy(
        update={
            "max_wind_speed_m_s": float(condition.wind_speed_m_s),
            "vessel_motion": condition.vessel_motion,
        }
    )
    return doc.model_copy(update={"environment": environment})
