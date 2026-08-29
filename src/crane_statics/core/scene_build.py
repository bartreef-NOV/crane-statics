"""Build an immutable :class:`SceneFrame` from an authored document and drawn state.

This module is the single definition of *what the scene canvas shows*. It is pure:
one :class:`SceneInputs` value in, one :class:`SceneFrame` out, with no Qt types and
no mutable renderer state. There is no ordering for a caller to know -- assembling
the inputs is the whole protocol.

Two deliberate choices in the interface:

* **Colours are data.** ``SceneFrame`` carries them as hex strings all the way to
  QML, so styling arrives as a ``palette`` mapping rather than as a dependency.
  A renderer may substitute its own palette without this module changing.
* **Loads are not recomputed here.** Every force and moment comes from
  :mod:`crane_statics.core.drawn_loads`; this module only projects them into scene
  coordinates and styles them. The scene draws the load model, it does not own it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping, Optional, Tuple

from crane_statics.calculation.rope_mass import compute_winch_marker_masses_kg
from crane_statics.presentation.formatters import HoistFormatter, node_display_name

from . import drawn_loads
from .drawn_loads import BodyLoads, FreeBodyFilter, LoadConditions, LoadMoment, LoadVector
from .scene_frame import (
    SceneFrame,
    SceneFrameBuilder,
    SceneMapping,
    SceneStatus,
)

Axis = Tuple[float, float]
Positions = dict[str, dict[str, float]]

#: How arrow length relates to magnitude.
#:
#: ``hybrid``   auto-scale, but never shorter than ``force_min_visible_px``
#: ``physical`` auto-scale with no floor, so tiny forces stay tiny
#: ``fixed``    direction only, every arrow the same pixel length
FORCE_SCALE_MODES = ("hybrid", "physical", "fixed")

#: Which free body the scene is cut down to. ``none`` means the whole crane.
FREEBODY_TARGETS = ("none", "platform", "boom", "front_leg", "rear_leg")

#: Rope colour slots, in the order hoists claim them. Okabe-Ito, plus a neutral.
ROPE_COLOR_KEYS = (
    "rope_c0",
    "rope_c1",
    "rope_c2",
    "rope_c3",
    "rope_c4",
    "rope_c5",
    "rope_c6",
    "rope_c7",
)

#: Load category -> palette key. Categories that share a physical origin (the hook
#: and the rope/idle-hook interface loads that balance it) share a colour.
FORCE_PALETTE_KEYS: dict[str, str] = {
    drawn_loads.GRAVITY: "force_hook",
    drawn_loads.IDLE_HOOK_MASS: "force_hook",
    drawn_loads.HOOK_LOAD: "force_hook",
    drawn_loads.WIND: "force_wind",
    drawn_loads.INERTIA: "force_inertia",
    drawn_loads.ROPE_INTERFACE: "force_hook",
    drawn_loads.REACTIONS: "force_reaction",
}

#: Theme-independent canvas colours, fixed to the Light baseline semantics so the
#: printed scene matches the screen. Lower-case hex, as ``SceneFrame`` expects.
DEFAULT_PALETTE: dict[str, str] = {
    "text": "#000000",
    "muted_text": "#7a7a7a",
    "neutral": "#7a7a7a",
    "frame": "#7a7a7a",
    "axis_x": "#d64545",
    "axis_z": "#3a78d1",
    "rope_c0": "#0072b2",
    "rope_c1": "#e69f00",
    "rope_c2": "#009e73",
    "rope_c3": "#d55e00",
    "rope_c4": "#cc79a7",
    "rope_c5": "#56b4e9",
    "rope_c6": "#f0e442",
    "rope_c7": "#000000",
    "rope_fallback": "#8a8f98",
    "force_hook": "#0072b2",
    "force_wind": "#e69f00",
    "force_inertia": "#009e73",
    "force_reaction": "#d55e00",
}


def normalize_force_scale_mode(mode: object) -> str:
    """Coerce an arbitrary value to a supported force-scale mode."""
    normalized = str(mode or "hybrid").strip().lower()
    return normalized if normalized in FORCE_SCALE_MODES else "hybrid"


def normalize_freebody_target(target: object) -> str:
    """Coerce an arbitrary value to a supported free-body target."""
    normalized = str(target or "none").strip().lower().replace(" ", "_")
    return normalized if normalized in FREEBODY_TARGETS else "none"


def segment_line_width(multiplier: int) -> float:
    """Stroke width for a rope segment carrying ``multiplier`` parts of line.

    Sub-linear so x12 and x20 stay distinguishable without the stroke swamping the
    geometry it runs through.
    """
    parts = max(1, int(multiplier))
    return max(1.5, min(6.0, 0.9 + 0.75 * math.sqrt(parts)))


def _with_alpha(hex_rgb: str, alpha: int) -> str:
    """Return ``#aarrggbb`` for an ``#rrggbb`` colour."""
    return f"#{int(alpha) & 0xFF:02x}{str(hex_rgb).lstrip('#').lower()}"


