"""Reference values from the live app for the Excel validation workbook (22689).

Regenerate the golden file with ``python -m scripts.excel_workbook.reference`` from the
repo root (in a worktree whose venv has another checkout installed editable, set
``PYTHONPATH=src`` so this checkout's ``crane_statics`` is the one imported).

Everything here goes through the app's own code paths, so the golden values are what
the Scene view shows -- nothing is re-derived:

* ``app_results`` builds a ``SessionModel`` exactly as opening the file does
  (``set_document`` -> default design-limit catalog), selects the case's hoist, writes the
  case into the hoist's ``SceneState`` and calls
  ``AnalysisCalculator.compute_current_result_rows`` -- the call ``SceneViewModel`` makes
  to fill the Scene results table (rope rows and connection rows).
* ``scene_reaction_arrows`` builds the Scene's whole-crane ``BodyLoads`` (``SceneInputs``
  -> ``drawn_loads.build_body_loads``) for the same point; its ``Reactions`` category and
  reaction moments are the reaction arrows. They are the same numbers as the table's
  Fx/Fz rows (and platform-base My); the tests check that.

Which definition is used (there is only one per quantity in the Scene view): each value
is ``baseline + sensitivity * hook_load_kN`` of the ``AnalysisPoint`` solved at the
scene state, the hook load being the Scene's hook force in kN (payload + hook block,
times DAF, times g -- the case gives it directly). Rope tensions are the table's rope
rows, so the boom hoist (the ``tension_mode == "solve"`` rope) reads ``tension.BH``.

``app_results`` keys
--------------------
* ``tension.<hoist>`` -- one per rope row, named as the table names it (the hoist id
  owning the rope): ``tension.BH``, ``tension.MH``, ``tension.WH``, ``tension.SH`` (kN).
* ``reaction.<entity>.<component>`` -- one per connection row of the default
  design-limit catalog, component lower-cased (kN, kNm or kN/m):

  - ``heel_point``: ``fx fz resultant boom_axial boom_normal``
  - ``heel_left``, ``heel_right`` (out-of-plane split of the heel point):
    ``fx fz resultant boom_axial boom_normal``
  - ``front_hinge``, ``rear_hinge``: ``fx fz resultant leg_axial leg_normal``
  - ``upper_hinge``: ``fx fz resultant``
  - ``platform_base``: ``fx fy fz mx my fradial mradial max_bearing_line_load
    min_bearing_line_load``

  Pinned connections (heel point, hinges) report no moment. ``platform_base.my`` is the
  in-plane base moment (the arrow's moment); ``fy``/``mx`` are the out-of-plane pass.
  The hinge totals have no Fy row in the app; the front/rear leg left/right splits are
  computed by the engine but are not shown in the Scene, so they are not keys.

``expanded_model`` keys (read by Task 3)
----------------------------------------
``expanded_model(yaml_path)`` is the runtime model after ``normalize_document``, as plain
JSON. Lengths m, masses t, areas m^2, angles deg. Top level:

* ``source``: the YAML path as given.
* ``environment``: ``gravity_m_s2`` (signed, -9.81), ``gravity_abs_m_s2``,
  ``air_density_kg_m3``, ``max_wind_speed_m_s``, ``vessel_motion`` {``accel_x_m_s2``,
  ``accel_y_m_s2``, ``accel_z_m_s2``, ``roll_deg``, ``pitch_deg``,
  ``pitch_angular_accel_rad_s2``, ``roll_angular_accel_rad_s2``, ``reference_x_m``,
  ``reference_z_m``} (the motion values are the document's +/- limits, not used by a
  scene case; the reference point is used for pitch/roll lever arms).
* ``structure``: ``boom_width_m``, ``slewing_bearing_diameter_m`` and ``points``:
  {``boom_heel``, ``upper_hinge``, ``rear_hinge``, ``front_hinge``, ``platform_base``}
  -> {``node_id``, ``x_m``, ``z_m``}. ``node_id`` is the runtime node the point is
  (``rear_top``, ``rear_base``, ``front_base``, ...). The app also creates the derived
  nodes ``front_top`` (= upper hinge), ``platform_rear`` (= rear hinge),
  ``platform_front`` (= front hinge), ``platform_heel`` (= boom heel); they are in
  ``nodes``.
* ``bodies``: list of {``id``, ``mass_points``, ``wind_areas``}; body ids are the fixed
  ``boom``, ``rear_leg``, ``front_leg``, ``platform``.

  - mass point: {``id``, ``mass_t``, ``frame``, ``u_m``, ``v_m``, ``w_m``, ``x_m``,
    ``y_m``, ``z_m``}. ``frame`` is ``"boom_local"`` (use ``u_m``/``w_m`` along/normal to
    the boom from the heel, ``v_m`` lateral) or ``"global"`` (use ``x_m``/``y_m``/``z_m``);
    the unused triple is ``null``.
  - wind area: {``id``, ``cd``, ``area_x_m2`` (X wind; runtime ``area_w_m2``),
    ``area_y_m2`` (Y wind; runtime ``area_v_m2``), ``frame``, ``u_m``, ``w_m``, ``x_m``,
    ``z_m``}. Boom-local areas are scaled by ``|sin(boom angle)|`` in both directions.
* ``nodes``: list of {``id``, ``body``, ``frame``, ``x_m``, ``z_m``, ``u_m``, ``w_m``,
  ``below_node_id``, ``hanging_drop_m``, ``spool_node``}. ``frame`` is ``"boom_local"``
  (``u_m``/``w_m``), ``"global"`` (``x_m``/``z_m``) or ``"hanging"`` (the node hangs
  ``hanging_drop_m`` below ``below_node_id``; the active hoist's hook hangs the tackle
  length below it instead). ``spool_node`` is true for the node the app treats as the
  hoist's winch drum (first node id containing "winch" on that hoist's rope), which
  carries the rope not reeved.
* ``ropes``: list of {``id``, ``tension_mode`` (``"solve"`` or ``"fixed"``),
  ``linear_mass_kg_m``, ``segments``: [{``from_node_id``, ``to_node_id``, ``mult``}]}.
* ``hoists``: list of {``id``, ``rope_id``, ``is_payload`` (false for the boom hoist),
  ``load_node_id`` (hook node; for the boom hoist the boom sheave), ``support_node_id``,
  ``falls``, ``parts_at_hook`` (rope parts meeting the hook node, which the solver
  divides the hook load by), ``hook_mass_t``, ``hook_daf``, ``offlead_deg``,
  ``sidelead_deg`` (authored defaults), ``linear_mass_kg_m``, ``rope_length_m`` (total
  rope incl. spooled), ``max_hook_travel_m``, ``lowest_hook_height_m``,
  ``splitable_block``, ``split_falls``, ``split_hook_mass_t``, ``spool_node_id``}.

Name-based rules in the solver and models (audit, 2026-10-25)
-------------------------------------------------------------
Rules that key on id strings rather than on explicit fields:

1. ``calculation/rope_mass.py`` ``find_winch_node_ids``: a node whose id contains
   "winch" (case-insensitive) on a hoist's rope holds that hoist's spooled rope
   (``rope_length_m`` minus reeved length); a hoist with no such node loses its spooled
   mass. Workbook: explicit ``spool_node`` flag.
2. ``"boom_hoist"`` rope channel: the solve rope's tension is published under the
   channel ``"boom_hoist"``, not its rope id (``crane_solver._build_rope_response_maps``,
   ``drawn_loads.rope_tension_channel``, ``engine.resolve_limit_target``,
   ``demand_extraction._limit_rope_entity``, ``analysis_services.compute_result_rows``,
   ``formatters.HoistFormatter.runtime_rope_channel_to_rope_id``). Selection is by
   ``tension_mode == "solve"``; only the channel name is fixed. Workbook: a rope role
   column (solve/fixed).
3. ``rope_id == "boom_hoist"`` exclusions of idle hoists
   (``crane_solver._inactive_rope_mass_per_part``, ``drawn_loads._idle_hook_masses``):
   the runtime boom-hoist rope id is ``BH__rope``, so these never match; the boom hoist
   is excluded in effect only because its ``hook_mass_t`` is 0.
4. Fixed topology node ids: ``boom_heel``, ``rear_base``, ``rear_top``, ``front_base``,
   ``front_top``, ``platform_base``, ``platform_heel``, ``platform_rear``,
   ``platform_front`` (``crane_solver._run_statics``, ``engine._out_of_plane_geometry``
   support-group origins, ``drawn_loads.REACTION_SPECS``,
   ``kinematics.KinematicsAdapter``). Workbook: fixed structure-point inputs.
5. Fixed body ids: ``boom``, ``rear_leg``, ``front_leg``, ``platform``. Only body
   ``boom`` resolves boom-local (u, w) coordinates (kinematics, mass/wind rotation) and
   gets the ``|sin(angle)|`` wind-area scale (``crane_solver._wind_fx`` checks
   ``body_ids[bidx] == "boom"``; the out-of-plane pass checks ``body.id == "boom"``).
   Note ``build_solver_static_context`` treats any mass/wind with ``local_x_m`` as
   boom-local regardless of body. A node whose body is unknown defaults to ``boom`` for
   hook loads (``node_body_map.get(node_id, "boom")``).
6. Heel local axis priority list (``crane_solver._connection_local_axes_for_nodes``):
   the boom axis for ``heel_point``/``heel_left``/``heel_right`` ``boom_axial`` /
   ``boom_normal`` is heel -> first present node of ``mh_boom_sheave_3``,
   ``bh_sheave_3``, ``mh_boom_sheave_4``, ``ah_boom_sheave_3``, ``ah_boom_sheave_4``,
   ``sh_boom_sheave_3``, ``sh_boom_sheave_4``, ``mh_hook``, ``ah_hook``, ``sh_hook``
   (22689: ``mh_boom_sheave_3``; the axis is then *not* the boom angle, because that
   sheave sits at w = 3.85 m). Leg axes are ``rear_base -> rear_top`` and
   ``front_base -> front_top``.
7. Normalisation (``data/models.py``): reeving node ids get the hoist prefix
   (``bh_``, ``mh_`` ... via ``hoist_node_prefix``), rope ids are ``<hoist>__rope``, the
   boom hoist is id ``BH``, and each payload hoist gets a managed hook node
   ``__hook__<hoist>`` hanging below its support node. Presentation strips ``__rope`` /
   ``_rope`` suffixes for display (``HoistFormatter.display_name``), and limit ids
   ``<rope>_T`` try both suffixes (``engine.resolve_limit_target``).

No-solve-rope behaviour: an authored document always yields one solve rope (the
required ``model_definition.boom_hoist`` becomes ``BH__rope`` with
``tension_mode="solve"``). A runtime document without one gives an all-zero third column
in the boom 3x3 matrix ``[Hx, Hz, T_bh]``; ``np.linalg.solve`` raises, ``_run_statics``
returns ``{}``, the basis is ``None`` and ``compute_analysis_point`` returns ``None`` --
the Scene shows no results and no reaction arrows. There is no supported fallback.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crane_statics.calculation.engine import AnalysisPoint, clear_calculator_cache
from crane_statics.calculation.rope_mass import (
    active_hook_positions,
    find_winch_node_ids,
    rope_mass_at_nodes,
)
from crane_statics.calculation.solver.kinematics import KinematicsAdapter
from crane_statics.calculation.vessel_frame import VesselInputs, crane_frame_motion
from crane_statics.core import drawn_loads
from crane_statics.core.analysis_services import (
    AnalysisCalculator,
    HoistStateService,
    KinematicsService,
)
from crane_statics.core.io import load_document
from crane_statics.core.scene_build import SceneInputs
from crane_statics.core.session_model import SessionModel
from crane_statics.data.models import PRIMARY_STRUCTURE_TO_RUNTIME_NODE, CraneDocument

REPO_ROOT = Path(__file__).resolve().parents[2]
YAML_PATH = REPO_ROOT / "examples" / "crane_input_22689.yaml"
GOLDEN_PATH = REPO_ROOT / "tests" / "golden" / "22689_workbook_cases.json"

#: Scene connection entities that draw a reaction arrow (``drawn_loads.REACTION_SPECS``).
ARROW_ENTITIES = tuple(drawn_loads.REACTION_SPECS)


@dataclass(frozen=True)
class SceneCase:
    """The Scene inputs of one operating state (vessel-frame motion, as the Scene takes it)."""

    hoist_id: str
    boom_angle_deg: float
    hook_load_kN: float
    tackle_length_m: float
    offlead_deg: float = 0.0
    sidelead_deg: float = 0.0
    wind_speed_m_s: float = 0.0
    wind_direction: str = "+X"
    accel_x_m_s2: float = 0.0
    accel_y_m_s2: float = 0.0
    accel_z_m_s2: float = 0.0
    pitch_accel_rad_s2: float = 0.0
    roll_accel_rad_s2: float = 0.0
    vessel_roll_deg: float = 0.0
    vessel_pitch_deg: float = 0.0
    crane_slewing_angle_deg: float = 0.0


CASES: dict[str, SceneCase] = {
    # Dead weight, rope self-weight, idle hooks (WH, SH) and the MH hook load only.
    "base": SceneCase(
        hoist_id="MH",
        boom_angle_deg=60.0,
        hook_load_kN=6500.0,
        tackle_length_m=40.0,
    ),
    # In-plane wind (+X), vessel X/Z accelerations, pitch acceleration, vessel pitch and
    # offlead.
    "inplane_wind_accel": SceneCase(
        hoist_id="MH",
        boom_angle_deg=45.0,
        hook_load_kN=8000.0,
        tackle_length_m=60.0,
        offlead_deg=1.0,
        wind_speed_m_s=15.1,
        wind_direction="+X",
        accel_x_m_s2=0.6,
        accel_z_m_s2=-0.8,
        pitch_accel_rad_s2=0.03,
        vessel_pitch_deg=1.5,
    ),
    # Out-of-plane: Y wind, Y acceleration, roll acceleration, vessel roll (slewed, so it
    # also tilts gravity in-plane) and sidelead.
    "outofplane_wind_roll_sidelead": SceneCase(
        hoist_id="MH",
        boom_angle_deg=70.0,
        hook_load_kN=5000.0,
        tackle_length_m=30.0,
        sidelead_deg=2.5,
        wind_speed_m_s=15.1,
        wind_direction="+Y",
        accel_y_m_s2=0.5,
        roll_accel_rad_s2=0.02,
        vessel_roll_deg=2.0,
        crane_slewing_angle_deg=15.0,
    ),
    # WH carries the hook load; MH (102 t block, 20 falls) and SH are idle, their ropes
    # carrying m_hook * (g + az) / falls and their blocks hanging 1 m below the sheave.
    "idle_hoist": SceneCase(
        hoist_id="WH",
        boom_angle_deg=55.0,
        hook_load_kN=1450.0,
        tackle_length_m=50.0,
        accel_z_m_s2=0.4,
    ),
}


# -- expanded model -----------------------------------------------------------------


def _frame(body: str, local_x: Any, below: Any = None) -> str:
    if below is not None and local_x is None:
        return "hanging"
    return "boom_local" if body == "boom" and local_x is not None else "global"


def _mass_point(body_id: str, mp: dict[str, Any]) -> dict[str, Any]:
    frame = _frame(body_id, mp.get("local_x_m"))
    local = frame == "boom_local"
    return {
        "id": mp["id"],
        "mass_t": float(mp["mass_t"]),
        "frame": frame,
        "u_m": float(mp["local_x_m"]) if local else None,
        "v_m": float(mp.get("local_y_m") or 0.0) if local else None,
        "w_m": float(mp.get("local_z_m") or 0.0) if local else None,
        "x_m": None if local else float(mp["x_m"]),
        "y_m": None if local else float(mp.get("y_m") or 0.0),
        "z_m": None if local else float(mp["z_m"]),
    }


def _wind_area(body_id: str, wa: dict[str, Any]) -> dict[str, Any]:
    frame = _frame(body_id, wa.get("local_x_m"))
    local = frame == "boom_local"
    return {
        "id": wa["id"],
        "cd": float(wa["cd"]),
        "area_x_m2": float(wa["area_w_m2"]),
        "area_y_m2": float(wa["area_v_m2"]),
        "frame": frame,
        "u_m": float(wa["local_x_m"]) if local else None,
        "w_m": float(wa.get("local_z_m") or 0.0) if local else None,
        "x_m": None if local else float(wa["x_m"]),
        "z_m": None if local else float(wa["z_m"]),
    }


def _expanded_model_from_document(doc: CraneDocument, source: str) -> dict[str, Any]:
    dd = doc.model_dump()
    spool_by_hoist = {
        h["id"]: (find_winch_node_ids(dd, h["id"]) or [None])[0] for h in dd["hoists"]
    }
    spool_nodes = {node_id for node_id in spool_by_hoist.values() if node_id}
    node_by_id = {n["id"]: n for n in dd["nodes"]}
    env = dd["environment"]

    nodes = []
    for n in dd["nodes"]:
        frame = _frame(n["body"], n.get("local_x_m"), n.get("below_node_id"))
        local = frame == "boom_local"
        hanging = frame == "hanging"
        nodes.append(
            {
                "id": n["id"],
                "body": n["body"],
                "frame": frame,
                "x_m": None if local or hanging else float(n["x_m"]),
                "z_m": None if local or hanging else float(n["z_m"]),
                "u_m": float(n["local_x_m"]) if local else None,
                "w_m": float(n.get("local_z_m") or 0.0) if local else None,
                "below_node_id": n.get("below_node_id") if hanging else None,
                "hanging_drop_m": (
                    (1.0 if n.get("hanging_drop_m") is None else float(n["hanging_drop_m"]))
                    if hanging
                    else None
                ),
                "spool_node": n["id"] in spool_nodes,
            }
        )

    ropes = [
        {
            "id": r["id"],
            "tension_mode": "solve" if r.get("tension_mode") == "solve" else "fixed",
            "linear_mass_kg_m": float(r.get("linear_mass_kg_m") or 0.0),
            "segments": [
                {
                    "from_node_id": s["from_node_id"],
                    "to_node_id": s["to_node_id"],
                    "mult": int(s["mult"]),
                }
                for s in r["segments"]
            ],
        }
        for r in dd["ropes"]
    ]
    rope_by_id = {r["id"]: r for r in ropes}

    hoists = []
    for h in dd["hoists"]:
        rope = rope_by_id.get(h["rope_id"], {"segments": [], "tension_mode": "fixed"})
        hook = h["load_node_id"]
        parts = sum(
            s["mult"] for s in rope["segments"] if hook in (s["from_node_id"], s["to_node_id"])
        )
        hoists.append(
            {
                "id": h["id"],
                "rope_id": h["rope_id"],
                "is_payload": rope["tension_mode"] != "solve",
                "load_node_id": hook,
                "support_node_id": h.get("support_node_id"),
                "falls": h.get("falls"),
                "parts_at_hook": max(1, int(parts)),
                "hook_mass_t": float(h["hook_mass_t"]),
                "hook_daf": float(h["hook_daf"]),
                "offlead_deg": float(h["offlead_deg"]),
                "sidelead_deg": float(h["sidelead_deg"]),
                "linear_mass_kg_m": float(h.get("linear_mass_kg_m") or 0.0),
                "rope_length_m": h.get("rope_length_m"),
                "max_hook_travel_m": h.get("max_hook_travel_m"),
                "lowest_hook_height_m": h.get("lowest_hook_height_m"),
                "splitable_block": bool(h.get("splitable_block")),
                "split_falls": h.get("split_falls"),
                "split_hook_mass_t": h.get("split_hook_mass_t"),
                "spool_node_id": spool_by_hoist[h["id"]],
            }
        )

    points = {}
    for name, (node_id, _body) in PRIMARY_STRUCTURE_TO_RUNTIME_NODE.items():
        node = node_by_id[node_id]
        points[name] = {"node_id": node_id, "x_m": float(node["x_m"]), "z_m": float(node["z_m"])}
    base = node_by_id["platform_base"]
    points["platform_base"] = {
        "node_id": "platform_base",
        "x_m": float(base["x_m"]),
        "z_m": float(base["z_m"]),
    }

    return {
        "source": source,
        "environment": {
            "gravity_m_s2": float(env["gravity_m_s2"]),
            "gravity_abs_m_s2": abs(float(env["gravity_m_s2"])),
            "air_density_kg_m3": float(env["air_density_kg_m3"]),
            "max_wind_speed_m_s": float(env["max_wind_speed_m_s"]),
            "vessel_motion": {k: float(v) for k, v in env["vessel_motion"].items()},
        },
        "structure": {
            "boom_width_m": float(dd["support_widths"]["boom_width_m"]),
            "slewing_bearing_diameter_m": dd["support_widths"]["slewing_bearing_diameter_m"],
            "points": points,
        },
        "bodies": [
            {
                "id": b["id"],
                "mass_points": [_mass_point(b["id"], mp) for mp in b["mass_points"]],
                "wind_areas": [_wind_area(b["id"], wa) for wa in b["wind_areas"]],
            }
            for b in dd["bodies"]
        ],
        "nodes": nodes,
        "ropes": ropes,
        "hoists": hoists,
    }


def expanded_model(yaml_path: Path) -> dict[str, Any]:
    """The runtime (normalised) model of ``yaml_path`` as plain JSON; keys in the docstring."""
    return _expanded_model_from_document(load_document(Path(yaml_path)), str(yaml_path))


# -- live app results ---------------------------------------------------------------


def _scene_session(yaml_path: Path, case: SceneCase) -> tuple[SessionModel, AnalysisCalculator]:
    """A session opened on ``yaml_path`` with the case typed into the Scene."""
    clear_calculator_cache()  # the calculator cache is keyed by id(document)
    session = SessionModel()
    session.set_document(load_document(Path(yaml_path)), Path(yaml_path))
    session.select_payload_hoist(case.hoist_id)
    if session.selected_hoist_id != case.hoist_id:
        raise ValueError(f"{case.hoist_id!r} is not a payload hoist of {yaml_path}")
    state = session.get_active_hoist_state()
    assert state is not None
    for name, value in dataclasses.asdict(case).items():
        if name != "hoist_id":
            setattr(state.scene_state, name, value)
    kinematics = KinematicsService(session)
    calculator = AnalysisCalculator(session, kinematics, HoistStateService(session))
    return session, calculator


def _solve(yaml_path: Path, case: SceneCase) -> tuple[SessionModel, AnalysisCalculator, Any]:
    session, calculator = _scene_session(yaml_path, case)
    pt, rope_rows, conn_rows = calculator.compute_current_result_rows()
    if pt is None:
        raise RuntimeError(f"the app found no solution for {case}")
    return session, calculator, (pt, rope_rows, conn_rows)


def app_results(yaml_path: Path, case: SceneCase) -> dict[str, float]:
    """The Scene results table for ``case``: ``tension.<hoist>``, ``reaction.<entity>.<comp>``."""
    _session, _calculator, (_pt, rope_rows, conn_rows) = _solve(yaml_path, case)
    out: dict[str, float] = {}
    for row in rope_rows:
        out[f"tension.{row.name}"] = float(row.demand_kN)
    for row in conn_rows:
        out[f"reaction.{row.entity_id}.{str(row.component).lower()}"] = float(row.demand_kN)
    return out


def _scene_inputs(session: SessionModel, calculator: AnalysisCalculator, pt: Any) -> SceneInputs:
    doc = session.document
    assert doc is not None
    hoist_id = str(session.selected_hoist_id)
    state = session.get_active_hoist_state()
    assert state is not None
    document_dict = doc.model_dump()
    return SceneInputs(
        document_dict=document_dict,
        kinematics=KinematicsAdapter(document_dict),
        hoist_id=hoist_id,
        hoist=drawn_loads.active_hoist_dict(document_dict, hoist_id),
        conditions=calculator.drawn_load_conditions(),
        analysis_point=pt,
        tackle_length_m=float(state.scene_state.tackle_length_m),
    )


def scene_reaction_arrows(yaml_path: Path, case: SceneCase) -> dict[str, dict[str, float]]:
    """Whole-crane reaction arrows: {entity: {"fx", "fz"[, moment key]}} (as drawn)."""
    session, calculator, (pt, _rope_rows, _conn_rows) = _solve(yaml_path, case)
    inputs = _scene_inputs(session, calculator, pt)
    loads = inputs.body_loads(inputs.node_positions())
    arrows: dict[str, dict[str, float]] = {}
    for vector in loads.category(drawn_loads.REACTIONS):
        entity = vector.label.removeprefix("Reaction ")
        arrows[entity] = {"fx": vector.fx_kN, "fz": vector.fz_kN}
    for moment in loads.moments:
        key = moment.detail.split("\n")[1].split("=")[0].lower()
        arrows.setdefault(moment.entity_id, {})[key] = moment.moment_kNm
    return arrows


def _debug(session: SessionModel, calculator: AnalysisCalculator, pt: AnalysisPoint) -> dict:
    """Intermediate values for debugging the workbook (not compared by tests)."""
    doc = session.document
    assert doc is not None
    state = session.get_active_hoist_state()
    assert state is not None
    sc = state.scene_state
    dd = doc.model_dump()
    hoist_id = str(session.selected_hoist_id)
    positions = active_hook_positions(
        dd,
        hoist_id,
        KinematicsAdapter(dd).compute_all_node_positions(sc.boom_angle_deg),
        sc.tackle_length_m,
    )
    motion = crane_frame_motion(
        abs(float(doc.environment.gravity_m_s2)),
        VesselInputs(
            accel_x_m_s2=sc.accel_x_m_s2,
            accel_y_m_s2=sc.accel_y_m_s2,
            accel_z_m_s2=sc.accel_z_m_s2,
            roll_deg=sc.vessel_roll_deg,
            pitch_deg=sc.vessel_pitch_deg,
            slew_deg=sc.crane_slewing_angle_deg,
            roll_accel_rad_s2=sc.roll_accel_rad_s2,
            pitch_accel_rad_s2=sc.pitch_accel_rad_s2,
        ),
    )
    inputs = _scene_inputs(session, calculator, pt)
    loads = inputs.body_loads(inputs.node_positions())
    totals = {}
    for name, vectors in loads.categories:
        if name == drawn_loads.REACTIONS:
            continue
        totals[name] = {
            "fx_kN": sum(v.fx_kN for v in vectors),
            "fz_kN": sum(v.fz_kN for v in vectors),
            "m_about_platform_base_kNm": sum(
                v.world_x * v.fz_kN - v.world_z * v.fx_kN for v in vectors
            ),
        }
    return {
        "node_positions": {
            nid: {"x_m": float(p["x"]), "z_m": float(p["z"])} for nid, p in positions.items()
        },
        "rope_mass_t_by_node": {
            nid: entry.mass_t for nid, entry in rope_mass_at_nodes(dd, positions).items()
        },
        "crane_frame_motion": {
            "accel_x_m_s2": motion.accel_x_m_s2,
            "accel_y_m_s2": motion.accel_y_m_s2,
            "accel_z_m_s2": motion.accel_z_m_s2,
            "pitch_accel_rad_s2": motion.pitch_accel_rad_s2,
            "roll_accel_rad_s2": motion.roll_accel_rad_s2,
            "load_accel_m_s2": list(motion.load_accel),
        },
        "in_plane_load_totals": totals,
        "outreach_m": float(pt.outreach_m),
    }


def golden_cases(yaml_path: Path = YAML_PATH) -> dict[str, Any]:
    """The golden-file content for every case in ``CASES``."""
    cases: dict[str, Any] = {}
    for name, case in CASES.items():
        session, calculator, (pt, _r, _c) = _solve(yaml_path, case)
        cases[name] = {
            "inputs": dataclasses.asdict(case),
            "app_results": app_results(yaml_path, case),
            "debug": _debug(session, calculator, pt),
        }
    return {
        "source": "examples/crane_input_22689.yaml",
        "generator": "python -m scripts.excel_workbook.reference",
        "units": "kN, kNm, kN/m, m, t",
        "cases": cases,
    }


def main() -> None:
    content = golden_cases()
    GOLDEN_PATH.write_text(json.dumps(content, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    n = sum(len(c["app_results"]) for c in content["cases"].values())
    print(f"wrote {GOLDEN_PATH} ({len(content['cases'])} cases, {n} values)")


if __name__ == "__main__":
    main()
