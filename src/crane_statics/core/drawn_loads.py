"""Drawn loads: the single in-plane definition of the crane load model.

Every load the scene draws and the Equilibrium Check verifies is built here, in
**world** coordinates, as named values. No Qt, no colours, no scene projection --
projection and styling belong to the renderer, which applies them to what this
module returns.

Scope: this module models the **X/Z plane only**. Lateral acceleration
(``accel_y_m_s2``), roll acceleration, sidelead and Y-axis wind produce purely
out-of-plane (Y) forces -- see ``engine._build_split_support_reactions``, which
routes them into ``fy`` alone -- so they have no drawable vector here and no
effect on in-plane equilibrium. They are deliberately absent from
:class:`LoadConditions` rather than silently dropped.

On a heeled/trimmed vessel gravity tilts. Its in-plane part is drawn here: every
weight gets an X component and a reduced Z component, from the same
``vessel_attitude.crane_frame_gravity`` the solver uses, derived from the
document's attitude and ``LoadConditions.slew_deg``. The out-of-plane part
belongs to the support split, like sidelead.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping, Optional, Sequence

from ..calculation.rope_mass import RopeNodeMass, hook_support_node_id, rope_mass_at_nodes
from ..calculation.vessel_attitude import CraneFrameGravity, VesselAttitude, crane_frame_gravity
from ..presentation.formatters import node_display_name

# Unified reaction semantics: a reaction's participating bodies and the node it
# is anchored at, per body. Keeps sign and anchor from drifting apart.
REACTION_SPECS: dict[str, dict[str, Any]] = {
    "heel_point": {
        "default_anchor": "boom_heel",
        "participants": ("boom", "platform"),
        "anchors_by_body": {
            "boom": "boom_heel",
            "platform": "platform_heel",
        },
    },
    "rear_hinge": {
        "default_anchor": "rear_base",
        "participants": ("rear_leg", "platform"),
        "anchors_by_body": {
            "rear_leg": "rear_base",
            "platform": "platform_rear",
        },
    },
    "front_hinge": {
        "default_anchor": "front_base",
        "participants": ("front_leg", "platform"),
        "anchors_by_body": {
            "front_leg": "front_base",
            "platform": "platform_front",
        },
    },
    "upper_hinge": {
        "default_anchor": "rear_top",
        # Scene-only participant semantics at top-joint coordinates.
        "participants": ("front_leg", "rear_leg"),
        "anchors_by_body": {
            "front_leg": "front_top",
            "rear_leg": "rear_top",
        },
    },
    "platform_base": {
        "default_anchor": "platform_base",
        "participants": ("platform",),
        "anchors_by_body": {
            "platform": "platform_base",
        },
    },
}

# The synthetic support that carries a selected body's residual moment.
_SYNTHETIC_SUPPORT_BY_BODY = {
    "platform": "platform_base",
    "boom": "heel_point",
    "rear_leg": "rear_hinge",
    "front_leg": "front_hinge",
}

GRAVITY = "Gravity"
ROPE_WEIGHT = "Rope weight"
IDLE_HOOK_MASS = "Idle hook mass"
HOOK_LOAD = "Hook load"
WIND = "Wind"
INERTIA = "Inertia"
ROPE_INTERFACE = "Rope interface"
REACTIONS = "Reactions"

#: Report/overlay order. The Equilibrium Check renders categories in this order.
CATEGORY_ORDER = (
    GRAVITY,
    ROPE_WEIGHT,
    IDLE_HOOK_MASS,
    HOOK_LOAD,
    WIND,
    INERTIA,
    ROPE_INTERFACE,
    REACTIONS,
)


@dataclass(frozen=True)
class LoadVector:
    """A force applied at a world point, in kN."""

    world_x: float
    world_z: float
    fx_kN: float
    fz_kN: float
    category: str
    label: str
    detail: str = ""

    @property
    def magnitude_kN(self) -> float:
        return math.hypot(self.fx_kN, self.fz_kN)


@dataclass(frozen=True)
class LoadMoment:
    """A moment applied at a world point, in kNm."""

    world_x: float
    world_z: float
    moment_kNm: float
    entity_id: str
    label: str
    detail: str = ""


@dataclass(frozen=True)
class BodyLoads:
    """Named load categories plus reaction moments for one free-body selection."""

    categories: tuple[tuple[str, tuple[LoadVector, ...]], ...] = ()
    moments: tuple[LoadMoment, ...] = ()

    def category(self, name: str) -> tuple[LoadVector, ...]:
        for category_name, vectors in self.categories:
            if category_name == name:
                return vectors
        return ()

    def vectors(self, *names: str) -> tuple[LoadVector, ...]:
        """All vectors, or only those in the named categories, in report order."""
        wanted = set(names) if names else None
        return tuple(
            vector
            for name, vectors in self.categories
            if wanted is None or name in wanted
            for vector in vectors
        )

    def sum_fx_kN(self) -> float:
        return sum(vector.fx_kN for vector in self.vectors())

    def sum_fz_kN(self) -> float:
        return sum(vector.fz_kN for vector in self.vectors())


@dataclass(frozen=True)
class LoadConditions:
    """In-plane environmental and hoist state a load set is evaluated at.

    Out-of-plane inputs (lateral/roll acceleration, sidelead, Y-wind) are
    absent by design -- see the module docstring.
    """

    boom_angle_deg: float = 0.0
    hook_load_kN: float = 0.0
    wind_speed_m_s: float = 0.0
    wind_direction: str = "+X"
    accel_x_m_s2: float = 0.0
    accel_z_m_s2: float = 0.0
    pitch_accel_rad_s2: float = 0.0
    offlead_deg: float = 0.0
    split_mode_active: bool = False
    # Crane slew on the vessel; it only matters when the document sets heel/trim.
    slew_deg: float = 0.0


@dataclass(frozen=True)
class FreeBodyFilter:
    """Which body's loads to include. ``selected_body=None`` means the whole crane."""

    selected_body: Optional[str] = None
    node_body_by_id: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def whole_crane(cls, node_body_by_id: Optional[Mapping[str, str]] = None) -> "FreeBodyFilter":
        return cls(None, node_body_by_id or {})

    @property
    def is_free_body(self) -> bool:
        return self.selected_body is not None

    def matches_body(self, body_id: object) -> bool:
        if self.selected_body is None:
            return True
        return str(body_id or "").strip().lower() == self.selected_body

    def owns_node(self, node_id: object) -> bool:
        if self.selected_body is None:
            return True
        body = self.node_body_by_id.get(str(node_id), "")
        return str(body).strip().lower() == self.selected_body

    def reaction_sign(self, entity_id: str) -> Optional[float]:
        """+1 / -1 for a reaction acting on the selected body, or None if it doesn't."""
        if self.selected_body is None:
            return 1.0
        participants = tuple(REACTION_SPECS.get(str(entity_id), {}).get("participants", ()))
        if not participants:
            return None
        if len(participants) == 1:
            return 1.0 if participants[0] == self.selected_body else None
        if self.selected_body == participants[0]:
            return 1.0
        if self.selected_body == participants[1]:
            return -1.0
        return None

    def reaction_anchor_node(self, entity_id: str) -> str:
        spec = REACTION_SPECS.get(str(entity_id), {})
        default = str(spec.get("default_anchor", "")).strip()
        if self.selected_body is None:
            return default
        anchors = spec.get("anchors_by_body", {})
        return str(anchors.get(self.selected_body, default)).strip()

    def synthetic_support_entity(self) -> Optional[str]:
        if self.selected_body is None:
            return None
        return _SYNTHETIC_SUPPORT_BY_BODY.get(self.selected_body)


