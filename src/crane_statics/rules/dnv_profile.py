"""DNV-ST-0378 (July 2019, amended October 2021) profile. Pure: no Qt, no UI.

Builds, for one condition, hoist and analysis mode, the dynamic factor (psi), the
lateral live-load settings and the foundation factor SF1, each with a provenance
record. Document consistency (no ``crane_class`` under DNV, offboard inputs) is checked
by ``validation.validate_rules_document``; this module only guards what it needs to
build the factors.

Ship-motion inertia (4.1.5.1) belongs to Case III, which is out of scope, so both
in-service cases carry zero accelerations. Horizontal operational loads SH are out of
scope as well. Clause strings carry the printed page number of the DNV document where
it was verified.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from ..calculation.dynamic_factor import DynamicFactor
from ..calculation.solver.crane_solver import wind_force_kN
from ..data.models import ConditionSpec, CraneDocument, Hoist, RulesSpec, VesselMotion
from .factors import LinearFactor, MaxFactor, RelativeVelocityFactor
from .foundation import dnv_sf1
from .types import (
    NEUTRAL_FOUNDATION,
    CaseSpec,
    FoundationFactors,
    LateralSpec,
    LiftSetup,
    ProvenanceRecord,
)
from .validation import RulesValidationError

if TYPE_CHECKING:  # core imports rules at run time; keep this edge type-only.
    from ..core.analysis_cases import HoistAnalysisMode

#: DNV 4.2.3.2: Case II heel/trim at least 1.5 times the Case I (4.1.2.3) values.
CASE_II_INCLINE_FACTOR = 1.5
#: DNV has no minimum side load on the suspended load.
MIN_SIDE_LOAD_FRACTION = 0.0
#: DNV has no separate retaining-component load factor.
RETAINING_LIVE_FACTOR = 1.0
#: ``Hoist.hook_daf`` default; any other value is a manual override.
_DEFAULT_DAF = 1.0

_CL_PSI = "DNV-ST-0378 4.1.3.2, p.54"
_CL_FLOOR = "DNV-ST-0378 8.2.2.1, p.90"
_CL_V_H = "DNV-ST-0378 8.2.2.2, p.91"
_CL_SF1 = "DNV-ST-0378 8.2.2.4, p.91"
#: Case I (4.2.2.1, p.57) heel/trim: the still-water minimum angles of 4.1.2.3.
_CL_INCLINE_CASE_I = "DNV-ST-0378 4.1.2.3, Table 4-1, p.54"
_CL_CASE_II = "DNV-ST-0378 4.2.3.2, p.58"
_CL_LOAD_WIND = "DNV-ST-0378 4.2.3.3, p.58"

_CASE_I = "Case I"
_CASE_II = "Case II"


def dnv_psi_floor(w_kN: float) -> float:
    """DNV 8.2.2.1 lower limit of psi at the maximum working load ``w_kN`` of the curve.

    1.3 up to 2500 kN, ``1.5 - W/12500`` below 5000 kN, 1.1 from 5000 kN. The standard
    states the 1.3 band for W > 10 kN; 1.3 is also used below that.
    """
    if w_kN <= 2500.0:
        return 1.3
    if w_kN < 5000.0:
        return 1.5 - w_kN / 12500.0
    return 1.1


def dnv_v_h(h_s_m: float) -> float:
    """DNV 8.2.2.2 minimum hoisting speed ``VH = 0.1 (Hs + 1)``, m/s (Hs in m)."""
    return 0.1 * (h_s_m + 1.0)


class DnvProfile:
    """DNV cases and lift setup for a document whose ``rules.standard`` is DNV."""

    #: Name of the pedestal/foundation factor in reported rows.
    foundation_label = "DNV SF1"
    #: Live-load factor of retaining components, 1.0: no separate retaining load.
    retaining_live_factor = RETAINING_LIVE_FACTOR

    def cases(self, doc: CraneDocument, cond: ConditionSpec) -> tuple[CaseSpec, CaseSpec]:
        """DNV 4.2.2 and 4.2.3: Case I without wind, Case II with wind and 1.5x heel/trim.

        The condition's ``vessel_motion`` roll and pitch are the Case I values. Both
        cases drop the vessel accelerations (Case III, out of scope).
        """
        _rules(doc)
        motion = cond.vessel_motion
        case_i = _static_motion(motion, motion.roll_deg, motion.pitch_deg)
        case_ii = _static_motion(
            motion,
            CASE_II_INCLINE_FACTOR * motion.roll_deg,
            CASE_II_INCLINE_FACTOR * motion.pitch_deg,
        )
        return (
            CaseSpec(_CASE_I, 0.0, case_i),
            CaseSpec(_CASE_II, cond.wind_speed_m_s, case_ii),
        )

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

        ``chart_max_load_t`` sets the curve's maximum working load, ``chart_max_load_t``
        plus the mode's hook mass plus ``suspended_rope_mass_t``, which fixes the psi
        floor; psi itself is evaluated at the point's own working load. The safe working
        load for SF1 is ``chart_max_load_t`` alone (accessories excluded, 4.1.2.1).
        ``case`` sets the heel/trim of the lateral spec; it defaults to Case I.
        ``support_x_m`` (shared signature with the ABS profile, keyword-required there) is
        unused: both DNV cases have no vessel accelerations; nonzero condition
        accelerations are reported in the warnings. A maximum working load of 0 (no hook
        mass, no load chart) leaves out the computed dynamic-factor record, with a warning.
        """
        rules = _rules(doc)
        hoist = _hoist(doc, hoist_id)
        gravity = abs(doc.environment.gravity_m_s2)
        if case is None:
            case = self.cases(doc, cond)[0]
        motion = case.vessel_motion
        w_kN = (chart_max_load_t + mode.lower_block_mass_t + suspended_rope_mass_t) * gravity

        records: list[ProvenanceRecord] = []
        warnings: list[str] = []
        if _has_acceleration(cond.vessel_motion):
            warnings.append(
                f"conditions.{cond.name}.vessel_motion: vessel accelerations are not applied "
                "under DNV: ship-motion inertia is Case III, out of scope"
            )
        floor = dnv_psi_floor(w_kN)
        records.append(
            ProvenanceRecord(
                "psi_floor",
                floor,
                "-",
                _CL_FLOOR,
                "psi_min = 1.3 (W <= 2500 kN); 1.5 - W/12500 (W < 5000 kN); 1.1 otherwise",
                {"W_max_kN": w_kN},
                "computed",
            )
        )
        factor: DynamicFactor
        floor_factor = LinearFactor(floor, suspended_rope_mass_t)
        if cond.lift == "onboard":
            factor = floor_factor
            clause, formula = _CL_FLOOR, "psi = psi_min (onboard lift)"
            inputs: dict[str, float] = {"psi_min": floor}
        else:
            v_r = _relative_velocity(cond, hoist, records, warnings)
            factor = MaxFactor(
                (
                    floor_factor,
                    RelativeVelocityFactor(stiffness_kN_m, v_r, suspended_rope_mass_t),
                )
            )
            clause = _CL_PSI
            formula = "psi = max(1 + v_r*sqrt(C/(W*g)), psi_min)"
            inputs = {"psi_min": floor, "K_kN_m": stiffness_kN_m, "v_r_m_s": v_r}

        if w_kN > 0.0:
            computed = _value_at(
                factor, w_kN, mode.lower_block_mass_t, suspended_rope_mass_t, gravity
            )
            rec_inputs = {
                **inputs,
                "W_kN": w_kN,
                "suspended_rope_mass_t": suspended_rope_mass_t,
            }
            records.append(
                ProvenanceRecord(
                    "dynamic_factor", computed, "-", clause, formula, rec_inputs, "computed"
                )
            )
        else:
            # No hook mass and no load chart: psi is still evaluated at each point's own W.
            warnings.append(
                f"hoists.{hoist_id} ({mode.name}): the maximum working load is 0 kN (no hook "
                "mass and no load chart), so no representative dynamic factor is stated; "
                "each point uses its own working load"
            )
        if hoist.hook_daf != _DEFAULT_DAF:
            # The daf replaces the factor value, not the load: the suspended rope stays in W.
            factor = LinearFactor(float(hoist.hook_daf), suspended_rope_mass_t)
            records.append(
                ProvenanceRecord(
                    "dynamic_factor",
                    float(hoist.hook_daf),
                    "-",
                    f"{clause} (overridden by hoists.{hoist_id}.hook_daf)",
                    "psi = manual daf",
                    {"hook_daf": float(hoist.hook_daf)},
                    "override",
                )
            )

        # 4.2.3.3: the engineer enters the largest load area facing the wind and C. The
        # pressure is the solver's aerodynamic one (0.5 rho V^2 C), as for the structure.
        rho = float(doc.environment.air_density_kg_m3)
        wind_per_v2 = wind_force_kN(rho, 1.0, cond.load_drag_coefficient, cond.load_wind_area_m2)
        lateral = LateralSpec(
            accel_fraction_x=0.0,
            accel_fraction_y=0.0,
            incline_deg=math.hypot(motion.roll_deg, motion.pitch_deg),
            wind_area_m2=cond.load_wind_area_m2,
            wind_cd=cond.load_drag_coefficient,
            min_fraction=MIN_SIDE_LOAD_FRACTION,
            wind_force_per_speed_sq=wind_per_v2,
        )
        records.append(
            ProvenanceRecord(
                "list_trim_incline",
                lateral.incline_deg,
                "deg",
                _CL_CASE_II if case.name == _CASE_II else _CL_INCLINE_CASE_I,
                "theta = sqrt(heel^2 + trim^2); Case II heel/trim = 1.5 x Case I",
                {"heel_deg": motion.roll_deg, "trim_deg": motion.pitch_deg},
                "computed",
            )
        )
        records.append(
            ProvenanceRecord(
                "load_wind_area",
                cond.load_wind_area_m2,
                "m^2",
                _CL_LOAD_WIND,
                "largest load area facing the wind; C = 1.2 containers, 1.0 other (entered)",
                {"C": cond.load_drag_coefficient},
                "computed",
            )
        )
        records.append(
            ProvenanceRecord(
                "load_wind_force",
                lateral.wind_force_kN(case.wind_speed_m_s),
                "kN",
                _CL_LOAD_WIND,
                "F = 0.5 * rho * C * V^2 * A / 1000 (Case I: no wind)",
                {
                    "V_m_s": case.wind_speed_m_s,
                    "C": cond.load_drag_coefficient,
                    "A_m2": cond.load_wind_area_m2,
                    "rho_kg_m3": rho,
                },
                "computed",
            )
        )

        swl_kN = chart_max_load_t * gravity
        sf1 = dnv_sf1(swl_kN) if rules.cabin_above_slewing_bearing else 1.0
        # Without a cabin above the bearing SF1 does not apply: the neutral factors.
        foundation = (
            FoundationFactors(live_factor=lambda _ll: sf1, dead_factor=sf1)
            if rules.cabin_above_slewing_bearing
            else NEUTRAL_FOUNDATION
        )
        records.append(
            ProvenanceRecord(
                "pedestal_factor",
                sf1,
                "-",
                _CL_SF1,
                "SF1 = 1.3 (SWL < 2500 kN); 1.1 otherwise; 1.0 without cabin above bearing",
                {
                    "SWL_kN": swl_kN,
                    "cabin_above_slewing_bearing": float(rules.cabin_above_slewing_bearing),
                },
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


def _rules(doc: CraneDocument) -> RulesSpec:
    rules = doc.rules
    if rules is None or rules.standard != "DNV":
        raise RulesValidationError("rules.standard: the DNV profile needs standard DNV")
    return rules


def _has_acceleration(motion: VesselMotion) -> bool:
    """Whether ``motion`` has any nonzero linear or angular acceleration."""
    return any(
        getattr(motion, field) != 0.0
        for field in (
            "accel_x_m_s2",
            "accel_y_m_s2",
            "accel_z_m_s2",
            "pitch_angular_accel_rad_s2",
            "roll_angular_accel_rad_s2",
        )
    )


def _static_motion(motion: VesselMotion, roll_deg: float, pitch_deg: float) -> VesselMotion:
    """``motion`` with the given heel/trim and every acceleration set to zero."""
    return motion.model_copy(
        update={
            "accel_x_m_s2": 0.0,
            "accel_y_m_s2": 0.0,
            "accel_z_m_s2": 0.0,
            "roll_deg": roll_deg,
            "pitch_deg": pitch_deg,
            "pitch_angular_accel_rad_s2": 0.0,
            "roll_angular_accel_rad_s2": 0.0,
        }
    )


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
    """``v_r = max(0.5 v_L, VH) + sqrt(v_in^2 + v_t^2)``; warns when v_L is below VH."""
    prefix = f"conditions.{cond.name}"
    v_l = hoist.max_hoisting_speed_m_s
    if v_l is None:
        raise RulesValidationError(
            f"hoists.{hoist.id}.max_hoisting_speed_m_s: required for offboard lifts"
        )
    h_s = cond.significant_wave_height_m
    v_in = cond.v_in_m_s
    v_t = cond.v_t_m_s
    if h_s is None or v_in is None or v_t is None:
        raise RulesValidationError(
            f"{prefix}: significant_wave_height_m, v_in_m_s and v_t_m_s are required "
            "for offboard lifts"
        )
    v_h = dnv_v_h(h_s)
    records.append(
        ProvenanceRecord(
            "min_hoisting_speed",
            v_h,
            "m/s",
            _CL_V_H,
            "VH = 0.1*(Hs + 1)",
            {"Hs_m": h_s},
            "computed",
        )
    )
    if v_l < v_h:
        warnings.append(
            f"hoists.{hoist.id}.max_hoisting_speed_m_s: {v_l:g} m/s is below the DNV "
            f"minimum VH {v_h:.4g} m/s at Hs {h_s:g} m ({_CL_V_H}); the entered speed is "
            "used and the shaded load-chart region is deferred"
        )
    v_r = max(0.5 * v_l, v_h) + math.hypot(v_in, v_t)
    records.append(
        ProvenanceRecord(
            "relative_velocity",
            v_r,
            "m/s",
            _CL_FLOOR,
            "v_r = max(0.5*v_L, VH) + sqrt(v_in^2 + v_t^2)",
            {"v_L_m_s": v_l, "VH_m_s": v_h, "v_in_m_s": v_in, "v_t_m_s": v_t},
            "computed",
        )
    )
    return v_r


def _value_at(
    factor: DynamicFactor,
    w_kN: float,
    lower_block_mass_t: float,
    rope_mass_t: float,
    gravity: float,
) -> float:
    """The factor ``F / W`` at working load ``w_kN``."""
    payload_t = w_kN / gravity - lower_block_mass_t - rope_mass_t
    return factor.hook_force_kN(payload_t, lower_block_mass_t, gravity) / w_kN
