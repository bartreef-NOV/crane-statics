"""Vertical hook stiffness by virtual work: C = 1 / sum(t^2 * L / EA)."""

import math
from pathlib import Path

import pytest

from crane_statics.calculation.engine import get_calculator
from crane_statics.core.io import load_document
from crane_statics.rules import RulesValidationError
from crane_statics.rules.stiffness import (
    StiffnessTerm,
    hook_stiffness_kN_per_m,
    payload_hoist_stiffness_terms,
    worst_case_tackle_length_m,
)
from tests.rules_reference import hook_stiffness

GT283 = Path(__file__).parent.parent / "examples" / "crane_input_GT283.yaml"
ANGLE_DEG = 45.0
EA_MH_KN = 90000.0
EA_BH_KN = 150000.0


def _gt283(ea=True):
    doc = load_document(GT283)
    if not ea:
        return doc
    ea_by_rope = {"MH__rope": EA_MH_KN, "BH__rope": EA_BH_KN}
    ropes = [
        r.model_copy(update={"ea_kN": ea_by_rope[r.id]}) if r.id in ea_by_rope else r
        for r in doc.ropes
    ]
    return doc.model_copy(update={"ropes": ropes})


def _point(doc):
    # Pure vertical hook load: no offlead, so the boom-hoist sensitivity is vertical only.
    point = get_calculator(doc).compute_analysis_point(ANGLE_DEG, 0.0, "MH", offlead_deg=0.0)
    assert point is not None
    return point


# --- Hand geometry of GT283 at 45 deg, written from the YAML, not from the app ---------------
_C, _S = math.cos(math.radians(ANGLE_DEG)), math.sin(math.radians(ANGLE_DEG))
_HEEL = (2.5, 6.742)


def _boom(u, w):
    return (_HEEL[0] + u * _C - w * _S, _HEEL[1] + u * _S + w * _C)


def _dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


_MH_WINCH, _MH_AFRAME = (1.81, 3.99), (-6.235, 38.612)
_MH_S3, _MH_S4 = _boom(103.9, 1.6), _boom(109.0, -4.25)
_BH_WINCH, _BH_AFRAME, _BH_S3 = (-1.81, 3.99), (-9.385, 40.222), _boom(106.0, 3.75)
_MH_FALLS = 20


def _hand_mh_length(hook_drop_m):
    """Every part of the MH rope: winch run x2, A-frame to boom x2, tip sheaves x2, falls x20."""
    return (
        2 * _dist(_MH_WINCH, _MH_AFRAME)
        + 2 * _dist(_MH_AFRAME, _MH_S3)
        + 2 * _dist(_MH_S3, _MH_S4)
        + _MH_FALLS * hook_drop_m
    )


def _hand_bh_length():
    return 2 * _dist(_BH_WINCH, _BH_AFRAME) + 28 * _dist(_BH_AFRAME, _BH_S3)


def _hand_bh_tension_per_hook_kN():
    """Boom moment about the heel per kN of vertical hook load.

    External loads on the boom: 1 kN down at the hook (directly below sheave 4), the two MH
    parts leaving sheave 3 for the A-frame at 1/20 kN each, and 28 boom-hoist parts at t.
    """

    def moment(p, f):
        return (p[0] - _HEEL[0]) * f[1] - (p[1] - _HEEL[1]) * f[0]

    def toward(a, b, scale):
        d = _dist(a, b)
        return ((b[0] - a[0]) / d * scale, (b[1] - a[1]) / d * scale)

    m_load = moment(_MH_S4, (0.0, -1.0)) + moment(_MH_S3, toward(_MH_S3, _MH_AFRAME, 2 / 20))
    m_bh_per_t = moment(_BH_S3, toward(_BH_S3, _BH_AFRAME, 28.0))
    return -m_load / m_bh_per_t


# --- Pure formula -----------------------------------------------------------------------------


