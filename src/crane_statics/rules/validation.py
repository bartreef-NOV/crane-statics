"""Document-level validation of a rules (ABS/DNV) crane document."""

from __future__ import annotations

from ..calculation.rope_mass import derive_hook_geometry
from ..data.models import CraneDocument, is_solve_hoist, payload_hoist_ids

#: Gravitational acceleration, m/s^2.
GRAVITY_M_S2 = 9.81
#: Heavy-lift cranes are limited to this vessel acceleration, in g, per axis.
HEAVY_LIFT_MAX_ACCEL_G = 0.07
_REL_TOL = 1e-9


class RulesValidationError(ValueError):
    """A rules document is inconsistent; the message is one line and names the field."""


def validate_rules_document(doc: CraneDocument) -> None:
    """Raise ``RulesValidationError`` if ``doc.rules`` is set and the document is inconsistent."""
    rules = doc.rules
    if rules is None:
        return
    if rules.standard == "DNV" and rules.crane_class is not None:
        raise RulesValidationError("rules.crane_class: not applicable under standard DNV")
    if rules.standard == "ABS" and rules.crane_class is None:
        raise RulesValidationError("rules.crane_class: required under standard ABS")

    limit = HEAVY_LIFT_MAX_ACCEL_G * GRAVITY_M_S2
    for name, cond in doc.conditions.items():
        prefix = f"conditions.{name}"
        if rules.crane_class == "heavy_lift":
            if cond.lift == "offboard":
                raise RulesValidationError(
                    f"{prefix}.lift: offboard lifts are not allowed for crane_class heavy_lift; "
                    "use crane_class offshore"
                )
            motion = cond.vessel_motion
            for axis in ("x", "y", "z"):
                value = getattr(motion, f"accel_{axis}_m_s2")
                if abs(value) > limit * (1.0 + _REL_TOL):
                    raise RulesValidationError(
                        f"{prefix}.vessel_motion.accel_{axis}_m_s2: |{value:g}| m/s^2 exceeds "
                        f"{HEAVY_LIFT_MAX_ACCEL_G:g} g for heavy_lift; see the offshore "
                        "crane requirements"
                    )
        if cond.lift == "offboard":
            for field in ("v_in_m_s", "v_t_m_s", "significant_wave_height_m"):
                if getattr(cond, field) is None:
                    raise RulesValidationError(f"{prefix}.{field}: required for offboard lifts")

    if any(c.lift == "offboard" for c in doc.conditions.values()):
        _validate_offboard_inputs(doc)
    _validate_hook_heights(doc)


def _validate_offboard_inputs(doc: CraneDocument) -> None:
    ropes = {r.id: r for r in doc.ropes}
    payload = set(payload_hoist_ids(doc))
    for hoist in doc.hoists:
        is_payload = hoist.id in payload
        is_boom = is_solve_hoist(doc, hoist.id)
        if not (is_payload or is_boom):
            continue
        rope = ropes.get(hoist.rope_id)
        if rope is None or rope.axial_stiffness_kN is None:
            raise RulesValidationError(
                f"hoists.{hoist.id}.rope.ea_kN: required for offboard lifts "
                "(or elastic_modulus_kN_mm2 with metallic_area_mm2)"
            )
        if is_payload and hoist.max_hoisting_speed_m_s is None:
            raise RulesValidationError(
                f"hoists.{hoist.id}.max_hoisting_speed_m_s: required for offboard lifts"
            )


def _validate_hook_heights(doc: CraneDocument) -> None:
    """Overrides must lie within each payload hoist's reachable hook heights.

    Reachable: from ``lowest_hook_height_m`` (the rope is sized for it) up to the
    support node's height at minimum outreach (the hook cannot pass its sheave).
    """
    overrides = {
        n: c.hook_height_override_m
        for n, c in doc.conditions.items()
        if c.hook_height_override_m is not None
    }
    if not overrides:
        return
    doc_dict = doc.model_dump()
    for hoist in doc.hoists:
        if hoist.id not in set(payload_hoist_ids(doc)):
            continue
        lowest = hoist.lowest_hook_height_m if hoist.lowest_hook_height_m is not None else 0.0
        try:
            derived = derive_hook_geometry(doc_dict, hoist.id, float(lowest))
        except ValueError:
            continue
        if derived is None:
            continue
        highest = float(lowest) + derived[0]
        for name, height in overrides.items():
            if height < lowest - 1e-9 or height > highest + 1e-9:
                raise RulesValidationError(
                    f"conditions.{name}.hook_height_override_m: {height:g} m is outside the "
                    f"reachable range {lowest:g} to {highest:g} m of hoist {hoist.id}"
                )