def node_body_map(document_dict: Mapping[str, Any]) -> dict[str, str]:
    """Node id -> owning body id, for :class:`FreeBodyFilter`."""
    return {
        str(node.get("id", "")): str(node.get("body", ""))
        for node in document_dict.get("nodes", [])
        if node.get("id")
    }


def _positive_int(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _nonnegative_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except Exception:
        return None
    return parsed if parsed >= 0.0 else None


def effective_segment_mult(
    hoist: Mapping[str, Any],
    segment: Mapping[str, Any],
    authored_mult: int,
    rope_id: str,
    *,
    split_mode_active: bool,
) -> int:
    """Falls carried by one rope segment, honouring the hoist's split-block mode.

    Only the segment the active hoist manages (support node <-> load node) is
    overridden; every other segment keeps its authored multiplier.
    """
    hoist_rope_id = str(hoist.get("rope_id", "")).strip()
    if not hoist_rope_id or str(rope_id).strip() != hoist_rope_id:
        return authored_mult

    support_node_id = str(hoist.get("support_node_id", "")).strip()
    load_node_id = str(hoist.get("load_node_id", "")).strip()
    if not support_node_id or not load_node_id:
        return authored_mult

    from_node = str(segment.get("from_node_id", "")).strip()
    to_node = str(segment.get("to_node_id", "")).strip()
    is_managed_hook_segment = (from_node == support_node_id and to_node == load_node_id) or (
        from_node == load_node_id and to_node == support_node_id
    )
    if not is_managed_hook_segment:
        return authored_mult

    falls = _positive_int(hoist.get("falls"))
    split_falls = _positive_int(hoist.get("split_falls"))
    if split_mode_active and split_falls is not None:
        return split_falls
    if falls is not None:
        return falls
    return authored_mult


def split_support_mass_t(hoist: Mapping[str, Any], *, split_mode_active: bool) -> Optional[float]:
    """Mass left at the support node when a splitable block is split, in tonnes."""
    if not split_mode_active:
        return None
    if not bool(hoist.get("splitable_block", False)):
        return None
    hook_mass_t = _nonnegative_float(hoist.get("hook_mass_t"))
    split_hook_mass_t = _nonnegative_float(hoist.get("split_hook_mass_t"))
    if hook_mass_t is None or split_hook_mass_t is None:
        return None
    support_mass_t = max(0.0, hook_mass_t - split_hook_mass_t)
    if support_mass_t <= 1e-9:
        return None
    return support_mass_t


def active_hoist_dict(document_dict: Mapping[str, Any], hoist_id: str) -> dict[str, Any]:
    """The authored hoist a load set is built for, or ``{}`` when unresolved."""
    return next(
        (h for h in document_dict.get("hoists", []) if h.get("id") == hoist_id),
        {},
    )


def rope_tension_channel(rope: Mapping[str, Any], rope_id: str) -> str:
    """Which analysis-point channel carries this rope's tension."""
    mode = str(rope.get("tension_mode", "") or "").strip().lower()
    return "boom_hoist" if mode == "solve" else rope_id


def resolve_rope_tension_kN(
    rope: Mapping[str, Any],
    rope_id: str,
    *,
    analysis_point: Any,
    hook_load_kN: float,
) -> Optional[float]:
    """Rope tension at the given hook load, linearised about the analysis point."""
    if analysis_point is None:
        return None
    baseline = getattr(analysis_point, "baseline_rope_tensions", {}) or {}
    sensitivity = getattr(analysis_point, "sensitivity_rope_tensions", {}) or {}
    channel = rope_tension_channel(rope, rope_id)
    base = float(baseline.get(channel, baseline.get(rope_id, 0.0)))
    sens = float(sensitivity.get(channel, sensitivity.get(rope_id, 0.0)))
    return base + sens * float(hook_load_kN)


def drawn_crane_gravity(
    document_dict: Mapping[str, Any], conditions: LoadConditions, analysis_point: Any = None
) -> CraneFrameGravity:
    """The gravity direction a drawing of these conditions uses.

    Reactions come from the solved point, so its gravity is authoritative; the
    conditions' slew only stands in when there is no point yet.
    """
    solved = getattr(analysis_point, "crane_gravity", None)
    if isinstance(solved, CraneFrameGravity):
        return solved
    attitude = VesselAttitude.from_environment((document_dict or {}).get("environment"))
    return crane_frame_gravity(attitude, float(conditions.slew_deg))


def _weight_detail(title: str, fx: float, fz: float) -> str:
    if fx == 0.0:
        return f"{title}\nFz={fz:.1f} kN"
    return f"{title}\nFx={fx:.1f} kN  Fz={fz:.1f} kN"


def mass_point_label(mass_point: Mapping[str, Any]) -> str:
    mass_point_id = str(mass_point.get("id", "")).strip()
    return mass_point_id if mass_point_id else "Unnamed mass point"


class _LoadBuilder:
    """Assembles one :class:`BodyLoads` for a document, hoist and condition set."""

    def __init__(
        self,
        document_dict: Mapping[str, Any],
        hoist: Mapping[str, Any],
        conditions: LoadConditions,
        positions: Mapping[str, Mapping[str, float]],
        analysis_point: Any,
        body_filter: FreeBodyFilter,
    ) -> None:
        self._doc = document_dict or {}
        self._hoist = hoist or {}
        self._c = conditions
        self._positions = positions or {}
        self._pt = analysis_point
        self._filter = body_filter
        self._env = self._doc.get("environment", {}) or {}
        self._g = drawn_crane_gravity(self._doc, conditions, analysis_point)

    # -- geometry ---------------------------------------------------------

    def _weight(self, mass_t: float) -> tuple[float, float]:
        """(Fx, Fz) weight of a mass in the crane's X/Z plane."""
        g_kN_per_t = abs(float(self._env.get("gravity_m_s2", 9.81)))
        return (
            float(mass_t) * g_kN_per_t * self._g.lateral_x,
            -float(mass_t) * g_kN_per_t * self._g.vertical,
        )

    def _sheave_of(self, hoist_id: str, hook_node_id: str) -> str:
        """The node a hook block hangs from; its rope's line of action passes there."""
        sheave_id = hook_support_node_id(dict(self._doc), hoist_id)
        return sheave_id if sheave_id in self._positions else hook_node_id

    def _heel(self) -> Mapping[str, float]:
        return self._positions.get("boom_heel", {"x": 0.0, "z": 0.0})

    def _body_point(self, body_id: str, spec: Mapping[str, Any]) -> Optional[tuple[float, float]]:
        """World point of an authored mass point / wind area, or None if unplaced."""
        local_x = spec.get("local_x_m")
        if local_x is not None and body_id == "boom":
            heel = self._heel()
            angle = math.radians(self._c.boom_angle_deg)
            local_z = float(spec.get("local_z_m", 0.0))
            xw = heel["x"] + float(local_x) * math.cos(angle) - local_z * math.sin(angle)
            zw = heel["z"] + float(local_x) * math.sin(angle) + local_z * math.cos(angle)
            return xw, zw
        if spec.get("x_m") is not None:
            return float(spec["x_m"]), float(spec.get("z_m", 0.0))
        return None

    def _bodies(self) -> Iterator[tuple[str, Mapping[str, Any]]]:
        for body in self._doc.get("bodies", []):
            body_id = body.get("id", "")
            if self._filter.is_free_body and not self._filter.matches_body(body_id):
                continue
            yield str(body_id), body

    # -- categories -------------------------------------------------------

    def gravity(self) -> tuple[LoadVector, ...]:
        vectors: list[LoadVector] = []

        for body_id, body in self._bodies():
            for mass_point in body.get("mass_points", []):
                mass = float(mass_point.get("mass_t", 0.0))
                if mass <= 0:
                    continue
                point = self._body_point(body_id, mass_point)
                if point is None:
                    continue
                xw, zw = point
                fx, fz = self._weight(mass)
                label = mass_point_label(mass_point)
                vectors.append(
                    LoadVector(
                        world_x=xw,
                        world_z=zw,
                        fx_kN=fx,
                        fz_kN=fz,
                        category=GRAVITY,
                        label=f"Weight {label}: {math.hypot(fx, fz):.1f} kN",
                        detail=_weight_detail(f"Weight {label} ({body_id})", fx, fz),
                    )
                )

        support_mass_t = split_support_mass_t(
            self._hoist, split_mode_active=self._c.split_mode_active
        )
        support_node_id = str(self._hoist.get("support_node_id", "")).strip()
        if support_mass_t is not None and support_node_id and support_node_id in self._positions:
            if not self._filter.is_free_body or self._filter.owns_node(support_node_id):
                position = self._positions[support_node_id]
                fx, fz = self._weight(float(support_mass_t))
                vectors.append(
                    LoadVector(
                        world_x=float(position["x"]),
                        world_z=float(position["z"]),
                        fx_kN=fx,
                        fz_kN=fz,
                        category=GRAVITY,
                        label=f"Split block weight: {math.hypot(fx, fz):.1f} kN",
                        detail=_weight_detail("Split block weight", fx, fz),
                    )
                )
        return tuple(vectors)

    def rope_weight_node_masses(self) -> dict[str, RopeNodeMass]:
        """Rope self-weight lumped per node, filtered to the selected free body."""
        masses = rope_mass_at_nodes(
            dict(self._doc),
            self._positions,
            effective_mult=lambda rope_id, segment, authored_mult: effective_segment_mult(
                self._hoist,
                segment,
                authored_mult,
                rope_id,
                split_mode_active=self._c.split_mode_active,
            ),
        )
        return {
            node_id: entry
            for node_id, entry in masses.items()
            if node_id in self._positions
            and entry.mass_t > 1e-9
            and (not self._filter.is_free_body or self._filter.owns_node(node_id))
        }

    def rope_weight(self) -> tuple[LoadVector, ...]:
        """One vector per node carrying rope: its weight and its inertia combined.

        The falls and the winch drum are the same rope, so they are reported as
        one arrow per node rather than split across the Gravity and Inertia
        categories -- the detail text names the reeved and spooled shares.
        """
        vessel_motion = self._env.get("vessel_motion", {}) or {}
        ref_x = float(vessel_motion.get("reference_x_m", 0.0))
        ref_z = float(vessel_motion.get("reference_z_m", 0.0))
        ax = float(self._c.accel_x_m_s2)
        az = float(self._c.accel_z_m_s2)
        pitch = float(self._c.pitch_accel_rad_s2)

        vectors: list[LoadVector] = []
        for node_id, entry in self.rope_weight_node_masses().items():
            position = self._positions[node_id]
            xw, zw = float(position["x"]), float(position["z"])
            mass_t = float(entry.mass_t)
            # Rope carries no wind area and no hook DAF: dead mass on a moving vessel.
            weight_fx, weight_fz = self._weight(mass_t)
            fx = weight_fx - mass_t * (ax + pitch * (zw - ref_z))
            fz = weight_fz - mass_t * (az - pitch * (xw - ref_x))
            name = node_display_name(node_id)
            vectors.append(
                LoadVector(
                    world_x=xw,
                    world_z=zw,
                    fx_kN=fx,
                    fz_kN=fz,
                    category=ROPE_WEIGHT,
                    label=f"Rope weight @ {name}: {mass_t:.1f} t",
                    detail=(
                        f"Rope weight @ {name} ({', '.join(entry.hoist_ids)})\n"
                        f"reeved {entry.reeved_t:.1f} t + spooled {entry.spooled_t:.1f} t\n"
                        f"Fx={fx:.1f} kN  Fz={fz:.1f} kN"
                    ),
                )
            )
        return tuple(vectors)

    def wind(self) -> tuple[LoadVector, ...]:
        vectors: list[LoadVector] = []
        direction = str(self._c.wind_direction or "+X")
        if direction not in {"+X", "-X"}:
            # The scene is an X/Z projection, so Y-axis wind has no drawable vector.
            return ()
        wind = float(self._c.wind_speed_m_s)
        rho = float(self._env.get("air_density_kg_m3", 1.225))
        z_ref = float(self._env.get("wind_reference_height_m_asl", 10.0))
        exponent = float(self._env.get("wind_profile_exponent", 0.143))
        msl = float(self._env.get("mean_sealevel_z_m", 0.0))
        angle = math.radians(self._c.boom_angle_deg)

        for body_id, body in self._bodies():
            for wind_area in body.get("wind_areas", []):
                area = float(wind_area.get("area_w_m2", 0.0))
                cd = float(wind_area.get("cd", 1.2))
                point = self._body_point(body_id, wind_area)
                if point is None:
                    continue
                xw, zw = point
                is_boom_local = wind_area.get("local_x_m") is not None and body_id == "boom"
                area_proj = area * abs(math.sin(angle)) if is_boom_local else area

                h_asl = zw - msl
                v_eff = abs(wind) * (max(h_asl, 0.1) / max(z_ref, 0.1)) ** exponent
                force = 0.5 * rho * cd * area_proj * v_eff**2 / 1000.0
                fx = force if direction == "+X" else -force
                if abs(fx) < 1e-6:
                    continue
                vectors.append(
                    LoadVector(
                        world_x=xw,
                        world_z=zw,
                        fx_kN=fx,
                        fz_kN=0.0,
                        category=WIND,
                        label=f"Wind {direction} {body_id}: {abs(fx):.1f} kN",
                        detail=f"Wind {direction} {body_id}\n{abs(fx):.1f} kN @ {v_eff:.1f} m/s",
                    )
                )
        return tuple(vectors)

    def inertia(self) -> tuple[LoadVector, ...]:
        ax = float(self._c.accel_x_m_s2)
        az = float(self._c.accel_z_m_s2)
        pitch = float(self._c.pitch_accel_rad_s2)
        if abs(ax) < 1e-9 and abs(az) < 1e-9 and abs(pitch) < 1e-9:
            return ()

        vessel_motion = self._env.get("vessel_motion", {}) or {}
        ref_x = float(vessel_motion.get("reference_x_m", 0.0))
        ref_z = float(vessel_motion.get("reference_z_m", 0.0))

        vectors: list[LoadVector] = []
        for body_id, body in self._bodies():
            for mass_point in body.get("mass_points", []):
                mass = float(mass_point.get("mass_t", 0.0))
                if mass <= 0:
                    continue
                point = self._body_point(body_id, mass_point)
                if point is None:
                    continue
                xw, zw = point
                dx, dz = xw - ref_x, zw - ref_z
                ax_pt = ax + pitch * dz
                az_pt = az - pitch * dx
                # D'Alembert inertia; gravity is carried by the Gravity category.
                fx, fz = -mass * ax_pt, -mass * az_pt
                if abs(fx) < 1e-6 and abs(fz) < 1e-6:
                    continue
                vectors.append(
                    LoadVector(
                        world_x=xw,
                        world_z=zw,
                        fx_kN=fx,
                        fz_kN=fz,
                        category=INERTIA,
                        label=f"Inertia {body_id}",
                        detail=f"{body_id}\nFx={fx:.1f} kN  Fz={fz:.1f} kN",
                    )
                )
        return tuple(vectors)

    def hook_load(self) -> tuple[LoadVector, ...]:
        """Hook load: its vertical part at the hook, its lateral part at the sheave.

        The lateral part is the offlead plus, on a tilted vessel, the plumb hook's
        lean in the luffing plane.
        """
        load_node_id = self._hoist.get("load_node_id")
        if not load_node_id or load_node_id not in self._positions:
            return ()
        if self._filter.is_free_body and not self._filter.owns_node(str(load_node_id)):
            return ()
        hook_kN = max(0.0, float(self._c.hook_load_kN))
        if hook_kN <= 0:
            return ()

        hook = self._positions[load_node_id]
        vectors = [
            LoadVector(
                world_x=float(hook["x"]),
                world_z=float(hook["z"]),
                fx_kN=0.0,
                fz_kN=-hook_kN * self._g.vertical,
                category=HOOK_LOAD,
                label=f"Hook {hook_kN:.0f} kN",
            )
        ]

        offlead_fx = math.sin(math.radians(float(self._c.offlead_deg))) * hook_kN
        tilt_fx = self._g.lateral_x * hook_kN
        lateral_fx = offlead_fx + tilt_fx
        if abs(lateral_fx) > 1e-9:
            # Lateral load enters the boom at the sheave; the tackle below carries no moment arm.
            anchor = self._positions[
                self._sheave_of(str(self._hoist.get("id", "")), str(load_node_id))
            ]
            label = (
                f"Offlead {abs(lateral_fx):.0f} kN"
                if tilt_fx == 0.0
                else f"Hook lateral {abs(lateral_fx):.0f} kN (offlead + tilt)"
            )
            vectors.append(
                LoadVector(
                    world_x=float(anchor["x"]),
                    world_z=float(anchor["z"]),
                    fx_kN=lateral_fx,
                    fz_kN=0.0,
                    category=HOOK_LOAD,
                    label=label,
                )
            )
        return tuple(vectors)

    # -- rope tension -----------------------------------------------------

    def _rope_tension_kN(self, rope: Mapping[str, Any], rope_id: str) -> Optional[float]:
        return resolve_rope_tension_kN(
            rope,
            rope_id,
            analysis_point=self._pt,
            hook_load_kN=self._c.hook_load_kN,
        )

    def rope_interface_node_forces(self) -> dict[str, tuple[float, float]]:
        """Net rope force at each node, summed over every segment meeting there."""
        node_forces: dict[str, list[float]] = {}
        if not self._doc or self._pt is None:
            return {}

        for rope in self._doc.get("ropes", []):
            rope_id = str(rope.get("id", "")).strip()
            if not rope_id:
                continue
            tension_kN = self._rope_tension_kN(rope, rope_id)
            if tension_kN is None or abs(tension_kN) < 1e-9:
                continue

            for segment in rope.get("segments", []):
                node_a = str(segment.get("from_node_id", "")).strip()
                node_b = str(segment.get("to_node_id", "")).strip()
                if not node_a or not node_b:
                    continue
                if node_a not in self._positions or node_b not in self._positions:
                    continue

                mult = effective_segment_mult(
                    self._hoist,
                    segment,
                    int(segment.get("mult", 1)),
                    rope_id,
                    split_mode_active=self._c.split_mode_active,
                )
                if mult <= 0:
                    continue

                xa = float(self._positions[node_a]["x"])
                za = float(self._positions[node_a]["z"])
                xb = float(self._positions[node_b]["x"])
                zb = float(self._positions[node_b]["z"])
                length = math.hypot(xb - xa, zb - za)
                if length < 1e-9:
                    continue

                ux = (xb - xa) / length
                uz = (zb - za) / length
                fx = tension_kN * ux * mult
                fz = tension_kN * uz * mult

                if not self._filter.is_free_body or self._filter.owns_node(node_a):
                    current = node_forces.setdefault(node_a, [0.0, 0.0])
                    current[0] += fx
                    current[1] += fz
                if not self._filter.is_free_body or self._filter.owns_node(node_b):
                    current = node_forces.setdefault(node_b, [0.0, 0.0])
                    current[0] -= fx
                    current[1] -= fz

        return {node_id: (values[0], values[1]) for node_id, values in node_forces.items()}

    def rope_interface(self) -> tuple[LoadVector, ...]:
        vectors: list[LoadVector] = []
        for node_id, (fx, fz) in self.rope_interface_node_forces().items():
            if node_id not in self._positions:
                continue
            if abs(fx) < 1e-3 and abs(fz) < 1e-3:
                continue
            name = node_display_name(node_id)
            vectors.append(
                LoadVector(
                    world_x=float(self._positions[node_id]["x"]),
                    world_z=float(self._positions[node_id]["z"]),
                    fx_kN=fx,
                    fz_kN=fz,
                    category=ROPE_INTERFACE,
                    label=f"Rope interface {name}",
                    detail=f"Rope interface @ {name}\nFx={fx:.1f} kN  Fz={fz:.1f} kN",
                )
            )
        return tuple(vectors)

    # -- idle hook mass ---------------------------------------------------

    def idle_hook_mass_node_forces(self) -> dict[str, tuple[float, float]]:
        """Dead weight of every hook block except the active hoist's."""
        node_forces: dict[str, list[float]] = {}
        if not self._doc:
            return {}

        active_hoist_id = str(self._hoist.get("id", "")).strip()

        for hoist in self._doc.get("hoists", []):
            if str(hoist.get("id", "")).strip() == active_hoist_id:
                continue
            if str(hoist.get("rope_id", "")).strip().lower() == "boom_hoist":
                continue

            node_id = str(hoist.get("load_node_id", "")).strip()
            if not node_id or node_id not in self._positions:
                continue

            try:
                hook_mass_t = float(hoist.get("hook_mass_t", 0.0) or 0.0)
            except Exception:
                hook_mass_t = 0.0
            if hook_mass_t <= 0.0:
                continue

            # The block hangs plumb: its weight's vertical part acts at the hook, its
            # in-plane lean at the sheave it hangs from (like the active hook's).
            weight_fx, weight_fz = self._weight(hook_mass_t)
            if not self._filter.is_free_body or self._filter.owns_node(node_id):
                current = node_forces.setdefault(node_id, [0.0, 0.0])
                current[1] += weight_fz
            sheave_id = self._sheave_of(str(hoist.get("id", "")), node_id)
            if weight_fx != 0.0 and (
                not self._filter.is_free_body or self._filter.owns_node(sheave_id)
            ):
                current = node_forces.setdefault(sheave_id, [0.0, 0.0])
                current[0] += weight_fx

        return {node_id: (values[0], values[1]) for node_id, values in node_forces.items()}

    def idle_hook_mass(self) -> tuple[LoadVector, ...]:
        vectors: list[LoadVector] = []
        for node_id, (fx, fz) in self.idle_hook_mass_node_forces().items():
            if node_id not in self._positions:
                continue
            if abs(fx) < 1e-3 and abs(fz) < 1e-3:
                continue
            name = node_display_name(node_id)
            vectors.append(
                LoadVector(
                    world_x=float(self._positions[node_id]["x"]),
                    world_z=float(self._positions[node_id]["z"]),
                    fx_kN=fx,
                    fz_kN=fz,
                    category=IDLE_HOOK_MASS,
                    label=f"Idle hook mass @ {name}: {abs(fz):.1f} kN",
                    detail=f"Inactive hook mass @ {name}\nFx={fx:.1f} kN  Fz={fz:.1f} kN",
                )
            )
        return tuple(vectors)

    # -- reactions --------------------------------------------------------

    def _other_reaction_forces(
        self, exclude_entity_id: str
    ) -> list[tuple[float, float, float, float]]:
        """(x, z, fx, fz) of the selected body's OTHER supports -- moments excluded."""
        if self._pt is None:
            return []
        hook_kN = float(self._c.hook_load_kN)
        result: list[tuple[float, float, float, float]] = []
        for entity_id in REACTION_SPECS:
            if entity_id == exclude_entity_id:
                continue
            node_id = self._filter.reaction_anchor_node(entity_id)
            if node_id not in self._positions or not self._filter.owns_node(node_id):
                continue
            sign = self._filter.reaction_sign(entity_id)
            if sign is None:
                continue
            base = self._pt.baseline_reactions.get(entity_id, {})
            sens = self._pt.sensitivity_reactions.get(entity_id, {})
            fx = sign * (float(base.get("Fx", 0.0)) + float(sens.get("Fx", 0.0)) * hook_kN)
            fz = sign * (float(base.get("Fz", 0.0)) + float(sens.get("Fz", 0.0)) * hook_kN)
            position = self._positions[node_id]
            result.append((float(position["x"]), float(position["z"]), fx, fz))
        return result

    def _synthetic_support_moment(self, node_id: str, entity_id: str) -> Optional[float]:
        """Residual moment the selected body's fixed support must carry.

        Only used where the solver reports no moment for that support: the body's
        other (pinned, moment-free) reactions are included, or their balancing
        force would be misattributed to this moment.
        """
        if not self._filter.is_free_body or node_id not in self._positions:
            return None
        if self._filter.selected_body is None:
            return None

        applied: list[tuple[float, float, float, float]] = [
            (vector.world_x, vector.world_z, vector.fx_kN, vector.fz_kN)
            for vector in (
                self.gravity()
                + self.rope_weight()
                + self.idle_hook_mass()
                + self.hook_load()
                + self.wind()
                + self.inertia()
                + self.rope_interface()
            )
        ]
        applied.extend(self._other_reaction_forces(entity_id))
        if not applied:
            return None

        x0 = float(self._positions[node_id]["x"])
        z0 = float(self._positions[node_id]["z"])
        residual = 0.0
        for x, z, fx, fz in applied:
            residual += (x - x0) * fz - (z - z0) * fx
        return -float(residual)

    def _resolved_reactions(self) -> Iterator[tuple[str, str, float, float, Optional[float], str]]:
        if self._pt is None:
            return
        hook_kN = float(self._c.hook_load_kN)
        synthetic_entity = self._filter.synthetic_support_entity()

        for entity_id in REACTION_SPECS:
            node_id = self._filter.reaction_anchor_node(entity_id)
            if node_id not in self._positions:
                continue
            if self._filter.is_free_body and not self._filter.owns_node(node_id):
                continue
            sign = self._filter.reaction_sign(entity_id)
            if sign is None:
                continue

            base = self._pt.baseline_reactions.get(entity_id, {})
            sens = self._pt.sensitivity_reactions.get(entity_id, {})
            fx = sign * (float(base.get("Fx", 0.0)) + float(sens.get("Fx", 0.0)) * hook_kN)
            fz = sign * (float(base.get("Fz", 0.0)) + float(sens.get("Fz", 0.0)) * hook_kN)

            moment_key = "My" if ("My" in base or "My" in sens) else "M"
            moment_available = (moment_key in base) or (moment_key in sens)
            moment = sign * (
                float(base.get(moment_key, 0.0)) + float(sens.get(moment_key, 0.0)) * hook_kN
            )

            if self._filter.is_free_body and entity_id == synthetic_entity and not moment_available:
                synthetic = self._synthetic_support_moment(node_id, entity_id)
                if synthetic is not None:
                    moment = sign * float(synthetic)
                    moment_key = "M"
                    moment_available = True

            yield (
                entity_id,
                node_id,
                fx,
                fz,
                (moment if moment_available else None),
                moment_key,
            )

    def reactions(self) -> tuple[LoadVector, ...]:
        vectors: list[LoadVector] = []
        for entity_id, node_id, fx, fz, _moment, _key in self._resolved_reactions():
            if abs(fx) < 1e-3 and abs(fz) < 1e-3:
                continue
            position = self._positions[node_id]
            vectors.append(
                LoadVector(
                    world_x=float(position["x"]),
                    world_z=float(position["z"]),
                    fx_kN=fx,
                    fz_kN=fz,
                    category=REACTIONS,
                    label=f"Reaction {entity_id}",
                    detail=f"{entity_id}\nFx={fx:.1f} kN  Fz={fz:.1f} kN",
                )
            )
        return tuple(vectors)

    def reaction_moments(self) -> tuple[LoadMoment, ...]:
        moments: list[LoadMoment] = []
        for entity_id, node_id, _fx, _fz, moment, moment_key in self._resolved_reactions():
            if moment is None or abs(moment) < 1e-3:
                continue
            position = self._positions[node_id]
            moments.append(
                LoadMoment(
                    world_x=float(position["x"]),
                    world_z=float(position["z"]),
                    moment_kNm=moment,
                    entity_id=entity_id,
                    label=f"Moment {entity_id}: {moment:.1f} kNm",
                    detail=f"{entity_id}\n{moment_key}={moment:.1f} kNm",
                )
            )
        return tuple(moments)

    def loaded_node_ids(self) -> set[str]:
        """Nodes carrying an applied load -- the pins a free-body view should show."""
        loaded: set[str] = set()
        if not self._filter.is_free_body:
            return loaded

        load_node_id = str(self._hoist.get("load_node_id", "")).strip()
        if (
            load_node_id
            and load_node_id in self._positions
            and self._filter.owns_node(load_node_id)
            and max(0.0, float(self._c.hook_load_kN)) > 0.0
        ):
            loaded.add(load_node_id)

        support_mass_t = split_support_mass_t(
            self._hoist, split_mode_active=self._c.split_mode_active
        )
        support_node_id = str(self._hoist.get("support_node_id", "")).strip()
        if (
            support_mass_t is not None
            and float(support_mass_t) > 0.0
            and support_node_id
            and support_node_id in self._positions
            and self._filter.owns_node(support_node_id)
        ):
            loaded.add(support_node_id)

        if self._pt is not None:
            for _entity, node_id, fx, fz, moment, _key in self._resolved_reactions():
                moment_mag = abs(float(moment)) if moment is not None else 0.0
                if abs(fx) >= 1e-3 or abs(fz) >= 1e-3 or moment_mag >= 1e-3:
                    loaded.add(str(node_id))

        for node_id, (fx, fz) in self.rope_interface_node_forces().items():
            if abs(fx) >= 1e-3 or abs(fz) >= 1e-3:
                loaded.add(str(node_id))

        for node_id, (fx, fz) in self.idle_hook_mass_node_forces().items():
            if abs(fx) >= 1e-3 or abs(fz) >= 1e-3:
                loaded.add(str(node_id))

        loaded.update(self.rope_weight_node_masses())

        return loaded

    def build(self) -> BodyLoads:
        return BodyLoads(
            categories=(
                (GRAVITY, self.gravity()),
                (ROPE_WEIGHT, self.rope_weight()),
                (IDLE_HOOK_MASS, self.idle_hook_mass()),
                (HOOK_LOAD, self.hook_load()),
                (WIND, self.wind()),
                (INERTIA, self.inertia()),
                (ROPE_INTERFACE, self.rope_interface()),
                (REACTIONS, self.reactions()),
            ),
            moments=self.reaction_moments(),
        )


def build_body_loads(
    document_dict: Mapping[str, Any],
    *,
    hoist: Mapping[str, Any],
    conditions: LoadConditions,
    node_positions: Mapping[str, Mapping[str, float]],
    analysis_point: Any = None,
    body_filter: Optional[FreeBodyFilter] = None,
) -> BodyLoads:
    """Every in-plane load acting on the selected body, in world coordinates.

    ``body_filter=None`` builds the whole crane's loads. Pass a
    :class:`FreeBodyFilter` with a ``selected_body`` to cut a free body, which
    also brings in the interface loads (rope, reactions) that body sees.
    """
    return _LoadBuilder(
        document_dict,
        hoist,
        conditions,
        node_positions,
        analysis_point,
        body_filter or FreeBodyFilter.whole_crane(node_body_map(document_dict)),
    ).build()


def loaded_node_ids(
    document_dict: Mapping[str, Any],
    *,
    hoist: Mapping[str, Any],
    conditions: LoadConditions,
    node_positions: Mapping[str, Mapping[str, float]],
    analysis_point: Any = None,
    body_filter: Optional[FreeBodyFilter] = None,
) -> set[str]:
    """Nodes carrying an applied load, for free-body node-pin visibility."""
    return _LoadBuilder(
        document_dict,
        hoist,
        conditions,
        node_positions,
        analysis_point,
        body_filter or FreeBodyFilter.whole_crane(node_body_map(document_dict)),
    ).loaded_node_ids()


def sum_moment_about(
    vectors: Sequence[LoadVector], moments: Sequence[LoadMoment], x0: float, z0: float
) -> float:
    """Total moment of a load set about a world point, in kNm."""
    total = sum(
        (vector.world_x - x0) * vector.fz_kN - (vector.world_z - z0) * vector.fx_kN
        for vector in vectors
    )
    return total + sum(moment.moment_kNm for moment in moments)
