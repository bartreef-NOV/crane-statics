"""Pedestal and foundation load factors. Pure: no Qt, no UI."""

from __future__ import annotations

from .validation import RulesValidationError

#: ABS 2-2/5.15 (p.46): PF = 1.56 - LL/4000 (LL in kN), at most 1.5.
_PF_INTERCEPT = 1.56
_PF_LL_SCALE_KN = 4000.0
_PF_MAX = 1.5
_PF_MIN = {"offshore": 1.2, "heavy_lift": 1.0}


def abs_pedestal_factor(ll_kN: float, crane_class: str) -> float:
    """ABS 2-2/5.15 pedestal factor: ``clamp(1.56 - LL/4000, min, 1.5)``.

    ``min`` is 1.2 for offshore cranes and 1.0 for heavy-lift cranes.
    """
    lower = _PF_MIN.get(crane_class)
    if lower is None:
        raise RulesValidationError(f"rules.crane_class: no ABS pedestal factor for {crane_class!r}")
    return min(max(_PF_INTERCEPT - ll_kN / _PF_LL_SCALE_KN, lower), _PF_MAX)
