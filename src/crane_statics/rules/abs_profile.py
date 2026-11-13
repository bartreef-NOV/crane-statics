"""ABS Lifting Appliances (January 2026) profile. Pure: no Qt, no UI.

Builds, for one condition, hoist and analysis mode, the dynamic factor (VAF), the
lateral live-load settings, the pedestal factor and the retaining-component factor,
each with a provenance record. Document consistency (crane class, heavy-lift 0.07 g
limit on the linear accelerations, offboard inputs) is checked by
``validation.validate_rules_document``; this module only guards what it needs to build
the factors; the heavy-lift 0.07 g limit on a_v at the boom tip is checked at load over
the rated angles and warned here at a point beyond them.

Clause strings carry the printed page number of the ABS document.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from ..calculation.dynamic_factor import DynamicFactor
from ..data.models import ConditionHoist, ConditionSpec, CraneDocument, Hoist
from .factors import AbsOnboardFactor, LinearFactor, MaxFactor
from .factors import RelativeVelocityFactor
from .foundation import abs_pedestal_factor
from .types import CaseSpec, FoundationFactors, LateralSpec, LiftSetup, ProvenanceRecord
from .validation import (
    GRAVITY_M_S2,
    RulesValidationError,
    heavy_lift_a_v_excess,
    tip_vertical_accel_g,
)

if TYPE_CHECKING:  # core imports rules at run time; keep this edge type-only.
    from ..core.analysis_cases import HoistAnalysisMode

#: ABS 2-2/9.3.1 (offshore) and 2-2/11.3 (heavy lift): side load >= 0.02 * VDL.
MIN_SIDE_LOAD_FRACTION = 0.02
#: ABS 2-2/5.13.5(c): retaining components use 3.75 times the vertical design load.
RETAINING_LIVE_FACTOR = 3.75
#: ABS 2-2/11.3: heavy-lift VAF in mild conditions, before vessel acceleration.
HEAVY_LIFT_BASE_VAF = 1.1

_CL_ONBOARD = "ABS 2-2/9.3.1, p.53"
_CL_OFFBOARD = "ABS 2-2/9.3.2, p.53"
_CL_V_HMIN = "ABS 2-2/9.3.2, p.54"
_CL_HEAVY = "ABS 2-2/11.3, p.56-57"
_CL_LIST_TRIM = "ABS 2-2/5.21, p.50"
_CL_WIND = "ABS 2-2/5.19.2-5.19.3, p.49-50"
#: ABS 2-2/5.19.2: P = V^2 * Cs / 1637 kN/m^2 (V in m/s).
WIND_PRESSURE_DIVISOR = 1637.0
#: ABS 2-2/5.19.3 i): A_LL = 0.1215 * LL^(2/3) m^2 (LL in kN).
LIVE_LOAD_AREA_COEFF = 0.1215
_CL_PEDESTAL = "ABS 2-2/5.15, p.46"
_CL_RETAINING = "ABS 2-2/5.13.5(c), p.46"


def abs_v_hmin(h_sig_m: float) -> float:
    """ABS 2-2/9.3.2 minimum hoisting speed, m/s (Hsig in m)."""
    if h_sig_m <= 1.8:
        return 0.01 + 0.098 * h_sig_m
    return 0.067 * (h_sig_m + 1.0)


class AbsProfile:
    """ABS cases and lift setup for a document whose ``rules.standard`` is ABS."""

    #: Name of the pedestal/foundation factor in reported rows.
    foundation_label = "ABS PF"
    #: Live-load factor of retaining components, 3.75 (2-2/5.13.5(c)).
    retaining_live_factor = RETAINING_LIVE_FACTOR

    def cases(self, doc: CraneDocument, cond: ConditionSpec) -> tuple[CaseSpec, ...]:
        """ABS 2-2/5.1.1: one most-severe in-service case per condition."""
        _crane_class(doc)
        return (CaseSpec("In-service", cond.wind_speed_m_s, cond.vessel_motion),)

    def lift_setup(
        self,
        doc: CraneDocument,
        cond: ConditionSpec,
        hoist_id: str,
        mode: HoistAnalysisMode,
        stiffness_kN_m: float,
        suspended_rope_mass_t: float,
        chart_max_load_t: float,
        *,
        case: Optional[CaseSpec] = None,
        support_x_m: float,
    ) -> LiftSetup:
        """Dynamic factor, lateral and foundation settings for one hoist and mode.

        ``chart_max_load_t`` does not change any ABS factor (each is evaluated at the
        point's own LL); it only sets the representative LL, ``chart_max_load_t`` plus
        the mode's hook mass plus ``suspended_rope_mass_t``, at which the provenance
        records state the dynamic and pedestal factors. ``case`` (shared signature with
        the DNV profile) supplies the vessel motion; it defaults to the single ABS case,
        whose motion is the condition's.

        ``support_x_m`` is the crane-frame x of the node the hook hangs from (the boom tip)
        at the point's boom angle. 5.17's a_v is the vertical acceleration there: the
        linear ``|a_z|`` plus the angular accelerations times a bound on their lever arm
        over every slew, ``(|alpha_pitch| + |alpha_roll|) * (|x_ref| + |x_tip|)`` (spec
        section 9.7 item 10). It is required: a default of 0 would drop the lever arm.
        A heavy-lift a_v over 0.07 g there warns: ``validate_rules_document`` rejects a
        document exceeding it at any rated angle (2-2/11.3: the offshore requirements apply
        instead), so only a point beyond them, such as the Scene's free angle, gets here.
        A representative LL of 0 (no hook mass, no load chart) leaves out the computed
        dynamic-factor record, with a warning.
        """
        crane_class = _crane_class(doc)
        hoist = _hoist(doc, hoist_id)
        gravity = abs(doc.environment.gravity_m_s2)
        motion = (case if case is not None else self.cases(doc, cond)[0]).vessel_motion
        # The solver gives a point a_z - alpha_pitch_c * (x - x_ref), with alpha_pitch_c the
        # slew-rotated (alpha_roll, alpha_pitch) and x_ref in the crane frame; physically the
        # reference point stays on the vessel while the boom slews about x = 0. Both levers
        # are at most |x_ref| + |x_tip|, and |alpha_pitch_c| <= |alpha_pitch| + |alpha_roll|.
        a_v_g, lever_m = tip_vertical_accel_g(motion, support_x_m)
        ll_kN = (chart_max_load_t + mode.lower_block_mass_t + suspended_rope_mass_t) * gravity

        records: list[ProvenanceRecord] = []
        warnings: list[str] = []
        factor: DynamicFactor
        if crane_class == "heavy_lift":
            # 2-2/11.3: validate_rules_document rejected a_v over 0.07 g at every rated
            # angle; a point beyond them (the Scene's free angle) warns instead.
            excess = heavy_lift_a_v_excess(cond.name, motion, support_x_m)
            if excess is not None:
                warnings.append(
                    f"{excess} (this boom angle is outside the hoist's operating range and "
                    "load chart, over which the document was checked)"
                )
            factor = LinearFactor(HEAVY_LIFT_BASE_VAF + a_v_g, suspended_rope_mass_t)
            clause, formula = _CL_HEAVY, "VAF = 1.1 + a_v"
            inputs = {"a_v_g": a_v_g, "a_v_lever_m": lever_m}
            min_side_clause = _CL_HEAVY
        elif cond.lift == "onboard":
            factor = AbsOnboardFactor(a_v_g, suspended_rope_mass_t)
            clause = _CL_ONBOARD
            formula = "VAF = clamp(1.373 - LL/5220 + a_v, 1.1 + a_v, 1.33 + a_v)"
            inputs = {"a_v_g": a_v_g, "a_v_lever_m": lever_m}
            min_side_clause = _CL_ONBOARD
        else:
            v_r = _relative_velocity(cond, hoist, records, warnings)
            factor = MaxFactor(
                (
                    AbsOnboardFactor(a_v_g, suspended_rope_mass_t),
                    RelativeVelocityFactor(stiffness_kN_m, v_r, suspended_rope_mass_t),
                )
            )
            clause = _CL_OFFBOARD
            formula = "VAF = max(1 + v_r*sqrt(K/(g*LL)), VAF_onb)"
            inputs = {
                "a_v_g": a_v_g,
                "a_v_lever_m": lever_m,
                "K_kN_m": stiffness_kN_m,
                "v_r_m_s": v_r,
            }
            min_side_clause = _CL_ONBOARD

        if ll_kN > 0.0:
            computed = _value_at(
                factor, ll_kN, mode.lower_block_mass_t, suspended_rope_mass_t, gravity
            )
            rec_inputs = {
                **inputs,
                "LL_kN": ll_kN,
                "suspended_rope_mass_t": suspended_rope_mass_t,
            }
            records.append(
                ProvenanceRecord(
                    "dynamic_factor", computed, "-", clause, formula, rec_inputs, "computed"
                )
            )
        else:
            # No hook mass and no load chart: the factor is still evaluated at each
            # point's own LL; there is no representative value to state.
            warnings.append(
                f"hoists.{hoist_id} ({mode.name}): the representative live load is 0 kN "
                "(no hook mass and no load chart), so no representative dynamic factor is "
                "stated; each point uses its own live load"
            )
        settings = _hoist_settings(cond, hoist_id)
        if settings.daf is not None:
            # An authored daf is the manual override (omitted: derived from the standard).
            # It replaces the factor value, not the load: the suspended rope stays in LL.
            daf = float(settings.daf)
            factor = LinearFactor(daf, suspended_rope_mass_t)
            records.append(
                ProvenanceRecord(
                    "dynamic_factor",
                    daf,
                    "-",
                    f"{clause} (overridden by conditions.{cond.name}.hoists.{hoist_id}.daf)",
                    "VAF = manual daf",
                    {"daf": daf},
                    "override",
                )
            )
        area_m2 = cond.load_wind_area_m2
        if area_m2 == 0.0:
            # Owner ruling: the LL-dependent default is evaluated once, at the chart's
            # maximum live load, so the wind force is a constant (conservative, linear in H).
            area_m2 = LIVE_LOAD_AREA_COEFF * ll_kN ** (2.0 / 3.0)
            warnings.append(
                f"conditions.{cond.name}.load_wind_area_m2: 0; the ABS 2-2/5.19.3 (p.50) "
                f"default projected load area 0.1215*LL^(2/3) = {area_m2:.4g} m^2 is applied, "
                f"evaluated at the chart's maximum live load LL = {ll_kN:.6g} kN"
            )
            records.append(
                ProvenanceRecord(
                    "load_wind_area",
                    area_m2,
                    "m^2",
                    _CL_WIND,
                    "A_LL = 0.1215 * LL^(2/3), LL at the chart maximum (default area)",
                    {"LL_kN": ll_kN},
                    "computed",
                )
            )
        wind_per_v2 = cond.load_drag_coefficient * area_m2 / WIND_PRESSURE_DIVISOR
        records.append(
            ProvenanceRecord(
                "load_wind_force",
                wind_per_v2 * cond.wind_speed_m_s**2,
                "kN",
                _CL_WIND,
                "HL_wind = P * A; P = V^2 * Cs / 1637",
                {
                    "V_m_s": cond.wind_speed_m_s,
                    "Cs": cond.load_drag_coefficient,
                    "A_m2": area_m2,
                },
                "computed",
            )
        )

        lateral = LateralSpec(
            accel_fraction_x=abs(motion.accel_x_m_s2) / GRAVITY_M_S2,
            accel_fraction_y=abs(motion.accel_y_m_s2) / GRAVITY_M_S2,
            incline_deg=math.hypot(motion.roll_deg, motion.pitch_deg),
            wind_area_m2=area_m2,
            wind_cd=cond.load_drag_coefficient,
            min_fraction=MIN_SIDE_LOAD_FRACTION,
            wind_force_per_speed_sq=wind_per_v2,
            # 5.17: a_h is the acceleration at the boom tip, so the angular accelerations
            # add their lever-arm term there (core evaluates it at the support node).
            accel_fraction_per_m_x=abs(motion.pitch_angular_accel_rad_s2) / GRAVITY_M_S2,
            accel_fraction_per_m_y=abs(motion.roll_angular_accel_rad_s2) / GRAVITY_M_S2,
            reference_z_m=motion.reference_z_m,
        )
        records.append(
            ProvenanceRecord(
                "min_side_load_fraction",
                MIN_SIDE_LOAD_FRACTION,
                "-",
                min_side_clause,
                "HL_min = 0.02 * VDL",
                {},
                "computed",
            )
        )
        records.append(
            ProvenanceRecord(
                "list_trim_incline",
                lateral.incline_deg,
                "deg",
                _CL_LIST_TRIM,
                "theta = sqrt(list^2 + trim^2); HL_SIA = L * sin(theta)",
                {"list_deg": motion.roll_deg, "trim_deg": motion.pitch_deg},
                "computed",
            )
        )

        foundation = FoundationFactors(
            live_factor=lambda ll: abs_pedestal_factor(ll, crane_class), dead_factor=1.0
        )
        floor = "1.2" if crane_class == "offshore" else "1.0"
        records.append(
            ProvenanceRecord(
                "pedestal_factor",
                foundation.live_factor(ll_kN),
                "-",
                _CL_PEDESTAL,
                f"PF = clamp(1.56 - LL/4000, {floor}, 1.5)",
                {"LL_kN": ll_kN},
                "computed",
            )
        )
        records.append(
            ProvenanceRecord(
                "retaining_live_factor",
                RETAINING_LIVE_FACTOR,
                "-",
                _CL_RETAINING,
                "live load at 3.75 * VDL; dead load at 1.0; PF not applied",
                {},
                "computed",
            )
        )
        return LiftSetup(
            factor=factor,
            lateral=lateral,
            foundation=foundation,
            retaining_live_factor=RETAINING_LIVE_FACTOR,
            records=tuple(records),
            warnings=tuple(warnings),
        )


def _crane_class(doc: CraneDocument) -> str:
    rules = doc.rules
    if rules is None or rules.standard != "ABS":
        raise RulesValidationError("rules.standard: the ABS profile needs standard ABS")
    if rules.crane_class is None:
        raise RulesValidationError("rules.crane_class: required under standard ABS")
    return rules.crane_class


def _hoist_settings(cond: ConditionSpec, hoist_id: str) -> ConditionHoist:
    """``hoist_id``'s entry in ``cond``: its lead limits and optional manual daf."""
    settings = cond.hoists.get(hoist_id)
    if settings is None:
        raise RulesValidationError(
            f"conditions.{cond.name}.hoists.{hoist_id}: hoist {hoist_id!r} is not usable in "
            f"condition {cond.name!r}"
        )
    return settings


def _hoist(doc: CraneDocument, hoist_id: str) -> Hoist:
    hoist = next((h for h in doc.hoists if h.id == hoist_id), None)
    if hoist is None:
        raise RulesValidationError(f"hoists.{hoist_id}: not defined")
    return hoist


def _relative_velocity(
    cond: ConditionSpec,
    hoist: Hoist,
    records: list[ProvenanceRecord],
    warnings: list[str],
) -> float:
    """``v_r = v_h + sqrt(v_d^2 + v_c^2)``; warns, without raising v_h, below v_hmin."""
    prefix = f"conditions.{cond.name}"
    v_h = hoist.max_hoisting_speed_m_s
    if v_h is None:
        raise RulesValidationError(
            f"hoists.{hoist.id}.max_hoisting_speed_m_s: required for offboard lifts"
        )
    h_sig = cond.significant_wave_height_m
    v_in = cond.v_in_m_s
    v_t = cond.v_t_m_s
    if h_sig is None or v_in is None or v_t is None:
        raise RulesValidationError(
            f"{prefix}: significant_wave_height_m, v_in_m_s and v_t_m_s are required "
            "for offboard lifts"
        )
    v_hmin = abs_v_hmin(h_sig)
    records.append(
        ProvenanceRecord(
            "min_hoisting_speed",
            v_hmin,
            "m/s",
            _CL_V_HMIN,
            "v_hmin = 0.01 + 0.098*Hsig (Hsig <= 1.8 m); 0.067*(Hsig + 1) otherwise",
            {"Hsig_m": h_sig},
            "computed",
        )
    )
    if v_h < v_hmin:
        warnings.append(
            f"hoists.{hoist.id}.max_hoisting_speed_m_s: {v_h:g} m/s is below the ABS "
            f"minimum v_hmin {v_hmin:.4g} m/s at Hsig {h_sig:g} m ({_CL_V_HMIN}); "
            "the entered speed is used"
        )
    v_r = v_h + math.hypot(v_in, v_t)
    records.append(
        ProvenanceRecord(
            "relative_velocity",
            v_r,
            "m/s",
            _CL_OFFBOARD,
            "v_r = v_h + sqrt(v_in^2 + v_t^2)  (ABS v_d, v_c)",
            {"v_h_m_s": v_h, "v_in_m_s": v_in, "v_t_m_s": v_t},
            "computed",
        )
    )
    return v_r


def _value_at(
    factor: DynamicFactor,
    ll_kN: float,
    lower_block_mass_t: float,
    rope_mass_t: float,
    gravity: float,
) -> float:
    """The factor ``F / LL`` at live load ``ll_kN``."""
    payload_t = ll_kN / gravity - lower_block_mass_t - rope_mass_t
    return factor.hook_force_kN(payload_t, lower_block_mass_t, gravity) / ll_kN
