"""Document-level validation of a rules (ABS/DNV) crane document."""

from __future__ import annotations

import math
from typing import Any, Optional

from ..calculation.rope_mass import derive_hook_geometry, hook_support_node_id
from ..data.models import CraneDocument, VesselMotion, is_solve_hoist, payload_hoist_ids

#: Gravitational acceleration, m/s^2.
GRAVITY_M_S2 = 9.81
#: Heavy-lift cranes are limited to this vessel acceleration, in g, per axis.
HEAVY_LIFT_MAX_ACCEL_G = 0.07
_REL_TOL = 1e-9


class RulesValidationError(ValueError):
    """A rules document is inconsistent; the message is one line and names the field."""


def tip_vertical_accel_g(motion: VesselMotion, support_x_m: float) -> tuple[float, float]:
    """ABS 5.17 a_v at a hook support node at crane-frame x ``support_x_m``: (a_v in g, lever).

    The linear ``|a_z|`` plus the angular accelerations times a bound on their lever arm
    over every slew, ``(|alpha_pitch| + |alpha_roll|) * (|x_ref| + |x_tip|)``. It grows
    with ``|support_x_m|``, so a bound on the reach bounds a_v.
    """
    lever_m = abs(motion.reference_x_m) + abs(float(support_x_m))
    angular = abs(motion.pitch_angular_accel_rad_s2) + abs(motion.roll_angular_accel_rad_s2)
    return (abs(motion.accel_z_m_s2) + angular * lever_m) / GRAVITY_M_S2, lever_m


def check_heavy_lift_a_v(
    condition_name: str,
    motion: VesselMotion,
    support_x_m: float,
    where: str = "at the boom tip",
) -> float:
    """ABS 2-2/11.3: a heavy-lift a_v over 0.07 g raises; returns a_v in g."""
    a_v_g, lever_m = tip_vertical_accel_g(motion, support_x_m)
    if a_v_g > HEAVY_LIFT_MAX_ACCEL_G * (1.0 + _REL_TOL):
        raise RulesValidationError(
            f"conditions.{condition_name}.vessel_motion: a_v {a_v_g:.4g} g {where} "
            f"(x {abs(float(support_x_m)):g} m, lever arm {lever_m:g} m) exceeds "
            f"{HEAVY_LIFT_MAX_ACCEL_G:g} g for heavy_lift; see the offshore crane requirements"
        )
    return a_v_g


def max_support_reach_m(doc_dict: dict[str, Any], hoist_id: str) -> Optional[float]:
    """An upper bound on ``|x|`` of ``hoist_id``'s hook support node at any boom angle.

    A boom-local node at (u, w) from the heel lies at ``heel_x + u cos(a) - w sin(a)``,
    so ``|x| <= |heel_x| + hypot(u, w)``; a fixed node is at its own x and a hanging node
    at the x of the node it hangs below (as ``KinematicsAdapter`` resolves them). None
    when the node cannot be resolved.
    """
    nodes = {n.get("id"): n for n in doc_dict.get("nodes", []) or []}
    node = nodes.get(hook_support_node_id(doc_dict, hoist_id))
    for _ in range(len(nodes) + 1):
        if node is None:
            return None
        if node.get("body") == "boom" and node.get("local_x_m") is not None:
            heel_x = float((nodes.get("boom_heel") or {}).get("x_m", 0.0))
            local = math.hypot(float(node["local_x_m"]), float(node.get("local_z_m") or 0.0))
            return abs(heel_x) + local
        if node.get("below_node_id") is not None:
            node = nodes.get(node["below_node_id"])
            continue
        if node.get("x_m") is not None:
            return abs(float(node["x_m"]))
        return None
    return None


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
            _validate_heavy_lift_tip(doc, name)
        if cond.lift == "offboard":
            for field in ("v_in_m_s", "v_t_m_s", "significant_wave_height_m"):
                if getattr(cond, field) is None:
                    raise RulesValidationError(f"{prefix}.{field}: required for offboard lifts")

    if any(c.lift == "offboard" for c in doc.conditions.values()):
        _validate_offboard_inputs(doc)
    _validate_hook_heights(doc)


def _validate_heavy_lift_tip(doc: CraneDocument, condition_name: str) -> None:
    """a_v at the largest boom-tip reach of each payload hoist is within 0.07 g.

    The profile checks a_v at each point's actual tip (``AbsProfile.lift_setup``); the
    reach bounds every such tip, so a document passing here passes there too.
    """
    motion = doc.conditions[condition_name].vessel_motion
    if motion.pitch_angular_accel_rad_s2 == 0.0 and motion.roll_angular_accel_rad_s2 == 0.0:
        return  # a_v is |a_z|, checked above
    doc_dict = doc.model_dump()
    for hoist_id in payload_hoist_ids(doc):
        reach = max_support_reach_m(doc_dict, hoist_id)
        if reach is None:
            continue
        check_heavy_lift_a_v(
            condition_name, motion, reach, where=f"at hoists.{hoist_id}'s largest boom-tip reach"
        )


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
