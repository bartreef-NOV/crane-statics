"""Tests for the Excel validation workbook tooling."""

import copy
import dataclasses
import json
import math
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.formula import ArrayFormula

from crane_statics.calculation.engine import split_wind_speed_components
from crane_statics.calculation.rope_mass import (
    active_hook_positions,
    falls_override_effective_mult,
    rope_mass_at_nodes,
)
from crane_statics.calculation.solver import crane_solver
from crane_statics.calculation.solver.kinematics import KinematicsAdapter
from crane_statics.calculation.vessel_frame import VesselInputs, crane_frame_motion
from crane_statics.core import drawn_loads
from crane_statics.core.io import load_document
from scripts.excel_workbook import layout
from scripts.excel_workbook.build import build_workbook
from scripts.excel_workbook.recalc import recalculate
from scripts.excel_workbook.reference import (
    CASES,
    GOLDEN_PATH,
    YAML_PATH,
    SceneCase,
    _scene_inputs,
    _solve,
    app_results,
    expanded_model,
    scene_reaction_arrows,
)

CASE_NAMES = {"base", "inplane_wind_accel", "outofplane_wind_roll_sidelead", "idle_hoist"}


def _num(value: float | str | None) -> float:
    assert isinstance(value, float), value
    return value


def test_recalculate_supports_minverse_mmult(tmp_path: Path) -> None:
    matrix = [[4.0, -2.0, 1.0], [3.0, 6.0, -4.0], [2.0, 1.0, 8.0]]
    vector = [12.0, -25.0, 32.0]
    wb = Workbook()
    ws = wb.active
    ws.title = "Solve"
    for r, row in enumerate(matrix, start=1):
        for c, value in enumerate(row, start=1):
            ws.cell(row=r, column=c, value=value)
        ws.cell(row=r, column=5, value=vector[r - 1])
    ws["G1"] = ArrayFormula("G1:G3", "=MMULT(MINVERSE(A1:C3),E1:E3)")
    path = tmp_path / "solve.xlsx"
    wb.save(path)

    values = recalculate(path)["Solve"]

    expected = np.linalg.solve(np.array(matrix), np.array(vector))
    got = [values["G1"], values["G2"], values["G3"]]
    assert np.allclose(got, expected, rtol=0, atol=1e-9)


