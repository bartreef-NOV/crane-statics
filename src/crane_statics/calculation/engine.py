"""Calculation engine for crane statics analysis.

This module implements the core mathematical solver for:
- Rope tensions
- Connection reactions
- Response baseline + sensitivity decomposition
- Allowable hook load inversion
- Contractual evaluation
"""

from dataclasses import dataclass
from typing import Optional, Any, Sequence
import math

import numpy as np
from ..data.models import CraneDocument
from .solver.kinematics import KinematicsAdapter
from .solver.crane_solver import (
    UNAVAILABLE_REASON_KEY,
    build_solver_static_context,
    build_directional_response_basis,
    compose_unit_basis_point,
    inertia_force,
    rotate_boom_local_point,
)
from .allowable import allowable_hook_load
from .demand_formulas import (  # noqa: F401  (re-exported: used by core and scripts)
    compute_platform_base_fradial_kN,
    compute_platform_base_max_bearing_line_load_kN_per_m,
    compute_platform_base_min_bearing_line_load_kN_per_m,
    compute_platform_base_mradial_kNm,
    resolve_connection_component_linear_response,
)
from .results import AllowableCapacity, AnalysisPoint
from .dynamic_factor import DynamicFactorLike
from .vessel_frame import CraneFrameMotion, VesselInputs, crane_frame_motion

_WIND_DIRECTIONS = {"+X", "-X", "+Y", "-Y"}

# Module-level calculator cache for cross-service reuse
# Maps document id -> CraneCalculator instance
_CALCULATOR_CACHE: dict[int, "CraneCalculator"] = {}


def get_calculator(document: CraneDocument) -> "CraneCalculator":
    """Get or create a CraneCalculator for the given document.

    Calculators are reused per document so the derived document dict, kinematics
    adapter and static solver context are built once rather than per service
    (sweep, limit_auto_set, analysis_services).

    Args:
        document: CraneDocument to analyze

    Returns:
        The CraneCalculator instance for this document.

    Example:
        calc = get_calculator(doc)
        pt = calc.compute_analysis_point(10.0, 50.0, "hoist_1")
        cap = calc.compute_allowable_load(pt, limits)
    """
    doc_id = id(document)
    if doc_id not in _CALCULATOR_CACHE:
        _CALCULATOR_CACHE[doc_id] = CraneCalculator(document)
    return _CALCULATOR_CACHE[doc_id]


# ─────────────────────────────────────────────────────────────────────────────
# Numeric Tolerance Constants
# ─────────────────────────────────────────────────────────────────────────────

NUMERIC_TOLERANCE = 1e-6  # General-purpose tolerance for statics/comparisons
WIND_SPEED_THRESHOLD = 1e-12  # Threshold for non-zero wind speed

# Component suffixes stripped from limit ids ('rear_hinge_Fx' -> 'rear_hinge').
_LIMIT_KEY_COMPONENTS = (
    "T",
    "Fx",
    "Fy",
    "Fz",
    "M",
    "Mx",
    "My",
    "fradial",
    "mradial",
    "resultant",
    "boom_axial",
    "boom_normal",
    "leg_axial",
    "leg_normal",
    "max_bearing_line_load",
    "min_bearing_line_load",
)


# ─────────────────────────────────────────────────────────────────────────────
# Boom Rotation Reference Nodes
# ─────────────────────────────────────────────────────────────────────────────
# Priority list of nodes used to establish boom local rotation angle.
def normalize_wind_direction(direction: Optional[str]) -> str:
    raw = str(direction or "+X").strip().upper().replace(" ", "")
    return raw if raw in _WIND_DIRECTIONS else "+X"


def split_wind_speed_components(
    wind_speed_m_s: float, wind_direction: Optional[str]
) -> tuple[float, float]:
    magnitude = abs(float(wind_speed_m_s))
    direction = normalize_wind_direction(wind_direction)
    if direction == "+X":
        return magnitude, 0.0
    if direction == "-X":
        return -magnitude, 0.0
    if direction == "+Y":
        return 0.0, magnitude
    return 0.0, -magnitude


def split_wind_angle_components(
    wind_speed_m_s: float, wind_angle_deg: float
) -> tuple[float, float]:
    """Wind speed components ``(V cos, V sin)`` for a wind angle from +X toward +Y."""
    magnitude = abs(float(wind_speed_m_s))
    angle = math.radians(float(wind_angle_deg))
    x, y = magnitude * math.cos(angle), magnitude * math.sin(angle)
    return (0.0 if abs(x) < 1e-12 else x, 0.0 if abs(y) < 1e-12 else y)


