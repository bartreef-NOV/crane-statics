"""Toolkit-neutral document mutations shared by both front ends."""

from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Optional

from pydantic import ValidationError

from ..data.authored_form import document_to_authored_form, tagged_load_chart
from ..data.authored_models import (
    AuthoredDocument,
    format_authored_validation_error,
    hoist_node_prefix,
)
from ..data.models import (
    Body,
    ConditionHoist,
    ConditionSpec,
    ContractualPoint,
    CraneDocument,
    Hoist,
    MassPoint,
    Node,
    Rope,
    Segment,
    WindArea,
    RESERVED_TOPOLOGY_NODE_IDS,
    MANAGED_HOOK_FALLBACK_DROP_M,
    _is_managed_hook_node_id,
    _managed_hook_node_id,
)
from ..data.normalize import derive_payload_hoist_rope_geometry
from ..rules import RulesValidationError, validate_rules_document
from .hoist_daf import entered_daf

BOOM_BODY_ID = "boom"
CONDITION_NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")


class DocumentEditError(ValueError):
    """Raised when an edit would violate a document invariant."""


# ----------------------------------------------------------------------
# Builders — turn plain field values into validated document objects
# ----------------------------------------------------------------------


def build_node(
    body_id: str,
    node_id: str,
    *,
    hanging: bool = False,
    below_node_id: str = "",
    x_m: float = 0.0,
    z_m: float = 0.0,
    local_x_m: float = 0.0,
    local_z_m: float = 0.0,
) -> Node:
    node_id = node_id.strip()
    if not node_id:
        raise DocumentEditError("Node ID cannot be empty")
    if hanging:
        below = below_node_id.strip()
        if not below:
            raise DocumentEditError("Hang From Node ID is required for hanging nodes")
        return Node(id=node_id, body=body_id, x_m=0.0, z_m=0.0, below_node_id=below)
    if body_id == BOOM_BODY_ID:
        return Node(
            id=node_id,
            body=body_id,
            x_m=0.0,
            z_m=0.0,
            local_x_m=float(local_x_m),
            local_z_m=float(local_z_m),
        )
    return Node(id=node_id, body=body_id, x_m=float(x_m), z_m=float(z_m))


def build_mass_point(
    body_id: str,
    mass_point_id: str,
    mass_t: float,
    *,
    x_m: float = 0.0,
    y_m: float = 0.0,
    z_m: float = 0.0,
    local_x_m: float = 0.0,
    local_y_m: float = 0.0,
    local_z_m: float = 0.0,
) -> MassPoint:
    mass_point_id = mass_point_id.strip()
    if not mass_point_id:
        raise DocumentEditError("Mass point ID cannot be empty")
    boom = body_id == BOOM_BODY_ID
    return MassPoint(
        id=mass_point_id,
        mass_t=float(mass_t),
        x_m=0.0 if boom else float(x_m),
        y_m=0.0 if boom else float(y_m),
        z_m=0.0 if boom else float(z_m),
        local_x_m=float(local_x_m) if boom else None,
        local_y_m=float(local_y_m) if boom else None,
        local_z_m=float(local_z_m) if boom else None,
    )


def build_wind_area(
    body_id: str,
    wind_area_id: str,
    area_w_m2: float,
    area_v_m2: float,
    *,
    x_m: float = 0.0,
    z_m: float = 0.0,
    local_x_m: float = 0.0,
    local_z_m: float = 0.0,
    cd: float = 1.0,
) -> WindArea:
    wind_area_id = wind_area_id.strip()
    if not wind_area_id:
        raise DocumentEditError("Wind area ID cannot be empty")
    boom = body_id == BOOM_BODY_ID
    return WindArea(
        id=wind_area_id,
        area_w_m2=float(area_w_m2),
        area_v_m2=float(area_v_m2),
        x_m=0.0 if boom else float(x_m),
        z_m=0.0 if boom else float(z_m),
        local_x_m=float(local_x_m) if boom else None,
        local_z_m=float(local_z_m) if boom else None,
        cd=float(cd),
    )


def build_payload_hoist(
    hoist_id: str,
    support_node_id: str,
    *,
    falls: int = 1,
    lower_block_mass_t: float = 0.0,
    splitable_block: bool = False,
    split_falls: Optional[int] = None,
    split_lower_block_mass_t: Optional[float] = None,
    linear_mass_kg_m: float = 0.0,
    lowest_hook_height_m: float = 0.0,
) -> Hoist:
    """A payload hoist. Its lead limits, DAF and charts are per condition
    (``DocumentEditor.set_condition_hoist_settings``), not part of the hoist."""
    hoist_id = hoist_id.strip()
    if not hoist_id:
        raise DocumentEditError("Hoist ID cannot be empty")
    if splitable_block:
        if split_falls is None or int(split_falls) > int(falls):
            raise DocumentEditError("Split falls must be <= normal falls")
        if split_lower_block_mass_t is None or float(split_lower_block_mass_t) > float(
            lower_block_mass_t
        ):
            raise DocumentEditError("Split lower block mass must be <= lower block mass")

    return Hoist(
        id=hoist_id,
        rope_id=f"{hoist_id}__rope",
        load_node_id=_managed_hook_node_id(hoist_id),
        support_node_id=support_node_id.strip(),
        falls=int(falls),
        lower_block_mass_t=float(lower_block_mass_t),
        splitable_block=bool(splitable_block),
        split_falls=None if split_falls is None else int(split_falls),
        split_lower_block_mass_t=(
            None if split_lower_block_mass_t is None else float(split_lower_block_mass_t)
        ),
        linear_mass_kg_m=max(0.0, float(linear_mass_kg_m)),
        lowest_hook_height_m=float(lowest_hook_height_m),
    )


