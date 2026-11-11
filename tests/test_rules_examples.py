"""The four rules examples under ``examples/`` load and chart every condition."""

from __future__ import annotations

from pathlib import Path

import pytest

from crane_statics.core import load_document
from crane_statics.core.load_condition import condition_names
from crane_statics.core.sweep import run_mode_sweep

EXAMPLES = Path(__file__).parent.parent / "examples"

CASES = [
    ("crane_input_GT283_abs.yaml", "ABS", "offshore"),
    ("crane_input_GT283_dnv.yaml", "DNV", None),
    ("crane_input_22689_abs.yaml", "ABS", "offshore"),
    ("crane_input_13778_retracted_dnv.yaml", "DNV", None),
]
NEW = {"crane_input_22689_abs.yaml", "crane_input_13778_retracted_dnv.yaml"}
PAYLOAD_HOIST = "MH"


@pytest.mark.parametrize("name, standard, crane_class", CASES, ids=[c[0] for c in CASES])
def test_example_loads_with_rules(name: str, standard: str, crane_class: object) -> None:
    doc = load_document(EXAMPLES / name)
    assert doc.rules is not None
    assert doc.rules.standard == standard
    assert doc.rules.crane_class == crane_class
    if name in NEW:
        assert condition_names(doc) == ("onboard_sea", "offboard_supply")


@pytest.mark.parametrize("name, standard, crane_class", CASES, ids=[c[0] for c in CASES])
def test_example_sweeps_every_condition(name: str, standard: str, crane_class: object) -> None:
    doc = load_document(EXAMPLES / name)
    hoist = next(h for h in doc.hoists if h.id == PAYLOAD_HOIST)
    for condition in condition_names(doc):
        payload = run_mode_sweep(
            doc,
            hoist.id,
            "normal",
            {f"{hoist.rope_id}_T": {"T": 1.0e4}},
            5.0,
            {},
            condition_name=condition,
        )
        assert payload is not None and payload["curve_data"], condition
