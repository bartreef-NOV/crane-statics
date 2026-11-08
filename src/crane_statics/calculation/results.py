"""Result types of the calculation engine: analysis points and allowable capacities."""

import math
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class HookLateral:
    """Horizontal live load at the hoist's support node: ``fraction * H + constant``.

    ``fraction_x``/``fraction_y`` are crane-frame components per kN of hook force H (exact
    signed values, like every other solve input). ``min_fraction`` floors their magnitude:
    a smaller fraction vector is scaled up to ``min_fraction`` in its own direction (along
    +x when it is zero), so the load stays linear in H. ``constant_x_kN``/``constant_y_kN``
    are forces that do not grow with H, carried by the wind: the force when the solve's
    wind blows along +x / +y. A solve applies ``constant_x_kN * w_x`` and
    ``constant_y_kN * w_y`` with ``w = (V_x|V_x|, V_y|V_y|) / V^2`` (the structural wind's
    scaling: +-1 for an axis wind, nothing without wind).
    """

    fraction_x: float = 0.0
    fraction_y: float = 0.0
    constant_x_kN: float = 0.0
    constant_y_kN: float = 0.0
    min_fraction: float = 0.0

    def floored_fractions(self) -> tuple[float, float]:
        """The fraction vector after the ``min_fraction`` floor."""
        fx, fy = float(self.fraction_x), float(self.fraction_y)
        floor = abs(float(self.min_fraction))
        size = math.hypot(fx, fy)
        if size >= floor:
            return fx, fy
        if size == 0.0:
            return floor, 0.0
        return fx * floor / size, fy * floor / size

    def magnitude(self) -> float:
        """The floored H-proportional magnitude ``max(|fraction|, min_fraction)``."""
        return max(math.hypot(self.fraction_x, self.fraction_y), abs(float(self.min_fraction)))


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
    # The +x unit with the left/right support entities (half the total each); the off-lead
    # unit above keeps the totals only. The hook lateral composes with this one.
    lateral_x_unit_reactions: Optional[dict[str, dict[str, float]]] = None

    # Local axis information (for boom and leg components)
    connection_local_axes: Optional[dict[str, dict[str, float] | tuple[float, float]]] = (
        None  # connection_id -> {ux, uz}
    )

    # Governing signs for environmental loads
    governing_signs: dict[str, int] | None = None  # wind, accel_x, accel_z, pitch -> {-1, 0, 1}
    governing_wind_direction: Optional[str] = None


@dataclass
class AllowableCapacity:
    """Result of allowable hook load calculation with two distinct metrics.

    CRITICAL: These fields measure capacity in TWO INCOMPATIBLE DOMAINS:
    - max_allowable_load_kN: Hook-force domain (kN). This is the force applied at the hook,
      including all DAF and hook-mass effects. Used internally for equilibrium checks.
    - max_allowable_load_t: Payload domain (tonnes). This is the net payload mass that can
      be lifted after subtracting hook mass. Used for Load Chart Y-axis and contractual checks.

    METRIC CONVERSION (hook_force → payload), see ``dynamic_factor.DynamicFactor``; for a
    constant factor:
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