@dataclass(frozen=True)
class SceneDisplay:
    """Which overlays the scene shows, and how forces are scaled.

    Normalizes on construction, so ``force_scale_mode`` and ``selected_freebody``
    are invariants of the value rather than of one construction path.
    """

    show_labels: bool = False
    show_hook_forces: bool = False
    show_gravity_forces: bool = False
    show_wind_forces: bool = False
    show_inertia_forces: bool = False
    show_reaction_forces: bool = False
    force_scale_mode: str = "hybrid"
    selected_freebody: str = "none"

    _FLAGS = (
        "show_labels",
        "show_hook_forces",
        "show_gravity_forces",
        "show_wind_forces",
        "show_inertia_forces",
        "show_reaction_forces",
    )

    def __post_init__(self) -> None:
        for flag in self._FLAGS:
            object.__setattr__(self, flag, bool(getattr(self, flag)))
        object.__setattr__(
            self, "force_scale_mode", normalize_force_scale_mode(self.force_scale_mode)
        )
        object.__setattr__(
            self, "selected_freebody", normalize_freebody_target(self.selected_freebody)
        )

    @property
    def freebody_body(self) -> Optional[str]:
        """The cut body, or ``None`` for the whole crane."""
        return None if self.selected_freebody == "none" else self.selected_freebody

    def to_dict(self) -> dict[str, Any]:
        """Flat mapping for QML or storage."""
        return {
            **{flag: getattr(self, flag) for flag in self._FLAGS},
            "force_scale_mode": self.force_scale_mode,
            "selected_freebody": self.selected_freebody,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SceneDisplay":
        """Build from a flat mapping, ignoring unknown keys."""
        known = {field_name for field_name in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in data.items() if key in known})

    def with_overlay(self, name: str, visible: bool) -> "SceneDisplay":
        """Return a copy with one named overlay toggled."""
        flag = {
            "hook": "show_hook_forces",
            "gravity": "show_gravity_forces",
            "wind": "show_wind_forces",
            "inertia": "show_inertia_forces",
            "reactions": "show_reaction_forces",
            "labels": "show_labels",
        }.get(name)
        return self if flag is None else replace(self, **{flag: bool(visible)})


@dataclass(frozen=True)
class SceneLayout:
    """Fixed pixel geometry of the scene canvas.

    Scene coordinates are canvas-independent: the frame is built at this nominal
    size and the viewport scales it. Callers only override this to render at a
    different aspect ratio.
    """

    pad: float = 60.0
    height: float = 760.0
    fit_margin: float = 28.0
    structural_member_width: float = 2.0
    cg_marker_radius: float = 6.0
    hit_target_radius: float = 10.0
    boom_axis_length_m: float = 15.0
    #: Largest auto-scaled arrow, as a fraction of canvas height.
    force_height_fraction: float = 0.15
    force_min_visible_px: float = 12.0
    force_fixed_length_px: float = 48.0
    #: Arrows shorter than this are dropped rather than drawn as specks.
    force_cull_px: float = 4.0
    moment_radius: float = 14.0
    moment_sweep_deg: float = 280.0
    moment_arrow_head_px: float = 9.0


DEFAULT_LAYOUT = SceneLayout()