def build_segment(from_node_id: str, to_node_id: str, mult: int = 1) -> Segment:
    from_node_id = from_node_id.strip()
    to_node_id = to_node_id.strip()
    if not from_node_id or not to_node_id:
        raise DocumentEditError("Segment endpoints are required")
    if from_node_id == to_node_id:
        raise DocumentEditError("Segment endpoints must differ")
    return Segment(from_node_id=from_node_id, to_node_id=to_node_id, mult=max(1, int(mult)))


def _check_condition_hoist_values(
    offlead_deg: float, sidelead_deg: float, daf: Optional[float]
) -> None:
    """The bounds of ``ConditionHoist``: leads >= 0, an authored DAF >= 1."""
    if float(offlead_deg) < 0.0 or float(sidelead_deg) < 0.0:
        raise DocumentEditError("Lead angles must be >= 0")
    if daf is not None and float(daf) < 1.0:
        raise DocumentEditError("DAF must be >= 1")


@dataclass(frozen=True)
class TaggedChartPoint:
    """One authored load-chart point of a payload hoist and the conditions it names."""

    outreach_m: float
    load_t: float
    conditions: tuple[str, ...]


def build_contractual_point(outreach_m: float, load_t: float) -> ContractualPoint:
    return ContractualPoint(outreach_m=float(outreach_m), load_t=float(load_t))


def authored_document_error(doc: CraneDocument) -> Optional[str]:
    """Why ``doc`` does not save as a valid authored document; None when it does."""
    try:
        AuthoredDocument.model_validate(document_to_authored_form(doc))
    except ValidationError as exc:
        return format_authored_validation_error(exc)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        return str(exc)
    return None


# ----------------------------------------------------------------------
# Editor
# ----------------------------------------------------------------------


