"""AnalysisPresenter: Pure presentation layer for equilibrium checks and load reports.

Generates human-readable reports from analysis results without domain coupling.
All methods are pure functions with no side effects.
"""

from __future__ import annotations

import logging
import math
import re
from typing import TYPE_CHECKING, Any, Optional

from . import drawn_loads
from .drawn_loads import BodyLoads, FreeBodyFilter, LoadConditions

if TYPE_CHECKING:
    from .session_model import SessionModel
    from .analysis_services import AnalysisCalculator, HoistStateService

_LOG = logging.getLogger(__name__)

_TRAILING_MAGNITUDE = re.compile(r"\s*:?\s*[-+]?[\d.]+\s*(kN|kNm)\s*$")


def clean_load_label(label: object) -> str:
    """Strip magnitude baked into overlay labels; numeric columns carry it."""
    return _TRAILING_MAGNITUDE.sub("", str(label or "")).strip()


class AnalysisPresenter:
    """Pure report generation: equilibrium checks, load summaries, drill-downs."""

    EQUILIBRIUM_REFERENCE_NODES = {
        "boom": "boom_heel",
        "rear_leg": "rear_base",
        "front_leg": "front_base",
        "platform": "platform_base",
    }
    EQUILIBRIUM_TOLERANCE = 1e-6
    EQUILIBRIUM_RELATIVE_TOLERANCE = 1e-9

    def __init__(
        self,
        session: SessionModel,
        calculator: AnalysisCalculator,
        hoist_state: HoistStateService,
    ):
        self._session = session
        self._calculator = calculator
        self._hoist_state = hoist_state

    def _body_load_section(self, body_id: str, positions: dict, loads: BodyLoads) -> dict:
        """Per-category load rows for one body, with totals and equilibrium verdict."""
        reference_node = self.EQUILIBRIUM_REFERENCE_NODES[body_id]
        if reference_node not in positions:
            return {
                "name": body_id.replace("_", " ").title(),
                "passed": False,
                "sum_fx": 0.0,
                "sum_fz": 0.0,
                "sum_m": 0.0,
                "categories": [],
                "message": f"reference node {reference_node} unavailable",
            }

        x0 = float(positions[reference_node]["x"])
        z0 = float(positions[reference_node]["z"])

        category_rows: list[dict] = []
        force_scale = 0.0
        moment_scale = 0.0
        for name, vectors in loads.categories:
            rows = []
            for vector in vectors:
                fx, fz = vector.fx_kN, vector.fz_kN
                moment = (vector.world_x - x0) * fz - (vector.world_z - z0) * fx
                rows.append(
                    {
                        "label": clean_load_label(vector.label),
                        "fx": fx,
                        "fz": fz,
                        "magnitude": vector.magnitude_kN,
                        "x": vector.world_x,
                        "z": vector.world_z,
                        "moment": moment,
                    }
                )
                force_scale += vector.magnitude_kN
                moment_scale += abs(moment)
            category_rows.append(
                {
                    "name": name,
                    "rows": rows,
                    "sum_fx": sum(row["fx"] for row in rows),
                    "sum_fz": sum(row["fz"] for row in rows),
                    "sum_m": sum(row["moment"] for row in rows),
                    "count": len(rows),
                }
            )

        moment_rows = []
        for load_moment in loads.moments:
            value = load_moment.moment_kNm
            moment_rows.append(
                {
                    "label": clean_load_label(load_moment.label),
                    "fx": None,
                    "fz": None,
                    "magnitude": None,
                    "x": load_moment.world_x,
                    "z": load_moment.world_z,
                    "moment": value,
                }
            )
            moment_scale += abs(value)
        category_rows.append(
            {
                "name": "Reaction moments",
                "rows": moment_rows,
                "sum_fx": 0.0,
                "sum_fz": 0.0,
                "sum_m": sum(row["moment"] for row in moment_rows),
                "count": len(moment_rows),
            }
        )

        sum_fx = sum(row["sum_fx"] for row in category_rows)
        sum_fz = sum(row["sum_fz"] for row in category_rows)
        sum_m = sum(row["sum_m"] for row in category_rows)
        force_residual = math.hypot(sum_fx, sum_fz)
        moment_residual = abs(sum_m)
        force_tolerance = max(
            self.EQUILIBRIUM_TOLERANCE, self.EQUILIBRIUM_RELATIVE_TOLERANCE * force_scale
        )
        moment_tolerance = max(
            self.EQUILIBRIUM_TOLERANCE, self.EQUILIBRIUM_RELATIVE_TOLERANCE * moment_scale
        )
        passed = force_residual <= force_tolerance and moment_residual <= moment_tolerance

        if passed:
            message = "closed"
        else:
            dominant = max(
                category_rows,
                key=lambda row: math.hypot(row["sum_fx"], row["sum_fz"]) + abs(row["sum_m"]),
            )
            message = (
                f"|F|={force_residual:.3e}, |M|={moment_residual:.3e}, "
                f"largest term: {dominant['name']}"
            )

        return {
            "name": body_id.replace("_", " ").title(),
            "passed": passed,
            "sum_fx": sum_fx,
            "sum_fz": sum_fz,
            "sum_m": sum_m,
            "force_residual": force_residual,
            "moment_residual": moment_residual,
            "force_tolerance": force_tolerance,
            "moment_tolerance": moment_tolerance,
            "categories": category_rows,
            "message": message,
        }

    def build_drawn_load_sections(
        self,
        *,
        document_dict: dict[str, Any],
        analysis_point: Any,
        node_positions: dict[str, dict[str, float]],
        conditions: LoadConditions,
    ) -> dict:
        """Shared payload: equilibrium check and load summary.

        Takes the drawn scene's own node positions and conditions, so the report
        verifies exactly the loads the scene draws rather than a second derivation.
        """
        state = self._session.get_active_hoist_state()
        hoist_id = self._session.selected_hoist_id
        if self._session.document is None or state is None or not hoist_id:
            return {"available": False, "message": "No active analysis is available."}

        if analysis_point is None or not document_dict or not node_positions:
            return {"available": False, "message": "The current state has not been analyzed yet."}

        node_body_by_id = drawn_loads.node_body_map(document_dict)
        sections = [
            self._body_load_section(
                body_id,
                node_positions,
                drawn_loads.build_body_loads(
                    document_dict,
                    hoist=drawn_loads.active_hoist_dict(document_dict, hoist_id),
                    conditions=conditions,
                    node_positions=node_positions,
                    analysis_point=analysis_point,
                    body_filter=FreeBodyFilter(body_id, node_body_by_id),
                ),
            )
            for body_id in self.EQUILIBRIUM_REFERENCE_NODES
        ]
        return {
            "available": True,
            "passed": all(section["passed"] for section in sections),
            "tolerance": self.EQUILIBRIUM_TOLERANCE,
            # Y-axis wind acts out of the X/Z plane, so it cannot appear in these sums.
            "wind_out_of_plane": str(conditions.wind_direction or "+X") in {"+Y", "-Y"}
            and abs(float(conditions.wind_speed_m_s)) > 1e-12,
            "state": {
                "hoist_id": hoist_id,
                "boom_angle_deg": float(conditions.boom_angle_deg),
                "hook_load_kN": float(conditions.hook_load_kN),
            },
            "sections": sections,
        }

    def _overview_point_demand(
        self,
        row_meta: dict,
        hoist_id: str,
        hook_load_kN: float,
        *,
        wind_speed_m_s: float,
        wind_direction: str,
        accel_x_m_s2: float,
        accel_y_m_s2: float,
        accel_z_m_s2: float,
        pitch_accel_rad_s2: float,
        roll_accel_rad_s2: float,
        offlead_deg: float,
        sidelead_deg: float,
        boom_angle_deg: float,
        tackle_length_m: float,
        hoist_runtime_overrides: Optional[dict[str, dict[str, Any]]] = None,
    ) -> Optional[float]:
        """Compute demand for a result row at specific environmental conditions."""
        from ..calculation.engine import CraneCalculator

        doc = self._session.document
        if doc is None:
            return None
        calc = CraneCalculator(doc)
        point = calc.compute_analysis_point(
            boom_angle_deg,
            0.0,
            hoist_id,
            wind_speed_m_s=wind_speed_m_s,
            wind_direction=wind_direction,
            accel_x_m_s2=accel_x_m_s2,
            accel_y_m_s2=accel_y_m_s2,
            accel_z_m_s2=accel_z_m_s2,
            pitch_accel_rad_s2=pitch_accel_rad_s2,
            roll_accel_rad_s2=roll_accel_rad_s2,
            offlead_deg=offlead_deg,
            sidelead_deg=sidelead_deg,
            hoist_runtime_overrides=hoist_runtime_overrides,
            tackle_length_m=tackle_length_m,
        )
        if point is None:
            return None
        return self._calculator.resolve_row_demand(point, hook_load_kN, row_meta)

    def build_load_contribution_overview(self, row_meta: dict) -> Optional[dict]:
        """Decompose result row demand into cumulative load-case contributions."""
        doc = self._session.document
        hoist_id = self._session.selected_hoist_id
        state = self._session.get_active_hoist_state()
        if doc is None or hoist_id is None or state is None:
            return None

        sc = state.scene_state
        hook = float(sc.hook_load_kN)
        overrides = self._hoist_state.active_hoist_runtime_overrides()

        def _demand(**kwargs: Any) -> Optional[float]:
            return self._overview_point_demand(
                row_meta,
                hoist_id,
                boom_angle_deg=float(sc.boom_angle_deg),
                tackle_length_m=float(sc.tackle_length_m),
                hoist_runtime_overrides=overrides,
                **kwargs,
            )

        zero_env = dict(
            wind_speed_m_s=0.0,
            wind_direction=sc.wind_direction,
            accel_x_m_s2=0.0,
            accel_y_m_s2=0.0,
            accel_z_m_s2=0.0,
            pitch_accel_rad_s2=0.0,
            roll_accel_rad_s2=0.0,
            offlead_deg=0.0,
            sidelead_deg=0.0,
        )
        wind_env = dict(
            zero_env, wind_speed_m_s=float(sc.wind_speed_m_s), wind_direction=str(sc.wind_direction)
        )
        inertia_env = dict(
            wind_env,
            accel_x_m_s2=float(sc.accel_x_m_s2),
            accel_y_m_s2=float(sc.accel_y_m_s2),
            accel_z_m_s2=float(sc.accel_z_m_s2),
            pitch_accel_rad_s2=float(sc.pitch_accel_rad_s2),
            roll_accel_rad_s2=float(sc.roll_accel_rad_s2),
        )
        offlead_env = dict(inertia_env, offlead_deg=float(sc.offlead_deg))
        full_env = dict(offlead_env, sidelead_deg=float(sc.sidelead_deg))

        dead = _demand(hook_load_kN=0.0, **zero_env)
        with_hook = _demand(hook_load_kN=hook, **zero_env)
        with_wind = _demand(hook_load_kN=hook, **wind_env)
        with_inertia = _demand(hook_load_kN=hook, **inertia_env)
        with_offlead = _demand(hook_load_kN=hook, **offlead_env)
        full = _demand(hook_load_kN=hook, **full_env)
        if (
            dead is None
            or with_hook is None
            or with_wind is None
            or with_inertia is None
            or with_offlead is None
            or full is None
        ):
            return None

        terms: list[dict[str, Any]] = [
            {"name": "Dead load baseline", "value_kN": float(dead)},
            {"name": "Hook load", "value_kN": float(with_hook - dead)},
            {"name": "Wind", "value_kN": float(with_wind - with_hook)},
            {"name": "Inertia", "value_kN": float(with_inertia - with_wind)},
            {"name": "Offlead", "value_kN": float(with_offlead - with_inertia)},
            {"name": "Sidelead", "value_kN": float(full - with_offlead)},
        ]
        reconstructed = float(sum(float(t["value_kN"]) for t in terms))
        demand_kN_raw = row_meta.get("demand_kN")
        demand_kN = float(demand_kN_raw) if demand_kN_raw is not None else full
        return {
            "title": "Load Contribution Overview",
            "section": str(row_meta.get("kind") or "").title(),
            "row_name": str(row_meta.get("row_name") or ""),
            "unit": str(row_meta.get("unit") or "kN"),
            "demand_kN": demand_kN,
            "limit_kN": row_meta.get("limit_kN"),
            "utilization_pct": row_meta.get("utilization_pct"),
            "terms": terms,
            "reconstructed_kN": reconstructed,
            "delta_kN": reconstructed - demand_kN,
        }
