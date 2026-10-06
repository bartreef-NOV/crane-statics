"""Toolkit-neutral document mutations shared by both front ends."""

from __future__ import annotations

from typing import Optional

from ..data.authored_models import hoist_node_prefix
from ..data.models import (
    Body,
    ContractualPoint,
    CraneDocument,
    derive_payload_hoist_rope_geometry,
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

BOOM_BODY_ID = "boom"


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
    hook_mass_t: float = 0.0,
    splitable_block: bool = False,
    split_falls: Optional[int] = None,
    split_hook_mass_t: Optional[float] = None,
    hook_daf: float = 1.0,
    offlead_deg: float = 0.0,
    sidelead_deg: float = 0.0,
    linear_mass_kg_m: float = 0.0,
    drum_dead_turns: int = 0,
    drum_diameter_m: Optional[float] = None,
) -> Hoist:
    hoist_id = hoist_id.strip()
    if not hoist_id:
        raise DocumentEditError("Hoist ID cannot be empty")
    if splitable_block:
        if split_falls is None or int(split_falls) > int(falls):
            raise DocumentEditError("Split falls must be <= normal falls")
        if split_hook_mass_t is None or float(split_hook_mass_t) > float(hook_mass_t):
            raise DocumentEditError("Split hook mass must be <= normal hook mass")

    return Hoist(
        id=hoist_id,
        rope_id=f"{hoist_id}__rope",
        load_node_id=_managed_hook_node_id(hoist_id),
        support_node_id=support_node_id.strip(),
        falls=int(falls),
        hook_mass_t=float(hook_mass_t),
        splitable_block=bool(splitable_block),
        split_falls=None if split_falls is None else int(split_falls),
        split_hook_mass_t=None if split_hook_mass_t is None else float(split_hook_mass_t),
        hook_daf=float(hook_daf),
        offlead_deg=float(offlead_deg),
        sidelead_deg=float(sidelead_deg),
        linear_mass_kg_m=max(0.0, float(linear_mass_kg_m)),
        drum_dead_turns=max(0, int(drum_dead_turns)),
        drum_diameter_m=None if drum_diameter_m is None else max(1e-9, float(drum_diameter_m)),
        split_contractual_points=(
            [ContractualPoint(outreach_m=0.0, load_t=0.0)] if splitable_block else []
        ),
    )


def build_segment(from_node_id: str, to_node_id: str, mult: int = 1) -> Segment:
    from_node_id = from_node_id.strip()
    to_node_id = to_node_id.strip()
    if not from_node_id or not to_node_id:
        raise DocumentEditError("Segment endpoints are required")
    if from_node_id == to_node_id:
        raise DocumentEditError("Segment endpoints must differ")
    return Segment(from_node_id=from_node_id, to_node_id=to_node_id, mult=max(1, int(mult)))


def build_contractual_point(outreach_m: float, load_t: float) -> ContractualPoint:
    return ContractualPoint(outreach_m=float(outreach_m), load_t=float(load_t))


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
        of the design hook height, so they are recomputed rather than carried.
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

    def add_hoist(self, hoist: Hoist, tension_mode: str = "fixed") -> None:
        if any(h.id == hoist.id for h in self._doc.hoists):
            raise DocumentEditError(f"Hoist '{hoist.id}' already exists")
        if any(r.id == hoist.rope_id for r in self._doc.ropes):
            raise DocumentEditError(f"Generated rope '{hoist.rope_id}' already exists")

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
        current = self._hoist(hoist_id)
        if self.is_solve_hoist(current):
            raise DocumentEditError(f"Hoist '{hoist_id}' is the boom hoist; use update_boom_hoist")

        # The derived pair belongs to the document, not the edit form.
        edited.max_hook_travel_m = current.max_hook_travel_m
        edited.rope_length_m = current.rope_length_m
        edited.rope_id = current.rope_id
        edited.load_node_id = current.load_node_id
        edited.contractual_points = [cp.model_copy(deep=True) for cp in current.contractual_points]
        edited.split_contractual_points = [
            cp.model_copy(deep=True) for cp in current.split_contractual_points
        ]
        self.sync_managed_payload_hook(edited)

        for index, hoist in enumerate(self._doc.hoists):
            if hoist.id == hoist_id:
                self._doc.hoists[index] = edited
                break

        rope = self.rope_for_hoist(edited)
        if rope is not None:
            rope.tension_mode = "fixed"
            rope.linear_mass_kg_m = float(edited.linear_mass_kg_m)

    def delete_hoist(self, hoist_id: str) -> None:
        hoist = self._hoist(hoist_id)
        if self.is_solve_hoist(hoist):
            raise DocumentEditError("Boom hoist cannot be deleted from this table")

        rope_id = hoist.rope_id
        managed_hook_id = str(hoist.load_node_id)
        rope = self.rope_for_hoist(hoist)
        path_node_ids = {
            end
            for seg in (rope.segments if rope else [])
            for end in (seg.from_node_id, seg.to_node_id)
        }
        self._doc.hoists = [h for h in self._doc.hoists if h.id != hoist_id]

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

    def contractual_points(self, hoist_id: str, mode: str = "normal") -> list[ContractualPoint]:
        hoist = self._hoist(hoist_id)
        if mode == "split":
            if not bool(hoist.splitable_block):
                raise DocumentEditError("Selected hoist is not splitable")
            return hoist.split_contractual_points
        return hoist.contractual_points

    def add_contractual_point(
        self, hoist_id: str, point: ContractualPoint, mode: str = "normal"
    ) -> None:
        self.contractual_points(hoist_id, mode).append(point)

    def update_contractual_point(
        self, hoist_id: str, index: int, point: ContractualPoint, mode: str = "normal"
    ) -> None:
        points = self.contractual_points(hoist_id, mode)
        self._guard_index(index, len(points), "contractual point")
        points[index] = point

    def delete_contractual_point(self, hoist_id: str, index: int, mode: str = "normal") -> None:
        points = self.contractual_points(hoist_id, mode)
        self._guard_index(index, len(points), "contractual point")
        points.pop(index)

    @staticmethod
    def _guard_index(index: int, length: int, what: str) -> None:
        if not (0 <= index < length):
            raise DocumentEditError(f"Select a {what} first")