class DocumentEditor:
    """Applies validated structural edits to a crane document in place."""

    def __init__(self, document: CraneDocument):
        self._doc = document

    @property
    def document(self) -> CraneDocument:
        return self._doc

    def refresh_derived_geometry(self) -> None:
        """Re-derive every payload hoist's hook travel and rope length.

        Any edit can move the sheave -- a node, a hinge, a gravity change that
        shifts nothing but is cheap to re-run -- and both values are consequences
        of each hoist's lowest hook height, so they are recomputed rather than carried.
        """
        derive_payload_hoist_rope_geometry(self._doc)

    # -- discovery -----------------------------------------------------

    def editable_node_ids(self) -> list[str]:
        return [
            n.id
            for n in self._doc.nodes
            if n.id not in RESERVED_TOPOLOGY_NODE_IDS and not _is_managed_hook_node_id(n.id)
        ]

    def visible_nodes_for_body(self, body_id: str) -> list[Node]:
        nodes = [
            n
            for n in self._doc.nodes
            if n.body == body_id
            and n.id not in RESERVED_TOPOLOGY_NODE_IDS
            and not _is_managed_hook_node_id(n.id)
        ]
        return sorted(nodes, key=lambda n: n.id)

    def rope_for_hoist(self, hoist: Hoist) -> Optional[Rope]:
        return next((r for r in self._doc.ropes if r.id == hoist.rope_id), None)

    def is_solve_hoist(self, hoist: Hoist) -> bool:
        rope = self.rope_for_hoist(hoist)
        mode = "fixed" if rope is None or rope.tension_mode is None else str(rope.tension_mode)
        return mode == "solve"

    def visible_rope_segments(self, hoist: Hoist) -> list[tuple[int, Segment]]:
        """Rope segments excluding the synthesized managed-hook segment."""
        rope = self.rope_for_hoist(hoist)
        if rope is None:
            return []
        managed_hook_id = str(hoist.load_node_id)
        solve = self.is_solve_hoist(hoist)
        return [
            (idx, seg)
            for idx, seg in enumerate(rope.segments)
            if solve or managed_hook_id not in (seg.from_node_id, seg.to_node_id)
        ]

    def _hoist(self, hoist_id: str) -> Hoist:
        hoist = next((h for h in self._doc.hoists if h.id == hoist_id), None)
        if hoist is None:
            raise DocumentEditError(f"Hoist '{hoist_id}' not found")
        return hoist

    def _body(self, body_id: str) -> Body:
        body = next((b for b in self._doc.bodies if b.id == body_id), None)
        if body is None:
            raise DocumentEditError(f"Component '{body_id}' not found")
        return body

    # -- nodes ---------------------------------------------------------

    def add_node(self, node: Node) -> None:
        self._guard_node_id(node.id, previous_id=None)
        self._doc.nodes.append(node)

    def update_node(self, previous_id: str, node: Node) -> None:
        self._guard_node_id(node.id, previous_id=previous_id)
        for index, existing in enumerate(self._doc.nodes):
            if existing.id == previous_id:
                self._doc.nodes[index] = node
                break
        else:
            raise DocumentEditError(f"Node '{previous_id}' not found")
        if node.id != previous_id:
            self._rename_node_references(previous_id, node.id)

    def _rename_node_references(self, previous_id: str, new_id: str) -> None:
        """Carry a renamed node through everything that names it.

        A node id is a reference, not a label: ropes are reeved through it, hoists
        hang from it and other nodes hang below it. Renaming without rewriting would
        leave the document pointing at a node that no longer exists, which the
        authored schema rejects on the next save.
        """
        for rope in self._doc.ropes:
            for segment in rope.segments:
                if segment.from_node_id == previous_id:
                    segment.from_node_id = new_id
                if segment.to_node_id == previous_id:
                    segment.to_node_id = new_id
        for hoist in self._doc.hoists:
            if hoist.load_node_id == previous_id:
                hoist.load_node_id = new_id
            if hoist.support_node_id == previous_id:
                hoist.support_node_id = new_id
        for other in self._doc.nodes:
            if other.below_node_id == previous_id:
                other.below_node_id = new_id
        for body in self._doc.bodies:
            for mass_point in body.mass_points:
                if mass_point.below_node_id == previous_id:
                    mass_point.below_node_id = new_id

    def delete_node(self, node_id: str) -> None:
        remaining = [n for n in self._doc.nodes if n.id != node_id]
        if len(remaining) == len(self._doc.nodes):
            raise DocumentEditError(f"Node '{node_id}' not found")
        self._doc.nodes = remaining

    def _guard_node_id(self, node_id: str, *, previous_id: Optional[str]) -> None:
        if node_id in RESERVED_TOPOLOGY_NODE_IDS and node_id != previous_id:
            raise DocumentEditError(
                f"Node '{node_id}' is reserved for primary structure. "
                "Edit it in the Primary Structure section."
            )
        if node_id != previous_id and any(n.id == node_id for n in self._doc.nodes):
            raise DocumentEditError(
                f"Node '{node_id}' already exists. "
                "Node IDs must be globally unique across all components."
            )

    # -- mass points ---------------------------------------------------

    def add_mass_point(self, body_id: str, mass_point: MassPoint) -> None:
        self._body(body_id).mass_points.append(mass_point)

    def update_mass_point(self, body_id: str, index: int, mass_point: MassPoint) -> None:
        points = self._body(body_id).mass_points
        self._guard_index(index, len(points), "mass point")
        points[index] = mass_point

    def delete_mass_point(self, body_id: str, index: int) -> None:
        points = self._body(body_id).mass_points
        self._guard_index(index, len(points), "mass point")
        points.pop(index)

    # -- wind areas ----------------------------------------------------

    def add_wind_area(self, body_id: str, wind_area: WindArea) -> None:
        self._body(body_id).wind_areas.append(wind_area)

    def update_wind_area(self, body_id: str, index: int, wind_area: WindArea) -> None:
        areas = self._body(body_id).wind_areas
        self._guard_index(index, len(areas), "wind area")
        areas[index] = wind_area

    def delete_wind_area(self, body_id: str, index: int) -> None:
        areas = self._body(body_id).wind_areas
        self._guard_index(index, len(areas), "wind area")
        areas.pop(index)

    # -- hoists --------------------------------------------------------

    @contextmanager
    def _atomic(self) -> Iterator[None]:
        """Put the document back exactly as it was if the block raises."""
        saved = self._doc.model_copy(deep=True)
        try:
            yield
        except BaseException:
            self._doc.__dict__.update(saved.__dict__)
            raise

    @contextmanager
    def _keeping_valid(self) -> Iterator[None]:
        """``_atomic``, and a document that saved as a valid authored document before the
        block still does after it: otherwise the block is undone and refused.

        A document that was already incomplete (a hoist added but not charted yet, a
        document built in code) is not held to it: the edit may be a step towards valid.
        """
        valid_before = authored_document_error(self._doc) is None
        with self._atomic():
            yield
            if valid_before:
                error = authored_document_error(self._doc)
                if error is not None:
                    raise DocumentEditError(error)

    def add_hoist(self, hoist: Hoist, tension_mode: str = "fixed") -> None:
        """Add ``hoist``. A payload hoist is usable in every condition, with no lead
        limits (``offlead_deg`` 0.0, ``sidelead_deg`` 0.0), no DAF override and no chart
        points yet (its settings are edited per condition: ``set_condition_hoist``). The
        boom hoist (``tension_mode`` "solve") is listed in no condition.

        Until it has chart points in each condition the document does not save (the
        authored contract needs them): add them, or drop the conditions it is not
        meant for with ``remove_condition_hoist``.

        Everything is checked first: a rejected edit leaves the document unchanged.
        """
        if any(h.id == hoist.id for h in self._doc.hoists):
            raise DocumentEditError(f"Hoist '{hoist.id}' already exists")
        if any(r.id == hoist.rope_id for r in self._doc.ropes):
            raise DocumentEditError(f"Generated rope '{hoist.rope_id}' already exists")

        with self._atomic():
            self._doc.ropes.append(
                Rope(
                    id=hoist.rope_id,
                    segments=[],
                    tension_mode=tension_mode,
                    linear_mass_kg_m=float(hoist.linear_mass_kg_m),
                )
            )
            self._doc.hoists.append(hoist)
            self.sync_managed_payload_hook(hoist)
            if tension_mode == "solve":
                return
            for spec in self._doc.conditions.values():
                spec.hoists[hoist.id] = ConditionHoist(offlead_deg=0.0)

    def update_boom_hoist(
        self,
        hoist_id: str,
        *,
        linear_mass_kg_m: float,
        rope_length_m: Optional[float],
    ) -> None:
        """Edit the two boom-hoist fields that are authored rather than derived."""
        current = self._hoist(hoist_id)
        if not self.is_solve_hoist(current):
            raise DocumentEditError(f"Hoist '{hoist_id}' is not the boom hoist")
        rope = self.rope_for_hoist(current)
        if rope is None:
            raise DocumentEditError("Boom hoist rope is missing")
        rope.linear_mass_kg_m = max(0.0, float(linear_mass_kg_m))
        current.linear_mass_kg_m = max(0.0, float(linear_mass_kg_m))
        current.rope_length_m = None if rope_length_m is None else max(0.0, float(rope_length_m))

    def update_hoist(self, hoist_id: str, edited: Hoist) -> None:
        """Replace payload hoist ``hoist_id`` by ``edited``.

        A new id renames the hoist in every condition that lists it (same place, same
        settings and charts); its lead limits, DAF and charts are edited per condition.
        Everything is checked first: a rejected edit leaves the document unchanged.
        """
        current = self._hoist(hoist_id)
        if self.is_solve_hoist(current):
            raise DocumentEditError(f"Hoist '{hoist_id}' is the boom hoist; use update_boom_hoist")
        new_id = edited.id
        if new_id != hoist_id and any(h.id == new_id for h in self._doc.hoists):
            raise DocumentEditError(f"Hoist '{new_id}' already exists")

        with self._atomic():
            # The derived pair belongs to the document, not the edit form.
            edited.max_hook_travel_m = current.max_hook_travel_m
            edited.rope_length_m = current.rope_length_m
            edited.rope_id = current.rope_id
            edited.load_node_id = current.load_node_id
            # The hoist's lead limits, DAF and charts live in the conditions.
            self.sync_managed_payload_hook(edited)

            for index, hoist in enumerate(self._doc.hoists):
                if hoist.id == hoist_id:
                    self._doc.hoists[index] = edited
                    break

            rope = self.rope_for_hoist(edited)
            if rope is not None:
                rope.tension_mode = "fixed"
                rope.linear_mass_kg_m = float(edited.linear_mass_kg_m)

            if new_id != hoist_id:
                for spec in self._doc.conditions.values():
                    if hoist_id in spec.hoists:
                        spec.hoists = {
                            (new_id if hid == hoist_id else hid): entry
                            for hid, entry in spec.hoists.items()
                        }

    def delete_hoist(self, hoist_id: str) -> None:
        """Delete payload hoist ``hoist_id``, its entries in every condition and the
        sheaves only it used. Refused when that would leave a condition listing no hoist
        (or otherwise break a document that saves)."""
        hoist = self._hoist(hoist_id)
        if self.is_solve_hoist(hoist):
            raise DocumentEditError("Boom hoist cannot be deleted from this table")
        for spec in self._doc.conditions.values():
            if list(spec.hoists) == [hoist_id]:
                raise DocumentEditError(
                    f"Hoist '{hoist_id}' is the only hoist usable in condition "
                    f"{spec.name!r}; make another hoist usable there first"
                )
        with self._keeping_valid():
            self._delete_hoist(hoist)

    def _delete_hoist(self, hoist: Hoist) -> None:
        hoist_id = hoist.id
        rope_id = hoist.rope_id
        managed_hook_id = str(hoist.load_node_id)
        rope = self.rope_for_hoist(hoist)
        path_node_ids = {
            end
            for seg in (rope.segments if rope else [])
            for end in (seg.from_node_id, seg.to_node_id)
        }
        self._doc.hoists = [h for h in self._doc.hoists if h.id != hoist_id]
        # No condition may list a hoist the document no longer has.
        for spec in self._doc.conditions.values():
            spec.hoists.pop(hoist_id, None)

        if not any(h.rope_id == rope_id for h in self._doc.hoists):
            self._doc.ropes = [r for r in self._doc.ropes if r.id != rope_id]
        if _is_managed_hook_node_id(managed_hook_id):
            self._doc.nodes = [n for n in self._doc.nodes if n.id != managed_hook_id]
        self._remove_orphaned_hoist_nodes(hoist_id, path_node_ids)

    def _remove_orphaned_hoist_nodes(self, hoist_id: str, path_node_ids: set[str]) -> None:
        """Drop the deleted hoist's own sheave/winch nodes that no remaining rope uses."""
        prefix = hoist_node_prefix(hoist_id)
        in_use = {
            end
            for rope in self._doc.ropes
            for seg in rope.segments
            for end in (seg.from_node_id, seg.to_node_id)
        }
        self._doc.nodes = [
            n
            for n in self._doc.nodes
            if not (
                n.id in path_node_ids
                and n.id.startswith(prefix)
                and n.id not in RESERVED_TOPOLOGY_NODE_IDS
                and n.id not in in_use
                and not _is_managed_hook_node_id(n.id)
            )
        ]

    def resolved_support_node_id(self, hoist: Hoist) -> str:
        support = str(hoist.support_node_id or "").strip()
        if support:
            return support
        load_node = next((n for n in self._doc.nodes if n.id == hoist.load_node_id), None)
        if load_node is not None and load_node.below_node_id:
            return str(load_node.below_node_id)
        return str(hoist.load_node_id)

    def sync_managed_payload_hook(self, hoist: Hoist) -> None:
        """Recreate the synthesized hook node and its rope segment for a payload hoist."""
        if self.is_solve_hoist(hoist):
            return

        support_node_id = self.resolved_support_node_id(hoist)
        support_node = next((n for n in self._doc.nodes if n.id == support_node_id), None)
        if support_node is None:
            raise DocumentEditError(
                f"Payload hoist '{hoist.id}' support node '{support_node_id}' not found"
            )

        managed_hook_id = _managed_hook_node_id(hoist.id)
        hoist.load_node_id = managed_hook_id
        hoist.support_node_id = support_node_id
        hoist.falls = int(hoist.falls or 1)

        managed_node = Node(
            id=managed_hook_id,
            body=support_node.body,
            x_m=0.0,
            z_m=0.0,
            below_node_id=support_node_id,
            hanging_drop_m=MANAGED_HOOK_FALLBACK_DROP_M,
        )
        self._doc.nodes = [n for n in self._doc.nodes if n.id != managed_hook_id]
        self._doc.nodes.append(managed_node)

        rope = self.rope_for_hoist(hoist)
        if rope is None:
            return
        rope.segments = [
            seg
            for seg in rope.segments
            if managed_hook_id not in (seg.from_node_id, seg.to_node_id)
        ]
        rope.segments.append(
            Segment(
                from_node_id=support_node_id,
                to_node_id=managed_hook_id,
                mult=max(1, int(hoist.falls or 1)),
            )
        )

    # -- rope segments -------------------------------------------------

    def get_or_create_rope(self, hoist: Hoist) -> Rope:
        rope = self.rope_for_hoist(hoist)
        if rope is not None:
            return rope
        rope = Rope(id=hoist.rope_id, segments=[], tension_mode="fixed")
        self._doc.ropes.append(rope)
        return rope

    def add_rope_segment(self, hoist_id: str, segment: Segment) -> None:
        self.get_or_create_rope(self._hoist(hoist_id)).segments.append(segment)

    def update_rope_segment(self, hoist_id: str, visible_index: int, segment: Segment) -> None:
        hoist = self._hoist(hoist_id)
        rope_index = self._rope_segment_index(hoist, visible_index)
        self.get_or_create_rope(hoist).segments[rope_index] = segment

    def delete_rope_segment(self, hoist_id: str, visible_index: int) -> None:
        hoist = self._hoist(hoist_id)
        rope_index = self._rope_segment_index(hoist, visible_index)
        self.get_or_create_rope(hoist).segments.pop(rope_index)

    def _rope_segment_index(self, hoist: Hoist, visible_index: int) -> int:
        visible = self.visible_rope_segments(hoist)
        self._guard_index(visible_index, len(visible), "rope segment")
        return visible[visible_index][0]

    # -- contractual points --------------------------------------------

    def _condition_hoist(self, hoist_id: str, condition_name: Optional[str]) -> ConditionHoist:
        """``hoist_id``'s entry in condition ``condition_name`` (None: the first)."""
        self._hoist(hoist_id)
        if condition_name is None:
            spec = next(iter(self._doc.conditions.values()), None)
            if spec is None:
                raise DocumentEditError("The document has no load condition")
        else:
            spec = self._doc.conditions.get(condition_name)
            if spec is None:
                raise DocumentEditError(f"Unknown condition {condition_name!r}")
        settings = spec.hoists.get(hoist_id)
        if settings is None:
            raise DocumentEditError(f"Hoist '{hoist_id}' is not usable in condition {spec.name!r}")
        return settings

    def contractual_points(
        self, hoist_id: str, mode: str = "normal", condition_name: Optional[str] = None
    ) -> list[ContractualPoint]:
        """``hoist_id``'s chart points in ``mode`` under ``condition_name`` (None: the
        first condition), the list itself: edits apply to that condition only."""
        hoist = self._hoist(hoist_id)
        settings = self._condition_hoist(hoist_id, condition_name)
        if mode == "split":
            if not bool(hoist.splitable_block):
                raise DocumentEditError("Selected hoist is not splitable")
            return settings.split_contractual_points
        return settings.contractual_points

    def add_contractual_point(
        self,
        hoist_id: str,
        point: ContractualPoint,
        mode: str = "normal",
        condition_name: Optional[str] = None,
    ) -> None:
        self.contractual_points(hoist_id, mode, condition_name).append(point)

    def update_contractual_point(
        self,
        hoist_id: str,
        index: int,
        point: ContractualPoint,
        mode: str = "normal",
        condition_name: Optional[str] = None,
    ) -> None:
        points = self.contractual_points(hoist_id, mode, condition_name)
        self._guard_index(index, len(points), "contractual point")
        points[index] = point

    def delete_contractual_point(
        self,
        hoist_id: str,
        index: int,
        mode: str = "normal",
        condition_name: Optional[str] = None,
    ) -> None:
        points = self.contractual_points(hoist_id, mode, condition_name)
        self._guard_index(index, len(points), "contractual point")
        points.pop(index)

    # -- condition hoists and chart-point tags -------------------------

    def _payload_hoist(self, hoist_id: str) -> Hoist:
        hoist = self._hoist(hoist_id)
        if self.is_solve_hoist(hoist):
            raise DocumentEditError(f"The boom hoist '{hoist_id}' cannot be listed in a condition")
        return hoist

    def _condition(self, name: str) -> ConditionSpec:
        spec = self._doc.conditions.get(name)
        if spec is None:
            raise DocumentEditError(f"Unknown condition {name!r}")
        return spec

    def set_condition_hoist(
        self,
        condition: str,
        hoist_id: str,
        offlead_deg: float,
        sidelead_deg: float,
        daf: Optional[float],
    ) -> None:
        """Make payload hoist ``hoist_id`` usable in ``condition`` with these lead limits
        and DAF (None: no override -- derived under rules, 1.0 without).

        A hoist already usable there keeps its chart points. A hoist not yet usable there
        takes a copy of the points (normal and split) of the first condition, in document
        order, that lists it -- those points then name ``condition`` too; a hoist no
        condition lists starts with none.
        """
        spec = self._condition(condition)
        self._payload_hoist(hoist_id)
        _check_condition_hoist_values(offlead_deg, sidelead_deg, daf)
        with self._keeping_valid():
            entry = spec.hoists.get(hoist_id)
            if entry is None:
                source = next(
                    (
                        s.hoists[hoist_id]
                        for s in self._doc.conditions.values()
                        if hoist_id in s.hoists
                    ),
                    None,
                )
                entry = ConditionHoist(
                    offlead_deg=0.0,
                    contractual_points=(
                        []
                        if source is None
                        else [p.model_copy() for p in source.contractual_points]
                    ),
                    split_contractual_points=(
                        []
                        if source is None
                        else [p.model_copy() for p in source.split_contractual_points]
                    ),
                )
                spec.hoists[hoist_id] = entry
            entry.offlead_deg = float(offlead_deg)
            entry.sidelead_deg = float(sidelead_deg)
            entry.daf = None if daf is None else float(daf)

    def remove_condition_hoist(self, condition: str, hoist_id: str) -> None:
        """Make ``hoist_id`` unusable in ``condition``: its settings and chart points there
        go (points naming other conditions stay). Refused when ``condition`` is the last
        condition the hoist is usable in, or when it is the condition's last hoist."""
        spec = self._condition(condition)
        if hoist_id not in spec.hoists:
            raise DocumentEditError(f"Hoist '{hoist_id}' is not usable in condition {condition!r}")
        if not any(
            hoist_id in other.hoists
            for name, other in self._doc.conditions.items()
            if name != condition
        ):
            raise DocumentEditError(
                f"Hoist '{hoist_id}' is usable only in condition {condition!r}; every "
                "payload hoist must be usable in at least one condition"
            )
        if len(spec.hoists) == 1:
            raise DocumentEditError(
                f"Hoist '{hoist_id}' is the only hoist usable in condition {condition!r}; "
                "a condition needs at least one"
            )
        with self._keeping_valid():
            spec.hoists = {hid: e for hid, e in spec.hoists.items() if hid != hoist_id}

    def enter_condition_hoist(
        self,
        condition: str,
        hoist_id: str,
        offlead_deg: float,
        sidelead_deg: float,
        daf: Optional[float],
    ) -> None:
        """``set_condition_hoist`` with an entered DAF (None: clear the override), stored
        under the document's own rules (``hoist_daf.entered_daf``)."""
        self.set_condition_hoist(
            condition,
            hoist_id,
            offlead_deg,
            sidelead_deg,
            entered_daf(daf, rules=self._doc.rules is not None),
        )

    def set_condition_hoist_usable(self, condition: str, hoist_id: str, usable: bool) -> bool:
        """List ``hoist_id`` in ``condition`` (no lead limits, no DAF override, the chart
        points of the first condition listing it: ``set_condition_hoist``) or drop it there
        (``remove_condition_hoist``). False, and nothing changes, when it already is so."""
        spec = self._condition(condition)
        if (hoist_id in spec.hoists) == bool(usable):
            self._payload_hoist(hoist_id)
            return False
        if usable:
            self.set_condition_hoist(condition, hoist_id, 0.0, 0.0, None)
        else:
            self.remove_condition_hoist(condition, hoist_id)
        return True

    def tagged_chart(self, hoist_id: str, split: bool = False) -> list[TaggedChartPoint]:
        """``hoist_id``'s load chart (``split``: the split-block one) as saved: each point
        once, with the conditions it names (``authored_form.tagged_load_chart``)."""
        hoist = self._payload_hoist(hoist_id)
        if split and not bool(hoist.splitable_block):
            raise DocumentEditError(f"Hoist '{hoist_id}' is not splitable")
        return [
            TaggedChartPoint(
                outreach_m=float(p["outreach_m"]),
                load_t=float(p["load_t"]),
                conditions=tuple(p["conditions"]),
            )
            for p in tagged_load_chart(self._doc, hoist_id, split=split)
        ]

    def set_point_conditions(
        self, hoist_id: str, split: bool, index: int, conditions: list[str]
    ) -> None:
        """Make chart point ``index`` of ``tagged_chart(hoist_id, split)`` name exactly
        ``conditions`` (>= 1, unique, each a condition ``hoist_id`` is usable in).

        A condition it stops naming loses that point; one it starts naming gains it, in
        chart order. Refused when a condition would be left without a point in that chart.
        """
        chart = self.tagged_chart(hoist_id, split)
        self._guard_index(index, len(chart), "chart point")
        point = chart[index]
        self._retag(
            hoist_id,
            split,
            chart,
            index,
            conditions,
            build_contractual_point(point.outreach_m, point.load_t),
        )

    def usable_conditions(self, hoist_id: str) -> list[str]:
        """The conditions listing ``hoist_id``, in document order."""
        return [name for name, spec in self._doc.conditions.items() if hoist_id in spec.hoists]

    def add_chart_point(
        self,
        hoist_id: str,
        split: bool,
        point: ContractualPoint,
        conditions: Optional[list[str]] = None,
    ) -> None:
        """Add ``point`` to ``hoist_id``'s load chart (``split``: the split-block one),
        naming ``conditions`` (>= 1, unique, each a condition the hoist is usable in;
        None: every one, ``usable_conditions``).

        Each named condition takes it before its first point of larger outreach, so a
        chart kept in outreach order stays so.
        """
        self.tagged_chart(hoist_id, split)  # the hoist and the chart exist
        names = self._checked_point_conditions(
            hoist_id, self.usable_conditions(hoist_id) if conditions is None else conditions
        )
        with self._keeping_valid():
            for name in names:
                points = self._condition_chart(name, hoist_id, split)
                position = next(
                    (i for i, p in enumerate(points) if p.outreach_m > point.outreach_m),
                    len(points),
                )
                points.insert(position, point.model_copy())

    def update_chart_point(
        self,
        hoist_id: str,
        split: bool,
        index: int,
        point: ContractualPoint,
        conditions: Optional[list[str]] = None,
    ) -> None:
        """Replace chart point ``index`` of ``tagged_chart(hoist_id, split)`` by ``point``
        in every condition it names, at the same place in each; ``conditions`` (None: the
        ones it names now) also retags it, as ``set_point_conditions``. One edit: refused
        as a whole."""
        chart = self.tagged_chart(hoist_id, split)
        self._guard_index(index, len(chart), "chart point")
        names = list(chart[index].conditions) if conditions is None else conditions
        self._retag(hoist_id, split, chart, index, names, point)

    def delete_chart_point(self, hoist_id: str, split: bool, index: int) -> None:
        """Delete chart point ``index`` of ``tagged_chart(hoist_id, split)`` from every
        condition it names. Refused when that would leave one of them without a point in
        that chart."""
        chart = self.tagged_chart(hoist_id, split)
        self._guard_index(index, len(chart), "chart point")
        self._guard_points_left(hoist_id, split, chart, index, keep=set())
        with self._keeping_valid():
            for name in chart[index].conditions:
                position = sum(name in p.conditions for p in chart[:index])
                self._condition_chart(name, hoist_id, split).pop(position)

    def _condition_chart(self, condition: str, hoist_id: str, split: bool) -> list:
        entry = self._doc.conditions[condition].hoists[hoist_id]
        return entry.split_contractual_points if split else entry.contractual_points

    def _checked_point_conditions(self, hoist_id: str, conditions: list[str]) -> list[str]:
        """``conditions`` as names a chart point of ``hoist_id`` may carry: >= 1, unique,
        each a condition that lists the hoist; otherwise ``DocumentEditError``."""
        names = [str(name) for name in conditions]
        if not names:
            raise DocumentEditError("A chart point must name at least one condition")
        repeated = sorted({n for n in names if names.count(n) > 1})
        if repeated:
            raise DocumentEditError(
                f"A chart point names each condition once; repeated: {', '.join(repeated)}"
            )
        for name in names:
            spec = self._condition(name)
            if hoist_id not in spec.hoists:
                raise DocumentEditError(
                    f"Condition {name!r} does not list hoist '{hoist_id}'; make it usable "
                    "there first"
                )
        return names

    @staticmethod
    def _guard_points_left(
        hoist_id: str, split: bool, chart: list[TaggedChartPoint], index: int, keep: set[str]
    ) -> None:
        """Refuse when a condition point ``index`` names, and ``keep`` does not, would be
        left without a point in ``chart``."""
        for name in chart[index].conditions:
            if name not in keep and sum(name in p.conditions for p in chart) == 1:
                raise DocumentEditError(
                    f"Condition {name!r} would have no {'split ' if split else ''}chart "
                    f"point for hoist '{hoist_id}'"
                )

    def _retag(
        self,
        hoist_id: str,
        split: bool,
        chart: list[TaggedChartPoint],
        index: int,
        conditions: list[str],
        value: ContractualPoint,
    ) -> None:
        """Make ``chart[index]`` name exactly ``conditions`` with the values of ``value``:
        a condition it keeps naming has its point replaced in place, one it stops naming
        loses it, one it starts naming gains it at the same place in chart order."""
        names = self._checked_point_conditions(hoist_id, conditions)
        point = chart[index]
        wanted = set(names)
        self._guard_points_left(hoist_id, split, chart, index, keep=wanted)

        with self._keeping_valid():
            for name in self._doc.conditions:
                if name not in wanted and name not in point.conditions:
                    continue
                points = self._condition_chart(name, hoist_id, split)
                # The k-th chart point naming a condition is its k-th point.
                position = sum(name in p.conditions for p in chart[:index])
                if name in point.conditions and name not in wanted:
                    points.pop(position)
                elif name in wanted and name not in point.conditions:
                    points.insert(position, value.model_copy())
                else:
                    points[position] = value.model_copy()

    @staticmethod
    def _guard_index(index: int, length: int, what: str) -> None:
        if not (0 <= index < length):
            raise DocumentEditError(f"Select a {what} first")

    # -- load conditions -----------------------------------------------

    # A condition's hoist entries carry its chart: a point names a condition by being in
    # that condition's point list, so renaming, duplicating or deleting a condition
    # carries its tags along with it.

    def add_condition(self, condition: ConditionSpec) -> None:
        """Append ``condition``. One listing no hoists lists copies of the first
        condition's hoist entries (settings and chart points, which then name it too):
        a condition needs at least one usable hoist, with points."""
        conditions = self._conditions()
        self._guard_condition_name(condition.name, conditions, previous=None)
        if not condition.hoists and conditions:
            first = next(iter(conditions.values()))
            condition = condition.model_copy(
                update={
                    "hoists": {
                        hid: entry.model_copy(deep=True) for hid, entry in first.hoists.items()
                    }
                }
            )
        self._commit_conditions({**conditions, condition.name: condition})

    def update_condition(self, name: str, edited: ConditionSpec) -> None:
        """Replace condition ``name`` by ``edited`` (a new name renames it in place).

        ``edited`` listing no hoists keeps the condition's current hoist entries: they are
        edited with ``set_condition_hoist``/``remove_condition_hoist``."""
        conditions = self._conditions()
        self._guard_known_condition(name, conditions)
        self._guard_condition_name(edited.name, conditions, previous=name)
        if not edited.hoists:
            edited = edited.model_copy(update={"hoists": conditions[name].hoists})
        self._commit_conditions(
            {
                (edited.name if k == name else k): (edited if k == name else v)
                for k, v in conditions.items()
            }
        )

    def duplicate_condition(self, name: str) -> str:
        conditions = self._conditions()
        self._guard_known_condition(name, conditions)
        new_name = f"{name}_copy"
        suffix = 2
        while new_name in conditions:
            new_name = f"{name}_copy{suffix}"
            suffix += 1
        copy = conditions[name].model_copy(deep=True, update={"name": new_name})
        result: dict[str, ConditionSpec] = {}
        for key, value in conditions.items():
            result[key] = value
            if key == name:
                result[new_name] = copy
        self._commit_conditions(result)
        return new_name

    def delete_condition(self, name: str) -> None:
        conditions = self._conditions()
        self._guard_known_condition(name, conditions)
        if len(conditions) == 1:
            raise DocumentEditError("A document needs at least one condition")
        for hoist_id in conditions[name].hoists:
            if not any(hoist_id in spec.hoists for key, spec in conditions.items() if key != name):
                raise DocumentEditError(
                    f"Hoist '{hoist_id}' is usable only in condition {name!r}; make it "
                    "usable in another condition first"
                )
        self._commit_conditions({k: v for k, v in conditions.items() if k != name})

    def _conditions(self) -> dict[str, ConditionSpec]:
        return dict(self._doc.conditions)

    @staticmethod
    def _guard_known_condition(name: str, conditions: dict[str, ConditionSpec]) -> None:
        if name not in conditions:
            raise DocumentEditError(f"Unknown condition {name!r}")

    @staticmethod
    def _guard_condition_name(
        name: str, conditions: dict[str, ConditionSpec], *, previous: Optional[str]
    ) -> None:
        if not CONDITION_NAME_PATTERN.fullmatch(name):
            raise DocumentEditError(
                "Condition name must start with a letter and use only letters, numbers, _ or -"
            )
        if name in conditions and name != previous:
            raise DocumentEditError(f"Condition {name!r} already exists")

    def _commit_conditions(self, conditions: dict[str, ConditionSpec]) -> None:
        """Make ``conditions`` the document's, if the rules (or, without rules, the
        authored contract: every condition onboard) accept them and a document that
        saved still does."""
        if self._doc.rules is None:
            for name, spec in conditions.items():
                if spec.lift != "onboard":
                    raise DocumentEditError(
                        f"conditions.{name}.lift: {spec.lift!r} requires rules; without "
                        "rules every condition must be 'onboard'"
                    )
        candidate = self._doc.model_copy(update={"conditions": conditions})
        try:
            validate_rules_document(candidate)
        except RulesValidationError as exc:
            raise DocumentEditError(str(exc)) from exc
        with self._keeping_valid():
            self._doc.conditions = conditions
