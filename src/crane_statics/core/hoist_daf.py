"""The hook DAF a condition's hoist entry authors: how it is shown and how an entered value
is stored. The one place the "1.0 vs None" rule lives.

``ConditionHoist.daf`` None is no override: under rules the factor is derived from the
standard, without rules it is 1.0.
"""

from __future__ import annotations

from typing import Optional

from ..data.models import CraneDocument


def shown_daf(daf: Optional[float]) -> float:
    """The factor an authored DAF stands for in a number field: an unset one is 1.0.

    (Under rules an unset DAF is derived from the standard: ``daf_is_derived``.)"""
    return 1.0 if daf is None else float(daf)


def daf_is_derived(doc: CraneDocument, daf: Optional[float]) -> bool:
    """Whether the factor of an entry authoring ``daf`` in ``doc`` is derived from the
    standard (rules present, no override) rather than the authored or default value."""
    return doc.rules is not None and daf is None


def entered_daf(value: Optional[float], *, rules: bool) -> Optional[float]:
    """The DAF to store for an entered ``value``; None is no override.

    Without rules 1.0 is the default factor and is stored as no override, so the document
    exports as it was authored. Under rules an entered 1.0 is an explicit override of the
    derived factor; clearing it (None) restores the derived one."""
    if value is None:
        return None
    number = float(value)
    if not rules and number == 1.0:
        return None
    return number