@dataclass(frozen=True)
class SceneInputs:
    """Everything the scene shows, as one value.

    This replaces an ordered eight-setter push protocol on the renderer. The two
    position sets it derives are deliberately distinct:

    * :meth:`node_positions` is the scene *as drawn* -- the hook hangs at the
      current tackle length.
    * :meth:`base_node_positions` is the *kinematic* geometry at the same boom
      angle, which is what the displayed boom basis is derived from. Lowering the
      hook must not rotate that basis.
    """

    document_dict: Optional[dict[str, Any]] = None
    #: Anything exposing ``compute_all_node_positions(boom_angle_deg)``.
    kinematics: Any = None
    hoist_id: str = ""
    hoist: Mapping[str, Any] = field(default_factory=dict)
    conditions: LoadConditions = field(default_factory=LoadConditions)
    display: SceneDisplay = field(default_factory=SceneDisplay)
    analysis_point: Any = None
    tackle_length_m: float = 0.0

    @property
    def has_geometry(self) -> bool:
        """Whether there is a document and a kinematic solver to draw it with."""
        return bool(self.document_dict) and self.kinematics is not None

    def base_node_positions(self) -> Positions:
        """Kinematic node positions at the drawn boom angle."""
        if self.kinematics is None:
            return {}
        return self.kinematics.compute_all_node_positions(self.conditions.boom_angle_deg)

    def node_positions(self) -> Positions:
        """Node positions as drawn, with the active hook lowered by the tackle length."""
        base = self.base_node_positions()
        if not base:
            return {}
        node_definitions = {
            node.get("id"): node for node in (self.document_dict or {}).get("nodes", [])
        }
        return SceneFrameBuilder.with_hook_tackle(
            base,
            node_definitions,
            str(self.hoist.get("load_node_id") or ""),
            self.tackle_length_m,
        )

    def body_filter(self, body_id: Optional[str] = None) -> FreeBodyFilter:
        """Free-body selection to build loads for; defaults to the displayed one."""
        selected = self.display.freebody_body if body_id is None else body_id
        normalized = normalize_freebody_target(selected)
        return FreeBodyFilter(
            None if normalized == "none" else normalized,
            drawn_loads.node_body_map(self.document_dict or {}),
        )

    def body_loads(self, node_positions: Positions, body_id: Optional[str] = None) -> BodyLoads:
        """Every in-plane load on one body, in world coordinates.

        The overlay and the equilibrium report both come through here, so they
        cannot disagree about what is acting on the body.
        """
        return drawn_loads.build_body_loads(
            self.document_dict or {},
            hoist=dict(self.hoist),
            conditions=self.conditions,
            node_positions=node_positions,
            analysis_point=self.analysis_point,
            body_filter=self.body_filter(body_id),
        )


def build_scene_frame(
    inputs: SceneInputs,
    *,
    layout: SceneLayout = DEFAULT_LAYOUT,
    palette: Mapping[str, str] = DEFAULT_PALETTE,
    revision: int = 1,
) -> SceneFrame:
    """One call, one frame: everything the scene canvas draws for ``inputs``.

    ``revision`` is a caller-owned change token; it is carried through untouched so
    a caller that renders repeatedly can tell successive frames apart.
    """
    return _SceneBuilder(inputs, layout, palette, revision).build()


def derive_boom_axes(base_node_positions: Positions, load_node_id: str) -> tuple[Axis, Axis]:
    """Display-only local boom basis, from heel and load-node geometry.

    Deliberately derived rather than stored: ``boom_angle_deg`` remains the one
    canonical orientation value the solver uses.
    """
    identity: tuple[Axis, Axis] = ((1.0, 0.0), (0.0, 1.0))
    heel = base_node_positions.get("boom_heel")
    load = base_node_positions.get(str(load_node_id or ""))
    if heel is None or load is None:
        return identity
    delta_x = float(load["x"]) - float(heel["x"])
    delta_z = float(load["z"]) - float(heel["z"])
    length = math.hypot(delta_x, delta_z)
    if length <= 1e-12:
        return identity
    return (
        (delta_x / length, delta_z / length),
        (-delta_z / length, delta_x / length),
    )