def candidate_wind_directions(wind_speed_m_s: Optional[float]) -> tuple[str, ...]:
    if wind_speed_m_s is None or abs(float(wind_speed_m_s)) <= WIND_SPEED_THRESHOLD:
        return ("+X",)
    return ("+X", "-X", "+Y", "-Y")


@dataclass(frozen=True)
class _OutOfPlaneGeometry:
    """Points of the out-of-plane pass at one boom angle, with lever arms about each group.

    ``mass_*`` are the mass points (document masses, then the lumped hook and rope masses);
    ``wind_coef`` is the wind force per wind speed squared of each wind area. ``*_rel_*`` have
    one row per support group (the order of ``origin_by_group``).
    """

    node_pos: dict[str, tuple[float, float]]
    origin_by_group: dict[str, tuple[float, float]]
    mass_t: np.ndarray
    mass_x: np.ndarray
    mass_y: np.ndarray
    mass_z: np.ndarray
    mass_rel_x: np.ndarray
    mass_rel_z: np.ndarray
    wind_coef: np.ndarray
    wind_rel_x: np.ndarray
    wind_rel_z: np.ndarray


class CraneCalculator:
    """Main calculation engine for crane statics."""

    # Numeric tolerance for comparisons
    TOLERANCE = NUMERIC_TOLERANCE

    def __init__(self, document: CraneDocument):
        """Initialize calculator with a document.

        Args:
            document: CraneDocument to analyze
        """
        self.doc = document
        self._doc_dict = document.model_dump()
        self.hoists = {h.id: h for h in document.hoists}
        self._kinematics = KinematicsAdapter(self._doc_dict)
        self._solver_ctx = build_solver_static_context(self._doc_dict)
        self._oop_geometry: Optional[tuple[tuple[Any, ...], _OutOfPlaneGeometry]] = None
        #: Why the last ``compute_analysis_point`` returned ``None`` (``None`` when it solved).
        self.unavailable_reason: Optional[str] = None

    def _build_out_of_plane_reactions(
        self,
        point: AnalysisPoint,
        hoist_id: str,
        boom_angle_deg: float,
        hook_force_kN: float,
        wind_y_m_s: float,
        accel_y_m_s2: float,
        roll_accel_rad_s2: float,
        side_lateral_force_kN: float,
        hoist_runtime_overrides: Optional[dict[str, dict[str, Any]]] = None,
        *,
        accel_x_m_s2: float = 0.0,
        accel_z_m_s2: float = 0.0,
        pitch_accel_rad_s2: float = 0.0,
        lumped_point_masses: Sequence[tuple[float, float, float]] = (),
    ) -> tuple[dict[str, dict[str, float]], float, float]:
        """Out-of-plane (Y) pass for one hook force and side force (``_out_of_plane_variants``)."""
        return self._out_of_plane_variants(
            point,
            hoist_id,
            boom_angle_deg,
            [(hook_force_kN, side_lateral_force_kN)],
            wind_y_m_s,
            accel_y_m_s2,
            roll_accel_rad_s2,
            hoist_runtime_overrides,
            accel_x_m_s2=accel_x_m_s2,
            accel_z_m_s2=accel_z_m_s2,
            pitch_accel_rad_s2=pitch_accel_rad_s2,
            lumped_point_masses=lumped_point_masses,
        )[0]

    def _out_of_plane_geometry(
        self, boom_angle_deg: float, lumped_point_masses: Sequence[tuple[float, float, float]]
    ) -> "_OutOfPlaneGeometry":
        """Mass and wind points of the out-of-plane pass at one boom angle (last one kept).

        A sweep evaluates several probes at one angle; the points and their lever arms about
        the support groups are the same for all of them, only the accelerations differ.
        """
        lumped = tuple((float(m), float(x), float(z)) for m, x, z in lumped_point_masses)
        rho = float(self.doc.environment.air_density_kg_m3)
        key = (boom_angle_deg, lumped, rho)
        cached = self._oop_geometry
        if cached is not None and cached[0] == key:
            return cached[1]

        node_positions = self._kinematics.compute_all_node_positions(boom_angle_deg)
        node_pos = {nid: (float(v["x"]), float(v["z"])) for nid, v in node_positions.items()}
        origin_by_group = {
            "heel": node_pos.get("boom_heel", (0.0, 0.0)),
            "front_leg": node_pos.get("front_base", (0.0, 0.0)),
            "rear_leg": node_pos.get("rear_base", (0.0, 0.0)),
            "platform_base": node_pos.get("platform_heel", (0.0, 0.0)),
        }

        masses: list[tuple[float, float, float, float]] = []  # (mass_t, x, y, z)
        for body in self.doc.bodies:
            for mp in body.mass_points:
                if body.id == "boom" and mp.local_x_m is not None:
                    xw, zw = rotate_boom_local_point(
                        float(mp.local_x_m), float(mp.local_z_m or 0.0), node_pos, boom_angle_deg
                    )
                    yw = float(mp.local_y_m or 0.0)
                else:
                    xw, zw = float(mp.x_m), float(mp.z_m)
                    yw = float(mp.y_m)
                masses.append((float(mp.mass_t), xw, yw, zw))
        # Idle hook blocks and rope self-weight, lumped at nodes on the crane centreline:
        # the same masses at the same positions as the X-Z solve
        # (``crane_solver.lumped_point_masses``, carried on the response basis).
        masses.extend((m, x, 0.0, z) for m, x, z in lumped)

        winds: list[tuple[float, float, float]] = []  # (force per speed squared, x, z)
        for body in self.doc.bodies:
            for wa in body.wind_areas:
                if body.id == "boom" and wa.local_x_m is not None:
                    xw, zw = rotate_boom_local_point(
                        float(wa.local_x_m), float(wa.local_z_m or 0.0), node_pos, boom_angle_deg
                    )
                else:
                    xw, zw = float(wa.x_m), float(wa.z_m)
                # Y wind sees the full area_v_m2 at any boom angle; only X wind is projected.
                winds.append((0.5 * rho * float(wa.cd) * float(wa.area_v_m2) / 1000.0, xw, zw))

        m_arr = np.array(masses, dtype=float).reshape(-1, 4)
        w_arr = np.array(winds, dtype=float).reshape(-1, 3)
        ox = np.array([float(o[0]) for o in origin_by_group.values()])[:, None]
        oz = np.array([float(o[1]) for o in origin_by_group.values()])[:, None]
        geometry = _OutOfPlaneGeometry(
            node_pos=node_pos,
            origin_by_group=origin_by_group,
            mass_t=m_arr[:, 0],
            mass_x=m_arr[:, 1],
            mass_y=m_arr[:, 2],
            mass_z=m_arr[:, 3],
            mass_rel_x=m_arr[:, 1][None, :] - ox,
            mass_rel_z=m_arr[:, 3][None, :] - oz,
            wind_coef=w_arr[:, 0],
            wind_rel_x=w_arr[:, 1][None, :] - ox,
            wind_rel_z=w_arr[:, 2][None, :] - oz,
        )
        self._oop_geometry = (key, geometry)
        return geometry

    def _out_of_plane_variants(
        self,
        point: AnalysisPoint,
        hoist_id: str,
        boom_angle_deg: float,
        variants: Sequence[tuple[float, float]],
        wind_y_m_s: float,
        accel_y_m_s2: float,
        roll_accel_rad_s2: float,
        hoist_runtime_overrides: Optional[dict[str, dict[str, Any]]] = None,
        *,
        accel_x_m_s2: float = 0.0,
        accel_z_m_s2: float = 0.0,
        pitch_accel_rad_s2: float = 0.0,
        lumped_point_masses: Sequence[tuple[float, float, float]] = (),
    ) -> list[tuple[dict[str, dict[str, float]], float, float]]:
        """Out-of-plane (Y) pass: left/right split, platform Fy and Mx.

        ``variants`` are ``(hook_force_kN, side_lateral_force_kN)`` pairs; the mass and wind
        loads do not depend on them, so they are accumulated once and each variant adds its
        own side force and totals. Returns one ``(split, platform_mx, platform_fy)`` per variant;
        the platform values are reactions (what the support exerts on the crane), the negative of
        the applied-load sums, while ``split`` is unchanged.

        All accelerations are the equivalent crane-frame values (``CraneFrameMotion``), so
        each mass carries the same in-plane (Fx, Fz) load as in the X-Z solve plus
        ``Fy = -m * (accel_y - roll_accel * (z - reference_z))`` (roll right-handed about +x).
        ``lumped_point_masses`` are the idle hook and rope masses ``(mass_t, x, z)`` from the
        response basis; ``compute_analysis_point`` always passes them.
        """
        geometry = self._out_of_plane_geometry(boom_angle_deg, lumped_point_masses)
        node_pos = geometry.node_pos
        origin_by_group = geometry.origin_by_group
        moments = {group: {"Mx": 0.0, "Mz": 0.0} for group in origin_by_group}
        total_fy_platform = 0.0

        def _accumulate_force(
            xw: float, yw: float, zw: float, fx: float, fy: float, fz: float
        ) -> None:
            nonlocal total_fy_platform
            total_fy_platform += float(fy)
            for group, origin in origin_by_group.items():
                ox, oz = float(origin[0]), float(origin[1])
                rel_x = float(xw) - ox
                rel_y = float(yw)
                rel_z = float(zw) - oz
                moments[group]["Mx"] += rel_y * float(fz) - rel_z * float(fy)
                moments[group]["Mz"] += rel_x * float(fy) - rel_y * float(fx)

        env = self.doc.environment
        vm = env.vessel_motion
        gravity_abs = abs(float(env.gravity_m_s2))
        ref_x = float(vm.reference_x_m if vm is not None else 0.0)
        roll_ref_z = float(vm.reference_z_m if vm is not None else 0.0)

        def _mass_force(mass_t: float, xw: float, zw: float) -> tuple[float, float, float]:
            fx, fz = inertia_force(
                mass_t,
                xw,
                zw,
                float(accel_x_m_s2),
                float(accel_z_m_s2),
                float(pitch_accel_rad_s2),
                ref_x,
                roll_ref_z,
                gravity_abs,
            )
            # Roll is right-handed about +x (like the roll angle): omega x r gives
            # a_y = -roll * (z - reference_z).
            ay_pt = float(accel_y_m_s2) - float(roll_accel_rad_s2) * (zw - roll_ref_z)
            return fx, -mass_t * ay_pt, fz

        # The mass and wind loads of every point at once (``inertia_force`` and ``_mass_force``
        # in array form); the moments about each support group are dot products with the
        # per-angle lever arms.
        mass_t = geometry.mass_t
        dz = geometry.mass_z - roll_ref_z
        dx = geometry.mass_x - ref_x
        pitch = float(pitch_accel_rad_s2)
        fx_m = -mass_t * (float(accel_x_m_s2) + pitch * dz)
        fz_m = -mass_t * (gravity_abs + (float(accel_z_m_s2) - pitch * dx))
        fy_m = -mass_t * (float(accel_y_m_s2) - float(roll_accel_rad_s2) * dz)
        wind_sign = 0.0 if abs(float(wind_y_m_s)) < 1e-12 else math.copysign(1.0, float(wind_y_m_s))
        fy_w = wind_sign * geometry.wind_coef * abs(float(wind_y_m_s)) ** 2
        mx = geometry.mass_y @ fz_m - geometry.mass_rel_z @ fy_m - geometry.wind_rel_z @ fy_w
        mz = geometry.mass_rel_x @ fy_m - geometry.mass_y @ fx_m + geometry.wind_rel_x @ fy_w
        for index, group in enumerate(origin_by_group):
            moments[group]["Mx"] = float(mx[index])
            moments[group]["Mz"] = float(mz[index])
        total_fy_platform = float(fy_m.sum() + fy_w.sum())

        shared_moments = moments
        shared_fy_platform = total_fy_platform
        results = []
        for hook_force_kN, side_lateral_force_kN in variants:
            moments = {group: dict(comps) for group, comps in shared_moments.items()}
            total_fy_platform = shared_fy_platform
            hoist = self.hoists.get(hoist_id)
            if hoist is not None:
                # The rope delivers the lateral load to the crane at the supporting sheave, not at
                # the hook (a placeholder node parked below the sheave).
                load_node = node_pos.get(str(getattr(hoist, "support_node_id", "") or ""))
                if load_node is None:
                    load_node = node_pos.get(str(hoist.load_node_id))
                if load_node is not None:
                    _accumulate_force(
                        float(load_node[0]),
                        0.0,
                        float(load_node[1]),
                        fx=0.0,
                        fy=float(side_lateral_force_kN),
                        fz=0.0,
                    )

                override = (hoist_runtime_overrides or {}).get(hoist_id, {})
                normal_hook_mass_t = float(hoist.hook_mass_t)
                effective_hook_mass_t = float(
                    override.get("hook_mass_t", normal_hook_mass_t) or 0.0
                )
                comp_mass_t = override.get("support_comp_mass_t")
                if comp_mass_t is None:
                    comp_mass_t = max(0.0, normal_hook_mass_t - effective_hook_mass_t)
                try:
                    comp_mass_t = max(0.0, float(comp_mass_t))
                except (TypeError, ValueError):
                    comp_mass_t = 0.0
                support_node_id = str(
                    override.get("support_node_id") or getattr(hoist, "support_node_id", "") or ""
                )
                if comp_mass_t > 1e-12 and support_node_id and support_node_id in node_pos:
                    sx, sz = node_pos[support_node_id]
                    # A mass like any other: weight plus the vessel motion, no invented side
                    # force when the vessel is level and still.
                    fx_comp, fy_comp, fz_comp = _mass_force(comp_mass_t, float(sx), float(sz))
                    _accumulate_force(float(sx), 0.0, float(sz), fx=fx_comp, fy=fy_comp, fz=fz_comp)

            widths = self.doc.support_widths
            boom_width = float(widths.boom_width_m)
            if boom_width <= 0.0:
                raise ValueError("Support widths must be > 0")

            total_map = {
                "heel": "heel_point",
                "front_leg": "front_hinge",
                "rear_leg": "rear_hinge",
            }
            side_entity = {
                "heel": ("heel_left", "heel_right", boom_width),
                "front_leg": ("front_leg_left", "front_leg_right", boom_width),
                "rear_leg": ("rear_leg_left", "rear_leg_right", boom_width),
            }
            split: dict[str, dict[str, float]] = {}
            for group, total_entity in total_map.items():
                left_entity, right_entity, width = side_entity[group]
                base = point.baseline_reactions.get(total_entity, {})
                sens = point.sensitivity_reactions.get(total_entity, {})
                total_fx = float(base.get("Fx", 0.0)) + float(sens.get("Fx", 0.0)) * float(
                    hook_force_kN
                )
                total_fz = float(base.get("Fz", 0.0)) + float(sens.get("Fz", 0.0)) * float(
                    hook_force_kN
                )
                d_fx = float(moments[group]["Mz"]) / float(width)
                d_fz = float(moments[group]["Mx"]) / float(width)
                # +Y is port (left looking along +x), so the side with the -d share is "left".
                split[right_entity] = {"Fx": 0.5 * total_fx + d_fx, "Fz": 0.5 * total_fz + d_fz}
                split[left_entity] = {"Fx": 0.5 * total_fx - d_fx, "Fz": 0.5 * total_fz - d_fz}
            # Applied-load sums negated: reactions are what the support exerts on the crane.
            results.append(
                (split, -float(moments["platform_base"]["Mx"]), -float(total_fy_platform))
            )
        return results

    def _augment_point_with_out_of_plane_loads(
        self,
        point: AnalysisPoint,
        hoist_id: str,
        wind_y_m_s: float,
        motion: "CraneFrameMotion",
        sidelead_deg: float,
        hoist_runtime_overrides: Optional[dict[str, dict[str, Any]]] = None,
        lumped_point_masses: Sequence[tuple[float, float, float]] = (),
    ) -> None:
        """Apply the out-of-plane (Y) loads -- sway, roll, sidelead, wind Y -- to the supports.

        Runs for every document. Rewrites the left/right support reactions and platform base
        ``Fy``/``Mx``; hinge totals, rope tensions and member loads stay in-plane.
        """
        (
            (split_at_zero, platform_mx_at_zero, platform_fy_at_zero),
            (split_at_one, platform_mx_at_one, platform_fy_at_one),
            (split_at_side_unit, platform_mx_at_side_unit, platform_fy_at_side_unit),
        ) = self._out_of_plane_variants(
            point,
            hoist_id,
            point.boom_angle_deg,
            # (hook force, side force): zero, one kN of hook load, one kN of side force.
            [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
            wind_y_m_s,
            motion.accel_y_m_s2,
            motion.roll_accel_rad_s2,
            hoist_runtime_overrides,
            accel_x_m_s2=motion.accel_x_m_s2,
            accel_z_m_s2=motion.accel_z_m_s2,
            pitch_accel_rad_s2=motion.pitch_accel_rad_s2,
            lumped_point_masses=lumped_point_masses,
        )
        side_scale = math.sin(math.radians(float(sidelead_deg)))
        side_unit_reactions: dict[str, dict[str, float]] = {}
        for entity, base_comp in split_at_zero.items():
            one_comp = split_at_one.get(entity, {})
            side_comp = split_at_side_unit.get(entity, {})
            side_unit_reactions[entity] = {
                "Fx": float(side_comp.get("Fx", 0.0)) - float(base_comp.get("Fx", 0.0)),
                "Fz": float(side_comp.get("Fz", 0.0)) - float(base_comp.get("Fz", 0.0)),
            }
            point.baseline_reactions[entity] = {
                "Fx": float(base_comp.get("Fx", 0.0)),
                "Fz": float(base_comp.get("Fz", 0.0)),
            }
            point.sensitivity_reactions[entity] = {
                "Fx": float(one_comp.get("Fx", 0.0))
                - float(base_comp.get("Fx", 0.0))
                + side_scale * side_unit_reactions[entity]["Fx"],
                "Fz": float(one_comp.get("Fz", 0.0))
                - float(base_comp.get("Fz", 0.0))
                + side_scale * side_unit_reactions[entity]["Fz"],
            }

        platform_base = point.baseline_reactions.setdefault("platform_base", {})
        platform_base_sens = point.sensitivity_reactions.setdefault("platform_base", {})
        platform_base["Fy"] = float(platform_fy_at_zero)
        side_unit_reactions.setdefault("platform_base", {})["Fy"] = float(
            platform_fy_at_side_unit
        ) - float(platform_fy_at_zero)
        platform_base_sens["Fy"] = (
            float(platform_fy_at_one)
            - float(platform_fy_at_zero)
            + side_scale * side_unit_reactions["platform_base"]["Fy"]
        )
        platform_base["Mx"] = float(platform_mx_at_zero)
        side_unit_reactions["platform_base"]["Mx"] = float(platform_mx_at_side_unit) - float(
            platform_mx_at_zero
        )
        platform_base_sens["Mx"] = (
            float(platform_mx_at_one)
            - float(platform_mx_at_zero)
            + side_scale * side_unit_reactions["platform_base"]["Mx"]
        )
        # Keep the in-plane moment under M while exposing the explicit My component.
        platform_base["My"] = float(platform_base.get("M", 0.0))
        platform_base_sens["My"] = float(platform_base_sens.get("M", 0.0))
        point.sidelead_lateral_unit_reactions = side_unit_reactions

    def compute_analysis_point(
        self,
        boom_angle_deg: float,
        hook_load_kN: float,
        hoist_id: str,
        wind_speed_m_s: Optional[float] = None,
        wind_direction: Optional[str] = None,
        accel_x_m_s2: Optional[float] = None,
        accel_y_m_s2: Optional[float] = None,
        accel_z_m_s2: Optional[float] = None,
        pitch_accel_rad_s2: Optional[float] = None,
        roll_accel_rad_s2: Optional[float] = None,
        offlead_deg: Optional[float] = None,
        sidelead_deg: Optional[float] = None,
        hoist_runtime_overrides: Optional[dict[str, dict[str, Any]]] = None,
        tackle_length_m: Optional[float] = None,
        vessel_roll_deg: Optional[float] = None,
        vessel_pitch_deg: Optional[float] = None,
        crane_slewing_angle_deg: Optional[float] = None,
        wind_angle_deg: Optional[float] = None,
    ) -> Optional[AnalysisPoint]:
        """Full linear response at one boom angle.

        ``wind_angle_deg`` (degrees from +X toward +Y), when given, overrides
        ``wind_direction``; the per-axis components then drive the X and Y responses.

        The motion inputs are **vessel-frame** values (accelerations exclude gravity); the
        vessel roll/pitch tilt gravity and the crane slewing angle rotates the result into
        the crane frame (``calculation.vessel_frame``). Each input left ``None`` takes the document
        ``vessel_motion`` default. All are exact signed values (no envelope).

        ``tackle_length_m`` is the rope paid out below the active hoist's sheave.
        It moves rope weight between the falls and the winch, so an interactive
        caller passes what the scene draws; leaving it ``None`` evaluates the
        designed operating position (see ``rope_mass.active_hook_positions``).

        When it returns ``None`` for a known cause, ``unavailable_reason`` says why.
        """
        self.unavailable_reason = None
        try:
            if not self.hoists.get(hoist_id):
                self.unavailable_reason = (
                    f"Analysis unavailable: hoist {hoist_id!r} is not defined in the document."
                )
                return None

            env = self.doc.environment
            vm = env.vessel_motion
            wind_ref = (
                env.max_wind_speed_m_s if wind_speed_m_s is None else abs(float(wind_speed_m_s))
            )
            wind_dir: Optional[str]
            if wind_angle_deg is not None:
                wind_dir = None
                wind_x_ref, wind_y_ref = split_wind_angle_components(wind_ref, wind_angle_deg)
            else:
                wind_dir = normalize_wind_direction(wind_direction)
                wind_x_ref, wind_y_ref = split_wind_speed_components(wind_ref, wind_dir)

            def _vm_default(value: Optional[float], name: str) -> float:
                if value is not None:
                    return float(value)
                return float(getattr(vm, name, 0.0) or 0.0) if vm is not None else 0.0

            # Vessel-frame inputs (exact signed values; ``None`` -> document default),
            # resolved into the equivalent crane-frame motion the solver channels use.
            motion = crane_frame_motion(
                abs(float(env.gravity_m_s2)),
                VesselInputs(
                    accel_x_m_s2=_vm_default(accel_x_m_s2, "accel_x_m_s2"),
                    accel_y_m_s2=_vm_default(accel_y_m_s2, "accel_y_m_s2"),
                    accel_z_m_s2=_vm_default(accel_z_m_s2, "accel_z_m_s2"),
                    roll_deg=_vm_default(vessel_roll_deg, "roll_deg"),
                    pitch_deg=_vm_default(vessel_pitch_deg, "pitch_deg"),
                    slew_deg=(
                        0.0 if crane_slewing_angle_deg is None else float(crane_slewing_angle_deg)
                    ),
                    roll_accel_rad_s2=_vm_default(roll_accel_rad_s2, "roll_angular_accel_rad_s2"),
                    pitch_accel_rad_s2=_vm_default(
                        pitch_accel_rad_s2, "pitch_angular_accel_rad_s2"
                    ),
                ),
            )
            accel_x_ref = motion.accel_x_m_s2
            accel_z_ref = motion.accel_z_m_s2
            pitch_ref = motion.pitch_accel_rad_s2
            sidelead_ref = 0.0 if sidelead_deg is None else float(sidelead_deg)
            basis = build_directional_response_basis(
                self._doc_dict,
                self._kinematics,
                hoist_id,
                boom_angle_deg,
                wind_speed_m_s=abs(wind_x_ref),
                accel_x_m_s2=accel_x_ref,
                accel_z_m_s2=accel_z_ref,
                pitch_rad_s2=pitch_ref,
                solver_ctx=self._solver_ctx,
                hoist_runtime_overrides=hoist_runtime_overrides,
                tackle_length_m=tackle_length_m,
            )
            if basis is None:
                self.unavailable_reason = self._solver_ctx.get(UNAVAILABLE_REASON_KEY)
                return None

            def _sign_of(v: float) -> float:
                return 0.0 if abs(v) < 1e-12 else math.copysign(1.0, v)

            # The basis holds each channel at |reference|; the exact signs are restored here.
            composed = compose_unit_basis_point(
                basis,
                wind_sign=_sign_of(wind_x_ref),
                accel_x_sign=_sign_of(accel_x_ref),
                accel_z_sign=_sign_of(accel_z_ref),
                pitch_sign=_sign_of(pitch_ref),
                offlead_deg=offlead_deg,
            )

            point = AnalysisPoint(
                boom_angle_deg=composed["boom_angle_deg"],
                outreach_m=composed["outreach_m"],
                baseline_rope_tensions=composed["baseline_rope_tensions"],
                baseline_reactions=composed["baseline_reactions"],
                sensitivity_rope_tensions=composed["sensitivity_rope_tensions"],
                sensitivity_reactions=composed["sensitivity_reactions"],
                offlead_lateral_unit_rope_tensions=composed.get(
                    "offlead_lateral_unit_rope_tensions"
                ),
                offlead_lateral_unit_reactions=composed.get("offlead_lateral_unit_reactions"),
                connection_local_axes=composed.get("connection_local_axes"),
                governing_signs=composed.get("governing_signs"),
                governing_wind_direction=(wind_dir if wind_ref > self.TOLERANCE else None),
            )
            self._augment_point_with_out_of_plane_loads(
                point,
                hoist_id,
                wind_y_m_s=wind_y_ref,
                motion=motion,
                lumped_point_masses=basis.lumped_point_masses,
                sidelead_deg=sidelead_ref,
                hoist_runtime_overrides=hoist_runtime_overrides,
            )
            return point
        except KeyError as exc:
            self.unavailable_reason = (
                f"Analysis unavailable: required geometry {exc} is missing from the document "
                "(a node or body the statics need is not defined)."
            )
            return None
        except Exception as exc:
            self.unavailable_reason = f"Analysis unavailable: {type(exc).__name__}: {exc}"
            return None

    def resolve_limit_target(self, limit_key: str, component: str) -> tuple[str, str]:
        """``(entity_id, rope_channel)`` that ``compute_allowable_load`` checks for a limit.

        ``limit_key`` may be an entity id ('boom_hoist') or a limit id ('rear_hinge_Fx'):
        a trailing ``_<component>`` suffix is stripped. For ``T`` limits the authored rope
        id maps to its solver channel ('boom_hoist' for solved ropes).
        """
        entity_id = limit_key
        for comp in _LIMIT_KEY_COMPONENTS:
            suffix = f"_{comp}"
            if limit_key.endswith(suffix):
                entity_id = limit_key[: -len(suffix)]
                break
        if component != "T":
            return entity_id, entity_id

        rope_ids_to_try = [entity_id]
        if entity_id.endswith("_rope") and not entity_id.endswith("__rope"):
            rope_ids_to_try.append(f"{entity_id[:-5]}__rope")
        if entity_id.endswith("__rope"):
            rope_ids_to_try.append(f"{entity_id[:-6]}_rope")

        for rid in rope_ids_to_try:
            rope = next((r for r in self.doc.ropes if r.id == rid), None)
            if rope is None:
                continue
            if rope.tension_mode == "solve":
                return entity_id, "boom_hoist"
            return entity_id, rid

        return entity_id, entity_id

    def compute_allowable_load(
        self,
        point: AnalysisPoint,
        design_limits: dict[str, dict],  # entity_id -> {component -> max_kN}
        hook_daf: DynamicFactorLike = 1.0,
        hook_mass_t: float = 0.0,
    ) -> AllowableCapacity:
        """The most restrictive design limit's hook-force and payload capacity.

        design_limits keys may be either entity_id ('boom_hoist') or limit_id
        ('boom_hoist_T'/'rear_hinge_Fx'); see :func:`allowable.allowable_hook_load`.
        """
        return allowable_hook_load(
            self.doc,
            point,
            design_limits,
            resolve_limit_target=self.resolve_limit_target,
            tolerance=self.TOLERANCE,
            hook_daf=hook_daf,
            hook_mass_t=hook_mass_t,
        )

    def compute_omnidirectional_allowable_load(
        self,
        boom_angle_deg: float,
        hoist_id: str,
        design_limits: dict[str, dict],
        hook_daf: DynamicFactorLike = 1.0,
        hook_mass_t: float = 0.0,
        *,
        wind_speed_m_s: Optional[float] = None,
        accel_x_m_s2: Optional[float] = None,
        accel_y_m_s2: Optional[float] = None,
        accel_z_m_s2: Optional[float] = None,
        pitch_accel_rad_s2: Optional[float] = None,
        roll_accel_rad_s2: Optional[float] = None,
        offlead_deg: Optional[float] = None,
        sidelead_deg: Optional[float] = None,
        hoist_runtime_overrides: Optional[dict[str, dict[str, Any]]] = None,
        vessel_roll_deg: Optional[float] = None,
        vessel_pitch_deg: Optional[float] = None,
        crane_slewing_angle_deg: Optional[float] = None,
        tackle_length_m: Optional[float] = None,
    ) -> Optional[AllowableCapacity]:
        wind_ref = (
            self.doc.environment.max_wind_speed_m_s
            if wind_speed_m_s is None
            else abs(float(wind_speed_m_s))
        )
        best_capacity: Optional[AllowableCapacity] = None
        for wind_direction in candidate_wind_directions(wind_ref):
            point = self.compute_analysis_point(
                boom_angle_deg,
                0.0,
                hoist_id,
                wind_speed_m_s=wind_ref,
                wind_direction=wind_direction,
                accel_x_m_s2=accel_x_m_s2,
                accel_y_m_s2=accel_y_m_s2,
                accel_z_m_s2=accel_z_m_s2,
                pitch_accel_rad_s2=pitch_accel_rad_s2,
                roll_accel_rad_s2=roll_accel_rad_s2,
                offlead_deg=offlead_deg,
                sidelead_deg=sidelead_deg,
                hoist_runtime_overrides=hoist_runtime_overrides,
                vessel_roll_deg=vessel_roll_deg,
                vessel_pitch_deg=vessel_pitch_deg,
                crane_slewing_angle_deg=crane_slewing_angle_deg,
                tackle_length_m=tackle_length_m,
            )
            if point is None:
                continue
            capacity = self.compute_allowable_load(
                point,
                design_limits,
                hook_daf=hook_daf,
                hook_mass_t=hook_mass_t,
            )
            capacity.governing_wind_direction = (
                wind_direction if wind_ref > self.TOLERANCE else None
            )
            if (
                best_capacity is None
                or capacity.max_allowable_load_kN < best_capacity.max_allowable_load_kN
            ):
                best_capacity = capacity
        return best_capacity
