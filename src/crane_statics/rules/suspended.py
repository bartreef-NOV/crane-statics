"""The suspended rope: the hook-segment rope a lifted load carries. Pure: no Qt, no UI.

Both standards count it in the live load (ABS LL, DNV W), so on a rules run it is amplified
with the payload and the hook block instead of being dead load on the crane. The solver
leaves exactly this mass out of its dead node masses (``amplified_rope_hoist_id``), so the
crane's total rope mass is unchanged.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from ..calculation.rope_mass import EffectiveMultFn, hook_segment_mass_t


def suspended_rope_mass_t(
    doc_dict: dict[str, Any],
    hoist_id: str,
    positions: Mapping[str, Mapping[str, float]],
    effective_mult: Optional[EffectiveMultFn] = None,
) -> float:
    """Mass of ``hoist_id``'s rope from its support node to its hook at ``positions``, t.

    Linear mass x hook-segment length x mult; ``effective_mult`` gives the mult a split
    block reeves (``rope_mass.falls_override_effective_mult``). ``positions`` must put
    the hook where the analysis does (``rope_mass.active_hook_positions``). 0 for an
    unknown hoist or one without a hook.
    """
    return hook_segment_mass_t(doc_dict, hoist_id, positions, effective_mult)
