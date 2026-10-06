"""Golden regression: a level vessel must reproduce today's statics exactly.

The goldens were captured before vessel heel/trim/slew existed. With heel and
trim at zero every analysis point, capacity sweep and rope auto-set result
must match them to rounding. Regenerate only for a deliberate model change:

    CRANE_STATICS_REGEN_GOLDENS=1 pytest tests/test_level_attitude_goldens.py
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
from pathlib import Path
from typing import Any

import pytest

from crane_statics.calculation.engine import CraneCalculator
from crane_statics.core.analysis_cases import analysis_mode_by_name
from crane_statics.core.io import load_document
from crane_statics.core.limit_auto_set import compute_required_rope_capacity_kN
from crane_statics.core.limit_factory import DesignLimitFactory
from crane_statics.core.sweep import run_capacity_sweep

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"
GOLDEN = Path(__file__).parent / "goldens" / "level_attitude_22689.json"


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _snapshot() -> dict[str, Any]:
    doc = load_document(EXAMPLE)
    calc = CraneCalculator(doc)
    wind = float(doc.environment.max_wind_speed_m_s)

    points: dict[str, Any] = {}
    for hoist_id in ("MH", "WH", "SH"):
        hoist = next(h for h in doc.hoists if h.id == hoist_id)
        for angle in (30.0, 50.0, 70.0):
            for direction in ("+X", "+Y"):
                point = calc.compute_analysis_point(
                    angle,
                    0.0,
                    hoist_id,
                    wind_speed_m_s=wind,
                    wind_direction=direction,
                    accel_x_m_s2=0.5,
                    accel_y_m_s2=0.3,
                    accel_z_m_s2=0.4,
                    pitch_accel_rad_s2=0.01,
                    roll_accel_rad_s2=0.02,
                    offlead_deg=float(hoist.offlead_deg),
                    sidelead_deg=float(hoist.sidelead_deg),
                    tackle_length_m=40.0,
                )
                assert point is not None
                points[f"{hoist_id}@{angle:g}{direction}"] = dataclasses.asdict(point)

    mh = next(h for h in doc.hoists if h.id == "MH")
    split = calc.compute_analysis_point(
        45.0,
        0.0,
        "MH",
        wind_speed_m_s=wind,
        wind_direction="+X",
        hoist_runtime_overrides=analysis_mode_by_name(mh, "split").runtime_overrides,
    )
    assert split is not None
    points["MH@45split"] = dataclasses.asdict(split)

    limits = {
        dl.id: {dl.component: dl.max_kN}
        for dl in DesignLimitFactory.create_for_document(doc)
        if dl.enabled and dl.max_kN is not None
    }
    # Connection limits that bind somewhere along the curve, so the radial,
    # resultant and magnitude inversions are all exercised.
    limits.update(
        {
            "heel_point_resultant": {"resultant": 30000.0},
            "heel_left_resultant": {"resultant": 16000.0},
            "rear_hinge_Fz": {"Fz": 60000.0},
            "platform_base_mradial": {"mradial": 1.0e6},
            "platform_base_fradial": {"fradial": 2000.0},
            "platform_base_max_bearing_line_load": {"max_bearing_line_load": 2500.0},
        }
    )
    sweep = run_capacity_sweep(doc, "MH", limits, 10.0, {})
    modes = {
        name: {
            "curve_data": mode["curve_data"],
            "limit_series": mode["limit_series"],
            "contractual_results": [
                (float(cp.outreach_m), allowable, passes)
                for cp, allowable, passes in mode["contractual_results"]
            ],
        }
        for name, mode in sweep["modes"].items()
    }

    auto_set = {
        rope.id: dataclasses.asdict(compute_required_rope_capacity_kN(doc, rope.id))
        for rope in doc.ropes
    }
    snapshot: dict[str, Any] = _jsonable(
        {"points": points, "sweep": modes, "auto_set": auto_set, "limits": limits}
    )
    return snapshot


def _assert_close(actual: Any, expected: Any, path: str = "$") -> None:
    if isinstance(expected, dict):
        assert isinstance(actual, dict), path
        assert set(actual) == set(expected), f"{path}: keys {set(actual) ^ set(expected)}"
        for key in expected:
            _assert_close(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), path
        for index, (a, e) in enumerate(zip(actual, expected)):
            _assert_close(a, e, f"{path}[{index}]")
    elif isinstance(expected, float) and not isinstance(expected, bool):
        assert isinstance(actual, (int, float)), path
        if math.isinf(expected):
            assert actual == expected, path
        else:
            assert actual == pytest.approx(expected, rel=1e-12, abs=1e-9), path
    else:
        assert actual == expected, path


def test_level_vessel_reproduces_the_captured_statics():
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    snapshot = _snapshot()
    if os.environ.get("CRANE_STATICS_REGEN_GOLDENS") == "1":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(snapshot, indent=1, sort_keys=True), encoding="utf-8")
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    _assert_close(snapshot, expected)
