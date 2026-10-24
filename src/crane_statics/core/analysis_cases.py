"""Shared normal/split analysis-case construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Optional

from ..calculation.engine import candidate_wind_directions


@dataclass(frozen=True)
class HoistAnalysisMode:
    """Effective hook configuration and contractual points for one mode."""

    name: str
    hook_mass_t: float
    runtime_overrides: dict[str, dict[str, float | int | str]]
    contractual_points: list[Any]


@dataclass(frozen=True)
class DirectionalAnalysisCase:
    """One wind and lead-sign configuration for a primitive response."""

    wind_direction: str
    offlead_deg: Optional[float]
    sidelead_deg: Optional[float]


def _signed_candidates(value: float) -> tuple[float, ...]:
    magnitude = abs(float(value))
    if magnitude <= 1e-9:
        return (0.0,)
    return (-magnitude, magnitude)


def iter_wind_lead_directional_cases(
    hoist: Any,
    wind_speed_m_s: float,
) -> Iterator[DirectionalAnalysisCase]:
    """Yield all wind and signed-lead combinations for Auto-Set worst-case evaluation."""
    offlead_values = _signed_candidates(getattr(hoist, "offlead_deg", 0.0))
    sidelead_values = _signed_candidates(getattr(hoist, "sidelead_deg", 0.0))
    for offlead_deg in offlead_values:
        for sidelead_deg in sidelead_values:
            for wind_direction in candidate_wind_directions(wind_speed_m_s):
                yield DirectionalAnalysisCase(wind_direction, offlead_deg, sidelead_deg)


def _split_mode_overrides(hoist: Any) -> dict[str, dict[str, float | int | str]]:
    split_hook_mass_t = float(getattr(hoist, "split_hook_mass_t", hoist.hook_mass_t))
    normal_hook_mass_t = float(hoist.hook_mass_t)
    payload: dict[str, float | int | str] = {
        "hook_mass_t": split_hook_mass_t,
        "support_comp_mass_t": max(0.0, normal_hook_mass_t - split_hook_mass_t),
    }
    split_falls = getattr(hoist, "split_falls", None)
    if split_falls is not None:
        payload["falls"] = int(split_falls)
    support_node_id = getattr(hoist, "support_node_id", None)
    if support_node_id:
        payload["support_node_id"] = str(support_node_id)
    return {str(hoist.id): payload}


def _contractual_points(hoist: Any, mode_name: str) -> list[Any]:
    if mode_name == "split":
        split_points = getattr(hoist, "split_contractual_points", None)
        if isinstance(split_points, list):
            return split_points
        return []
    return list(hoist.contractual_points)


def iter_hoist_analysis_modes(hoist: Any) -> tuple[HoistAnalysisMode, ...]:
    """Return the valid normal and optional split modes for a hoist."""
    modes = [
        HoistAnalysisMode(
            name="normal",
            hook_mass_t=float(hoist.hook_mass_t),
            runtime_overrides={},
            contractual_points=_contractual_points(hoist, "normal"),
        )
    ]
    if bool(getattr(hoist, "splitable_block", False)):
        split_hook_mass = getattr(hoist, "split_hook_mass_t", None)
        split_falls = getattr(hoist, "split_falls", None)
        if split_hook_mass is not None and split_falls is not None:
            modes.append(
                HoistAnalysisMode(
                    name="split",
                    hook_mass_t=float(split_hook_mass),
                    runtime_overrides=_split_mode_overrides(hoist),
                    contractual_points=_contractual_points(hoist, "split"),
                )
            )
    return tuple(modes)


def analysis_mode_by_name(hoist: Any, mode_name: str) -> HoistAnalysisMode:
    """Return one effective mode, falling back to normal when unavailable."""
    for mode in iter_hoist_analysis_modes(hoist):
        if mode.name == mode_name:
            return mode
    return iter_hoist_analysis_modes(hoist)[0]
