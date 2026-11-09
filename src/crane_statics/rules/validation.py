"""Document-level validation of a rules (ABS/DNV) crane document."""

from __future__ import annotations

import math
from typing import Optional

from ..calculation.rope_mass import derive_hook_geometry, hook_support_node_id
from ..calculation.solver.kinematics import KinematicsAdapter, hoist_angle_bounds
from ..data.models import CraneDocument, Hoist, VesselMotion, is_solve_hoist, payload_hoist_ids

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


def heavy_lift_a_v_excess(
    condition_name: str,
    motion: VesselMotion,
    support_x_m: float,
    where: str = "at the boom tip",
) -> Optional[str]:
    """ABS 2-2/11.3: the message when a heavy-lift a_v exceeds 0.07 g there, else None."""
    a_v_g, lever_m = tip_vertical_accel_g(motion, support_x_m)
    if a_v_g <= HEAVY_LIFT_MAX_ACCEL_G * (1.0 + _REL_TOL):
        return None
    return (
        f"conditions.{condition_name}.vessel_motion: a_v {a_v_g:.4g} g {where} "
        f"(x {abs(float(support_x_m)):g} m, lever arm {lever_m:g} m) exceeds "
        f"{HEAVY_LIFT_MAX_ACCEL_G:g} g for heavy_lift; see the offshore crane requirements"
    )


def heavy_lift_tip_reach_m(doc: CraneDocument, hoist: Hoist) -> Optional[float]:
    """The largest ``|x|`` of ``hoist``'s hook support node over its rated angles, m.

    The rated angles are the operating range (``kinematics.hoist_angle_bounds``, as the
    Scene and the sweep take it from ``outreach_min_m``/``outreach_max_m``) widened to
    the angle of every contractual point (normal and split), which the sweep and the
    limit auto-set also evaluate. A boom-local node (u, w) lies at
    ``heel_x + R cos(a + atan2(w, u))``, so ``|x|`` peaks at an end of the range or where
    ``a + atan2(w, u)`` is a multiple of 180 deg; a fixed node does not move and a
    hanging node takes the x of the node it hangs below. The x values come from
    ``KinematicsAdapter.compute_all_node_positions``, as ``LiftFactors.support_x_m``.
    None when the geometry does not resolve.
    """
    doc_dict = doc.model_dump()
    support_id = hook_support_node_id(doc_dict, hoist.id)
    try:
        kin = KinematicsAdapter(doc_dict)
        lo, hi = hoist_angle_bounds(kin, hoist.id, hoist.outreach_min_m, hoist.outreach_max_m)
        for point in (*hoist.contractual_points, *hoist.split_contractual_points):
            angle = kin.outreach_to_angle(float(point.outreach_m), hoist.id)
            if angle is not None:
                lo, hi = min(lo, float(angle)), max(hi, float(angle))
        candidates = {lo, hi}
        node = kin.nodes.get(support_id)
        for _ in range(len(kin.nodes) + 1):
            if node is None or node.get("local_x_m") is not None:
                break
            node = kin.nodes.get(str(node.get("below_node_id")))
        if node is not None and node.get("body") == "boom" and node.get("local_x_m") is not None:
            phase = math.degrees(
                math.atan2(float(node.get("local_z_m") or 0.0), float(node["local_x_m"]))
            )
            for k in range(-3, 4):
                angle = -phase + 180.0 * k
                if lo < angle < hi:
                    candidates.add(angle)
        reach = 0.0
        for angle in candidates:
            position = kin.compute_all_node_positions(angle).get(support_id)
            if position is None:
                return None
            reach = max(reach, abs(float(position["x"])))
        return reach
    except (TypeError, ValueError, RuntimeError):
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
    """a_v at each payload hoist's largest rated boom-tip reach is within 0.07 g.

    ``heavy_lift_tip_reach_m`` covers every angle a sweep, a contractual point or the
    limit auto-set evaluates, so those never exceed 0.07 g; a point outside them (the
    Scene's free angle) only warns (``AbsProfile.lift_setup``).
    """
    motion = doc.conditions[condition_name].vessel_motion
    if motion.pitch_angular_accel_rad_s2 == 0.0 and motion.roll_angular_accel_rad_s2 == 0.0:
        return  # a_v is |a_z|, checked above
    payload = set(payload_hoist_ids(doc))
    for hoist in doc.hoists:
        if hoist.id not in payload:
            continue
        reach = heavy_lift_tip_reach_m(doc, hoist)
        if reach is None:
            continue
        message = heavy_lift_a_v_excess(
            condition_name,
            motion,
            reach,
            where=f"at hoists.{hoist.id}'s largest boom-tip reach in its operating range",
        )
        if message is not None:
            raise RulesValidationError(message)


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
