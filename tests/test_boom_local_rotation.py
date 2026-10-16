"""Boom-local masses and wind areas follow the real boom angle.

The solver used to infer the boom angle from the first node in a hard-coded list,
assuming that node sat at the 22689 crane's local coordinates. Every example-based
test used 22689, where the guess happens to be right, so the error stayed hidden on
the other cranes. These tests run the free-body closure on every example.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from crane_statics.calculation import CraneCalculator
from crane_statics.core import drawn_loads as dl
from crane_statics.core import load_document
from crane_statics.data import normalize_document
from tests.test_acceptance import scene_inputs_at_drawn_tackle

EXAMPLES = Path(__file__).parent.parent / "examples"
EXAMPLE_NAMES = ["crane_input_22689", "crane_input_13778_retracted", "crane_input_GT283"]
FREE_BODY_REFERENCE_NODES = {
    "platform": "platform_base",
    "boom": "boom_heel",
    "rear_leg": "rear_base",
    "front_leg": "front_base",
}
# The boom heel and both leg hinges are pins: they carry no moment. drawn_loads reports a
# "synthetic" support moment equal to the body's residual whenever the solver gives none,
# so counting reaction moments would close these bodies by construction. Only the platform
# base carries a real moment from the solver.
PINNED_BODIES = {"boom", "rear_leg", "front_leg"}


def _assert_free_bodies_close(inputs) -> None:
    positions = inputs.node_positions()
    for body, ref_node in FREE_BODY_REFERENCE_NODES.items():
        loads = inputs.body_loads(positions, body)
        vectors = loads.vectors()
        assert vectors, body
        scale = max(1.0, sum(abs(v.fx_kN) + abs(v.fz_kN) for v in vectors))
        sum_fx = sum(v.fx_kN for v in vectors)
        sum_fz = sum(v.fz_kN for v in vectors)
        x0 = float(positions[ref_node]["x"])
        z0 = float(positions[ref_node]["z"])
        moments = () if body in PINNED_BODIES else loads.moments
        sum_m = dl.sum_moment_about(vectors, moments, x0, z0)
        lever = max(1.0, max(abs(v.world_x - x0) + abs(v.world_z - z0) for v in vectors))
        assert abs(sum_fx) <= 1e-9 * scale, (body, sum_fx)
        assert abs(sum_fz) <= 1e-9 * scale, (body, sum_fz)
        assert abs(sum_m) <= 1e-9 * scale * lever, (body, sum_m)


@pytest.mark.parametrize("angle", [30.0, 45.0, 60.0])
@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_every_free_body_closes_on_every_example(name: str, angle: float) -> None:
    doc = load_document(EXAMPLES / f"{name}.yaml")
    inputs = scene_inputs_at_drawn_tackle(doc, doc.hoists[0].id, angle=angle, wind_speed_m_s=0.0)
    assert inputs.analysis_point is not None
    _assert_free_bodies_close(inputs)


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_every_free_body_closes_with_wind_on_every_example(name: str) -> None:
    doc = load_document(EXAMPLES / f"{name}.yaml")
    wind = float(doc.environment.max_wind_speed_m_s)
    inputs = scene_inputs_at_drawn_tackle(
        doc, doc.hoists[0].id, angle=45.0, wind_speed_m_s=wind, wind_direction="+X"
    )
    assert inputs.analysis_point is not None
    _assert_free_bodies_close(inputs)


def test_renaming_a_sheave_does_not_change_the_statics() -> None:
    text = (EXAMPLES / "crane_input_GT283.yaml").read_text(encoding="utf-8")
    sheave = "- {node: boom_sheave_3, body: boom, u_m: 103.9, w_m: 1.6, parts: 2}"
    assert text.count(sheave) == 1
    renamed = text.replace(sheave, sheave.replace("boom_sheave_3", "sheave_three"))

    def solve(source: str):
        doc = normalize_document(yaml.safe_load(source))
        point = CraneCalculator(doc).compute_analysis_point(45.0, 0.0, "MH", wind_speed_m_s=0.0)
        assert point is not None
        return point.baseline_rope_tensions["boom_hoist"], point.baseline_reactions["heel_point"]

    pull, heel = solve(text)
    renamed_pull, renamed_heel = solve(renamed)
    assert renamed_pull == pytest.approx(pull, rel=1e-12)
    assert renamed_heel["Fx"] == pytest.approx(heel["Fx"], rel=1e-12)
    assert renamed_heel["Fz"] == pytest.approx(heel["Fz"], rel=1e-12)
