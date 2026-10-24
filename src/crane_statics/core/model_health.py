"""Actionable model health checks shared by both front ends."""

from __future__ import annotations

from typing import Optional

from ..data.models import CraneDocument, PRIMARY_NODE_IDS


def _sample(ids: list[str], limit: int = 3) -> str:
    head = ", ".join(ids[:limit]) if ids else "none"
    suffix = "" if len(ids) <= limit else f", +{len(ids) - limit} more"
    return f"{head}{suffix}"


def collect_model_health_issues(doc: Optional[CraneDocument]) -> tuple[list[str], list[str]]:
    """Return actionable blocking and warning issues for the model editor."""
    if doc is None:
        return [], []

    blocking: list[str] = []
    warnings: list[str] = []
    ropes_by_id = {rope.id: rope for rope in doc.ropes}

    duplicate_node_ids = sorted(
        {
            node.id
            for node in doc.nodes
            if node.id not in PRIMARY_NODE_IDS
            and sum(1 for other in doc.nodes if other.id == node.id) > 1
        }
    )
    if duplicate_node_ids:
        blocking.append(f"Duplicate node IDs: {_sample(duplicate_node_ids)}")

    missing_rope_segments = sorted(
        hoist.id
        for hoist in doc.hoists
        if not ropes_by_id.get(hoist.rope_id) or not ropes_by_id[hoist.rope_id].segments
    )
    if missing_rope_segments:
        blocking.append(f"Hoists missing rope segments: {_sample(missing_rope_segments)}")

    solve_hoist_ids = sorted(
        hoist.id
        for hoist in doc.hoists
        if ropes_by_id.get(hoist.rope_id) and ropes_by_id[hoist.rope_id].tension_mode == "solve"
    )
    if len(solve_hoist_ids) != 1:
        blocking.append(
            "Exactly one solve-mode boom hoist is required "
            f"(found {len(solve_hoist_ids)}: {_sample(solve_hoist_ids)})"
        )

    solve_hoists_with_contractual = sorted(
        hoist.id for hoist in doc.hoists if hoist.id in solve_hoist_ids and hoist.contractual_points
    )
    if solve_hoists_with_contractual:
        blocking.append(
            f"Solve-mode hoists cannot define contractual curves: "
            f"{_sample(solve_hoists_with_contractual)}"
        )

    hoists_without_contractual_points = sorted(
        hoist.id
        for hoist in doc.hoists
        if hoist.id not in solve_hoist_ids and not hoist.contractual_points
    )
    if hoists_without_contractual_points:
        warnings.append(
            f"Hoists without contractual points: {_sample(hoists_without_contractual_points)}"
        )

    splitable_without_split_points = sorted(
        hoist.id
        for hoist in doc.hoists
        if hoist.id not in solve_hoist_ids
        and bool(getattr(hoist, "splitable_block", False))
        and not list(getattr(hoist, "split_contractual_points", []))
    )
    if splitable_without_split_points:
        warnings.append(
            "Splitable hoists without split contractual points: "
            f"{_sample(splitable_without_split_points)}"
        )

    insufficient_rope_length = _hoists_with_insufficient_rope_length(doc, solve_hoist_ids)
    if insufficient_rope_length:
        warnings.append(
            f"Hoists with insufficient rope length: {_sample(insufficient_rope_length)}"
        )

    undrivable, unreachable = _payload_hook_height_issues(doc, solve_hoist_ids)
    if undrivable:
        warnings.append(
            "Hoists whose rope length and hook travel could not be derived: "
            f"{_sample(undrivable)}"
        )
    if unreachable:
        warnings.append(
            f"Hoists that cannot reach the lowest hook height at maximum outreach: "
            f"{_sample(unreachable)}"
        )

    return blocking, warnings


def _hoists_with_insufficient_rope_length(
    doc: CraneDocument, solve_hoist_ids: list[str]
) -> list[str]:
    """Boom-hoist ids whose authored rope_length_m is shorter than the reeving at 0 deg.

    Payload hoists are exempt: their rope length is derived from the lowest hook
    height, so it is sufficient by construction.
    """
    from ..calculation.rope_mass import reeved_length_at_angle_m

    doc_dict = doc.model_dump()
    flagged: list[str] = []
    for hoist in doc.hoists:
        if hoist.id not in solve_hoist_ids or hoist.rope_length_m is None:
            continue
        try:
            reference_length = reeved_length_at_angle_m(doc_dict, hoist.id, 0.0)
        except ValueError:
            continue
        if reference_length is not None and float(hoist.rope_length_m) < reference_length:
            flagged.append(hoist.id)
    return sorted(flagged)


def _payload_hook_height_issues(
    doc: CraneDocument, solve_hoist_ids: list[str]
) -> tuple[list[str], list[str]]:
    """(derivation failed, lowest hook height unreachable at max outreach) payload hoist ids.

    The second list is the honest form of the tackle clamp: at large outreach the
    sheave can sit below the lowest hook height, and there the hook stops at the
    sheave instead of reaching the water.
    """
    from ..calculation.rope_mass import hook_support_node_id
    from ..calculation.solver.kinematics import KinematicsAdapter

    doc_dict = doc.model_dump()
    kin = KinematicsAdapter(doc_dict)
    undrivable: list[str] = []
    unreachable: list[str] = []
    for hoist in doc.hoists:
        if hoist.id in solve_hoist_ids:
            continue
        if hoist.rope_length_m is None or hoist.max_hook_travel_m is None:
            undrivable.append(hoist.id)
            continue
        hook_height_m = hoist.lowest_hook_height_m
        if hook_height_m is None or hoist.outreach_max_m is None:
            continue
        support_id = hook_support_node_id(doc_dict, hoist.id)
        try:
            angle = kin.outreach_to_angle(float(hoist.outreach_max_m), hoist.id)
            support = (
                None if angle is None else kin.compute_all_node_positions(angle).get(support_id)
            )
        except (TypeError, ValueError, RuntimeError, ZeroDivisionError):
            continue
        if support is not None and float(support["z"]) < float(hook_height_m):
            unreachable.append(hoist.id)
    return sorted(undrivable), sorted(unreachable)


def format_issue_summary(issues: list[str]) -> str:
    if not issues:
        return ""
    extra = len(issues) - 1
    return issues[0] if extra <= 0 else f"{issues[0]} (+{extra} more)"


def health_status(
    doc: Optional[CraneDocument], validation_error: Optional[str] = None
) -> tuple[str, str, str]:
    """Return (severity, verdict, checks summary) for the model status strip."""
    if doc is None:
        return "none", "—", "Checks: —"

    blocking, warnings = collect_model_health_issues(doc)
    if validation_error:
        blocking = [f"Validation failed: {validation_error}", *blocking]

    if blocking:
        return "blocking", "⚠ Cannot apply changes", f"Checks: ⚠ {format_issue_summary(blocking)}"
    if warnings:
        return "warning", "✓ Valid with warnings", f"Checks: ⚠ {format_issue_summary(warnings)}"
    return "ok", "✓ Ready to apply", "Checks: ✓ Nodes unique, ropes complete, loads defined"
