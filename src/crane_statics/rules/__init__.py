"""Classification-rule support (ABS/DNV). Pure: no Qt, no UI."""

from __future__ import annotations

from ..data.models import RulesSpec
from .abs_profile import AbsProfile
from .dnv_profile import DnvProfile
from .validation import RulesValidationError, validate_rules_document


def profile_for(rules: RulesSpec) -> AbsProfile | DnvProfile:
    """The profile for the document's ``rules.standard``."""
    if rules.standard == "ABS":
        return AbsProfile()
    if rules.standard == "DNV":
        return DnvProfile()
    raise RulesValidationError(f"rules.standard: unknown standard {rules.standard!r}")


__all__ = [
    "AbsProfile",
    "DnvProfile",
    "RulesValidationError",
    "profile_for",
    "validate_rules_document",
]
