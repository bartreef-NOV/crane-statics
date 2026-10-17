"""Calculation engine for crane statics analysis.

This module implements the core mathematical solver for:
- Rope tensions
- Connection reactions
- Response baseline + sensitivity decomposition
- Allowable hook load inversion
- Contractual evaluation
"""

from dataclasses import dataclass
from typing import Optional, Any
import math
from ..data.models import CraneDocument
from .solver.kinematics import KinematicsAdapter
from .solver.crane_solver import (
    build_solver_static_context,
    build_directional_response_basis,
    compose_unit_basis_point,
    boom_wind_projection_scale,
    compose_scalar_envelope_unit_basis_point,
    rotate_boom_local_point,
)
from .capacity import solve_capacity_limit_kN, solve_radial_capacity_kN


@dataclass
class AnalysisPoint:
    """A single boom angle + outreach analysis point with full response."""

    boom_angle_deg: float
    outreach_m: float

    # Baseline (dead load + environment, zero hook load)
    baseline_rope_tensions: dict[str, float]  # rope_id -> kN
    baseline_reactions: dict[str, dict[str, float]]  # connection_id -> {component: value}

    # Sensitivity to hook force (per kN of hook load)
    sensitivity_rope_tensions: dict[str, float]  # rope_id -> kN/kN
    sensitivity_reactions: dict[str, dict[str, float]]  # connection_id -> {component: value/kN}

    # Independent force responses per lateral kN.
    offlead_lateral_unit_rope_tensions: Optional[dict[str, float]] = None
    offlead_lateral_unit_reactions: Optional[dict[str, dict[str, float]]] = None
    sidelead_lateral_unit_reactions: Optional[dict[str, dict[str, float]]] = None

    # Local axis information (for boom and leg components)
    connection_local_axes: Optional[dict[str, dict[str, float] | tuple[float, float]]] = (
        None  # connection_id -> {ux, uz}
    )

    # Governing signs for environmental loads
    governing_signs: dict[str, int] | None = None  # wind, accel_x, accel_z, pitch -> {-1, 0, 1}
    governing_wind_direction: Optional[str] = None


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


def clear_calculator_cache() -> None:
    """Clear all cached calculators (useful for session cleanup)."""
    _CALCULATOR_CACHE.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Numeric Tolerance Constants
# ─────────────────────────────────────────────────────────────────────────────

NUMERIC_TOLERANCE = 1e-6  # General-purpose tolerance for statics/comparisons
VECTOR_MAGNITUDE_TOLERANCE = 1e-12  # Threshold for zero magnitude (unitless direction)
QUADRATIC_SOLVER_TOLERANCE = 1e-9  # Tolerance for quadratic equation solving
WIND_SPEED_THRESHOLD = 1e-12  # Threshold for non-zero wind speed


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


def candidate_wind_directions(wind_speed_m_s: Optional[float]) -> tuple[str, ...]:
    if wind_speed_m_s is None or abs(float(wind_speed_m_s)) <= WIND_SPEED_THRESHOLD:
        return ("+X",)
    return ("+X", "-X", "+Y", "-Y")