class _SceneBuilder:
    """Single-use accumulator behind :func:`build_scene_frame`.

    Private on purpose: the ordering between its ``_draw_*`` steps is load-bearing
    (centre-of-gravity markers must exist before node pins, which suppress pins
    that would collide with them), and that ordering is exactly what a caller of
    ``build_scene_frame`` should not have to know.
    """

    def __init__(
        self,
        inputs: SceneInputs,
        layout: SceneLayout,
        palette: Mapping[str, str],
        revision: int,
    ) -> None:
        self._inputs = inputs
        self._layout = layout
        self._palette = palette
        self._revision = int(revision)
        self._frame = SceneFrameBuilder()
        self._mapping: Optional[SceneMapping] = None
        self._heel_world: Optional[Tuple[float, float]] = None
        self._scene_node_xy: dict[str, Tuple[float, float]] = {}
        self._boom_frame_segs: list[tuple[Axis, Axis]] = []
        self._fit_rect = (0.0, 0.0, 0.0, 0.0)
        self._guide_scene_x: Optional[float] = None
        self._guide_scene_y: Optional[float] = None
        self._guide_bottom_scene_y: Optional[float] = None
        self._outreach_label = ""
        self._hook_height_label = ""
        self._msl_z: Optional[float] = None
        self._msl_scene_y: Optional[float] = None

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def build(self) -> SceneFrame:
        inputs = self._inputs
        if not inputs.has_geometry:
            return self._status_frame(
                "Load a document to view geometry", self._palette["muted_text"]
            )
        try:
            positions = inputs.node_positions()
        except Exception as exc:  # kinematics failure modes are open-ended
            return self._status_frame(f"Geometry error: {exc}", self._palette["text"])

        self._mapping = SceneMapping.from_positions(
            positions, pad=self._layout.pad, height=self._layout.height
        )
        heel = positions.get("boom_heel")
        if heel:
            self._heel_world = (float(heel["x"]), float(heel["z"]))

        body_filter = inputs.body_filter()
        self._draw_rope_segments(positions)
        self._draw_cg_markers(positions, body_filter)
        self._draw_node_pins(positions, body_filter)
        self._draw_leg_members(positions)

        # Fit rect follows the node pins only: decorative extents (waterline fill,
        # status text, long force arrows) must not inflate what the viewport frames.
        self._fit_rect = self._mapping.fit_rect(
            self._scene_node_xy.values(), margin=self._layout.fit_margin
        )

        self._draw_waterline()
        self._draw_hook_marker(positions)
        self._draw_hook_guide(positions)
        self._draw_boom_frame(positions)
        self._draw_force_overlays(positions, body_filter)
        return self._publish()

    def _status_frame(self, text: str, color: str) -> SceneFrame:
        self._frame.status = SceneStatus(text, color)
        return self._frame.build(fit_rect=(0.0, 0.0, 0.0, 0.0), revision=self._revision)

    def _publish(self) -> SceneFrame:
        has_guide = self._guide_scene_x is not None and self._guide_scene_y is not None
        if has_guide:
            for kind, label in (
                ("outreach", self._outreach_label),
                ("hook_height", self._hook_height_label),
            ):
                self._frame.add_guide(
                    kind=kind,
                    scene_x=float(self._guide_scene_x or 0.0),
                    scene_y=float(self._guide_scene_y or 0.0),
                    label=label,
                )
        if self._msl_z is not None and self._msl_scene_y is not None:
            self._frame.set_waterline(
                scene_y=self._msl_scene_y,
                elevation_z=self._msl_z,
                label=f"MSL  z = {self._msl_z:.1f} m",
            )
        radius = self._layout.hit_target_radius
        for start, end in self._boom_frame_segs:
            self._frame.add_hit_target(
                kind="boom_angle",
                start_x=float(start[0]),
                start_y=float(start[1]),
                end_x=float(end[0]),
                end_y=float(end[1]),
                radius=radius,
                extends_to_canvas_edge=False,
            )
        if has_guide:
            guide_x = float(self._guide_scene_x or 0.0)
            guide_y = float(self._guide_scene_y or 0.0)
            self._frame.add_hit_target(
                kind="outreach",
                start_x=guide_x,
                start_y=guide_y,
                end_x=guide_x,
                end_y=float(self._guide_bottom_scene_y or guide_y),
                radius=radius,
                extends_to_canvas_edge=True,
            )
            self._frame.add_hit_target(
                kind="tackle_length",
                start_x=guide_x,
                start_y=guide_y,
                end_x=guide_x,
                end_y=guide_y,
                radius=radius,
                extends_to_canvas_edge=True,
            )
        return self._frame.build(
            fit_rect=self._fit_rect,
            revision=self._revision,
            mapping=self._mapping,
            heel_world=self._heel_world,
        )

    # ------------------------------------------------------------------
    # Projection and styling
    # ------------------------------------------------------------------

    def _to_scene(self, world_x: float, world_z: float) -> Tuple[float, float]:
        return (0.0, 0.0) if self._mapping is None else self._mapping.to_scene(world_x, world_z)

    def _color(self, key: str) -> str:
        return self._palette.get(key, DEFAULT_PALETTE.get(key, "#000000"))

    def _rope_color(self, rope_id: str) -> str:
        """Stable colour per rope: hoist order first, then a salt-free hash."""
        normalized = str(rope_id or "").strip().lower()
        fallback = self._color("rope_fallback")
        if not normalized:
            return fallback

        order = self._hoist_order_by_rope()
        if normalized in order:
            return self._color(ROPE_COLOR_KEYS[order[normalized] % len(ROPE_COLOR_KEYS)])

        # Deterministic cross-session index (Python's hash() is salted per process).
        accumulator = 0
        for character in normalized:
            accumulator = (accumulator * 131 + ord(character)) % 0x7FFFFFFF
        return self._color(ROPE_COLOR_KEYS[accumulator % len(ROPE_COLOR_KEYS)])

    def _hoist_order_by_rope(self) -> dict[str, int]:
        """Rope id -> colour slot. Solved ropes claim slots before payload ropes."""
        document = self._inputs.document_dict
        if not document:
            return {}
        solved_rope_ids = {
            str(rope.get("id", "")).strip().lower()
            for rope in document.get("ropes", [])
            if str(rope.get("tension_mode", "") or "").strip().lower() == "solve"
        }
        hoists = document.get("hoists", [])
        payload = [
            hoist
            for hoist in hoists
            if str(hoist.get("rope_id", "")).strip().lower() not in solved_rope_ids
        ]
        solved = [
            hoist
            for hoist in hoists
            if str(hoist.get("rope_id", "")).strip().lower() in solved_rope_ids
        ]
        order: dict[str, int] = {}
        for index, hoist in enumerate(solved + payload):
            rope_key = str(hoist.get("rope_id", "")).strip().lower()
            if rope_key:
                order[rope_key] = index
        return order

    def _force_color(self, category: str) -> str:
        key = FORCE_PALETTE_KEYS.get(category)
        return self._color("neutral") if key is None else self._color(key)

    # ------------------------------------------------------------------
    # Structure
    # ------------------------------------------------------------------

    def _effective_multiplier(self, rope_id: str, segment: dict, authored: int) -> int:
        return drawn_loads.effective_segment_mult(
            dict(self._inputs.hoist),
            segment,
            authored,
            rope_id,
            split_mode_active=self._inputs.conditions.split_mode_active,
        )

    def _draw_rope_segments(self, positions: Positions) -> None:
        inputs = self._inputs
        # A cut free body shows interface forces where its ropes were, not the ropes.
        if inputs.display.freebody_body is not None:
            return
        self._frame.add_rope_segments(
            (inputs.document_dict or {}).get("ropes", []),
            positions,
            project=self._to_scene,
            effective_multiplier=self._effective_multiplier,
            style_for=lambda rope_id, multiplier: (
                self._rope_color(rope_id),
                segment_line_width(multiplier),
            ),
            tooltip_for=self._rope_tooltip,
        )

    def _rope_tooltip(
        self,
        rope: dict,
        rope_id: str,
        segment: dict,
        index: int,
        count: int,
        authored: int,
        effective: int,
        positions: Positions,
    ) -> str:
        source_id = str(segment.get("from_node_id", "") or "")
        target_id = str(segment.get("to_node_id", "") or "")
        rope_label = HoistFormatter.display_name(
            rope_id, hoists=(self._inputs.document_dict or {}).get("hoists", [])
        )

        source = positions.get(source_id, {})
        target = positions.get(target_id, {})
        length_m = math.hypot(
            float(target.get("x", 0.0)) - float(source.get("x", 0.0)),
            float(target.get("z", 0.0)) - float(source.get("z", 0.0)),
        )

        tension_kN = drawn_loads.resolve_rope_tension_kN(
            rope,
            rope_id,
            analysis_point=self._inputs.analysis_point,
            hook_load_kN=self._inputs.conditions.hook_load_kN,
        )
        tension_text = "—"
        line_force_text = "—"
        if tension_kN is not None:
            tension_text = f"{tension_kN:.1f} kN"
            line_force_text = f"{abs(tension_kN) * max(1, int(effective)):.1f} kN"

        return "\n".join(
            [
                f"Rope: {rope_label}",
                f"{node_display_name(source_id)} -> {node_display_name(target_id)}",
                f"Parts: {effective}",
                f"Length: {length_m:.2f} m",
                f"Tension: {tension_text}",
                f"Line force: {line_force_text}",
            ]
        )

    def _draw_node_pins(self, positions: Positions, body_filter: FreeBodyFilter) -> None:
        inputs = self._inputs
        if body_filter.is_free_body:
            # A free body shows the nodes where load enters it, whoever owns them.
            visible_ids: Iterable[str] = drawn_loads.loaded_node_ids(
                inputs.document_dict or {},
                hoist=dict(inputs.hoist),
                conditions=inputs.conditions,
                node_positions=positions,
                analysis_point=inputs.analysis_point,
                body_filter=body_filter,
            )
        else:
            visible_ids = list(positions)
        nodes = self._frame.add_nodes_from_positions(
            positions,
            project=self._to_scene,
            tooltip_for=lambda node_id, position: (
                f"{node_display_name(str(node_id))}"
                f"\n({position['x']:.2f}, {position['z']:.2f}) m"
            ),
            visible_ids=visible_ids,
        )
        for node in nodes:
            self._scene_node_xy[node.id] = (node.scene_x, node.scene_y)

    def _draw_leg_members(self, positions: Positions) -> None:
        self._frame.add_structural_members(
            positions,
            project=self._to_scene,
            selected_freebody=self._inputs.display.selected_freebody,
            color=self._color("frame"),
            width=self._layout.structural_member_width,
        )

    def _draw_cg_markers(self, positions: Positions, body_filter: FreeBodyFilter) -> None:
        document = self._inputs.document_dict
        if not document:
            return
        self._frame.add_cg_markers(
            document.get("bodies", []),
            heel=positions.get("boom_heel", {"x": 0.0, "z": 0.0}),
            boom_angle_degrees=self._inputs.conditions.boom_angle_deg,
            project=self._to_scene,
            include_body=body_filter.matches_body,
            tooltip_for=drawn_loads.mass_point_label,
            radius=self._layout.cg_marker_radius,
        )
        self._draw_split_support_cg_marker(positions, body_filter)
        self._draw_winch_cg_markers(positions, body_filter)

    def _draw_split_support_cg_marker(
        self, positions: Positions, body_filter: FreeBodyFilter
    ) -> None:
        inputs = self._inputs
        self._frame.add_split_support_cg_marker(
            positions,
            support_node_id=str(inputs.hoist.get("support_node_id", "")).strip(),
            support_mass_t=drawn_loads.split_support_mass_t(
                dict(inputs.hoist), split_mode_active=inputs.conditions.split_mode_active
            ),
            include_node=body_filter.owns_node,
            project=self._to_scene,
            hoist_label=str(inputs.hoist_id or inputs.hoist.get("id") or "hoist"),
            radius=self._layout.cg_marker_radius,
        )

    def _draw_winch_cg_markers(self, positions: Positions, body_filter: FreeBodyFilter) -> None:
        """A centre-of-gravity symbol per winch node, carrying the rope mass spooled there."""
        document = self._inputs.document_dict
        if not document:
            return
        for hoist in document.get("hoists", []):
            hoist_id = str(hoist.get("id", "")).strip()
            if not hoist_id:
                continue
            try:
                mass_by_node = compute_winch_marker_masses_kg(
                    document, hoist_id, positions, self._effective_multiplier
                )
            except (ValueError, KeyError):
                continue
            for node_id, mass_kg in mass_by_node.items():
                if node_id not in positions or not body_filter.owns_node(node_id):
                    continue
                position = positions[node_id]
                scene_x, scene_y = self._to_scene(float(position["x"]), float(position["z"]))
                self._frame.add_marker(
                    kind="center_of_gravity",
                    scene_x=float(scene_x),
                    scene_y=float(scene_y),
                    radius=self._layout.cg_marker_radius,
                    tooltip=(
                        f"Center of gravity\nWinch: {hoist_id}\n"
                        f"Rope mass on winch: {mass_kg / 1000.0:.2f} t"
                    ),
                )

    # ------------------------------------------------------------------
    # Guides and annotation
    # ------------------------------------------------------------------

    def _draw_waterline(self) -> None:
        document = self._inputs.document_dict
        if self._inputs.display.freebody_body is not None or not document:
            return
        elevation_z = document.get("environment", {}).get("mean_sealevel_z_m")
        if elevation_z is None:
            return
        _, scene_y = self._to_scene(0.0, float(elevation_z))
        self._msl_z = float(elevation_z)
        self._msl_scene_y = scene_y

    def _hook_position(self, positions: Positions) -> Optional[dict[str, float]]:
        if self._inputs.display.freebody_body is not None:
            return None
        load_node_id = self._inputs.hoist.get("load_node_id")
        if not load_node_id or load_node_id not in positions:
            return None
        return positions[load_node_id]

    def _draw_hook_marker(self, positions: Positions) -> None:
        hook = self._hook_position(positions)
        if hook is None:
            return
        self._guide_bottom_scene_y = self._layout.height - self._layout.pad
        self._outreach_label = f"R = {float(hook['x']):.1f} m"

    def _draw_hook_guide(self, positions: Positions) -> None:
        """Anchor for the dashed hook-elevation and outreach guides."""
        hook = self._hook_position(positions)
        if hook is None:
            return
        scene_x, scene_y = self._to_scene(hook["x"], hook["z"])
        self._guide_scene_x = scene_x
        self._guide_scene_y = scene_y
        self._hook_height_label = f"Z = {float(hook['z']):.1f} m"

    def _boom_axes(self) -> tuple[Axis, Axis]:
        """The displayed boom basis, from *kinematic* geometry.

        Uses :meth:`SceneInputs.base_node_positions`, not the drawn positions, so
        lowering the hook on its tackle does not rotate the axes.
        """
        identity: tuple[Axis, Axis] = ((1.0, 0.0), (0.0, 1.0))
        inputs = self._inputs
        if not inputs.hoist_id or not inputs.hoist:
            return identity
        try:
            base_positions = inputs.base_node_positions()
        except Exception:  # kinematics failure modes are open-ended
            return identity
        return derive_boom_axes(base_positions, str(inputs.hoist.get("load_node_id") or ""))

    def _draw_boom_frame(self, positions: Positions) -> None:
        if self._inputs.display.freebody_body is not None:
            return
        heel = positions.get("boom_heel")
        if not heel:
            return
        heel_x, heel_z = float(heel["x"]), float(heel["z"])
        x_axis, z_axis = self._boom_axes()
        length = self._layout.boom_axis_length_m
        origin = self._to_scene(heel_x, heel_z)
        x_end = self._to_scene(heel_x + length * x_axis[0], heel_z + length * x_axis[1])
        z_end = self._to_scene(heel_x + length * z_axis[0], heel_z + length * z_axis[1])
        self._boom_frame_segs = [(origin, x_end), (origin, z_end)]
        for label, end, color_key in (("X", x_end, "axis_x"), ("Z", z_end, "axis_z")):
            self._frame.add_axis(
                label=label,
                start_x=float(origin[0]),
                start_y=float(origin[1]),
                end_x=float(end[0]),
                end_y=float(end[1]),
                color=self._color(color_key),
            )

    # ------------------------------------------------------------------
    # Force overlays
    # ------------------------------------------------------------------

    def _visible_categories(self, body_filter: FreeBodyFilter) -> tuple[str, ...]:
        """Which load categories the overlay toggles and free-body mode admit.

        A cut free body shows everything acting on it, including the interface loads
        (rope, idle hook mass) that are hidden in the whole-crane view -- otherwise
        its equilibrium would not close.
        """
        display = self._inputs.display
        free_body = body_filter.is_free_body
        visible: list[str] = []
        if free_body:
            visible.append(drawn_loads.IDLE_HOOK_MASS)
            visible.append(drawn_loads.ROPE_INTERFACE)
        if display.show_gravity_forces or free_body:
            visible.append(drawn_loads.GRAVITY)
        if display.show_hook_forces or free_body:
            visible.append(drawn_loads.HOOK_LOAD)
        if display.show_wind_forces or free_body:
            visible.append(drawn_loads.WIND)
        if display.show_inertia_forces or free_body:
            visible.append(drawn_loads.INERTIA)
        if (display.show_reaction_forces or free_body) and self._inputs.analysis_point:
            visible.append(drawn_loads.REACTIONS)
        return tuple(visible)

    def _draw_force_overlays(self, positions: Positions, body_filter: FreeBodyFilter) -> None:
        inputs = self._inputs
        if not inputs.document_dict:
            return

        loads = inputs.body_loads(positions)
        visible = self._visible_categories(body_filter)
        vectors = loads.vectors(*visible) if visible else ()
        # Moments are a free-body concept: they only balance a single cut body.
        moments = (
            loads.moments if body_filter.is_free_body and drawn_loads.REACTIONS in visible else ()
        )
        if not vectors and not moments:
            return

        layout = self._layout
        if inputs.display.force_scale_mode == "fixed":
            for vector in vectors:
                self._add_force_arrow(vector, 1.0, fixed_length=layout.force_fixed_length_px)
            self._add_moment_glyphs(moments)
            return

        # Auto-scale so the largest arrow spans a fixed fraction of the canvas.
        max_magnitude = max((vector.magnitude_kN for vector in vectors), default=0.0)
        if max_magnitude < 1e-9:
            return
        shared_scale = (layout.height * layout.force_height_fraction) / max_magnitude
        min_visible_px = (
            layout.force_min_visible_px if inputs.display.force_scale_mode == "hybrid" else 0.0
        )
        for vector in vectors:
            self._add_force_arrow(vector, shared_scale, min_visible_px=min_visible_px)
        self._add_moment_glyphs(moments)

    def _add_force_arrow(
        self,
        vector: LoadVector,
        px_per_kN: float,
        *,
        min_visible_px: float = 12.0,
        fixed_length: Optional[float] = None,
    ) -> None:
        origin_x, origin_y = self._to_scene(vector.world_x, vector.world_z)
        if fixed_length is not None:
            magnitude = math.hypot(vector.fx_kN, vector.fz_kN)
            if magnitude < 1e-9:
                return
            delta_x = (vector.fx_kN / magnitude) * fixed_length
            delta_y = -(vector.fz_kN / magnitude) * fixed_length
        else:
            delta_x = vector.fx_kN * px_per_kN
            delta_y = -vector.fz_kN * px_per_kN

        raw_length = math.hypot(delta_x, delta_y)
        if raw_length <= 1e-9:
            return

        # Clamped arrows are drawn dashed, translucent and tagged "not to scale":
        # they carry direction honestly but not magnitude.
        clamped = False
        if fixed_length is None:
            if min_visible_px > 0 and raw_length < min_visible_px:
                stretch = min_visible_px / raw_length
                delta_x *= stretch
                delta_y *= stretch
                clamped = True
            elif raw_length < self._layout.force_cull_px:
                return
        if math.hypot(delta_x, delta_y) < 1e-9:
            return

        color = _with_alpha(self._force_color(vector.category), 180 if clamped else 255)
        label = vector.label + (" (NTS)" if clamped else "")
        tip_x, tip_y = origin_x + delta_x, origin_y + delta_y
        self._frame.add_force_arrow(
            origin_x=float(origin_x),
            origin_y=float(origin_y),
            tip_x=float(tip_x),
            tip_y=float(tip_y),
            color=color,
            dashed=clamped,
            label=label,
            tooltip=vector.detail or vector.label,
        )
        if self._inputs.display.show_labels:
            self._frame.add_label(
                kind="force",
                scene_x=float(tip_x + 3),
                scene_y=float(tip_y - 12),
                color=color,
                text=label,
            )

    def _add_moment_glyphs(self, moments: Iterable[LoadMoment]) -> None:
        layout = self._layout
        color = _with_alpha(self._force_color(drawn_loads.REACTIONS), 255)
        radius = layout.moment_radius
        for moment in moments:
            origin_x, origin_y = self._to_scene(moment.world_x, moment.world_z)

            # Open arc plus arrowhead: reads more cleanly than a full circle.
            if moment.moment_kNm >= 0.0:
                start_deg = -50.0
                span_deg = layout.moment_sweep_deg  # Positive -> counterclockwise.
            else:
                start_deg = 230.0
                span_deg = -layout.moment_sweep_deg

            # Arrowhead base sits on the arc endpoint; the tip extends along the
            # local tangent so the head reads as tangent to the curve.
            base_rad = math.radians(start_deg + span_deg)
            base_x = origin_x + radius * math.cos(base_rad)
            base_y = origin_y - radius * math.sin(base_rad)
            tangent_x = -math.sin(base_rad)
            tangent_y = -math.cos(base_rad)
            if span_deg < 0.0:
                tangent_x, tangent_y = -tangent_x, -tangent_y
            tangent_length = math.hypot(tangent_x, tangent_y)
            if tangent_length < 1e-9:
                continue
            head = layout.moment_arrow_head_px

            self._frame.add_moment(
                origin_x=float(origin_x),
                origin_y=float(origin_y),
                moment_kNm=float(moment.moment_kNm),
                radius=radius,
                start_degrees=start_deg,
                span_degrees=span_deg,
                arrow_tip_x=float(base_x + (tangent_x / tangent_length) * head),
                arrow_tip_y=float(base_y + (tangent_y / tangent_length) * head),
                color=color,
                label=moment.label,
                tooltip=moment.detail or moment.label,
            )
            if self._inputs.display.show_labels:
                self._frame.add_label(
                    kind="moment",
                    scene_x=float(origin_x + radius + 4.0),
                    scene_y=float(origin_y - radius - 10.0),
                    color=color,
                    text=moment.label,
                )
