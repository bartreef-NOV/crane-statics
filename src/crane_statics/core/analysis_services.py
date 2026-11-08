"""Phase 3 Analysis Services: Split monolithic AnalysisService into focused responsibilities.

Each service is pure Python with no Qt dependencies. Composed together, they
form a cleaner API surface than the original monolithic AnalysisService.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any, Optional

from ..calculation.dynamic_factor import DynamicFactor, as_dynamic_factor
from ..calculation.engine import CraneCalculator, get_calculator
from ..calculation.solver.kinematics import KinematicsAdapter
from .analysis_cases import HoistAnalysisMode, analysis_mode_by_name
from .demand_extraction import extract_connection_component_response
from .lift_factor import (
    PLATFORM_BASE,
    RETAINING_ENTITY,
    LiftFactors,
    amplified_rope_hoist_id,
    factored_point,
    foundation_label,
    hook_lateral,
)
from .load_condition import scene_load_condition
from ..presentation.formatters import ConnectionFormatter, HoistFormatter, RopeFormatter
from .drawn_loads import LoadConditions
from .results import ResultRow
from ..calculation.vessel_frame import VesselInputs, crane_frame_motion

if TYPE_CHECKING:
    from ..calculation.allowable import DemandScale
    from ..calculation.engine import AllowableCapacity, AnalysisPoint
    from ..calculation.results import HookLateral
    from ..data.models import CraneDocument, Hoist
    from .session_model import SessionModel

_LOG = logging.getLogger(__name__)

#: Boom angles the Scene keeps a rules lift setup for (dragging the boom adds new ones).
_SCENE_LIFT_ENTRIES = 64


class KinematicsService:
    """Pure kinematics management: angle bounds, boom reach calculations."""

    def __init__(self, session: SessionModel):
        self._session = session
        self._angle_bounds: dict[str, tuple[float, float]] = {}
        self._kin: Optional[KinematicsAdapter] = None
        self._kin_doc: Optional[CraneDocument] = (
            None  # identity-tracks which doc the cached adapter was built from
        )

    @property
    def angle_bounds(self) -> dict[str, tuple[float, float]]:
        """Cached angle bounds for all hoists."""
        return self._angle_bounds

    def invalidate_kinematics(self) -> None:
        """Clear cached kinematics adapter (call after document change)."""
        self._kin_doc = None

    def kinematics(self) -> Optional[KinematicsAdapter]:
        """Get kinematics adapter, computing on first access and caching thereafter."""
        doc = self._session.document
        if doc is None:
            self._kin = None
            self._kin_doc = None
            return None
        if self._kin_doc is not doc:
            self._kin = KinematicsAdapter(doc.model_dump())
            self._kin_doc = doc
        return self._kin

    def recompute_angle_bounds(self, doc: Optional[CraneDocument]) -> None:
        """Recompute angle bounds for all hoists from document geometry."""
        self._angle_bounds = {}
        if not doc:
            return
        try:
            kin = KinematicsAdapter(doc.model_dump())
        except (TypeError, ValueError, RuntimeError) as exc:
            _LOG.warning("Failed to initialize kinematics adapter for angle-bounds: %s", exc)
            return
        for hoist in doc.hoists:
            lo_outreach = hoist.outreach_min_m or 0.0
            hi_outreach = hoist.outreach_max_m or 200.0
            try:
                a_lo = kin.outreach_to_angle(lo_outreach, hoist.id)
                a_hi = kin.outreach_to_angle(hi_outreach, hoist.id)
                if a_lo is not None and a_hi is not None:
                    self._angle_bounds[hoist.id] = (float(min(a_lo, a_hi)), float(max(a_lo, a_hi)))
                    continue
                angles = [a * 0.25 for a in range(0, int(180 / 0.25) + 1)]
                samples = [(a, kin.compute_outreach(a, hoist.id)) for a in angles]
                lo_angle = float(min(samples, key=lambda s: abs(s[1] - lo_outreach))[0])
                hi_angle = float(min(samples, key=lambda s: abs(s[1] - hi_outreach))[0])
                self._angle_bounds[hoist.id] = (min(lo_angle, hi_angle), max(lo_angle, hi_angle))
            except (TypeError, ValueError, RuntimeError) as exc:
                _LOG.debug("Falling back to default angle bounds for hoist %s: %s", hoist.id, exc)
                self._angle_bounds[hoist.id] = (0.0, 90.0)

    def spinbox_angle_bounds(self, hoist_id: Optional[str]) -> tuple[float, float]:
        """Angle bounds for UI spinbox: full range in auto-load, [0,max] otherwise."""
        state = self._session.get_active_hoist_state()
        auto = state.scene_state.hook_load_auto if state else False
        if hoist_id and hoist_id in self._angle_bounds:
            lo, hi = self._angle_bounds[hoist_id]
            if not auto:
                lo = 0.0
            return lo, hi
        return 0.0, 90.0


class HoistStateService:
    """Pure hoist parameter extraction: modes, hook mass, split configuration."""

    def __init__(self, session: SessionModel):
        self._session = session
        self._lift: Optional[LiftFactors] = None
        # The state of the document ``_lift`` serves: the app edits documents in place.
        self._lift_key: Optional[tuple[int, str]] = None

    def dynamic_factor(self, hoist: Optional[Hoist]) -> DynamicFactor:
        """The factor the Scene converts payload and hook force with, for ``hoist``.

        Legacy: the authored ``hook_daf`` (1.0 without a hoist). On a rules document, the
        profile's factor under the Scene's condition (``scene_load_condition``) at the
        hoist's current boom angle, hook position (tackle length) and hook mode, as the
        chart computes it there; it counts the rope hanging at that hook (``extra_mass_t``).
        """
        doc = self._session.document
        if hoist is None or doc is None or doc.rules is None:
            return as_dynamic_factor(float(hoist.hook_daf) if hoist is not None else 1.0)
        mode, angle, tackle_m = self._scene_hook_state(hoist)
        return (
            self._scene_lift(doc)
            .setup(scene_load_condition(doc), hoist.id, mode, angle, tackle_length_m=tackle_m)
            .factor
        )

    def hook_lateral(self, hoist_id: str) -> Optional[HookLateral]:
        """The live-load lateral the Scene's solves of ``hoist_id`` apply (legacy: None).

        Its magnitude and floor come from the Scene condition's lift setup (the one
        ``dynamic_factor`` uses), its wind on the load at the Scene's wind speed. A single
        state has no limit to maximise, so it points along the Scene's crane-frame
        horizontal inertia, ``-(a_x, a_y)`` of the resolved vessel motion with the tilt
        folded in (+x without any), and the wind on the load points the same way (both at
        full magnitude, as the envelope's worst direction has them); spec section 9.4.
        """
        doc = self._session.document
        hoist = self._session.payload_hoist_by_id(hoist_id)
        if doc is None or hoist is None or doc.rules is None:
            return None
        state = self._session.hoist_states.get(hoist.id)
        if state is None:
            return None
        mode, angle, tackle_m = self._scene_hook_state(hoist)
        setup = self._scene_lift(doc).setup(
            scene_load_condition(doc), hoist.id, mode, angle, tackle_length_m=tackle_m
        )
        sc = state.scene_state
        motion = crane_frame_motion(
            abs(float(doc.environment.gravity_m_s2)),
            VesselInputs(
                accel_x_m_s2=float(sc.accel_x_m_s2),
                accel_y_m_s2=float(sc.accel_y_m_s2),
                accel_z_m_s2=float(sc.accel_z_m_s2),
                roll_deg=float(sc.vessel_roll_deg),
                pitch_deg=float(sc.vessel_pitch_deg),
                slew_deg=float(sc.crane_slewing_angle_deg),
                roll_accel_rad_s2=float(sc.roll_accel_rad_s2),
                pitch_accel_rad_s2=float(sc.pitch_accel_rad_s2),
            ),
        )
        direction = (-float(motion.accel_x_m_s2), -float(motion.accel_y_m_s2))
        support_z = self._scene_lift(doc).support_z_m(hoist.id, angle)
        return hook_lateral(setup, float(sc.wind_speed_m_s), direction, support_z_m=support_z)

    def demand_scales(self, hoist_id: str) -> Optional[dict[str, DemandScale]]:
        """The pedestal and retaining-component scales of the Scene's solves (legacy: None).

        From the Scene condition's lift setup (the one ``dynamic_factor`` uses), with LL
        counting the rope hanging at the Scene hook (``lift_factor.demand_scales``).
        """
        doc = self._session.document
        hoist = self._session.payload_hoist_by_id(hoist_id)
        if doc is None or hoist is None or doc.rules is None:
            return None
        mode, angle, tackle_m = self._scene_hook_state(hoist)
        lift = self._scene_lift(doc)
        condition = scene_load_condition(doc)
        setup = lift.setup(condition, hoist.id, mode, angle, tackle_length_m=tackle_m)
        return lift.demand_scales(condition, hoist.id, mode, angle, setup, tackle_m)

    def _scene_lift(self, doc: CraneDocument) -> LiftFactors:
        """The Scene's ``LiftFactors``, rebuilt whenever the document changes."""
        # Every input of the factor, the contractual (rated) loads included.
        key = (id(doc), hashlib.sha256(doc.model_dump_json().encode("utf-8")).hexdigest())
        if self._lift is None or self._lift_key != key:
            # A private calculator: the shared one is never rebuilt after an in-place edit.
            calc = CraneCalculator(doc)
            self._lift = LiftFactors(doc, calc, max_entries=_SCENE_LIFT_ENTRIES)
            self._lift_key = key
        return self._lift

    def _scene_hook_state(self, hoist: Hoist) -> tuple[HoistAnalysisMode, float, Optional[float]]:
        """(mode, boom angle, tackle length) of ``hoist`` in the Scene."""
        state = self._session.hoist_states.get(hoist.id)
        split = bool(state is not None and state.split_mode_active)
        mode = analysis_mode_by_name(hoist, "split" if split else "normal")
        angle = float(state.scene_state.boom_angle_deg) if state is not None else 0.0
        tackle_m = float(state.scene_state.tackle_length_m) if state is not None else None
        return mode, angle, tackle_m

    def suspended_rope_mass_t(self, hoist_id: str) -> float:
        """The suspended rope the Scene factor of ``hoist_id`` amplifies, in t (legacy: 0).

        The same mass ``dynamic_factor`` passes to the profile (``LiftFactors``), at the
        Scene's boom angle, tackle length and hook mode.
        """
        doc = self._session.document
        hoist = self._session.payload_hoist_by_id(hoist_id)
        if doc is None or hoist is None or self.amplified_rope_hoist_id(hoist_id) is None:
            return 0.0
        mode, angle, tackle_m = self._scene_hook_state(hoist)
        return self._scene_lift(doc).suspended_rope_mass_t(hoist.id, mode, angle, tackle_m)

    def hook_force_follows_scene_state(self) -> bool:
        """Whether a payload's hook force changes with the boom angle, hook position and mode.

        True on a rules document: its factor is per boom angle and counts the suspended rope
        hanging at the Scene hook. A legacy factor is the constant ``hook_daf``.
        """
        doc = self._session.document
        return doc is not None and doc.rules is not None

    def amplified_rope_hoist_id(self, hoist_id: str) -> Optional[str]:
        """The hoist whose hook rope the Scene's solves count in the hook force, if any.

        On a rules document the Scene factor (``dynamic_factor``) carries the suspended
        rope, so the solves leave it out of the dead load; legacy: None.
        """
        doc = self._session.document
        if doc is None:
            return None
        return amplified_rope_hoist_id(scene_load_condition(doc), hoist_id)

    def contractual_points_for_hoist_mode(self, hoist: Optional[Hoist]) -> list:
        """Get contractual load points for hoist's current mode."""
        if hoist is None:
            return []
        hs = self._session.hoist_states.get(hoist.id)
        mode = str(getattr(hs, "chart_mode", "normal")) if hs is not None else "normal"
        return self._session.contractual_points_for_mode(hoist.id, mode)

    def gravity_abs(self) -> float:
        """Get absolute value of gravity from document, with sensible default."""
        doc = self._session.document
        if doc is not None:
            try:
                g = abs(float(doc.environment.gravity_m_s2))
                if g > 1e-9:
                    return g
            except (TypeError, ValueError, AttributeError) as exc:
                _LOG.debug("Invalid gravity value in document; falling back to default: %s", exc)
        return 9.81

    def selected_hoist(self) -> Optional[Hoist]:
        """Get currently selected hoist object."""
        hoist_id = self._session.selected_hoist_id
        return self._session.payload_hoist_by_id(hoist_id)

    def effective_hoist_parameters(self, hoist_id: str) -> tuple[int | None, float, float]:
        """Get (falls, hook_mass_t, support_comp_mass_t) for current runtime mode."""
        doc = self._session.document
        if doc is None:
            return None, 0.0, 0.0
        hoist = self._session.payload_hoist_by_id(hoist_id)
        if hoist is None:
            return None, 0.0, 0.0

        falls = int(hoist.falls) if hoist.falls is not None else None
        hook_mass_t = float(hoist.hook_mass_t)
        support_comp_mass_t = 0.0

        state = self._session.hoist_states.get(hoist_id)
        split_active = bool(state is not None and state.split_mode_active)
        splitable = bool(getattr(hoist, "splitable_block", False))
        if split_active and splitable:
            split_falls = getattr(hoist, "split_falls", None)
            if split_falls is not None:
                falls = int(split_falls)
            split_hook_mass_t = getattr(hoist, "split_hook_mass_t", None)
            if split_hook_mass_t is not None:
                split_hook_mass_t = float(split_hook_mass_t)
                support_comp_mass_t = max(0.0, hook_mass_t - split_hook_mass_t)
                hook_mass_t = split_hook_mass_t

        return falls, hook_mass_t, support_comp_mass_t

    def active_hoist_runtime_overrides(self) -> dict[str, dict[str, Any]]:
        """Build runtime override payload for selected hoist (split mode only)."""
        hoist_id = self._session.selected_hoist_id
        if not hoist_id:
            return {}
        doc = self._session.document
        if doc is None:
            return {}
        hoist = self._session.payload_hoist_by_id(hoist_id)
        if hoist is None:
            return {}

        falls, hook_mass_t, support_comp_mass_t = self.effective_hoist_parameters(hoist_id)
        state = self._session.hoist_states.get(hoist_id)
        if state is None or not state.split_mode_active:
            return {}
        if not bool(getattr(hoist, "splitable_block", False)):
            return {}

        payload: dict[str, Any] = {
            "hook_mass_t": float(hook_mass_t),
            "support_comp_mass_t": float(support_comp_mass_t),
        }
        if falls is not None:
            payload["falls"] = int(falls)
        support_node_id = getattr(hoist, "support_node_id", None)
        if support_node_id:
            payload["support_node_id"] = str(support_node_id)
        return {hoist_id: payload}

    def payload_t_to_hook_force_kN(self, payload_t: float, hoist_id: Optional[str] = None) -> float:
        """Convert payload mass to hook force including hook mass and DAF."""
        if hoist_id is None:
            hoist = self.selected_hoist()
        else:
            hoist = self._session.payload_hoist_by_id(hoist_id)

        payload = max(0.0, float(payload_t))
        hook_mass_t = 0.0
        factor = self.dynamic_factor(hoist)
        if hoist is not None:
            _, hook_mass_t, _ = self.effective_hoist_parameters(hoist.id)
        return factor.hook_force_kN(payload, hook_mass_t, self.gravity_abs())

    def hook_force_kN_to_payload_t(self, hook_force_kN: float) -> float:
        """Inverse of ``payload_t_to_hook_force_kN`` for the selected hoist (floored at 0)."""
        hoist = self.selected_hoist()
        hook_mass_t = 0.0
        factor = self.dynamic_factor(hoist)
        if hoist is not None:
            _, hook_mass_t, _ = self.effective_hoist_parameters(hoist.id)
        gravity = self.gravity_abs()
        if gravity <= 0.0:
            return 0.0
        return max(0.0, factor.payload_t(float(hook_force_kN), hook_mass_t, gravity))


class AnalysisCalculator:
    """Pure analysis computation: equilibrium checks, load capacity calculations."""

    EQUILIBRIUM_REFERENCE_NODES = {
        "boom": "boom_heel",
        "rear_leg": "rear_base",
        "front_leg": "front_base",
        "platform": "platform_base",
    }
    EQUILIBRIUM_TOLERANCE = 1e-6
    EQUILIBRIUM_RELATIVE_TOLERANCE = 1e-9

    def __init__(
        self, session: SessionModel, kinematics_svc: KinematicsService, hoist_svc: HoistStateService
    ):
        self._session = session
        self._kinematics = kinematics_svc
        self._hoist = hoist_svc
        self._unavailable_reason: Optional[str] = None

    def unavailable_reason(self) -> Optional[str]:
        """Why the last ``compute_analysis_point`` returned ``None`` (``None`` after a success)."""
        return self._unavailable_reason

    def compute_analysis_point(self) -> Optional[AnalysisPoint]:
        """Compute equilibrium check for current geometry and loads."""
        self._unavailable_reason = None
        doc = self._session.document
        hoist_id = self._session.selected_hoist_id
        if not doc or not hoist_id:
            return None
        state = self._session.get_active_hoist_state()
        if not state:
            return None
        sc = state.scene_state
        calc = get_calculator(doc)
        overrides = self._hoist.active_hoist_runtime_overrides()
        point = calc.compute_analysis_point(
            sc.boom_angle_deg,
            0.0,
            hoist_id,
            wind_speed_m_s=sc.wind_speed_m_s,
            wind_direction=sc.wind_direction,
            accel_x_m_s2=sc.accel_x_m_s2,
            accel_y_m_s2=sc.accel_y_m_s2,
            accel_z_m_s2=sc.accel_z_m_s2,
            pitch_accel_rad_s2=sc.pitch_accel_rad_s2,
            roll_accel_rad_s2=sc.roll_accel_rad_s2,
            offlead_deg=sc.offlead_deg,
            sidelead_deg=sc.sidelead_deg,
            hoist_runtime_overrides=overrides,
            tackle_length_m=sc.tackle_length_m,
            vessel_roll_deg=sc.vessel_roll_deg,
            vessel_pitch_deg=sc.vessel_pitch_deg,
            crane_slewing_angle_deg=sc.crane_slewing_angle_deg,
            amplified_rope_hoist_id=self._hoist.amplified_rope_hoist_id(hoist_id),
            hook_lateral=self._hoist.hook_lateral(hoist_id),
        )
        self._unavailable_reason = None if point is not None else calc.unavailable_reason
        return point

    def drawn_load_conditions(self) -> LoadConditions:
        """The in-plane conditions the drawn loads are evaluated at.

        The scene's vessel-frame inputs are resolved exactly as ``compute_analysis_point``
        resolves them, split for drawing: ``drawn_loads`` gets the crane-frame gravity g_c
        (tilted Gravity arrows) and the vessel accelerations a_c rotated into the crane
        frame (Inertia), so Gravity plus Inertia equals the tilted, slewed load vector
        m*k_c = m*(g_c - a_c) the solver applies.
        """
        state = self._session.get_active_hoist_state()
        doc = self._session.document
        if state is None:
            return LoadConditions()
        sc = state.scene_state
        gravity = 9.81 if doc is None else abs(float(doc.environment.gravity_m_s2))
        motion = crane_frame_motion(
            gravity,
            VesselInputs(
                accel_x_m_s2=float(sc.accel_x_m_s2),
                accel_y_m_s2=float(sc.accel_y_m_s2),
                accel_z_m_s2=float(sc.accel_z_m_s2),
                roll_deg=float(sc.vessel_roll_deg),
                pitch_deg=float(sc.vessel_pitch_deg),
                slew_deg=float(sc.crane_slewing_angle_deg),
                roll_accel_rad_s2=float(sc.roll_accel_rad_s2),
                pitch_accel_rad_s2=float(sc.pitch_accel_rad_s2),
            ),
        )
        return LoadConditions(
            boom_angle_deg=float(sc.boom_angle_deg),
            hook_load_kN=float(sc.hook_load_kN),
            wind_speed_m_s=float(sc.wind_speed_m_s),
            wind_direction=str(sc.wind_direction or "+X"),
            accel_x_m_s2=motion.accel_crane[0],
            accel_z_m_s2=motion.accel_crane[2],
            pitch_accel_rad_s2=motion.pitch_accel_rad_s2,
            offlead_deg=float(sc.offlead_deg),
            split_mode_active=bool(state.split_mode_active),
            amplified_rope_hoist_id=(
                None
                if self._session.selected_hoist_id is None
                else self._hoist.amplified_rope_hoist_id(self._session.selected_hoist_id)
            ),
            suspended_rope_mass_t=(
                0.0
                if self._session.selected_hoist_id is None
                else self._hoist.suspended_rope_mass_t(self._session.selected_hoist_id)
            ),
            gravity_x_m_s2=motion.gravity_crane[0],
            gravity_z_m_s2=motion.gravity_crane[2],
            hook_lateral_x_kN=self._hook_lateral_x_kN(sc),
        )

    def _hook_lateral_x_kN(self, sc: Any) -> float:
        """The in-plane part of the Scene's live-load lateral at its hook force, kN."""
        hoist_id = self._session.selected_hoist_id
        lateral = None if hoist_id is None else self._hoist.hook_lateral(hoist_id)
        if lateral is None:
            return 0.0
        fraction_x, _ = lateral.floored_fractions()
        return fraction_x * float(sc.hook_load_kN) + float(lateral.constant_x_kN)

    def compute_result_rows(
        self, pt: AnalysisPoint, hook_load_kN: float
    ) -> tuple[list[ResultRow], list[ResultRow]]:
        """Transform equilibrium check into result row objects for UI display."""
        active_limits = {
            dl.id: dl
            for dl in self._session.design_limits
            if dl.enabled and dl.allowable_kN is not None and dl.allowable_kN > 1e-9
        }
        pinned_momentless_connections = {"rear_hinge", "front_hinge", "heel_point", "upper_hinge"}

        rope_rows: list[ResultRow] = []
        rope_order: list[str] = []
        _seen_canonical: set[str] = set()
        for dl in self._session.design_limits:
            if dl.kind == "rope":
                canon = HoistFormatter.runtime_rope_channel_to_rope_id(
                    dl.entity_id, self._session.document
                )
                if canon not in _seen_canonical:
                    rope_order.append(dl.entity_id)
                    _seen_canonical.add(canon)
        for rope_id in pt.baseline_rope_tensions.keys():
            canon = HoistFormatter.runtime_rope_channel_to_rope_id(rope_id, self._session.document)
            if canon not in _seen_canonical:
                rope_order.append(rope_id)
                _seen_canonical.add(canon)

        solve_rope_ids = {
            str(r.id).strip()
            for r in getattr(self._session.document, "ropes", [])
            if str(getattr(r, "tension_mode", "") or "").strip().lower() == "solve"
        }
        rope_order.sort(
            key=lambda rid: (
                0
                if HoistFormatter.runtime_rope_channel_to_rope_id(rid, self._session.document)
                in solve_rope_ids
                else 1
            )
        )

        _bh_canon = HoistFormatter.runtime_rope_channel_to_rope_id(
            "boom_hoist", self._session.document
        )

        for rope_id in rope_order:
            _rope_canon = HoistFormatter.runtime_rope_channel_to_rope_id(
                rope_id, self._session.document
            )
            channel = "boom_hoist" if _rope_canon == _bh_canon else rope_id
            if channel not in pt.baseline_rope_tensions:
                continue
            baseline = pt.baseline_rope_tensions[channel]
            runtime_rope_id = HoistFormatter.runtime_rope_channel_to_rope_id(
                rope_id, self._session.document
            )
            display_hoist_id = HoistFormatter.display_name_for_rope_channel(
                rope_id, self._session.document
            )
            sens = float(pt.sensitivity_rope_tensions.get(channel, 0.0))
            demand = float(baseline) + sens * hook_load_kN
            limit = active_limits.get(f"{runtime_rope_id}_T") or active_limits.get(f"{channel}_T")
            limit_kN = limit.allowable_kN if limit is not None else None
            util_pct = abs(demand) / limit_kN * 100.0 if limit_kN else None
            rope_rows.append(
                ResultRow(
                    name=display_hoist_id,
                    unit=RopeFormatter.component_unit("T"),
                    demand_kN=demand,
                    limit_kN=limit_kN,
                    utilization_pct=util_pct,
                    kind="rope",
                    entity_id=rope_id,
                    component="T",
                    runtime_id=runtime_rope_id,
                )
            )

        conn_rows: list[ResultRow] = []
        conn_ids_order: list[str] = []
        conn_limits_by_id: dict[str, list] = {}
        for dl in self._session.design_limits:
            if dl.kind != "connection":
                continue
            if dl.entity_id not in conn_limits_by_id:
                conn_limits_by_id[dl.entity_id] = []
                conn_ids_order.append(dl.entity_id)
            conn_limits_by_id[dl.entity_id].append(dl)

        hoist_id = self._session.selected_hoist_id
        scales = None if hoist_id is None else self._hoist.demand_scales(hoist_id)
        # With a profile the platform-base limits check the factored demand: the plain
        # rows show the unfactored demand without a limit, the "factored" rows check it.
        factored_ids = {PLATFORM_BASE} if scales else set()

        def _entity_result_rows(
            conn_id: str,
            point: AnalysisPoint = pt,
            kind: str = "connection",
            label: Optional[str] = None,
            limits_of: Optional[str] = None,
        ) -> list[ResultRow]:
            rows: list[ResultRow] = []
            limit_entity = limits_of or conn_id
            for dl in conn_limits_by_id.get(limit_entity, []):
                comp = dl.component
                if comp == "M" and conn_id in pinned_momentless_connections:
                    continue
                widths = getattr(self._session.document, "support_widths", None)
                diameter = widths.slewing_bearing_diameter_m if widths is not None else None
                demand = extract_connection_component_response(
                    point,
                    hook_load_kN,
                    conn_id,
                    comp,
                    support_widths_diameter_m=diameter,
                )
                if demand is None:
                    continue
                limit = active_limits.get(f"{limit_entity}_{comp}")
                if kind == "connection" and conn_id in factored_ids:
                    limit = None
                limit_kN = limit.allowable_kN if limit is not None else None
                if comp == "min_bearing_line_load":
                    demand = max(0.0, demand)  # uplift only
                util_pct = abs(demand) / limit_kN * 100.0 if limit_kN else None
                name = ConnectionFormatter.format_label(limit_entity, comp)
                if label is not None:
                    name = f"{label} / {ConnectionFormatter.component_display_name(comp)}"
                rows.append(
                    ResultRow(
                        name=name,
                        unit=ConnectionFormatter.component_unit(comp),
                        demand_kN=demand,
                        limit_kN=limit_kN,
                        utilization_pct=util_pct,
                        kind=kind,
                        entity_id=limit_entity,
                        component=comp,
                        runtime_id=conn_id,
                    )
                )
            return rows

        present_conn_ids = set(conn_limits_by_id.keys())
        # The retaining copy has no reactions of its own: it is reported as factored rows.
        processed: set[str] = {RETAINING_ENTITY}

        for top_entity_id in ConnectionFormatter.top_level_entities(conn_ids_order):
            if top_entity_id == "heel_point":
                conn_rows.extend(_entity_result_rows("heel_point"))
                for child_entity_id in ConnectionFormatter.child_entities(
                    "heel_point", conn_ids_order
                ):
                    conn_rows.extend(_entity_result_rows(child_entity_id))
                    processed.add(child_entity_id)
                processed.add("heel_point")
                continue

            conn_rows.extend(_entity_result_rows(top_entity_id))
            processed.add(top_entity_id)

        # Entities outside the canonical order follow, in limit order and then any rest.
        for conn_id in [*conn_ids_order, *present_conn_ids]:
            if conn_id in processed:
                continue
            conn_rows.extend(_entity_result_rows(conn_id))
            processed.add(conn_id)

        if scales and PLATFORM_BASE in conn_limits_by_id:
            doc = self._session.document
            label = None if doc is None else foundation_label(doc)
            hoist = self._session.payload_hoist_by_id(hoist_id) if hoist_id else None
            _falls, hook_mass_t, _support = (
                self._hoist.effective_hoist_parameters(hoist_id) if hoist_id else (None, 0.0, 0.0)
            )
            lift_args: dict[str, Any] = dict(
                hook_daf=self._hoist.dynamic_factor(hoist),
                hook_mass_t=hook_mass_t,
                gravity_m_s2=self._hoist.gravity_abs(),
            )
            pedestal = factored_point(
                pt, scales[PLATFORM_BASE], hook_load_kN, PLATFORM_BASE, **lift_args
            )
            conn_rows.extend(
                _entity_result_rows(PLATFORM_BASE, pedestal, "factored", f"Platform Base ({label})")
            )
            if RETAINING_ENTITY in conn_limits_by_id:
                retaining = factored_point(
                    pt, scales[RETAINING_ENTITY], hook_load_kN, RETAINING_ENTITY, **lift_args
                )
                conn_rows.extend(
                    _entity_result_rows(
                        PLATFORM_BASE, retaining, "factored", limits_of=RETAINING_ENTITY
                    )
                )
        return rope_rows, conn_rows

    def compute_current_result_rows(self) -> tuple[Optional[Any], list[ResultRow], list[ResultRow]]:
        """Return current analysis point and result rows for active hoist."""
        state = self._session.get_active_hoist_state()
        if state is None:
            return None, [], []
        pt = self.compute_analysis_point()
        if pt is None:
            return None, [], []
        rope_rows, conn_rows = self.compute_result_rows(pt, state.scene_state.hook_load_kN)
        return pt, rope_rows, conn_rows

    def compute_auto_load(self) -> Optional[AllowableCapacity]:
        """Invert enabled limits to find allowable hook load; None when unavailable."""
        doc = self._session.document
        hoist_id = self._session.selected_hoist_id
        if not doc or not hoist_id:
            return None
        state = self._session.get_active_hoist_state()
        if not state:
            return None
        sc = state.scene_state
        calc = get_calculator(doc)
        enabled = {
            dl.id: {dl.component: dl.allowable_kN}
            for dl in self._session.design_limits
            if dl.enabled and dl.allowable_kN is not None
        }
        hoist = next(h for h in doc.hoists if h.id == hoist_id)
        _falls, effective_hook_mass_t, _support = self._hoist.effective_hoist_parameters(hoist_id)
        return calc.compute_omnidirectional_allowable_load(
            sc.boom_angle_deg,
            hoist_id,
            enabled,
            hook_daf=self._hoist.dynamic_factor(hoist),
            hook_mass_t=effective_hook_mass_t,
            wind_speed_m_s=sc.wind_speed_m_s,
            accel_x_m_s2=sc.accel_x_m_s2,
            accel_y_m_s2=sc.accel_y_m_s2,
            accel_z_m_s2=sc.accel_z_m_s2,
            pitch_accel_rad_s2=sc.pitch_accel_rad_s2,
            roll_accel_rad_s2=sc.roll_accel_rad_s2,
            offlead_deg=abs(float(sc.offlead_deg)),
            sidelead_deg=sc.sidelead_deg,
            hoist_runtime_overrides=self._hoist.active_hoist_runtime_overrides(),
            vessel_roll_deg=sc.vessel_roll_deg,
            vessel_pitch_deg=sc.vessel_pitch_deg,
            crane_slewing_angle_deg=sc.crane_slewing_angle_deg,
            tackle_length_m=sc.tackle_length_m,
            amplified_rope_hoist_id=self._hoist.amplified_rope_hoist_id(hoist_id),
            hook_lateral=self._hoist.hook_lateral(hoist_id),
            demand_scale=self._hoist.demand_scales(hoist_id),
        )

    def resolve_row_demand(
        self, point: AnalysisPoint, hook_load_kN: float, row_meta: dict
    ) -> Optional[float]:
        """Extract demand value from analysis point for a specific result row."""
        kind = str(row_meta.get("kind") or "")
        entity_id = str(row_meta.get("entity_id") or "")
        component = str(row_meta.get("component") or "")
        if kind == "rope":
            if not entity_id:
                return None
            bh_canon = HoistFormatter.runtime_rope_channel_to_rope_id(
                "boom_hoist", self._session.document
            )
            rope_canon = HoistFormatter.runtime_rope_channel_to_rope_id(
                entity_id, self._session.document
            )
            channel = "boom_hoist" if rope_canon == bh_canon else entity_id
            baseline = point.baseline_rope_tensions.get(channel)
            if baseline is None:
                return None
            sens = float(point.sensitivity_rope_tensions.get(channel, 0.0))
            return float(baseline) + sens * float(hook_load_kN)

        if kind == "connection":
            if not entity_id or not component:
                return None
            widths = getattr(self._session.document, "support_widths", None)
            diameter = widths.slewing_bearing_diameter_m if widths is not None else None
            return extract_connection_component_response(
                point,
                hook_load_kN,
                entity_id,
                component,
                support_widths_diameter_m=diameter,
            )

        return None
