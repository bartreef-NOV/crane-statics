"""Vertical hook stiffness from rope EA/L, by virtual work.

A unit hook load puts tension ``t_i`` in rope ``i``; its strain energy gives the
hook deflection ``sum(t_i^2 * L_i / EA_i)`` per kN, so the vertical hook stiffness
is ``C = 1 / sum(t_i^2 * L_i / EA_i)`` -- the ropes act as springs in series.
``L_i`` is the reeved length (each segment times its parts), which is exact
because a rope over frictionless sheaves carries one tension along its length.

Only the ropes are modelled: the active hoist and the boom hoist. Boom and
pedestal flexibility are ignored (owner decision; stiffer gives a higher dynamic
factor, so this is conservative). It is a documented deviation from the
standards, which ask for every element from the hook to the pedestal.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from ..calculation.results import AnalysisPoint
from ..calculation.rope_mass import (
    hook_support_node_id,
    reeved_length_at_angle_m,
    reeved_length_at_tackle_m,
)
from ..data.models import CraneDocument, Hoist, is_solve_hoist
from .validation import RulesValidationError

#: The solver's channel for the solve-mode (boom-hoist) rope tension.
BOOM_HOIST_CHANNEL = "boom_hoist"
#: The point's active-rope tension must be 1/falls to this relative tolerance.
_TENSION_REL_TOL = 1e-6


@dataclass(frozen=True)
class StiffnessTerm:
    """One rope: tension per kN of hook load, its reeved length and its EA."""

    tension_per_hook_kN: float
    reeved_length_m: float
    ea_kN: float


def hook_stiffness_kN_per_m(terms: Sequence[StiffnessTerm]) -> float:
    """Vertical hook stiffness ``1 / sum(t^2 * L / EA)``, in kN/m."""
    if not terms:
        raise RulesValidationError("hook stiffness: no rope terms to evaluate")
    compliance_m_per_kN = 0.0
    for term in terms:
        if term.ea_kN <= 0.0:
            raise RulesValidationError(f"hook stiffness: EA {term.ea_kN:g} kN must be positive")
        compliance_m_per_kN += term.tension_per_hook_kN**2 * term.reeved_length_m / term.ea_kN
    if compliance_m_per_kN <= 0.0:
        raise RulesValidationError("hook stiffness: the ropes carry no hook load")
    return 1.0 / compliance_m_per_kN


def worst_case_tackle_length_m() -> float:
    """Tackle length that maximises the stiffness over the hook's travel.

    The shortest rope is the stiffest: the hook hoisted to its sheave.
    """
    return 0.0


def payload_hoist_stiffness_terms(
    doc: CraneDocument,
    point: AnalysisPoint,
    hoist_id: str,
    tackle_length_m: Optional[float],
) -> list[StiffnessTerm]:
    """``[active hoist, boom hoist]`` stiffness terms at ``point``'s boom angle.

    The active hoist carries ``1 / falls`` per kN, falls being its hook segment's
    parts (dead-end fall included), over its reeved length with the hook
    ``tackle_length_m`` below the sheave (``None``: at ``lowest_hook_height_m``).
    The boom hoist carries ``point.sensitivity_rope_tensions["boom_hoist"]``.
    Compute ``point`` with ``offlead_deg=0`` so that sensitivity is the vertical
    hook load's alone. Split blocks are ignored: falls are the authored hook
    segment ``mult``, not ``split_falls``.

    Raises ``RulesValidationError`` when a rope's EA, the hook segment, the boom
    hoist or its sensitivity is missing, when ``point`` was computed for another
    active hoist, or when ``tackle_length_m`` is ``None`` and the hoist has no
    ``lowest_hook_height_m``.
    """
    doc_dict = doc.model_dump()
    hoist = _hoist(doc, hoist_id)
    if is_solve_hoist(doc, hoist_id):
        raise RulesValidationError(f"hoists.{hoist_id}: hook stiffness needs a payload hoist")
    falls = _hook_falls(doc, doc_dict, hoist)
    active_tension = point.sensitivity_rope_tensions.get(hoist.rope_id)
    if active_tension is None or not math.isclose(
        float(active_tension), 1.0 / falls, rel_tol=_TENSION_REL_TOL
    ):
        raise RulesValidationError(
            f"hoists.{hoist_id}: analysis point is not for this hoist (rope {hoist.rope_id} "
            f"tension {active_tension} kN/kN, expected 1/{falls})"
        )
    if tackle_length_m is None and hoist.lowest_hook_height_m is None:
        raise RulesValidationError(
            f"hoists.{hoist_id}.lowest_hook_height_m: required when no tackle length is given"
        )
    active_length_m = reeved_length_at_tackle_m(
        doc_dict, hoist_id, point.boom_angle_deg, tackle_length_m
    )
    if active_length_m is None:
        raise RulesValidationError(
            f"hoists.{hoist_id}: reeved length unresolved at {point.boom_angle_deg:g} deg"
        )

    boom_hoists = [h for h in doc.hoists if is_solve_hoist(doc, h.id)]
    if len(boom_hoists) != 1:
        raise RulesValidationError(
            f"hoists: hook stiffness needs exactly one boom hoist (tension_mode solve), "
            f"found {len(boom_hoists)}"
        )
    boom = boom_hoists[0]
    boom_tension = point.sensitivity_rope_tensions.get(BOOM_HOIST_CHANNEL)
    if boom_tension is None:
        raise RulesValidationError(
            f"hoists.{boom.id}: no boom-hoist tension sensitivity in the analysis point"
        )
    boom_length_m = reeved_length_at_angle_m(doc_dict, boom.id, point.boom_angle_deg)
    if boom_length_m is None:
        raise RulesValidationError(
            f"hoists.{boom.id}: reeved length unresolved at {point.boom_angle_deg:g} deg"
        )

    return [
        StiffnessTerm(1.0 / falls, active_length_m, _ea_kN(doc, hoist)),
        StiffnessTerm(float(boom_tension), boom_length_m, _ea_kN(doc, boom)),
    ]


def _hoist(doc: CraneDocument, hoist_id: str) -> Hoist:
    hoist = next((h for h in doc.hoists if h.id == hoist_id), None)
    if hoist is None:
        raise RulesValidationError(f"hoists.{hoist_id}: not defined")
    return hoist


def _ea_kN(doc: CraneDocument, hoist: Hoist) -> float:
    rope = next((r for r in doc.ropes if r.id == hoist.rope_id), None)
    ea = None if rope is None else rope.axial_stiffness_kN
    if ea is None:
        raise RulesValidationError(
            f"hoists.{hoist.id}.rope.ea_kN: required for hook stiffness "
            "(or elastic_modulus_kN_mm2 with metallic_area_mm2)"
        )
    return float(ea)


def _hook_falls(doc: CraneDocument, doc_dict: dict[str, Any], hoist: Hoist) -> int:
    """Parts of the segment between the hook and the node it hangs from."""
    support_id = hook_support_node_id(doc_dict, hoist.id)
    endpoints = {support_id, hoist.load_node_id}
    rope = next((r for r in doc.ropes if r.id == hoist.rope_id), None)
    for seg in [] if rope is None else rope.segments:
        if {seg.from_node_id, seg.to_node_id} == endpoints:
            return max(1, int(seg.mult))
    raise RulesValidationError(
        f"hoists.{hoist.id}: no rope segment between hook {hoist.load_node_id!r} "
        f"and {support_id!r}"
    )