def test_single_term():
    assert hook_stiffness_kN_per_m([StiffnessTerm(0.5, 100.0, 100000.0)]) == pytest.approx(4000.0)


def test_two_terms_in_series():
    terms = [StiffnessTerm(0.5, 100.0, 100000.0), StiffnessTerm(0.5, 50.0, 200000.0)]
    assert hook_stiffness_kN_per_m(terms) == pytest.approx(3200.0)


def test_agrees_with_reference():
    terms = [StiffnessTerm(0.05, 812.3, 90000.0), StiffnessTerm(0.078, 2310.0, 150000.0)]
    expected = hook_stiffness([(t.tension_per_hook_kN, t.reeved_length_m, t.ea_kN) for t in terms])
    assert hook_stiffness_kN_per_m(terms) == pytest.approx(expected, rel=1e-12)


def test_no_terms_rejected():
    with pytest.raises(RulesValidationError):
        hook_stiffness_kN_per_m([])


def test_worst_case_tackle_length_is_hook_at_sheave():
    assert worst_case_tackle_length_m() == 0.0


# --- GT283 ------------------------------------------------------------------------------------


def test_gt283_terms_match_hand_calculation():
    doc = _gt283()
    point = _point(doc)
    terms = payload_hoist_stiffness_terms(doc, point, "MH", worst_case_tackle_length_m())
    assert len(terms) == 2
    active, boom = terms

    assert active.tension_per_hook_kN == pytest.approx(1.0 / _MH_FALLS, rel=1e-12)
    assert active.reeved_length_m == pytest.approx(_hand_mh_length(0.0), rel=1e-9)
    assert active.ea_kN == EA_MH_KN

    assert boom.tension_per_hook_kN == pytest.approx(_hand_bh_tension_per_hook_kN(), rel=1e-9)
    assert boom.reeved_length_m == pytest.approx(_hand_bh_length(), rel=1e-9)
    assert boom.ea_kN == EA_BH_KN

    expected = hook_stiffness(
        [
            (1.0 / _MH_FALLS, _hand_mh_length(0.0), EA_MH_KN),
            (_hand_bh_tension_per_hook_kN(), _hand_bh_length(), EA_BH_KN),
        ]
    )
    assert hook_stiffness_kN_per_m(terms) == pytest.approx(expected, rel=1e-9)


def test_gt283_tackle_length_pays_out_falls():
    doc = _gt283()
    point = _point(doc)
    active = payload_hoist_stiffness_terms(doc, point, "MH", 30.0)[0]
    assert active.reeved_length_m == pytest.approx(_hand_mh_length(30.0), rel=1e-9)


def test_gt283_hook_at_sheave_stiffer_than_at_lowest_hook_height():
    doc = _gt283()
    point = _point(doc)
    at_sheave = hook_stiffness_kN_per_m(
        payload_hoist_stiffness_terms(doc, point, "MH", worst_case_tackle_length_m())
    )
    lowest_drop_m = _MH_S4[1] - (-53.0)
    at_lowest = payload_hoist_stiffness_terms(doc, point, "MH", lowest_drop_m)
    assert at_lowest[0].reeved_length_m == pytest.approx(_hand_mh_length(lowest_drop_m), rel=1e-9)
    assert at_sheave > hook_stiffness_kN_per_m(at_lowest)


def test_missing_active_ea_raises():
    doc = _gt283(ea=False)
    with pytest.raises(RulesValidationError, match="MH"):
        payload_hoist_stiffness_terms(doc, _point(doc), "MH", 0.0)


def test_missing_boom_hoist_ea_raises():
    doc = _gt283()
    ropes = [r.model_copy(update={"ea_kN": None}) if r.id == "BH__rope" else r for r in doc.ropes]
    doc = doc.model_copy(update={"ropes": ropes})
    with pytest.raises(RulesValidationError, match="BH"):
        payload_hoist_stiffness_terms(doc, _point(doc), "MH", 0.0)