def resolve_connection_component_linear_response(
    point: AnalysisPoint,
    connection_id: str,
    component: str,
) -> Optional[tuple[float, float]]:
    """Resolve baseline/sensitivity for linear connection components.

    Returns (baseline, sensitivity) for components representable as
    baseline + sensitivity * hook_load_kN. Returns None when the
    component is unsupported or required local-axis data is unavailable.
    """
    base_map = point.baseline_reactions.get(connection_id, {})
    sens_map = point.sensitivity_reactions.get(connection_id, {})

    if component in {"Fx", "Fy", "Fz", "M", "Mx", "My"}:
        return float(base_map.get(component, 0.0)), float(sens_map.get(component, 0.0))

    axis_kind = None
    if component == "boom_axial":
        axis_kind = "axial"
    elif component == "boom_normal":
        axis_kind = "normal"
    elif component == "leg_axial":
        axis_kind = "axial"
    elif component == "leg_normal":
        axis_kind = "normal"
    else:
        return None

    axis_map = point.connection_local_axes or {}
    axis = axis_map.get(connection_id)
    if not axis:
        return None

    if isinstance(axis, dict):
        ux = float(axis.get("ux", 0.0))
        uz = float(axis.get("uz", 0.0))
    elif isinstance(axis, (tuple, list)) and len(axis) >= 2:
        ux = float(axis[0])
        uz = float(axis[1])
    else:
        return None

    if abs(ux) + abs(uz) <= 1e-12:
        return None

    fx0 = float(base_map.get("Fx", 0.0))
    fz0 = float(base_map.get("Fz", 0.0))
    sfx = float(sens_map.get("Fx", 0.0))
    sfz = float(sens_map.get("Fz", 0.0))

    if axis_kind == "axial":
        return fx0 * ux + fz0 * uz, sfx * ux + sfz * uz
    # Right-handed in-plane normal from axial (ux, uz).
    return fx0 * (-uz) + fz0 * ux, sfx * (-uz) + sfz * ux


def compute_platform_base_max_bearing_line_load_kN_per_m(
    *,
    fz_kN: float,
    mx_kNm: float,
    my_kNm: float,
    slewing_bearing_diameter_m: float,
) -> float:
    """Compute bearing line load demand from vertical force and resultant moment."""
    diameter = float(slewing_bearing_diameter_m)
    if diameter <= 0.0:
        raise ValueError("slewing_bearing_diameter_m must be > 0")
    m_res = math.hypot(float(mx_kNm), float(my_kNm))
    return float(fz_kN) / (math.pi * diameter) + 4.0 * m_res / (math.pi * diameter * diameter)


def compute_platform_base_fradial_kN(
    *,
    fx_kN: float,
    fy_kN: float,
) -> float:
    """Compute platform-base radial force magnitude from Fx/Fy."""
    return math.hypot(float(fx_kN), float(fy_kN))


def compute_platform_base_mradial_kNm(
    *,
    mx_kNm: float,
    my_kNm: float,
) -> float:
    """Compute platform-base radial moment magnitude from Mx/My."""
    return math.hypot(float(mx_kNm), float(my_kNm))


