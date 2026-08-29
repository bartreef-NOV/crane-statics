"""Actionable model health checks shared by both front ends."""

from __future__ import annotations

from typing import Optional

from ..data.models import PRIMARY_NODE_IDS


def _sample(ids: list[str], limit: int = 3) -> str:
    head = ", ".join(ids[:limit]) if ids else "none"
    suffix = "" if len(ids) <= limit else f", +{len(ids) - limit} more"
    return f"{head}{suffix}"


def collect_model_health_issues(doc) -> tuple[list[str], list[str]]:
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

    insufficient_rope_length = _hoists_with_insufficient_rope_length(doc)
    if insufficient_rope_length:
        warnings.append(
            f"Hoists with insufficient rope length: {_sample(insufficient_rope_length)}"
        )

    return blocking, warnings


def _hoists_with_insufficient_rope_length(doc) -> list[str]:
    """Hoist ids whose authored rope_length_m can't reach max hook travel at 0 deg boom angle."""
    from ..calculation.rope_mass import compute_reference_reeved_length_m

    doc_dict = doc.model_dump()
    flagged: list[str] = []
    for hoist in doc.hoists:
        if hoist.rope_length_m is None:
            continue
        try:
            reference_length = compute_reference_reeved_length_m(doc_dict, hoist.id)
        except ValueError:
            continue
        if reference_length is not None and float(hoist.rope_length_m) < reference_length:
            flagged.append(hoist.id)
    return sorted(flagged)


def format_issue_summary(issues: list[str]) -> str:
    if not issues:
        return ""
    extra = len(issues) - 1
    return issues[0] if extra <= 0 else f"{issues[0]} (+{extra} more)"


def health_status(doc, validation_error: Optional[str] = None) -> tuple[str, str, str]:
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
