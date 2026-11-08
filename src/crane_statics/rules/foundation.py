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


#: DNV-ST-0378 8.2.2.4 (p.91): SF1 >= 1.3 below 2500 kN capacity, >= 1.1 from 2500 kN.
_SF1_BAND_KN = 2500.0
_SF1_LOW = 1.3
_SF1_HIGH = 1.1


def dnv_sf1(swl_kN: float) -> float:
    """DNV 8.2.2.4 foundation factor SF1 at safe working load ``swl_kN``.

    1.3 for a capacity below 2500 kN, 1.1 for 2500 kN and more. It applies only when
    the operator cabin is above the slewing bearing; the caller decides that.
    """
    return _SF1_LOW if swl_kN < _SF1_BAND_KN else _SF1_HIGH