def test_recalculate_reads_sumproduct_if_index_match(tmp_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Fn"
    for i, (key, val) in enumerate([(1, 10.0), (2, 20.0), (3, 30.0)], start=1):
        ws.cell(row=i, column=1, value=key)
        ws.cell(row=i, column=2, value=val)
    ws["D1"] = "=SUMPRODUCT(A1:A3,B1:B3)"
    ws["D2"] = '=IF(B1>5,"big","small")'
    ws["D3"] = "=INDEX(B1:B3,MATCH(2,A1:A3,0))"
    ws["D4"] = "=ABS(-3.5)"
    ws["D5"] = "=SQRT(16)"
    ws["D6"] = "=SIN(0.5)"
    ws["D7"] = "=COS(0.5)"
    ws["D8"] = "=ATAN2(1,2)"
    path = tmp_path / "fn.xlsx"
    wb.save(path)

    values = recalculate(path)["Fn"]

    assert values["D1"] == 140.0
    assert values["D2"] == "big"
    assert values["D3"] == 20.0
    assert values["D4"] == 3.5
    assert values["D5"] == 4.0
    assert math.isclose(_num(values["D6"]), math.sin(0.5), abs_tol=1e-12)
    assert math.isclose(_num(values["D7"]), math.cos(0.5), abs_tol=1e-12)
    # Excel ATAN2(x, y) takes x first.
    assert math.isclose(_num(values["D8"]), math.atan2(2, 1), abs_tol=1e-12)


def test_recalculate_extra_functions(tmp_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Extra"
    for i, (k, v) in enumerate([("a", 1.0), ("b", 2.0), ("a", 4.0)], start=1):
        ws.cell(row=i, column=1, value=k)
        ws.cell(row=i, column=2, value=v)
    formulas = {
        "D1": ("=RADIANS(180)", math.pi),
        "D2": ("=DEGREES(PI())", 180.0),
        "D3": ("=ACOS(0.5)", math.acos(0.5)),
        "D4": ("=ATAN(1)", math.atan(1)),
        "D5": ("=MAX(B1:B3)", 4.0),
        "D6": ("=MIN(B1:B3)", 1.0),
        "D7": ("=SUM(B1:B3)", 7.0),
        "D8": ('=SUMIF(A1:A3,"a",B1:B3)', 5.0),
        "D9": ('=SUMIFS(B1:B3,A1:A3,"a",B1:B3,">1")', 4.0),
        "D10": ("=SQRT(3^2+4^2)", 5.0),
    }
    for cell, (formula, _) in formulas.items():
        ws[cell] = formula
    path = tmp_path / "extra.xlsx"
    wb.save(path)

    values = recalculate(path)["Extra"]

    for cell, (_, expected) in formulas.items():
        assert math.isclose(_num(values[cell]), expected, abs_tol=1e-12), cell


def _golden() -> dict[str, Any]:
    golden: dict[str, Any] = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    return golden


def test_golden_cases_match_live_app() -> None:
    golden = _golden()
    assert set(golden["cases"]) == CASE_NAMES
    assert set(CASES) == CASE_NAMES
    for name, entry in golden["cases"].items():
        assert entry["inputs"] == dataclasses.asdict(CASES[name]), name
        live = app_results(YAML_PATH, CASES[name])
        stored = entry["app_results"]
        assert set(stored) == set(live), name
        for key, value in stored.items():
            assert math.isclose(value, live[key], rel_tol=0.0, abs_tol=1e-9), (name, key)


@pytest.mark.parametrize("name", sorted(CASE_NAMES))
def test_reaction_arrows_match_result_rows(name: str) -> None:
    results = app_results(YAML_PATH, CASES[name])
    arrows = scene_reaction_arrows(YAML_PATH, CASES[name])
    assert set(arrows) == {
        "heel_point",
        "rear_hinge",
        "front_hinge",
        "upper_hinge",
        "platform_base",
    }
    for entity, comps in arrows.items():
        for comp, value in comps.items():
            assert math.isclose(
                value, results[f"reaction.{entity}.{comp}"], rel_tol=0.0, abs_tol=1e-9
            ), (name, entity, comp)


def test_cases_exercise_their_feature() -> None:
    base, wind, oop, idle = (
        CASES[k]
        for k in ("base", "inplane_wind_accel", "outofplane_wind_roll_sidelead", "idle_hoist")
    )
    assert base.hook_load_kN > 0 and base.wind_speed_m_s == 0 and base.accel_x_m_s2 == 0
    assert wind.wind_direction in {"+X", "-X"} and wind.wind_speed_m_s > 0
    assert wind.accel_x_m_s2 != 0 and wind.accel_z_m_s2 != 0 and wind.pitch_accel_rad_s2 != 0
    assert oop.wind_direction in {"+Y", "-Y"} and oop.wind_speed_m_s > 0
    assert oop.vessel_roll_deg != 0 and oop.sidelead_deg != 0 and oop.roll_accel_rad_s2 != 0
    assert idle.hoist_id != base.hoist_id
    assert idle.vessel_roll_deg == 0 and idle.vessel_pitch_deg == 0
    oop_results = app_results(YAML_PATH, oop)
    assert abs(oop_results["reaction.platform_base.fy"]) > 1.0
    assert abs(oop_results["reaction.platform_base.mx"]) > 1.0
    # The base case's hook-loaded hoist is idle in the idle-hoist case: its rope
    # carries only its hook block, m_hook * (g + az) / falls (no vessel tilt here).
    idle_results = app_results(YAML_PATH, idle)
    model = expanded_model(YAML_PATH)
    mh = next(h for h in model["hoists"] if h["id"] == base.hoist_id)
    g = abs(model["environment"]["gravity_m_s2"])
    expected = mh["hook_mass_t"] * (g + idle.accel_z_m_s2) / mh["falls"]
    assert math.isclose(idle_results[f"tension.{base.hoist_id}"], expected, abs_tol=1e-9)


def test_expanded_model_is_json_serialisable() -> None:
    model = expanded_model(YAML_PATH)
    json.dumps(model)
    for key in ("environment", "structure", "bodies", "nodes", "ropes", "hoists"):
        assert key in model


# -- workbook: inputs and checks ----------------------------------------------------

LAYOUT = layout.DEFAULT_LAYOUT

#: expanded_model keys deliberately not typed on Inputs (derived in later sheets, or
#: kept once on the hoist row -- the app reads the hoist's linear mass).
DERIVED_HOIST_KEYS = {"is_payload", "parts_at_hook", "spool_node_id"}
OMITTED_ROPE_KEYS = {"tension_mode", "linear_mass_kg_m", "segments"}


def _model() -> dict[str, Any]:
    return copy.deepcopy(expanded_model(YAML_PATH))


def _build(tmp_path: Path, model: dict[str, Any] | None = None, case: str = "base") -> Path:
    path = tmp_path / f"wb_{case}.xlsx"
    build_workbook(_model() if model is None else model, CASES[case], path)
    return path


class _Book:
    """Read cells by sheet-qualified address; formula cells are recalculated."""

    def __init__(self, path: Path) -> None:
        self.wb = load_workbook(path)
        self.values = recalculate(path)

    def __call__(self, address: str) -> Any:
        sheet, coord = address.replace("$", "").split("!")
        raw = self.wb[sheet][coord].value
        if isinstance(raw, str) and raw.startswith("="):
            return self.values[sheet][coord]
        return raw


def _expected_rows(model: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        "mass_points": [
            {"body": b["id"], **mp} for b in model["bodies"] for mp in b["mass_points"]
        ],
        "wind_areas": [{"body": b["id"], **wa} for b in model["bodies"] for wa in b["wind_areas"]],
        "nodes": model["nodes"],
        "segments": [{"rope_id": r["id"], **s} for r in model["ropes"] for s in r["segments"]],
        "ropes": [{"id": r["id"], "role": r["tension_mode"]} for r in model["ropes"]],
        "hoists": model["hoists"],
    }


def _same(got: Any, expected: Any) -> bool:
    if expected is None:
        return got is None
    if isinstance(expected, bool):
        return bool(got == (1 if expected else 0))
    if isinstance(expected, (int, float)):
        return isinstance(got, (int, float)) and math.isclose(got, expected, abs_tol=1e-12)
    return bool(got == expected)


def test_inputs_round_trip(tmp_path: Path) -> None:
    model = _model()
    book = _Book(_build(tmp_path, model))
    rows = _expected_rows(model)
    assert set(rows) == set(LAYOUT.tables)
    assert set(model["hoists"][0]) - set(LAYOUT.tables["hoists"].keys) == DERIVED_HOIST_KEYS
    assert set(model["ropes"][0]) - set(LAYOUT.tables["ropes"].keys) == OMITTED_ROPE_KEYS
    for name, table in LAYOUT.tables.items():
        assert len(rows[name]) <= table.capacity, name
        for i, row in enumerate(rows[name], start=1):
            assert book(LAYOUT.addr(name, "active", i)) == 1, (name, i)
            for key in table.keys:
                if key != "active":
                    got = book(LAYOUT.addr(name, key, i))
                    assert _same(got, row[key]), (name, i, key, got, row[key])
        for i in range(len(rows[name]) + 1, table.capacity + 1):
            assert book(LAYOUT.addr(name, "active", i)) == 0, (name, i)
            for key in table.keys:
                if key != "active":
                    assert book(LAYOUT.addr(name, key, i)) is None, (name, i, key)
        assert book(table.overflow_addr) == 0, name

    env = model["environment"]
    for key in ("gravity_m_s2", "air_density_kg_m3", "max_wind_speed_m_s"):
        assert _same(book(LAYOUT.cell("environment", key)), env[key]), key
    for key in ("reference_x_m", "reference_z_m"):
        assert _same(book(LAYOUT.cell("environment", key)), env["vessel_motion"][key]), key
    structure = model["structure"]
    for key in ("boom_width_m", "slewing_bearing_diameter_m"):
        assert _same(book(LAYOUT.cell("structure", key)), structure[key]), key
    for point, values in structure["points"].items():
        for axis in ("x_m", "z_m"):
            got = book(LAYOUT.cell("structure", f"{point}_{axis}"))
            assert _same(got, values[axis]), (point, axis)


@pytest.mark.parametrize("name", sorted(CASE_NAMES))
def test_scene_state_cells_hold_the_case(tmp_path: Path, name: str) -> None:
    book = _Book(_build(tmp_path, case=name))
    for key, value in dataclasses.asdict(CASES[name]).items():
        assert _same(book(LAYOUT.cell("scene", key)), value), (name, key)


def test_checks_are_clean_for_22689(tmp_path: Path) -> None:
    book = _Book(_build(tmp_path))
    for key in layout.CHECK_DESCRIPTIONS:
        assert book(LAYOUT.check(key)) == 0, key
    assert book(LAYOUT.total_issues_addr) == 0


def test_overflow_check_trips(tmp_path: Path) -> None:
    model = _model()
    capacity = LAYOUT.tables["segments"].capacity
    extra = capacity + 1 - sum(len(r["segments"]) for r in model["ropes"])
    seg = model["ropes"][0]["segments"][0]
    model["ropes"][0]["segments"].extend(dict(seg) for _ in range(extra))
    path = _build(tmp_path, model)
    book = _Book(path)
    assert book(LAYOUT.tables["segments"].overflow_addr) == 1
    assert book(LAYOUT.check("overflow")) == 1
    assert book(LAYOUT.total_issues_addr) > 0
    assert book(LAYOUT.addr("segments", "active", capacity)) == 1


def test_overflow_check_counts_rows_typed_below_a_table(tmp_path: Path) -> None:
    path = _build(tmp_path)
    wb = load_workbook(path)
    sheet, coord = LAYOUT.tables["nodes"].guard_addr("id").replace("$", "").split("!")
    wb[sheet][coord] = "typed_below_the_table"
    wb.save(path)
    assert _Book(path)(LAYOUT.check("overflow")) == 1


def test_duplicate_id_check(tmp_path: Path) -> None:
    model = _model()
    model["nodes"].append(dict(model["nodes"][3]))
    assert _Book(_build(tmp_path, model))(LAYOUT.check("duplicate_ids")) > 0


def test_missing_node_reference_check(tmp_path: Path) -> None:
    model = _model()
    model["ropes"][0]["segments"][0]["to_node_id"] = "no_such_node"
    assert _Book(_build(tmp_path, model))(LAYOUT.check("node_references")) == 1


def test_inactive_node_reference_check(tmp_path: Path) -> None:
    path = _build(tmp_path)
    ids = [n["id"] for n in _model()["nodes"]]
    wb = load_workbook(path)
    row = ids.index("mh_aframe_sheave_1") + 1
    sheet, coord = LAYOUT.addr("nodes", "active", row).replace("$", "").split("!")
    wb[sheet][coord] = 0
    wb.save(path)
    # Two MH segments touch the deactivated sheave.
    assert _Book(path)(LAYOUT.check("node_references")) == 2


def test_two_solve_ropes_check(tmp_path: Path) -> None:
    model = _model()
    next(r for r in model["ropes"] if r["id"] == "MH__rope")["tension_mode"] = "solve"
    book = _Book(_build(tmp_path, model))
    assert book(LAYOUT.check("multiple_solve_ropes")) == 1
    assert book(LAYOUT.check("no_solve_rope")) == 0


def test_hoist_rope_without_active_segments_check(tmp_path: Path) -> None:
    model = _model()
    next(r for r in model["ropes"] if r["id"] == "SH__rope")["segments"] = []
    assert _Book(_build(tmp_path, model))(LAYOUT.check("hoist_without_segments")) == 1


def test_custom_capacities(tmp_path: Path) -> None:
    lay = layout.Layout(layout.Capacities(nodes=30, segments=16, hoists=5))
    assert lay.tables["segments"].first_row != LAYOUT.tables["segments"].first_row
    path = tmp_path / "small.xlsx"
    build_workbook(_model(), CASES["base"], path, lay)
    book = _Book(path)
    assert book(lay.addr("segments", "active", 16)) == 1
    assert book(lay.addr("nodes", "active", 30)) == 0
    assert book(lay.total_issues_addr) == 0


def test_workbook_sheets_in_order(tmp_path: Path) -> None:
    wb = load_workbook(_build(tmp_path))
    assert wb.sheetnames == list(layout.SHEETS)
    assert layout.SHEETS == (
        "Conventions",
        "Inputs",
        "Geometry",
        "Loads",
        "Statics",
        "OutOfPlane",
        "Results",
        "Checks",
    )


# -- workbook: geometry and frame motion -----------------------------------------------


@pytest.mark.parametrize("name", sorted(CASE_NAMES))
def test_node_positions_match_kinematics(tmp_path: Path, name: str) -> None:
    case = CASES[name]
    book = _Book(_build(tmp_path, case=name))
    doc = load_document(YAML_PATH).model_dump()
    expected = active_hook_positions(
        doc,
        case.hoist_id,
        KinematicsAdapter(doc).compute_all_node_positions(case.boom_angle_deg),
        case.tackle_length_m,
    )
    model = _model()
    assert len(model["nodes"]) == 29
    for i, node in enumerate(model["nodes"], start=1):
        assert book(LAYOUT.geo_addr("node_positions", "id", i)) == node["id"]
        assert book(LAYOUT.geo_addr("node_positions", "active", i)) == 1
        for axis in ("x", "z"):
            got = book(LAYOUT.geo_addr("node_positions", f"{axis}_m", i))
            want = expected[node["id"]][axis]
            assert math.isclose(got, want, rel_tol=0.0, abs_tol=1e-9), (name, node["id"], axis)


@pytest.mark.parametrize("name", sorted(CASE_NAMES))
def test_frame_motion_matches_vessel_frame(tmp_path: Path, name: str) -> None:
    case = CASES[name]
    book = _Book(_build(tmp_path, case=name))
    model = _model()
    motion = crane_frame_motion(
        abs(model["environment"]["gravity_m_s2"]),
        VesselInputs(
            accel_x_m_s2=case.accel_x_m_s2,
            accel_y_m_s2=case.accel_y_m_s2,
            accel_z_m_s2=case.accel_z_m_s2,
            roll_deg=case.vessel_roll_deg,
            pitch_deg=case.vessel_pitch_deg,
            slew_deg=case.crane_slewing_angle_deg,
            roll_accel_rad_s2=case.roll_accel_rad_s2,
            pitch_accel_rad_s2=case.pitch_accel_rad_s2,
        ),
    )
    expected = {
        "gx": motion.gravity_crane[0],
        "gy": motion.gravity_crane[1],
        "gz": motion.gravity_crane[2],
        "ax": motion.accel_crane[0],
        "ay": motion.accel_crane[1],
        "az": motion.accel_crane[2],
        "kx": motion.load_accel[0],
        "ky": motion.load_accel[1],
        "kz": motion.load_accel[2],
        "solver_ax": motion.accel_x_m_s2,
        "solver_ay": motion.accel_y_m_s2,
        "solver_az": motion.accel_z_m_s2,
        "pitch_accel_crane": motion.pitch_accel_rad_s2,
        "roll_accel_crane": motion.roll_accel_rad_s2,
    }
    for key, want in expected.items():
        got = book(LAYOUT.geo_cell("frame_motion", key))
        assert math.isclose(got, want, rel_tol=0.0, abs_tol=1e-9), (name, key, got, want)
    # k = g - a holds in the crane frame.
    for axis in "xyz":
        k = book(LAYOUT.geo_cell("frame_motion", f"k{axis}"))
        g = book(LAYOUT.geo_cell("frame_motion", f"g{axis}"))
        a = book(LAYOUT.geo_cell("frame_motion", f"a{axis}"))
        assert math.isclose(k, g - a, abs_tol=1e-12)


def test_geometry_spare_rows_are_zero_without_errors(tmp_path: Path) -> None:
    lay = layout.Layout(layout.Capacities(nodes=40))
    path = tmp_path / "spare.xlsx"
    build_workbook(_model(), CASES["base"], path, lay)
    values = recalculate(path)["Geometry"]
    table = lay.geo_tables["node_positions"]
    for i in range(30, 41):
        for key in table.keys:
            sheet, coord = lay.geo_addr("node_positions", key, i).replace("$", "").split("!")
            got = values[coord]
            assert not (isinstance(got, str) and got.startswith("#")), (i, key, got)
            if key not in ("id", "frame"):
                assert got == 0, (i, key, got)
    for cell_values in values.values():
        assert not (isinstance(cell_values, str) and cell_values.startswith("#"))
    assert _Book(path)(lay.total_issues_addr) == 0


def _solver_loads(
    case: SceneCase, mutate: Callable[[dict[str, Any]], None] | None = None
) -> tuple[dict[str, dict], dict[str, dict], dict[str, Any]]:
    """The solver's own per-body in-plane loads ``(ld, bh)`` at ``case``.

    ``_accumulate_loads`` evaluated directly with the inputs ``_angle_invariants`` and
    ``compute_analysis_point`` give it (the app composes the same linear terms from unit
    channels). Returns the positions and the document too.
    """
    doc = load_document(YAML_PATH).model_dump()
    if mutate is not None:
        mutate(doc)
    positions = active_hook_positions(
        doc,
        case.hoist_id,
        KinematicsAdapter(doc).compute_all_node_positions(case.boom_angle_deg),
        case.tackle_length_m,
    )
    motion = crane_frame_motion(
        abs(float(doc["environment"]["gravity_m_s2"])),
        VesselInputs(
            accel_x_m_s2=case.accel_x_m_s2,
            accel_y_m_s2=case.accel_y_m_s2,
            accel_z_m_s2=case.accel_z_m_s2,
            roll_deg=case.vessel_roll_deg,
            pitch_deg=case.vessel_pitch_deg,
            slew_deg=case.crane_slewing_angle_deg,
            roll_accel_rad_s2=case.roll_accel_rad_s2,
            pitch_accel_rad_s2=case.pitch_accel_rad_s2,
        ),
    )
    rope_mass = {
        nid: entry.mass_t
        for nid, entry in rope_mass_at_nodes(
            doc, positions, effective_mult=falls_override_effective_mult(doc, {})
        ).items()
    }
    wind_x, _wind_y = split_wind_speed_components(case.wind_speed_m_s, case.wind_direction)
    ld, bh = crane_solver._accumulate_loads(
        doc,
        {nid: (float(p["x"]), float(p["z"])) for nid, p in positions.items()},
        {n["id"]: n.get("body", "") for n in doc["nodes"]},
        case.hoist_id,
        case.hook_load_kN,
        wind_x,
        motion.accel_x_m_s2,
        motion.accel_z_m_s2,
        motion.pitch_accel_rad_s2,
        offlead_lateral_force_kN=math.sin(math.radians(case.offlead_deg)) * case.hook_load_kN,
        solver_ctx=crane_solver.build_solver_static_context(doc),
        rope_mass_t_by_node=rope_mass,
        boom_angle_deg=case.boom_angle_deg,
    )
    return ld, bh, {"doc": doc, "positions": positions}


def _drawn_category_sums(case: SceneCase) -> tuple[dict[str, dict[str, dict]], float]:
    """{body: {category: {"fx", "fz", "m"}}} of the Scene's free-body loads, and T_bh."""
    session, calculator, (pt, _rows, _conn) = _solve(YAML_PATH, case)
    inputs = _scene_inputs(session, calculator, pt)
    positions = inputs.node_positions()
    out: dict[str, dict[str, dict]] = {}
    for body in layout.BODIES:
        loads = drawn_loads.build_body_loads(
            inputs.document_dict,
            hoist=dict(inputs.hoist),
            conditions=inputs.conditions,
            node_positions=positions,
            analysis_point=pt,
            body_filter=drawn_loads.FreeBodyFilter(
                body, drawn_loads.node_body_map(inputs.document_dict)
            ),
        )
        out[body] = {
            cat: {
                "fx": sum(v.fx_kN for v in loads.category(title)),
                "fz": sum(v.fz_kN for v in loads.category(title)),
                "m": sum(v.world_x * v.fz_kN - v.world_z * v.fx_kN for v in loads.category(title)),
            }
            for cat, title in layout.LOAD_CATEGORIES.items()
        }
    t_bh = app_results(YAML_PATH, case)["tension.BH"]
    return out, t_bh


LOAD_TOL = 0.01


def _assert_body_totals_match_solver(
    book: "_Book", lay: layout.Layout, ld: dict[str, dict], bh: dict[str, dict], tag: Any
) -> None:
    for body in layout.BODIES:
        for comp, key in (("Fx", "fx"), ("Fz", "fz"), ("M", "m")):
            got = book(lay.body_total(body, key))
            assert math.isclose(got, ld[body][comp], abs_tol=LOAD_TOL), (tag, body, key)
            got = book(lay.body_total(body, f"bh_{key}"))
            assert math.isclose(got, bh[body][comp], abs_tol=1e-9), (tag, body, f"bh_{key}")


def _assert_no_errors(path: Path, sheet: str = layout.LOADS) -> dict[str, Any]:
    values = recalculate(path)[sheet]
    errors = {c: v for c, v in values.items() if isinstance(v, str) and v.startswith("#")}
    assert not errors, list(errors.items())[:10]
    return values


@pytest.mark.parametrize("name", ["base", "inplane_wind_accel", "idle_hoist"])
def test_total_loads_match_drawn_loads(tmp_path: Path, name: str) -> None:
    case = CASES[name]
    book = _Book(_build(tmp_path, case=name))
    drawn, t_bh = _drawn_category_sums(case)
    for body in layout.BODIES:
        known = {"fx": 0.0, "fz": 0.0, "m": 0.0}
        for cat in layout.LOAD_CATEGORIES:
            for comp in ("fx", "fz", "m"):
                got = book(LAYOUT.body_total(body, f"{cat}_{comp}"))
                want = drawn[body][cat][comp]
                if cat == "rope":
                    # The Scene draws the solved boom-hoist tension too; the workbook
                    # lists it as coefficients (bh_*) for Statics.
                    got += t_bh * book(LAYOUT.body_total(body, f"bh_{comp}"))
                assert math.isclose(got, want, abs_tol=LOAD_TOL), (name, body, cat, comp)
                known[comp] += book(LAYOUT.body_total(body, f"{cat}_{comp}"))
        for comp in ("fx", "fz", "m"):
            assert math.isclose(book(LAYOUT.body_total(body, comp)), known[comp], abs_tol=1e-6)
    ld, bh, _ = _solver_loads(case)
    _assert_body_totals_match_solver(book, LAYOUT, ld, bh, name)
    # Rope tensions of the fixed ropes are the Scene's rope rows.
    results = app_results(YAML_PATH, case)
    for i, hoist in enumerate(_model()["hoists"], start=1):
        row = next(
            k for k, r in enumerate(_model()["ropes"], start=1) if r["id"] == hoist["rope_id"]
        )
        got = book(LAYOUT.loads_addr("rope_tensions", "tension_kN", row))
        want = 0.0 if hoist["id"] == "BH" else results[f"tension.{hoist['id']}"]
        assert math.isclose(got, want, abs_tol=1e-9), (name, hoist["id"])


def _rename_node(model: dict[str, Any], old: str, new: str) -> None:
    for node in model["nodes"]:
        if node["id"] == old:
            node["id"] = new
    for rope in model["ropes"]:
        for seg in rope["segments"]:
            for end in ("from_node_id", "to_node_id"):
                if seg[end] == old:
                    seg[end] = new


@pytest.mark.parametrize("name", ["base", "idle_hoist"])
def test_rope_weight_reeved_and_spooled(tmp_path: Path, name: str) -> None:
    case = CASES[name]
    # The spool node is found by its flag, not by "winch" in its id: rename one drum.
    model = _model()
    _rename_node(model, "mh_winch", "mh_drum")
    book = _Book(_build(tmp_path, model, case=name))
    _ld, _bh, app = _solver_loads(case)
    expected = rope_mass_at_nodes(app["doc"], app["positions"])
    seen = set()
    for i, node in enumerate(model["nodes"], start=1):
        app_id = "mh_winch" if node["id"] == "mh_drum" else node["id"]
        entry = expected.get(app_id)
        for key in ("reeved_t", "spooled_t"):
            got = book(LAYOUT.loads_addr("node_loads", key, i))
            want = 0.0 if entry is None else getattr(entry, key)
            assert math.isclose(got, want, abs_tol=1e-9), (name, node["id"], key, got, want)
        if entry is not None:
            seen.add(app_id)
    assert seen == set(expected)
    assert expected["mh_winch"].spooled_t > 1.0
    assert book(LAYOUT.loads_addr("hoist_ropes", "spool_node_id", 1)) == "mh_drum"


def _wind_case(direction: str, speed: float = 15.1) -> SceneCase:
    return dataclasses.replace(
        CASES["inplane_wind_accel"], wind_direction=direction, wind_speed_m_s=speed
    )


#: Tight capacities (22689 fits exactly) keep the per-direction rebuilds quick.
TIGHT = layout.Layout(
    layout.Capacities(mass_points=9, wind_areas=8, nodes=29, segments=16, ropes=4, hoists=4)
)


def _build_case(tmp_path: Path, case: SceneCase, lay: layout.Layout = TIGHT) -> Path:
    path = tmp_path / f"wb_{case.wind_direction.replace('+', 'p').replace('-', 'm')}.xlsx"
    build_workbook(_model(), case, path, lay)
    return path


def test_wind_zero_speed_gives_zero(tmp_path: Path) -> None:
    case = _wind_case("+X", 0.0)
    path = _build_case(tmp_path, case)
    _assert_no_errors(path)
    book = _Book(path)
    for i in range(1, TIGHT.loads_tables["wind_loads"].capacity + 1):
        assert book(TIGHT.loads_addr("wind_loads", "fx", i)) == 0
    for body in layout.BODIES:
        for comp in ("fx", "fz", "m"):
            assert book(TIGHT.body_total(body, f"wind_{comp}")) == 0
    ld, bh, _ = _solver_loads(case)
    _assert_body_totals_match_solver(book, TIGHT, ld, bh, "zero wind")


@pytest.mark.parametrize("direction", ["+X", "-X", "+Y", "-Y"])
def test_wind_direction_signs(tmp_path: Path, direction: str) -> None:
    case = _wind_case(direction)
    book = _Book(_build_case(tmp_path, case))
    drawn, _t_bh = _drawn_category_sums(case)
    sign = {"+X": 1.0, "-X": -1.0}.get(direction, 0.0)
    assert book(TIGHT.loads_cell("load_scene", "wind_sign")) == sign
    for body in layout.BODIES:
        for comp in ("fx", "fz", "m"):
            got = book(TIGHT.body_total(body, f"wind_{comp}"))
            assert math.isclose(got, drawn[body]["wind"][comp], abs_tol=LOAD_TOL), (body, comp)
    boom_fx = book(TIGHT.body_total("boom", "wind_fx"))
    platform_fx = book(TIGHT.body_total("platform", "wind_fx"))
    if sign:
        assert boom_fx * sign > 1.0 and platform_fx * sign > 1.0
    else:
        assert boom_fx == 0 and platform_fx == 0
    ld, bh, _ = _solver_loads(case)
    _assert_body_totals_match_solver(book, TIGHT, ld, bh, direction)


def test_loads_spare_rows_are_zero_without_errors(tmp_path: Path) -> None:
    path = _build(tmp_path)
    values = _assert_no_errors(path)
    model = _model()
    used = {
        "mass_loads": sum(len(b["mass_points"]) for b in model["bodies"]),
        "wind_loads": sum(len(b["wind_areas"]) for b in model["bodies"]),
        "rope_tensions": len(model["ropes"]),
        "hoist_ropes": len(model["hoists"]),
        "segment_loads": sum(len(r["segments"]) for r in model["ropes"]),
        "node_loads": len(model["nodes"]),
    }
    for name, n_used in used.items():
        table = LAYOUT.loads_tables[name]
        assert table.capacity > n_used, name
        for i in range(n_used + 1, table.capacity + 1):
            for f in table.fields:
                got = values[LAYOUT.loads_addr(name, f.key, i).replace("$", "").split("!")[1]]
                if f.kind == "text":
                    assert got is None, (name, i, f.key, got)
                else:
                    assert got == 0, (name, i, f.key, got)
    assert _Book(path)(LAYOUT.total_issues_addr) == 0


def test_zero_length_segment_and_hoist_without_segments(tmp_path: Path) -> None:
    def mutate(doc: dict[str, Any]) -> None:
        ropes = {r["id"]: r for r in doc["ropes"]}
        ropes["SH__rope"]["segments"] = []
        seg = ropes["WH__rope"]["segments"][3]
        seg["to_node_id"] = seg["from_node_id"]

    model = _model()
    mutate(model)
    case = CASES["base"]
    path = tmp_path / "zero.xlsx"
    build_workbook(model, case, path, TIGHT)
    _assert_no_errors(path)
    book = _Book(path)
    assert book(TIGHT.check("hoist_without_segments")) == 1
    seg_row = 1 + sum(len(r["segments"]) for r in model["ropes"][:1]) + 3
    assert model["ropes"][1]["id"] == "WH__rope"
    for key in ("length_m", "ux", "uz", "fx", "fz", "half_mass_t"):
        assert book(TIGHT.loads_addr("segment_loads", key, seg_row)) == 0, key
    sh_row = next(i for i, h in enumerate(model["hoists"], start=1) if h["id"] == "SH")
    for key in ("reeved_m", "spooled_m", "spooled_t"):
        assert book(TIGHT.loads_addr("hoist_ropes", key, sh_row)) == 0, key
    ld, bh, _ = _solver_loads(case, mutate)
    _assert_body_totals_match_solver(book, TIGHT, ld, bh, "zero-length")


def test_hanging_chain_check(tmp_path: Path) -> None:
    model = _model()
    parent = next(n for n in model["nodes"] if n["frame"] == "hanging")
    child = dict(parent, id="chained_hook", below_node_id=parent["id"])
    model["nodes"].append(child)
    assert _Book(_build(tmp_path, model))(LAYOUT.check("hanging_chain")) == 1


# -- workbook: statics solve and in-plane results ------------------------------------

#: Golden reaction components the workbook must reproduce in-plane. The heel point's
#: boom_axial/normal (name-based axis node) and the out-of-plane rows are not in-plane.
INPLANE_REQUIRED = {
    ("heel_point", "fx"),
    ("heel_point", "fz"),
    ("rear_hinge", "fx"),
    ("rear_hinge", "fz"),
    ("front_hinge", "fx"),
    ("front_hinge", "fz"),
    ("upper_hinge", "fx"),
    ("upper_hinge", "fz"),
    ("platform_base", "fx"),
    ("platform_base", "fz"),
    ("platform_base", "my"),
}


def _workbook_results(book: "_Book", lay: layout.Layout, model: dict[str, Any]) -> dict[str, Any]:
    """The Results sheet as ``app_results`` keys (``tension.<hoist>``, ``reaction.*``)."""
    out: dict[str, Any] = {}
    for i, hoist in enumerate(model["hoists"], start=1):
        assert book(lay.results_addr("tensions", "hoist_id", i)) == hoist["id"]
        out[f"tension.{hoist['id']}"] = book(lay.results_addr("tensions", "tension_kN", i))
    for entity, component in lay.result_rows:
        out[f"reaction.{entity}.{component}"] = book(lay.result_cell(entity, component))
    return out


def _app_inplane(
    case: SceneCase, mutate: Callable[[dict[str, Any]], None] | None = None
) -> dict[str, float] | None:
    """The app's rope tensions and reaction components (in-plane and out-of-plane) for a
    (mutated) 22689 document, straight from ``CraneCalculator.compute_analysis_point``
    (``None`` if it finds none), read as the Scene results table reads them."""
    from crane_statics.calculation.engine import CraneCalculator
    from crane_statics.core.demand_extraction import extract_connection_component_response
    from crane_statics.data.models import CraneDocument

    doc_dict = load_document(YAML_PATH).model_dump()
    if mutate is not None:
        mutate(doc_dict)
    doc = CraneDocument.model_validate(doc_dict)
    diameter = doc.support_widths.slewing_bearing_diameter_m
    kwargs = dataclasses.asdict(case)
    hoist_id = kwargs.pop("hoist_id")
    angle, hook = kwargs.pop("boom_angle_deg"), kwargs.pop("hook_load_kN")
    pt = CraneCalculator(doc).compute_analysis_point(angle, hook, hoist_id, **kwargs)
    if pt is None:
        return None
    solve = {r["id"] for r in doc_dict["ropes"] if r.get("tension_mode") == "solve"}
    out: dict[str, float] = {}
    for hoist in doc_dict["hoists"]:
        channel = "boom_hoist" if hoist["rope_id"] in solve else hoist["rope_id"]
        base = pt.baseline_rope_tensions.get(channel, 0.0)
        sens = pt.sensitivity_rope_tensions.get(channel, 0.0)
        out[f"tension.{hoist['id']}"] = base + sens * hook
    for entity, component in layout.DEFAULT_LAYOUT.result_rows:
        comp = {"fx": "Fx", "fy": "Fy", "fz": "Fz", "mx": "Mx", "my": "My"}.get(
            component, component
        )
        value = extract_connection_component_response(
            pt, hook, entity, comp, support_widths_diameter_m=diameter
        )
        assert value is not None, (entity, component)
        if component == "min_bearing_line_load":
            value = max(0.0, value)  # the results row shows uplift only
        out[f"reaction.{entity}.{component}"] = value
    return out


def _solver_statics(
    case: SceneCase, mutate: Callable[[dict[str, Any]], None] | None = None
) -> dict[str, float]:
    """``crane_solver._run_statics`` at ``case``, with the inputs ``_solver_loads`` uses."""
    doc = load_document(YAML_PATH).model_dump()
    if mutate is not None:
        mutate(doc)
    positions = active_hook_positions(
        doc,
        case.hoist_id,
        KinematicsAdapter(doc).compute_all_node_positions(case.boom_angle_deg),
        case.tackle_length_m,
    )
    motion = crane_frame_motion(
        abs(float(doc["environment"]["gravity_m_s2"])),
        VesselInputs(
            accel_x_m_s2=case.accel_x_m_s2,
            accel_y_m_s2=case.accel_y_m_s2,
            accel_z_m_s2=case.accel_z_m_s2,
            roll_deg=case.vessel_roll_deg,
            pitch_deg=case.vessel_pitch_deg,
            slew_deg=case.crane_slewing_angle_deg,
            roll_accel_rad_s2=case.roll_accel_rad_s2,
            pitch_accel_rad_s2=case.pitch_accel_rad_s2,
        ),
    )
    rope_mass = {
        nid: entry.mass_t
        for nid, entry in rope_mass_at_nodes(
            doc, positions, effective_mult=falls_override_effective_mult(doc, {})
        ).items()
    }
    wind_x, _wind_y = split_wind_speed_components(case.wind_speed_m_s, case.wind_direction)
    raw: dict[str, float] = crane_solver._run_statics(
        doc,
        {nid: (float(p["x"]), float(p["z"])) for nid, p in positions.items()},
        {n["id"]: n.get("body", "") for n in doc["nodes"]},
        case.hoist_id,
        case.hook_load_kN,
        wind_x,
        motion.accel_x_m_s2,
        motion.accel_z_m_s2,
        motion.pitch_accel_rad_s2,
        offlead_lateral_force_kN=math.sin(math.radians(case.offlead_deg)) * case.hook_load_kN,
        solver_ctx=crane_solver.build_solver_static_context(doc),
        rope_mass_t_by_node=rope_mass,
        boom_angle_deg=case.boom_angle_deg,
    )
    return raw


def _assert_statics_match_solver(
    book: "_Book", lay: layout.Layout, raw: dict[str, float], tag: Any
) -> None:
    assert set(raw) == set(layout.STATICS_UNKNOWNS), tag
    for key, want in raw.items():
        got = book(lay.statics_value(key))
        assert math.isclose(got, want, rel_tol=1e-9, abs_tol=1e-6), (tag, key, got, want)


@pytest.mark.parametrize("name", ["base", "inplane_wind_accel", "idle_hoist"])
def test_inplane_results_match_golden(tmp_path: Path, name: str) -> None:
    path = _build(tmp_path, case=name)
    _assert_no_errors(path, layout.RESULTS)
    _assert_no_errors(path, layout.STATICS)
    book = _Book(path)
    got = _workbook_results(book, LAYOUT, _model())
    golden = _golden()["cases"][name]["app_results"]
    assert INPLANE_REQUIRED <= set(LAYOUT.result_rows)
    assert {k for k in golden if k.startswith("tension.")} == {
        k for k in got if k.startswith("tension.")
    }
    for key, value in got.items():
        assert key in golden, key
        assert math.isclose(value, golden[key], abs_tol=LOAD_TOL), (name, key, value, golden[key])
    assert book(LAYOUT.statics_cell("statics_status", "ok")) == 1
    assert book(LAYOUT.results_cell("results_status", "message")) == "OK"
    _assert_statics_match_solver(book, LAYOUT, _solver_statics(CASES[name]), name)
    _assert_book_clean(book, layout.OUT_OF_PLANE, layout.CHECKS)
    _assert_oop_matches_engine(book, LAYOUT, _model(), CASES[name], name)


def _collapse_rear_leg(model: dict[str, Any]) -> None:
    """Move the rear hinge onto the upper hinge: the rear leg has no length."""
    points = model["structure"]["points"]
    points["rear_hinge"]["x_m"] = points["upper_hinge"]["x_m"]
    points["rear_hinge"]["z_m"] = points["upper_hinge"]["z_m"]


def _collapse_rear_leg_doc(doc: dict[str, Any]) -> None:
    nodes = {n["id"]: n for n in doc["nodes"]}
    for node_id in ("rear_base", "platform_rear"):
        nodes[node_id]["x_m"] = nodes["rear_top"]["x_m"]
        nodes[node_id]["z_m"] = nodes["rear_top"]["z_m"]


def _assert_results_show_message(path: Path, lay: layout.Layout, words: str) -> "_Book":
    _assert_no_errors(path, layout.RESULTS)
    book = _Book(path)
    assert book(lay.statics_cell("statics_status", "ok")) == 0
    message = book(lay.results_cell("results_status", "message"))
    assert isinstance(message, str) and words in message.lower(), message
    for entity, component in lay.result_rows:
        assert isinstance(book(lay.result_cell(entity, component)), str), (entity, component)
    for i in range(1, len(_model()["hoists"]) + 1):
        assert isinstance(book(lay.results_addr("tensions", "tension_kN", i)), str), i
    return book


def test_singular_matrix_sets_flag_not_errors(tmp_path: Path) -> None:
    # The app: np.linalg.solve raises, _run_statics returns {} and there is no point.
    assert _solver_statics(CASES["base"], _collapse_rear_leg_doc) == {}
    assert _app_inplane(CASES["base"], _collapse_rear_leg_doc) is None
    model = _model()
    _collapse_rear_leg(model)
    path = tmp_path / "singular.xlsx"
    build_workbook(model, CASES["base"], path, TIGHT)
    book = _assert_results_show_message(path, TIGHT, "singular")
    assert book(TIGHT.statics_flag("leg_system")) == 1
    assert book(TIGHT.statics_flag("boom_system")) == 0
    assert book(TIGHT.check("singular_matrix")) == 1
    assert book(TIGHT.total_issues_addr) == 1


def test_no_solve_rope_shows_message(tmp_path: Path) -> None:
    def mutate(doc: dict[str, Any]) -> None:
        for rope in doc["ropes"]:
            rope["tension_mode"] = "fixed"

    assert _app_inplane(CASES["base"], mutate) is None
    model = _model()
    mutate(model)
    path = tmp_path / "no_solve.xlsx"
    build_workbook(model, CASES["base"], path, TIGHT)
    book = _assert_results_show_message(path, TIGHT, "solve rope")
    assert book(TIGHT.check("no_solve_rope")) == 1
    assert book(TIGHT.statics_flag("boom_system")) == 1


@pytest.mark.parametrize("name", ["inplane_wind_accel", "outofplane_wind_roll_sidelead"])
def test_spare_rows_do_not_change_results(tmp_path: Path, name: str) -> None:
    big = layout.Layout(
        layout.Capacities(mass_points=55, wind_areas=45, nodes=95, segments=70, ropes=11, hoists=12)
    )
    model = _model()
    got = {}
    for tag, lay in (("tight", TIGHT), ("big", big)):
        path = tmp_path / f"{tag}.xlsx"
        build_workbook(model, CASES[name], path, lay)
        book = _Book(path)
        _assert_book_clean(book, layout.OUT_OF_PLANE, layout.RESULTS, layout.CHECKS)
        got[tag] = _workbook_results(book, lay, model)
        got[tag].update({k: book(lay.statics_value(k)) for k in layout.STATICS_UNKNOWNS})
        for group in lay.oop.groups:
            for comp in ("mx", "mz"):
                got[tag][f"{group}.{comp}"] = book(lay.oop.moment(group, comp))
        for key in ("fy_kN", "mx_kNm"):
            got[tag][key] = book(lay.oop.cell("platform", key))
        assert book(lay.total_issues_addr) == 0
    assert set(got["tight"]) == set(got["big"])
    for key, value in got["tight"].items():
        assert math.isclose(value, got["big"][key], rel_tol=0.0, abs_tol=1e-9), key


def test_wind_zero_and_idle_hoist_zero_tension(tmp_path: Path) -> None:
    # Scene hoist with zero hook load, no wind, and an idle hoist (SH) whose rope has no
    # segment: the app reports MH = 0 and SH = its block weight over one part (not 0).
    case = dataclasses.replace(CASES["base"], hook_load_kN=0.0, wind_speed_m_s=0.0)

    def mutate(doc: dict[str, Any]) -> None:
        next(r for r in doc["ropes"] if r["id"] == "SH__rope")["segments"] = []

    want = _app_inplane(case, mutate)
    assert want is not None
    model = _model()
    mutate(model)
    path = tmp_path / "zero.xlsx"
    build_workbook(model, case, path, TIGHT)
    _assert_no_errors(path, layout.RESULTS)
    book = _Book(path)
    got = _workbook_results(book, TIGHT, model)
    assert got["tension.MH"] == 0 and want["tension.MH"] == 0
    assert want["tension.SH"] > 1.0
    assert set(got) == set(want)
    for key, value in want.items():
        assert math.isclose(got[key], value, abs_tol=LOAD_TOL), (key, got[key], value)
    _assert_statics_match_solver(book, TIGHT, _solver_statics(case, mutate), "zero")


# -- workbook: out-of-plane pass -------------------------------------------------------

#: Golden out-of-plane components the workbook must reproduce. heel_left/heel_right
#: boom_axial/boom_normal need the name-based heel axis node and are omitted, as for the
#: heel point.
OOP_REQUIRED = {
    ("heel_left", "fx"),
    ("heel_left", "fz"),
    ("heel_left", "resultant"),
    ("heel_right", "fx"),
    ("heel_right", "fz"),
    ("heel_right", "resultant"),
    ("platform_base", "fy"),
    ("platform_base", "mx"),
    ("platform_base", "fradial"),
    ("platform_base", "mradial"),
    ("platform_base", "max_bearing_line_load"),
    ("platform_base", "min_bearing_line_load"),
}
#: Support group of the engine's out-of-plane pass -> its (left, right) split entities.
OOP_SIDES = {
    "heel": ("heel_left", "heel_right"),
    "front_leg": ("front_leg_left", "front_leg_right"),
    "rear_leg": ("rear_leg_left", "rear_leg_right"),
}


def _assert_book_clean(book: "_Book", *sheets: str) -> None:
    for sheet in sheets:
        values = book.values[sheet]
        errors = {c: v for c, v in values.items() if isinstance(v, str) and v.startswith("#")}
        assert not errors, (sheet, list(errors.items())[:10])


def _case_motion(case: SceneCase) -> Any:
    return crane_frame_motion(
        abs(float(_model()["environment"]["gravity_m_s2"])),
        VesselInputs(
            accel_x_m_s2=case.accel_x_m_s2,
            accel_y_m_s2=case.accel_y_m_s2,
            accel_z_m_s2=case.accel_z_m_s2,
            roll_deg=case.vessel_roll_deg,
            pitch_deg=case.vessel_pitch_deg,
            slew_deg=case.crane_slewing_angle_deg,
            roll_accel_rad_s2=case.roll_accel_rad_s2,
            pitch_accel_rad_s2=case.pitch_accel_rad_s2,
        ),
    )


def _engine_oop(case: SceneCase) -> dict[str, Any]:
    """The engine's out-of-plane pass at ``case``, called directly.

    ``CraneCalculator.compute_analysis_point`` runs it (and leaves its point geometry, with
    the lumped hook and rope masses, in ``_oop_geometry``); ``_out_of_plane_variants`` is then
    evaluated once with the actual hook load and side force ``sin(sidelead) x hook load``.
    The group moments are recovered from the split: ``M = (left - right) x width / 2``.
    """
    from crane_statics.calculation.engine import CraneCalculator

    doc = load_document(YAML_PATH)
    calc = CraneCalculator(doc)
    kwargs = dataclasses.asdict(case)
    hoist_id = kwargs.pop("hoist_id")
    angle, hook = kwargs.pop("boom_angle_deg"), kwargs.pop("hook_load_kN")
    pt = calc.compute_analysis_point(angle, hook, hoist_id, **kwargs)
    assert pt is not None and calc._oop_geometry is not None
    (_angle, lumped, _rho), geometry = calc._oop_geometry
    motion = _case_motion(case)
    _wind_x, wind_y = split_wind_speed_components(case.wind_speed_m_s, case.wind_direction)
    side_kN = math.sin(math.radians(case.sidelead_deg)) * hook
    ((split, platform_mx, platform_fy),) = calc._out_of_plane_variants(
        pt,
        hoist_id,
        angle,
        [(hook, side_kN)],
        wind_y,
        motion.accel_y_m_s2,
        motion.roll_accel_rad_s2,
        accel_x_m_s2=motion.accel_x_m_s2,
        accel_z_m_s2=motion.accel_z_m_s2,
        pitch_accel_rad_s2=motion.pitch_accel_rad_s2,
        lumped_point_masses=lumped,
    )
    width = float(doc.support_widths.boom_width_m)
    moments: dict[str, dict[str, float]] = {
        group: {
            "mx": (split[left]["Fz"] - split[right]["Fz"]) * width / 2.0,
            "mz": (split[left]["Fx"] - split[right]["Fx"]) * width / 2.0,
        }
        for group, (left, right) in OOP_SIDES.items()
    }
    moments["platform_base"] = {"mx": platform_mx}
    assert doc.environment.vessel_motion is not None
    ref_z = float(doc.environment.vessel_motion.reference_z_m)
    # _out_of_plane_variants' fy_m and fy_w, on the engine's own point geometry.
    fy = -geometry.mass_t * (
        motion.accel_y_m_s2 - motion.roll_accel_rad_s2 * (geometry.mass_z - ref_z)
    )
    n_doc = sum(len(body.mass_points) for body in doc.bodies)
    sign = 0.0 if abs(wind_y) < 1e-12 else math.copysign(1.0, wind_y)
    return {
        "split": split,
        "moments": moments,
        "platform_fy": platform_fy,
        "mass_fy": fy[:n_doc],
        "mass_y": geometry.mass_y[:n_doc],
        "lumped_fy": float(fy[n_doc:].sum()),
        "wind_fy": sign * geometry.wind_coef * abs(wind_y) ** 2,
        "side_kN": side_kN,
    }


def _assert_oop_matches_engine(
    book: "_Book", lay: layout.Layout, model: dict[str, Any], case: SceneCase, tag: Any
) -> None:
    want = _engine_oop(case)
    oop = lay.oop

    def close(got: Any, value: float, what: Any) -> None:
        assert math.isclose(got, value, rel_tol=1e-9, abs_tol=1e-6), (tag, what, got, value)

    assert len(want["mass_fy"]) == sum(len(b["mass_points"]) for b in model["bodies"])
    for i, value in enumerate(want["mass_fy"], start=1):
        close(book(oop.addr("oop_masses", "fy_kN", i)), value, ("mass fy", i))
        close(book(oop.addr("oop_masses", "y_m", i)), want["mass_y"][i - 1], ("mass y", i))
    for i, value in enumerate(want["wind_fy"], start=1):
        close(book(oop.addr("oop_winds", "fy_kN", i)), value, ("wind fy", i))
    lumped = sum(
        book(oop.addr("oop_lumped", "fy_kN", i))
        for i in range(1, oop.tables["oop_lumped"].capacity + 1)
    )
    close(lumped, want["lumped_fy"], "lumped fy")
    close(book(oop.cell("sidelead", "fy_kN")), want["side_kN"], "side force")
    for group, comps in want["moments"].items():
        for comp, value in comps.items():
            close(book(oop.moment(group, comp)), value, (group, comp))
    for entity, comps in want["split"].items():
        for comp, value in comps.items():
            close(book(oop.split_value(entity, comp.lower())), value, (entity, comp))
    close(book(oop.cell("platform", "fy_kN")), want["platform_fy"], "platform fy")
    close(book(oop.cell("platform", "mx_kNm")), want["moments"]["platform_base"]["mx"], "mx")


def test_outofplane_results_match_golden(tmp_path: Path) -> None:
    name = "outofplane_wind_roll_sidelead"
    path = _build(tmp_path, case=name)
    book = _Book(path)
    _assert_book_clean(book, layout.STATICS, layout.OUT_OF_PLANE, layout.RESULTS, layout.CHECKS)
    got = _workbook_results(book, LAYOUT, _model())
    golden = _golden()["cases"][name]["app_results"]
    assert INPLANE_REQUIRED | OOP_REQUIRED <= set(LAYOUT.result_rows)
    for key, value in got.items():
        assert key in golden, key
        assert math.isclose(value, golden[key], abs_tol=LOAD_TOL), (name, key, value, golden[key])
    # The case loads the left/right split and the platform out of plane.
    assert abs(got["reaction.heel_left.fz"] - got["reaction.heel_right.fz"]) > 1000.0
    assert abs(got["reaction.heel_left.fx"] - got["reaction.heel_right.fx"]) > 1000.0
    assert got["reaction.platform_base.fy"] > 100.0
    assert book(LAYOUT.results_cell("results_status", "message")) == "OK"
    assert book(LAYOUT.total_issues_addr) == 0
    _assert_statics_match_solver(book, LAYOUT, _solver_statics(CASES[name]), name)
    _assert_oop_matches_engine(book, LAYOUT, _model(), CASES[name], name)


def test_zero_boom_width_is_flagged(tmp_path: Path) -> None:
    from crane_statics.calculation.engine import CraneCalculator

    case = CASES["outofplane_wind_roll_sidelead"]
    # The app rejects a document with boom width 0; past validation the engine's split
    # raises and compute_analysis_point gives no point (no results at all).
    doc = load_document(YAML_PATH)
    doc.support_widths.boom_width_m = 0.0
    kwargs = dataclasses.asdict(case)
    hoist_id = kwargs.pop("hoist_id")
    angle, hook = kwargs.pop("boom_angle_deg"), kwargs.pop("hook_load_kN")
    assert CraneCalculator(doc).compute_analysis_point(angle, hook, hoist_id, **kwargs) is None

    model = _model()
    model["structure"]["boom_width_m"] = 0.0
    path = tmp_path / "zero_width.xlsx"
    build_workbook(model, case, path, TIGHT)
    book = _Book(path)
    _assert_book_clean(book, layout.OUT_OF_PLANE, layout.RESULTS, layout.CHECKS)
    assert book(TIGHT.check("zero_boom_width")) == 1
    assert book(TIGHT.total_issues_addr) == 1
    assert book(TIGHT.statics_cell("statics_status", "ok")) == 1
    message = book(TIGHT.results_cell("results_status", "message"))
    assert isinstance(message, str) and "boom width" in message.lower(), message
    for entity, component in TIGHT.result_rows:
        assert isinstance(book(TIGHT.result_cell(entity, component)), str), (entity, component)
    for i in range(1, len(model["hoists"]) + 1):
        assert isinstance(book(TIGHT.results_addr("tensions", "tension_kN", i)), str), i


@pytest.mark.parametrize("direction", ["+Y", "-Y"])
def test_wind_y_direction_signs(tmp_path: Path, direction: str) -> None:
    # Y wind alone: no motion, no sidelead; the platform Fy is the wind force.
    case = dataclasses.replace(CASES["base"], wind_speed_m_s=15.1, wind_direction=direction)
    path = _build_case(tmp_path, case)
    book = _Book(path)
    _assert_book_clean(book, layout.OUT_OF_PLANE, layout.RESULTS, layout.CHECKS)
    sign = 1.0 if direction == "+Y" else -1.0
    assert book(TIGHT.oop.cell("oop_scene", "wind_y_sign")) == sign
    for body in layout.BODIES:
        assert book(TIGHT.body_total(body, "wind_fx")) == 0
    want = _app_inplane(case)
    assert want is not None
    got = _workbook_results(book, TIGHT, _model())
    assert set(got) == set(want)
    for key, value in want.items():
        assert math.isclose(got[key], value, abs_tol=LOAD_TOL), (direction, key, got[key], value)
    assert got["reaction.platform_base.fy"] * sign > 10.0
    assert got["reaction.platform_base.mx"] * sign < -100.0
    wind = sum(
        book(TIGHT.oop.addr("oop_winds", "fy_kN", i))
        for i in range(1, TIGHT.oop.tables["oop_winds"].capacity + 1)
    )
    assert math.isclose(wind, got["reaction.platform_base.fy"], abs_tol=1e-9)
    _assert_oop_matches_engine(book, TIGHT, _model(), case, direction)


def test_blank_bearing_diameter_hides_bearing_rows(tmp_path: Path) -> None:
    from crane_statics.calculation.engine import CraneCalculator
    from crane_statics.core.demand_extraction import extract_connection_component_response

    case = CASES["outofplane_wind_roll_sidelead"]
    kwargs = dataclasses.asdict(case)
    hoist_id = kwargs.pop("hoist_id")
    angle, hook = kwargs.pop("boom_angle_deg"), kwargs.pop("hook_load_kN")
    calc = CraneCalculator(load_document(YAML_PATH))
    pt = calc.compute_analysis_point(angle, hook, hoist_id, **kwargs)
    bearing = ("max_bearing_line_load", "min_bearing_line_load")
    for comp in bearing:
        # The app drops the row when the document has no diameter.
        assert extract_connection_component_response(pt, hook, "platform_base", comp, None) is None

    model = _model()
    model["structure"]["slewing_bearing_diameter_m"] = None
    path = tmp_path / "no_diameter.xlsx"
    build_workbook(model, case, path, TIGHT)
    book = _Book(path)
    _assert_book_clean(book, layout.OUT_OF_PLANE, layout.RESULTS, layout.CHECKS)
    assert book(TIGHT.total_issues_addr) == 0
    for comp in bearing:
        value = book(TIGHT.result_cell("platform_base", comp))
        assert isinstance(value, str) and "diameter" in value, value
    golden = _golden()["cases"]["outofplane_wind_roll_sidelead"]["app_results"]
    for comp in ("fradial", "mradial", "fy", "mx"):
        got = book(TIGHT.result_cell("platform_base", comp))
        assert math.isclose(got, golden[f"reaction.platform_base.{comp}"], abs_tol=LOAD_TOL)


# -- acceptance: the four 22689 cases, every sheet -----------------------------------

#: Golden keys the workbook deliberately does not produce: the heel's boom_axial and
#: boom_normal projections need the app's name-based heel axis node (reference.py rule 6).
EXPECTED_OMISSIONS = {
    f"reaction.{entity}.{component}"
    for entity in ("heel_point", "heel_left", "heel_right")
    for component in ("boom_axial", "boom_normal")
}
#: Acceptance tolerance: 0.01 kN for forces, 0.01 kNm for moments and 0.01 kN/m for the
#: platform bearing line loads (the same absolute figure in each row's own unit).
ACCEPT_TOL = 0.01

_CASE_BOOKS: dict[str, "_Book"] = {}


@pytest.fixture(scope="module")
def case_book(tmp_path_factory: pytest.TempPathFactory) -> Callable[[str], "_Book"]:
    """The recalculated delivered-layout workbook of a case (built once per module)."""

    def get(name: str) -> "_Book":
        if name not in _CASE_BOOKS:
            path = tmp_path_factory.mktemp(name) / f"accept_{name}.xlsx"
            build_workbook(_model(), CASES[name], path)
            _CASE_BOOKS[name] = _Book(path)
        return _CASE_BOOKS[name]

    return get


@pytest.mark.parametrize("name", sorted(CASE_NAMES))
def test_all_four_cases_within_tolerance(case_book: Callable[[str], "_Book"], name: str) -> None:
    book = case_book(name)
    golden = _golden()["cases"][name]["app_results"]
    got = _workbook_results(book, LAYOUT, _model())
    assert set(golden) - set(got) == EXPECTED_OMISSIONS, name
    assert set(got) <= set(golden), set(got) - set(golden)
    for key, value in got.items():
        assert isinstance(value, float), (name, key, value)
        assert math.isclose(value, golden[key], rel_tol=0.0, abs_tol=ACCEPT_TOL), (
            name,
            key,
            value,
            golden[key],
        )
    assert book(LAYOUT.results_cell("results_status", "message")) == "OK"
    assert book(LAYOUT.total_issues_addr) == 0


@pytest.mark.parametrize("name", sorted(CASE_NAMES))
def test_no_error_values_anywhere(case_book: Callable[[str], "_Book"], name: str) -> None:
    # Only a singular matrix may show #NUM!, in the raw MMULT(MINVERSE) column on
    # Statics; none of the 22689 cases is singular, so every sheet must be error-free.
    book = case_book(name)
    assert set(book.values) == set(layout.SHEETS)
    _assert_book_clean(book, *layout.SHEETS)
    assert sum(len(v) for v in book.values.values()) > 1000


def test_workbook_recalculates_on_open(tmp_path: Path) -> None:
    assert load_workbook(_build(tmp_path)).calculation.fullCalcOnLoad is True


@pytest.mark.parametrize(("diameter", "count"), [(0.0, 1), (-2.0, 1), (None, 0), (12.5, 0)])
def test_invalid_bearing_diameter_check(tmp_path: Path, diameter: float | None, count: int) -> None:
    model = _model()
    model["structure"]["slewing_bearing_diameter_m"] = diameter
    path = tmp_path / "bearing.xlsx"
    build_workbook(model, CASES["base"], path, TIGHT)
    book = _Book(path)
    assert book(TIGHT.check("invalid_bearing_diameter")) == count
    assert book(TIGHT.total_issues_addr) == count
