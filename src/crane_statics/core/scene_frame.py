"""Renderer-neutral scene geometry for Qt Quick scene canvases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from crane_statics.presentation.formatters import node_display_name


@dataclass(frozen=True)
class SceneNode:
    """A node marker in renderer scene coordinates."""

    id: str
    scene_x: float
    scene_y: float
    tooltip: str


@dataclass(frozen=True)
class SceneSegment:
    """A styled line segment in renderer scene coordinates."""

    kind: str
    source_id: str
    target_id: str
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    color: str
    width: float
    tooltip: str


@dataclass(frozen=True)
class SceneMarker:
    """A circular scene marker with a semantic role."""

    kind: str
    scene_x: float
    scene_y: float
    radius: float
    tooltip: str


@dataclass(frozen=True)
class SceneArrow:
    """A force arrow in renderer scene coordinates."""

    kind: str
    origin_x: float
    origin_y: float
    tip_x: float
    tip_y: float
    color: str
    dashed: bool
    label: str
    tooltip: str


@dataclass(frozen=True)
class SceneMoment:
    """An open-arc reaction moment glyph in renderer scene coordinates."""

    origin_x: float
    origin_y: float
    moment_kNm: float
    radius: float
    start_degrees: float
    span_degrees: float
    arrow_tip_x: float
    arrow_tip_y: float
    color: str
    label: str
    tooltip: str


@dataclass(frozen=True)
class SceneLabel:
    """A text label anchored in renderer scene coordinates."""

    kind: str
    scene_x: float
    scene_y: float
    color: str
    text: str


@dataclass(frozen=True)
class SceneGuide:
    """A scene-space anchor for a guide extending to a canvas edge."""

    kind: str
    scene_x: float
    scene_y: float
    label: str


@dataclass(frozen=True)
class SceneWaterline:
    """A horizontal mean-sea-level overlay in scene coordinates."""

    scene_y: float
    elevation_z: float
    label: str


@dataclass(frozen=True)
class SceneHitTarget:
    """A transformed scene-space target for canvas interaction."""

    kind: str
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    radius: float
    extends_to_canvas_edge: bool


@dataclass(frozen=True)
class SceneAxis:
    """A labeled local-coordinate axis arrow in renderer scene coordinates."""

    label: str
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    color: str


@dataclass(frozen=True)
class SceneStatus:
    """A centered status message for unloaded or invalid scene geometry."""

    text: str
    color: str


@dataclass(frozen=True)
class SceneMapping:
    """Deterministic affine transform between engineering and scene coordinates."""

    min_x: float
    min_z: float
    scale: float
    pad: float = 60.0
    height: float = 760.0

    @classmethod
    def from_positions(
        cls,
        positions: dict[str, dict[str, float]],
        *,
        pad: float = 60.0,
        height: float = 760.0,
    ) -> "SceneMapping":
        xs = [point["x"] for point in positions.values()]
        zs = [point["z"] for point in positions.values()]
        min_x, max_x = min(xs), max(xs)
        min_z, max_z = min(zs), max(zs)
        available = height - 2 * pad
        scale = min(
            available / max(max_x - min_x, 1.0),
            available / max(max_z - min_z, 1.0),
        )
        return cls(min_x=min_x, min_z=min_z, scale=scale, pad=pad, height=height)

    def to_scene(self, world_x: float, world_z: float) -> tuple[float, float]:
        return (
            self.pad + (world_x - self.min_x) * self.scale,
            self.height - self.pad - (world_z - self.min_z) * self.scale,
        )

    def to_world(self, scene_x: float, scene_y: float) -> tuple[float, float]:
        return (
            self.min_x + (scene_x - self.pad) / max(1e-9, self.scale),
            self.min_z + (self.height - self.pad - scene_y) / max(1e-9, self.scale),
        )

    def fit_rect(
        self,
        scene_nodes: Iterable[tuple[float, float]],
        *,
        margin: float = 28.0,
    ) -> tuple[float, float, float, float]:
        points = tuple(scene_nodes)
        if not points:
            return (0.0, 0.0, 0.0, 0.0)
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return (
            min(xs) - margin,
            min(ys) - margin,
            max(xs) - min(xs) + 2 * margin,
            max(ys) - min(ys) + 2 * margin,
        )


@dataclass(frozen=True)
class SceneFrame:
    """Immutable geometry consumed by declarative scene canvases."""

    revision: int
    fit_rect: tuple[float, float, float, float]
    nodes: tuple[SceneNode, ...]
    rope_segments: tuple[SceneSegment, ...]
    structural_segments: tuple[SceneSegment, ...]
    markers: tuple[SceneMarker, ...]
    force_arrows: tuple[SceneArrow, ...]
    moments: tuple[SceneMoment, ...]
    labels: tuple[SceneLabel, ...]
    guides: tuple[SceneGuide, ...]
    waterline: SceneWaterline | None
    hit_targets: tuple[SceneHitTarget, ...]
    boom_axes: tuple[SceneAxis, ...]
    status: SceneStatus | None
    #: The transform this frame was projected with, for scene<->world hit testing.
    #: ``None`` on a status-only frame, where there is no geometry to map.
    mapping: SceneMapping | None = None
    #: Boom heel in world coordinates -- the pivot drag gestures measure against.
    heel_world: tuple[float, float] | None = None


class SceneFrameBuilder:
    """Collects toolkit-neutral scene primitives into immutable frame revisions."""

    def __init__(self) -> None:
        self._revision = 0
        self.reset()

    def reset(self) -> None:
        self.nodes: list[SceneNode] = []
        self.rope_segments: list[SceneSegment] = []
        self.structural_segments: list[SceneSegment] = []
        self.markers: list[SceneMarker] = []
        self.force_arrows: list[SceneArrow] = []
        self.moments: list[SceneMoment] = []
        self.labels: list[SceneLabel] = []
        self.boom_axes: list[SceneAxis] = []
        self.guides: list[SceneGuide] = []
        self.hit_targets: list[SceneHitTarget] = []
        self.waterline: SceneWaterline | None = None
        self.status: SceneStatus | None = None

    @staticmethod
    def with_hook_tackle(
        base_positions: dict[str, dict[str, float]],
        node_definitions: dict[str, dict],
        load_node_id: str,
        tackle_length_m: float,
    ) -> dict[str, dict[str, float]]:
        """Return positions with the active hook lowered from its support node."""
        positions = {node_id: dict(point) for node_id, point in base_positions.items()}
        load_node = positions.get(load_node_id)
        reference_id = str(
            (node_definitions.get(load_node_id, {}) or {}).get("below_node_id") or ""
        )
        reference_node = positions.get(reference_id)
        if load_node is not None and reference_node is not None:
            positions[load_node_id] = {
                "x": float(load_node["x"]),
                "z": float(reference_node["z"]) - float(tackle_length_m),
            }
        return positions

    def add_node(self, node_id: str, scene_x: float, scene_y: float, tooltip: str) -> SceneNode:
        node = SceneNode(node_id, scene_x, scene_y, tooltip)
        self.nodes.append(node)
        return node

    def add_nodes_from_positions(
        self,
        positions: dict[str, dict[str, float]],
        *,
        project: Callable[[float, float], tuple[float, float]],
        tooltip_for: Callable[[str, dict[str, float]], str],
        visible_ids: Iterable[str] | None = None,
        overlap_margin: float = 4.0,
    ) -> tuple[SceneNode, ...]:
        allowed = None if visible_ids is None else set(visible_ids)
        nodes: list[SceneNode] = []
        for node_id, position in positions.items():
            if allowed is not None and node_id not in allowed:
                continue
            scene_x, scene_y = project(position["x"], position["z"])
            if any(
                ((scene_x - marker.scene_x) ** 2 + (scene_y - marker.scene_y) ** 2) ** 0.5
                <= marker.radius + overlap_margin
                for marker in self.markers
            ):
                continue
            nodes.append(self.add_node(node_id, scene_x, scene_y, tooltip_for(node_id, position)))
        return tuple(nodes)

    def add_segment(
        self,
        *,
        kind: str,
        source_id: str,
        target_id: str,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        color: str,
        width: float,
        tooltip: str,
    ) -> SceneSegment:
        segment = SceneSegment(
            kind,
            source_id,
            target_id,
            start_x,
            start_y,
            end_x,
            end_y,
            color,
            width,
            tooltip,
        )
        if kind == "rope":
            self.rope_segments.append(segment)
        else:
            self.structural_segments.append(segment)
        return segment

    def add_structural_members(
        self,
        positions: dict[str, dict[str, float]],
        *,
        project: Callable[[float, float], tuple[float, float]],
        selected_freebody: str,
        color: str,
        width: float,
    ) -> tuple[SceneSegment, ...]:
        if selected_freebody in {"boom", "platform"}:
            return ()
        members = (
            ("rear_base", "rear_top", "Rear leg", "rear_leg"),
            ("front_base", "front_top", "Front leg", "front_leg"),
        )
        segments: list[SceneSegment] = []
        for source_id, target_id, label, body_id in members:
            if selected_freebody in {"rear_leg", "front_leg"} and selected_freebody != body_id:
                continue
            source = positions.get(source_id)
            target = positions.get(target_id)
            if source is None or target is None:
                continue
            start_x, start_y = project(source["x"], source["z"])
            end_x, end_y = project(target["x"], target["z"])
            length_m = (
                (float(target["x"]) - float(source["x"])) ** 2
                + (float(target["z"]) - float(source["z"])) ** 2
            ) ** 0.5
            segments.append(
                self.add_segment(
                    kind="structural_member",
                    source_id=source_id,
                    target_id=target_id,
                    start_x=start_x,
                    start_y=start_y,
                    end_x=end_x,
                    end_y=end_y,
                    color=color,
                    width=width,
                    tooltip=(
                        f"{label}\n"
                        f"From: {node_display_name(source_id)}\n"
                        f"To: {node_display_name(target_id)}\n"
                        f"Length: {length_m:.2f} m"
                    ),
                )
            )
        return tuple(segments)

    def add_rope_segments(
        self,
        ropes: Iterable[dict],
        positions: dict[str, dict[str, float]],
        *,
        project: Callable[[float, float], tuple[float, float]],
        effective_multiplier: Callable[[str, dict, int], int],
        style_for: Callable[[str, int], tuple[str, float]],
        tooltip_for: Callable[
            [dict, str, dict, int, int, int, int, dict[str, dict[str, float]]], str
        ],
    ) -> tuple[SceneSegment, ...]:
        segments: list[SceneSegment] = []
        for rope in ropes:
            rope_id = str(rope.get("id", "") or "")
            rope_segments = list(rope.get("segments", []))
            count = len(rope_segments)
            for index, segment in enumerate(rope_segments, start=1):
                source_id = str(segment.get("from_node_id", "") or "")
                target_id = str(segment.get("to_node_id", "") or "")
                source = positions.get(source_id)
                target = positions.get(target_id)
                if source is None or target is None:
                    continue
                authored_multiplier = int(segment.get("mult", 1))
                multiplier = effective_multiplier(rope_id, segment, authored_multiplier)
                color, width = style_for(rope_id, multiplier)
                start_x, start_y = project(source["x"], source["z"])
                end_x, end_y = project(target["x"], target["z"])
                tooltip = tooltip_for(
                    rope,
                    rope_id,
                    segment,
                    index,
                    count,
                    authored_multiplier,
                    multiplier,
                    positions,
                )
                segments.append(
                    self.add_segment(
                        kind="rope",
                        source_id=source_id,
                        target_id=target_id,
                        start_x=start_x,
                        start_y=start_y,
                        end_x=end_x,
                        end_y=end_y,
                        color=color,
                        width=width,
                        tooltip=tooltip,
                    )
                )
        return tuple(segments)

    def add_marker(
        self,
        *,
        kind: str,
        scene_x: float,
        scene_y: float,
        radius: float,
        tooltip: str,
    ) -> SceneMarker:
        marker = SceneMarker(kind, scene_x, scene_y, radius, tooltip)
        self.markers.append(marker)
        return marker

    def add_cg_markers(
        self,
        bodies: Iterable[dict],
        *,
        heel: dict[str, float],
        boom_angle_degrees: float,
        project: Callable[[float, float], tuple[float, float]],
        include_body: Callable[[str], bool],
        tooltip_for: Callable[[dict], str],
        radius: float = 6.0,
    ) -> tuple[SceneMarker, ...]:
        import math

        angle = math.radians(boom_angle_degrees)
        markers: list[SceneMarker] = []
        for body in bodies:
            body_id = str(body.get("id", ""))
            if not include_body(body_id):
                continue
            for mass_point in body.get("mass_points", []):
                if float(mass_point.get("mass_t", 0.0)) <= 0.0:
                    continue
                local_x = mass_point.get("local_x_m")
                if local_x is not None and body_id == "boom":
                    local_z = float(mass_point.get("local_z_m", 0.0))
                    world_x = (
                        heel["x"] + float(local_x) * math.cos(angle) - local_z * math.sin(angle)
                    )
                    world_z = (
                        heel["z"] + float(local_x) * math.sin(angle) + local_z * math.cos(angle)
                    )
                elif mass_point.get("x_m") is not None:
                    world_x = float(mass_point["x_m"])
                    world_z = float(mass_point.get("z_m", 0.0))
                else:
                    continue
                scene_x, scene_y = project(world_x, world_z)
                mass_point_id = str(mass_point.get("id", "") or "").strip() or "Unnamed mass point"
                markers.append(
                    self.add_marker(
                        kind="center_of_gravity",
                        scene_x=scene_x,
                        scene_y=scene_y,
                        radius=radius,
                        tooltip=(
                            f"Center of gravity\n"
                            f"Mass point: {mass_point_id}\n"
                            f"Mass: {float(mass_point.get('mass_t', 0.0)):.2f} t\n"
                            f"Position: ({world_x:.2f}, {world_z:.2f}) m"
                        ),
                    )
                )
        return tuple(markers)

    def add_split_support_cg_marker(
        self,
        positions: dict[str, dict[str, float]],
        *,
        support_node_id: str,
        support_mass_t: float | None,
        include_node: Callable[[str], bool],
        project: Callable[[float, float], tuple[float, float]],
        hoist_label: str,
        radius: float = 6.0,
    ) -> SceneMarker | None:
        if support_mass_t is None or support_mass_t <= 0.0 or not support_node_id:
            return None
        if not include_node(support_node_id):
            return None
        position = positions.get(support_node_id)
        if position is None:
            return None
        world_x = float(position["x"])
        world_z = float(position["z"])
        scene_x, scene_y = project(world_x, world_z)
        tooltip = (
            f"{hoist_label} split block CG: {support_mass_t:.1f} t"
            f"  ({world_x:.1f} m, {world_z:.1f} m)"
        )
        return self.add_marker(
            kind="center_of_gravity",
            scene_x=scene_x,
            scene_y=scene_y,
            radius=radius,
            tooltip=tooltip,
        )

    def add_axis(
        self,
        *,
        label: str,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        color: str,
    ) -> SceneAxis:
        axis = SceneAxis(label, start_x, start_y, end_x, end_y, color)
        self.boom_axes.append(axis)
        return axis

    def add_force_arrow(
        self,
        *,
        origin_x: float,
        origin_y: float,
        tip_x: float,
        tip_y: float,
        color: str,
        dashed: bool,
        label: str,
        tooltip: str,
    ) -> SceneArrow:
        arrow = SceneArrow("force", origin_x, origin_y, tip_x, tip_y, color, dashed, label, tooltip)
        self.force_arrows.append(arrow)
        return arrow

    def add_moment(
        self,
        *,
        origin_x: float,
        origin_y: float,
        moment_kNm: float,
        radius: float,
        start_degrees: float,
        span_degrees: float,
        arrow_tip_x: float,
        arrow_tip_y: float,
        color: str,
        label: str,
        tooltip: str,
    ) -> SceneMoment:
        moment = SceneMoment(
            origin_x,
            origin_y,
            moment_kNm,
            radius,
            start_degrees,
            span_degrees,
            arrow_tip_x,
            arrow_tip_y,
            color,
            label,
            tooltip,
        )
        self.moments.append(moment)
        return moment

    def add_label(
        self,
        *,
        kind: str,
        scene_x: float,
        scene_y: float,
        color: str,
        text: str,
    ) -> SceneLabel:
        label = SceneLabel(kind, scene_x, scene_y, color, text)
        self.labels.append(label)
        return label

    def add_guide(self, *, kind: str, scene_x: float, scene_y: float, label: str) -> SceneGuide:
        guide = SceneGuide(kind, scene_x, scene_y, label)
        self.guides.append(guide)
        return guide

    def set_waterline(self, *, scene_y: float, elevation_z: float, label: str) -> SceneWaterline:
        self.waterline = SceneWaterline(scene_y, elevation_z, label)
        return self.waterline

    def add_hit_target(
        self,
        *,
        kind: str,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        radius: float,
        extends_to_canvas_edge: bool,
    ) -> SceneHitTarget:
        target = SceneHitTarget(
            kind,
            start_x,
            start_y,
            end_x,
            end_y,
            radius,
            extends_to_canvas_edge,
        )
        self.hit_targets.append(target)
        return target

    def build(
        self,
        *,
        fit_rect: tuple[float, float, float, float],
        revision: int | None = None,
        mapping: SceneMapping | None = None,
        heel_world: tuple[float, float] | None = None,
    ) -> SceneFrame:
        """Freeze the collected primitives into a frame.

        ``revision`` defaults to this builder's own incrementing counter; pass it
        explicitly when the change token is owned by the caller instead.
        """
        self._revision += 1
        return SceneFrame(
            revision=self._revision if revision is None else int(revision),
            fit_rect=fit_rect,
            mapping=mapping,
            heel_world=heel_world,
            nodes=tuple(self.nodes),
            rope_segments=tuple(self.rope_segments),
            structural_segments=tuple(self.structural_segments),
            markers=tuple(self.markers),
            force_arrows=tuple(self.force_arrows),
            moments=tuple(self.moments),
            labels=tuple(self.labels),
            guides=tuple(self.guides),
            waterline=self.waterline,
            hit_targets=tuple(self.hit_targets),
            boom_axes=tuple(self.boom_axes),
            status=self.status,
        )