@dataclass
class AllowableCapacity:
    """Result of allowable hook load calculation with two distinct metrics.

    CRITICAL: These fields measure capacity in TWO INCOMPATIBLE DOMAINS:
    - max_allowable_load_kN: Hook-force domain (kN). This is the force applied at the hook,
      including all DAF and hook-mass effects. Used internally for equilibrium checks.
    - max_allowable_load_t: Payload domain (tonnes). This is the net payload mass that can
      be lifted after subtracting hook mass. Used for Load Chart Y-axis and contractual checks.

    METRIC CONVERSION FORMULA (hook_force → payload):
        max_allowable_load_t = (max_allowable_load_kN / hook_daf / gravity) - hook_mass_t

    USAGE RULES:
    - Chart curves, contractual points, and payload displays MUST use max_allowable_load_t
    - Scene visualization of auto-load display uses hook_load_kN (stored separately in state)
    - Status messages showing hook-force capacity should be labeled with "kN", payload with "t"

    Example: 100 kN rope limit, 5 t hook, 1.0 DAF, 9.81 m/s² gravity:
        max_allowable_load_kN = 100.0 kN
        max_allowable_load_t = (100/1.0/9.81) - 5 ≈ 5.2 t
    """

    max_allowable_load_kN: float  # Hook-force domain (includes DAF & hook mass effects)
    max_allowable_load_t: float  # Payload domain (net mass after subtracting hook mass)

    governing_limit_id: Optional[str] = None
    governing_wind_direction: Optional[str] = None
    margin_kN: Optional[float] = None
    margin_t: Optional[float] = None


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

    def _build_connection_map(self) -> dict[str, dict]:
        if self.doc.connections is None:
            self.doc.connections = []
        return {str(c.get("id")): c for c in self.doc.connections}

    def _build_split_support_reactions(
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
    ) -> tuple[dict[str, dict[str, float]], float, float]:
        node_positions = self._kinematics.compute_all_node_positions(boom_angle_deg)
        node_pos = {nid: (float(v["x"]), float(v["z"])) for nid, v in node_positions.items()}

        origin_by_group = {
            "heel": node_pos.get("boom_heel", (0.0, 0.0)),
            "front_leg": node_pos.get("front_base", (0.0, 0.0)),
            "rear_leg": node_pos.get("rear_base", (0.0, 0.0)),
            "platform_base": node_pos.get("platform_heel", (0.0, 0.0)),
        }
        moments = {
            "heel": {"Mx": 0.0, "Mz": 0.0},
            "front_leg": {"Mx": 0.0, "Mz": 0.0},
            "rear_leg": {"Mx": 0.0, "Mz": 0.0},
            "platform_base": {"Mx": 0.0, "Mz": 0.0},
        }
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
        roll_ref_z = float(vm.reference_z_m if vm is not None else 0.0)

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
                ay_pt = float(accel_y_m_s2) + float(roll_accel_rad_s2) * (zw - roll_ref_z)
                fy_acc = -float(mp.mass_t) * ay_pt
                fz_weight = -float(mp.mass_t) * gravity_abs
                _accumulate_force(xw, yw, zw, fx=0.0, fy=fy_acc, fz=fz_weight)

        rho = float(env.air_density_kg_m3)
        wind_sign = 0.0 if abs(float(wind_y_m_s)) < 1e-12 else math.copysign(1.0, float(wind_y_m_s))
        wind_mag = abs(float(wind_y_m_s))
        boom_proj = boom_wind_projection_scale(boom_angle_deg)

        for body in self.doc.bodies:
            for wa in body.wind_areas:
                if body.id == "boom" and wa.local_x_m is not None:
                    xw, zw = rotate_boom_local_point(
                        float(wa.local_x_m), float(wa.local_z_m or 0.0), node_pos, boom_angle_deg
                    )
                    area_proj = float(wa.area_v_m2) * boom_proj
                else:
                    xw, zw = float(wa.x_m), float(wa.z_m)
                    area_proj = float(wa.area_v_m2)
                fy_wind = wind_sign * 0.5 * rho * float(wa.cd) * area_proj * wind_mag**2 / 1000.0
                _accumulate_force(xw, 0.0, zw, fx=0.0, fy=fy_wind, fz=0.0)

        hoist = self.hoists.get(hoist_id)
        if hoist is not None:
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
            effective_hook_mass_t = float(override.get("hook_mass_t", normal_hook_mass_t) or 0.0)
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
                # A weight: it acts downward (fz), not sideways.
                fz_comp = -comp_mass_t * gravity_abs
                _accumulate_force(float(sx), 0.0, float(sz), fx=0.0, fy=0.0, fz=fz_comp)

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
            split[left_entity] = {"Fx": 0.5 * total_fx + d_fx, "Fz": 0.5 * total_fz + d_fz}
            split[right_entity] = {"Fx": 0.5 * total_fx - d_fx, "Fz": 0.5 * total_fz - d_fz}
        return split, float(moments["platform_base"]["Mx"]), float(total_fy_platform)

    def _augment_point_with_split_supports(
        self,
        point: AnalysisPoint,
        hoist_id: str,
        wind_y_m_s: float,
        accel_y_m_s2: float,
        roll_accel_rad_s2: float,
        sidelead_deg: float,
        hoist_runtime_overrides: Optional[dict[str, dict[str, Any]]] = None,
    ) -> None:
        split_at_zero, platform_mx_at_zero, platform_fy_at_zero = (
            self._build_split_support_reactions(
                point,
                hoist_id,
                point.boom_angle_deg,
                hook_force_kN=0.0,
                wind_y_m_s=wind_y_m_s,
                accel_y_m_s2=accel_y_m_s2,
                roll_accel_rad_s2=roll_accel_rad_s2,
                side_lateral_force_kN=0.0,
                hoist_runtime_overrides=hoist_runtime_overrides,
            )
        )
        split_at_one, platform_mx_at_one, platform_fy_at_one = self._build_split_support_reactions(
            point,
            hoist_id,
            point.boom_angle_deg,
            hook_force_kN=1.0,
            wind_y_m_s=wind_y_m_s,
            accel_y_m_s2=accel_y_m_s2,
            roll_accel_rad_s2=roll_accel_rad_s2,
            side_lateral_force_kN=0.0,
            hoist_runtime_overrides=hoist_runtime_overrides,
        )
        split_at_side_unit, platform_mx_at_side_unit, platform_fy_at_side_unit = (
            self._build_split_support_reactions(
                point,
                hoist_id,
                point.boom_angle_deg,
                hook_force_kN=0.0,
                wind_y_m_s=wind_y_m_s,
                accel_y_m_s2=accel_y_m_s2,
                roll_accel_rad_s2=roll_accel_rad_s2,
                side_lateral_force_kN=1.0,
                hoist_runtime_overrides=hoist_runtime_overrides,
            )
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
    ) -> Optional[AnalysisPoint]:
        """Full linear response at one boom angle.

        ``tackle_length_m`` is the rope paid out below the active hoist's sheave.
        It moves rope weight between the falls and the winch, so an interactive
        caller passes what the scene draws; leaving it ``None`` evaluates the
        designed operating position (see ``rope_mass.active_hook_positions``).
        """
        try:
            if not self.hoists.get(hoist_id):
                return None

            env = self.doc.environment
            vm = env.vessel_motion
            wind_ref = (
                env.max_wind_speed_m_s if wind_speed_m_s is None else abs(float(wind_speed_m_s))
            )
            wind_dir = normalize_wind_direction(wind_direction)
            wind_x_ref, wind_y_ref = split_wind_speed_components(wind_ref, wind_dir)
            accel_x_ref = (
                (vm.accel_x_m_s2 if vm else 0.0) if accel_x_m_s2 is None else float(accel_x_m_s2)
            )
            accel_y_ref = (
                (getattr(vm, "accel_y_m_s2", 0.0) if vm else 0.0)
                if accel_y_m_s2 is None
                else float(accel_y_m_s2)
            )
            accel_z_ref = (
                (vm.accel_z_m_s2 if vm else 0.0) if accel_z_m_s2 is None else float(accel_z_m_s2)
            )
            pitch_ref = (
                (vm.pitch_angular_accel_rad_s2 if vm else 0.0)
                if pitch_accel_rad_s2 is None
                else float(pitch_accel_rad_s2)
            )
            roll_ref = (
                (getattr(vm, "roll_angular_accel_rad_s2", 0.0) if vm else 0.0)
                if roll_accel_rad_s2 is None
                else float(roll_accel_rad_s2)
            )
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
                return None

            # Use signed directional composition when explicit env values are provided;
            # fall back to worst-case scalar envelope for document-default calls.
            _explicit_env = not (
                wind_speed_m_s is None
                and accel_x_m_s2 is None
                and accel_y_m_s2 is None
                and accel_z_m_s2 is None
                and pitch_accel_rad_s2 is None
                and roll_accel_rad_s2 is None
            )
            if _explicit_env:

                def _sign_of(v: float) -> float:
                    return 0.0 if abs(v) < 1e-12 else math.copysign(1.0, v)

                composed = compose_unit_basis_point(
                    basis,
                    wind_sign=_sign_of(wind_x_ref),
                    accel_x_sign=_sign_of(accel_x_ref),
                    accel_z_sign=_sign_of(accel_z_ref),
                    pitch_sign=_sign_of(pitch_ref),
                    offlead_deg=offlead_deg,
                )
            else:
                composed = compose_scalar_envelope_unit_basis_point(basis, offlead_deg=offlead_deg)

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
            self._augment_point_with_split_supports(
                point,
                hoist_id,
                wind_y_m_s=wind_y_ref,
                accel_y_m_s2=accel_y_ref,
                roll_accel_rad_s2=roll_ref,
                sidelead_deg=sidelead_ref,
                hoist_runtime_overrides=hoist_runtime_overrides,
            )
            return point
        except Exception:
            return None

    def _compute_outreach(self, boom_angle_deg: float, hoist_id: str) -> float:
        try:
            return self._kinematics.compute_outreach(boom_angle_deg, hoist_id)
        except Exception:
            angle_rad = math.radians(boom_angle_deg)
            return 100.0 + 50.0 * math.cos(angle_rad)

    def compute_allowable_load(
        self,
        point: AnalysisPoint,
        design_limits: dict[str, dict],  # entity_id -> {component -> max_kN}
        hook_daf: float = 1.0,
        hook_mass_t: float = 0.0,
    ) -> AllowableCapacity:
        """Invert Q(H) = Q0 + s*H <= Q_max  →  H_max = (Q_max - Q0) / s.
        Returns the most restrictive limit.

        design_limits keys may be either entity_id ('boom_hoist') or
        limit_id ('boom_hoist_T'/'rear_hinge_Fx'); the function resolves
        the entity by stripping the component suffix when needed.
        """
        gravity = abs(self.doc.environment.gravity_m_s2)

        h_max_kN = float("inf")
        governing_limit_id = None

        _known_components = {
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
        }

        def _resolve_entity(key: str) -> str:
            """Strip trailing _Component suffix to get entity_id if key is a limit_id."""
            for comp in _known_components:
                suffix = f"_{comp}"
                if key.endswith(suffix):
                    return key[: -len(suffix)]
            return key

        def _resolve_rope_channel(entity_id: str, component: str) -> str:
            """Map authored rope ids to the effective solver rope channel for this limit."""
            if component != "T":
                return entity_id

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
                    return "boom_hoist"
                return rid

            return entity_id

        for limit_key, components in design_limits.items():
            entity_id = _resolve_entity(limit_key)
            for component, limit_kN in components.items():
                if not limit_kN:
                    continue

                rope_channel = _resolve_rope_channel(entity_id, component)

                if entity_id in point.sensitivity_reactions:
                    if component == "resultant":
                        base_map = point.baseline_reactions.get(entity_id, {})
                        sens_map = point.sensitivity_reactions.get(entity_id, {})
                        h_candidate = solve_radial_capacity_kN(
                            float(limit_kN),
                            float(base_map.get("Fx", 0.0)),
                            float(base_map.get("Fz", 0.0)),
                            float(sens_map.get("Fx", 0.0)),
                            float(sens_map.get("Fz", 0.0)),
                        )
                        if 0.0 <= h_candidate < h_max_kN:
                            h_max_kN = h_candidate
                            governing_limit_id = limit_key
                        continue
                    if component == "fradial" and entity_id == "platform_base":
                        base_map = point.baseline_reactions.get(entity_id, {})
                        sens_map = point.sensitivity_reactions.get(entity_id, {})
                        h_candidate = solve_radial_capacity_kN(
                            float(limit_kN),
                            float(base_map.get("Fx", 0.0)),
                            float(base_map.get("Fy", 0.0)),
                            float(sens_map.get("Fx", 0.0)),
                            float(sens_map.get("Fy", 0.0)),
                        )
                        if 0.0 <= h_candidate < h_max_kN:
                            h_max_kN = h_candidate
                            governing_limit_id = limit_key
                        continue
                    if component == "mradial" and entity_id == "platform_base":
                        base_map = point.baseline_reactions.get(entity_id, {})
                        sens_map = point.sensitivity_reactions.get(entity_id, {})
                        h_candidate = solve_radial_capacity_kN(
                            float(limit_kN),
                            float(base_map.get("Mx", 0.0)),
                            float(base_map.get("My", base_map.get("M", 0.0))),
                            float(sens_map.get("Mx", 0.0)),
                            float(sens_map.get("My", sens_map.get("M", 0.0))),
                        )
                        if 0.0 <= h_candidate < h_max_kN:
                            h_max_kN = h_candidate
                            governing_limit_id = limit_key
                        continue
                    if component == "max_bearing_line_load" and entity_id == "platform_base":
                        base_map = point.baseline_reactions.get(entity_id, {})
                        sens_map = point.sensitivity_reactions.get(entity_id, {})
                        diameter = float(
                            getattr(self.doc.support_widths, "slewing_bearing_diameter_m", 1.0)
                        )
                        h_candidate = solve_capacity_limit_kN(
                            float(limit_kN),
                            lambda hook_kN: compute_platform_base_max_bearing_line_load_kN_per_m(
                                fz_kN=float(base_map.get("Fz", 0.0))
                                + float(sens_map.get("Fz", 0.0)) * hook_kN,
                                mx_kNm=float(base_map.get("Mx", 0.0))
                                + float(sens_map.get("Mx", 0.0)) * hook_kN,
                                my_kNm=float(base_map.get("My", base_map.get("M", 0.0)))
                                + float(sens_map.get("My", sens_map.get("M", 0.0))) * hook_kN,
                                slewing_bearing_diameter_m=diameter,
                            ),
                            tolerance=self.TOLERANCE,
                        )
                        if 0.0 <= h_candidate < h_max_kN:
                            h_max_kN = h_candidate
                            governing_limit_id = limit_key
                        continue
                    linear = resolve_connection_component_linear_response(
                        point, entity_id, component
                    )
                    if linear is None:
                        continue
                    baseline, sens = linear
                elif rope_channel in point.sensitivity_rope_tensions:
                    sens = point.sensitivity_rope_tensions.get(rope_channel, 0.0)
                    baseline = point.baseline_rope_tensions.get(rope_channel, 0.0)
                else:
                    continue

                if baseline > limit_kN:
                    h_candidate = 0.0  # already exceeded with no hook load
                elif abs(sens) > self.TOLERANCE:
                    h_candidate = (limit_kN - baseline) / sens
                else:
                    continue
                if 0.0 <= h_candidate < h_max_kN:
                    h_max_kN = h_candidate
                    governing_limit_id = limit_key

        # No limit yields a candidate: the hook load is unlimited (inf), not 1000 kN.

        # Convert hook force to payload using DAF and gravity
        # Step 1: Remove DAF to get net hook force
        h_max_kN = max(0.0, h_max_kN)
        h_net_kN = h_max_kN / hook_daf
        # Step 2: Convert force to mass (kN / gravity_m_s2 = tonnes) and subtract hook mass
        h_net_payload_t = h_net_kN / gravity - hook_mass_t
        h_net_payload_t = max(0.0, h_net_payload_t)
        # Metric domain semantics:
        #   h_max_kN = hook-force domain (includes DAF & hook mass effects)
        #   h_net_payload_t = payload domain (net mass after subtracting hook mass)

        return AllowableCapacity(
            max_allowable_load_kN=h_max_kN,
            max_allowable_load_t=h_net_payload_t,
            governing_limit_id=governing_limit_id,
            governing_wind_direction=point.governing_wind_direction,
            margin_kN=max(0.0, h_max_kN),
        )

    def compute_omnidirectional_allowable_load(
        self,
        boom_angle_deg: float,
        hoist_id: str,
        design_limits: dict[str, dict],
        hook_daf: float = 1.0,
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

    def evaluate_contractual_point(
        self,
        hoist_id: str,
        required_load_t: float,
        required_outreach_m: float,
        point: AnalysisPoint,
        design_limits: dict[str, dict],
    ) -> dict:
        """Evaluate whether a contractual point passes or fails."""
        capacity = self.compute_allowable_load(
            point,
            design_limits,
            hook_daf=self.hoists[hoist_id].hook_daf,
            hook_mass_t=self.hoists[hoist_id].hook_mass_t,
        )

        margin_t = capacity.max_allowable_load_t - required_load_t
        passes = margin_t >= -self.TOLERANCE

        return {
            "hoist_id": hoist_id,
            "required_load_t": required_load_t,
            "required_outreach_m": required_outreach_m,
            "allowable_load_t": capacity.max_allowable_load_t,
            "margin_t": margin_t,
            "passes": passes,
            "governing_limit_id": capacity.governing_limit_id,
        }
