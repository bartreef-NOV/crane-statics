"""Where everything lives in the validation workbook: the single source of truth.

The writer (``build*.py``) and the tests address cells only through this module, so no
address is hard-coded anywhere else. Later sheets read the inputs like this::

    lay = DEFAULT_LAYOUT                   # or the Layout passed to the writer
    lay.addr("nodes", "x_m", 3)            # 'Inputs!$E$140'  (3rd node row)
    lay.col_range("segments", "mult")      # 'Inputs!$E$224:$E$283'  (all rows)
    lay.cell("scene", "boom_angle_deg")    # 'Inputs!$B$27'
    lay.check("overflow")                  # 'Checks!$C$6'  (count, 0 = OK)
    lay.tables["nodes"].sheet_row(3)       # 140  (to align rows on other sheets)

(Addresses shown for the default capacities; never copy them into code.)

Writers must use the ``Layout`` they are given rather than ``DEFAULT_LAYOUT``: tests
rebuild with other capacities (``Layout(Capacities(nodes=...))``) and expect identical
results.

Inputs sheet
------------
Stacked top to bottom: the single-value blocks ``environment``, ``structure`` and
``scene`` (label in column A, value in B, unit in C, note in D), then one table per
variable-length list. Every table has the same shape::

    title row      title, "Capacity" n, "Rows not written (overflow)" count
    header row     human header with unit
    key row        the field key used by ``addr`` (grey)
    data rows      ``capacity`` rows; row i (1-based) is ``first_row + i - 1``
    guard row      must stay blank; anything typed here counts as overflow on Checks
    end note row

Contract for formulas reading the tables (spare rows)
-----------------------------------------------------
* Spare rows have ``active`` = 0 and every other cell blank. An unused coordinate in an
  active row (the boom-local triple of a global mass point, a hanging node's x/z, the
  boom hoist's blank ``support_node_id``/``falls``) is blank too.
* A blank cell reads as 0 in arithmetic and as ``""`` in text comparisons, so formulas
  must gate every row by ``active`` (multiply by it, or ``IF(active=1, ..., 0)``) and
  never divide by an input that may be blank or 0 without a guard. Row-wise formulas on
  other sheets return 0 (never an error) for inactive rows.
* Column-wide aggregates use ``col_range`` with ``SUMPRODUCT``/``SUMIFS``/``COUNTIFS``;
  do not use whole-column references or dynamic-array functions (Excel 2016, no spill).
  Avoid the ``--(...)`` coercion idiom: the ``formulas`` recalculation library evaluates
  it wrongly; write ``1*(...)`` or multiply two conditions instead.
* Id matching uses ``COUNTIFS``/``MATCH``, which are case-insensitive and treat ``*``,
  ``?`` and ``~`` as wildcards; the app's ids are case-sensitive plain strings. Keep ids
  free of wildcard characters and unique ignoring case.

Fixed structure nodes
---------------------
The nine fixed-topology node ids (``FIXED_NODE_POINTS``) are rows in the ``nodes`` table
like any other node, but their ``x_m``/``z_m`` cells are formulas linking to the
``structure`` block, so each structure point is typed once.

Geometry sheet
--------------
All formulas; nothing is typed here. Top to bottom: the conventions notes
(``GEOMETRY_NOTES``), the single-value blocks ``scene_geometry`` (boom rotation, the
active hook) and ``frame_motion`` (gravity, ``k = g - a`` and the other crane-frame
motion values), then the ``node_positions`` table, one row per ``nodes`` row (row i
here is Inputs ``nodes`` row i). Later sheets read them like this::

    lay.geo_cell("frame_motion", "kx")              # 'Geometry!$B$40'
    lay.geo_addr("node_positions", "z_m", 3)        # 'Geometry!$L$75'  (3rd node)
    lay.geo_col_range("node_positions", "x_m")      # all node rows
    lay.geo_tables["node_positions"].sheet_row(3)

Spare node rows read 0 in every numeric column (the ``id`` column reads "").

Loads sheet
-----------
All formulas. The notes (``LOADS_NOTES``), the single-value block ``load_scene``, then one
table per Inputs list (row i = the Inputs row i: ``mass_loads``, ``wind_loads``,
``rope_tensions``, ``hoist_ropes``, ``segment_loads``, ``node_loads``) and ``body_totals``
(one row per ``BODIES`` entry, in that order). Statics reads the body totals::

    lay.body_total("boom", "fx")        # known in-plane loads on the boom (solver ld Fx)
    lay.body_total("boom", "bh_m")      # solve-rope moment per kN of its tension (bh M)
    lay.loads_addr("node_loads", "bh_fx", 3)
    lay.loads_col_range("rope_tensions", "tension_kN")
    lay.loads_cell("load_scene", "hook_kN")

Statics sheet
-------------
All formulas. The notes (``STATICS_NOTES``), then ``_STATICS_SECTIONS`` top to bottom: the
blocks ``statics_status``, ``structure_nodes``, ``leg_loads``, ``platform``, ``leg_axes`` and
the matrix systems ``boom_system`` (3x3) and ``leg_system`` (6x6), each a ``MatrixSystem``
(matrix A, right-hand side b, raw MMULT(MINVERSE) column, solution used, row norms, then
det / rel_det / singular rows)::

    lay.statics_value("t_bh")             # any _run_statics output (STATICS_UNKNOWNS)
    lay.statics_flag("leg_system")        # 1 = singular
    lay.statics_cell("statics_status", "ok")
    lay.statics_systems["boom_system"].a_addr(3, 1)

Results sheet
-------------
The notes, the ``results_status`` block (``ok``, ``reason``, ``message``), the
``tensions`` table (row i = Inputs hoists row i) and the ``reactions`` table (one row per
``RESULT_ROWS`` entry; Task 7 appends out-of-plane rows there)::

    lay.results_addr("tensions", "tension_kN", 2)
    lay.result_cell("platform_base", "my")     # value of reaction.platform_base.my
    lay.result_rows                            # ((entity, component), ...)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from openpyxl.utils import get_column_letter

# -- sheets --------------------------------------------------------------------------

CONVENTIONS = "Conventions"
INPUTS = "Inputs"
GEOMETRY = "Geometry"
LOADS = "Loads"
STATICS = "Statics"
RESULTS = "Results"
CHECKS = "Checks"
#: Workbook sheet order.
SHEETS = (CONVENTIONS, INPUTS, GEOMETRY, LOADS, STATICS, RESULTS, CHECKS)

# -- capacities (22689: 9 mass points, 8 wind areas, 29 nodes, 16 segments, 4 ropes,
# 4 hoists) --------------------------------------------------------------------------

MAX_MASS_POINTS = 40
MAX_WIND_AREAS = 40
MAX_NODES = 80
MAX_SEGMENTS = 60
MAX_ROPES = 8
MAX_HOISTS = 8

Kind = Literal["flag", "num", "text"]

BODIES = ("boom", "rear_leg", "front_leg", "platform")
POINT_FRAMES = ("boom_local", "global")
NODE_FRAMES = ("boom_local", "global", "hanging")
ROPE_ROLES = ("fixed", "solve")
WIND_DIRECTIONS = ("+X", "-X", "+Y", "-Y")

#: Fixed-topology node id -> structure point whose coordinates it takes (the app's
#: ``PRIMARY_STRUCTURE_TO_RUNTIME_NODE`` plus the derived nodes it creates).
FIXED_NODE_POINTS = {
    "boom_heel": "boom_heel",
    "platform_heel": "boom_heel",
    "rear_top": "upper_hinge",
    "front_top": "upper_hinge",
    "rear_base": "rear_hinge",
    "platform_rear": "rear_hinge",
    "front_base": "front_hinge",
    "platform_front": "front_hinge",
    "platform_base": "platform_base",
}
STRUCTURE_POINTS = ("boom_heel", "upper_hinge", "rear_hinge", "front_hinge", "platform_base")


@dataclass(frozen=True)
class Field:
    """One input: a table column or a single-value cell."""

    key: str
    header: str
    unit: str = ""
    kind: Kind = "num"
    #: Allowed values (an Excel list validation), if any.
    choices: tuple[str, ...] = ()
    note: str = ""


def _f(key: str, header: str, unit: str = "", kind: Kind = "num", choices=(), note="") -> Field:
    return Field(key, header, unit, kind, tuple(choices), note)


_ACTIVE = _f("active", "Active", "1/0", "flag", note="1 = row in use, 0 = spare")


@dataclass(frozen=True)
class Table:
    """A fixed-capacity table on a sheet; rows are numbered 1..capacity."""

    name: str
    title: str
    sheet: str
    fields: tuple[Field, ...]
    capacity: int
    title_row: int

    @property
    def header_row(self) -> int:
        return self.title_row + 1

    @property
    def key_row(self) -> int:
        return self.title_row + 2

    @property
    def first_row(self) -> int:
        return self.title_row + 3

    @property
    def last_row(self) -> int:
        return self.first_row + self.capacity - 1

    @property
    def guard_row(self) -> int:
        return self.last_row + 1

    @property
    def end_row(self) -> int:
        """Last row the table uses (the end note)."""
        return self.guard_row + 1

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(f.key for f in self.fields)

    def column(self, key: str) -> str:
        """Column letter of ``key``."""
        for index, f in enumerate(self.fields, start=1):
            if f.key == key:
                return str(get_column_letter(index))
        raise KeyError(f"table {self.name!r} has no field {key!r}")

    @property
    def last_column(self) -> str:
        return str(get_column_letter(len(self.fields)))

    def sheet_row(self, row: int) -> int:
        if not 1 <= row <= self.capacity:
            raise IndexError(f"{self.name} row {row} outside 1..{self.capacity}")
        return self.first_row + row - 1

    def addr(self, key: str, row: int) -> str:
        return f"{self.sheet}!${self.column(key)}${self.sheet_row(row)}"

    def col_range(self, key: str) -> str:
        col = self.column(key)
        return f"{self.sheet}!${col}${self.first_row}:${col}${self.last_row}"

    def guard_addr(self, key: str) -> str:
        return f"{self.sheet}!${self.column(key)}${self.guard_row}"

    @property
    def guard_range(self) -> str:
        return f"{self.sheet}!$A${self.guard_row}:${self.last_column}${self.guard_row}"

    #: Title-row cells: "Capacity" label in D, value in E; overflow label in F, count in G.
    @property
    def capacity_addr(self) -> str:
        return f"{self.sheet}!$E${self.title_row}"

    @property
    def overflow_addr(self) -> str:
        """Rows the generator could not write (more rows than ``capacity``)."""
        return f"{self.sheet}!$G${self.title_row}"


@dataclass(frozen=True)
class Block:
    """Single-value cells: label in column A, value in B, unit in C, note in D."""

    name: str
    title: str
    sheet: str
    fields: tuple[Field, ...]
    title_row: int

    @property
    def end_row(self) -> int:
        return self.title_row + len(self.fields)

    def row(self, key: str) -> int:
        for index, f in enumerate(self.fields, start=1):
            if f.key == key:
                return self.title_row + index
        raise KeyError(f"block {self.name!r} has no field {key!r}")

    def addr(self, key: str) -> str:
        return f"{self.sheet}!$B${self.row(key)}"


# -- field definitions ---------------------------------------------------------------

ENVIRONMENT_FIELDS = (
    _f("gravity_m_s2", "Gravity (signed, as authored)", "m/s^2", note="|g| is used"),
    _f("air_density_kg_m3", "Air density", "kg/m^3"),
    _f(
        "max_wind_speed_m_s",
        "Max wind speed (document)",
        "m/s",
        note="information only; the scene wind speed is below",
    ),
    _f("reference_x_m", "Vessel motion reference x", "m", note="pitch/roll lever-arm origin"),
    _f("reference_z_m", "Vessel motion reference z", "m", note="pitch/roll lever-arm origin"),
)

_POINT_NODE = {
    "boom_heel": "boom_heel (also platform_heel)",
    "upper_hinge": "rear_top (also front_top)",
    "rear_hinge": "rear_base (also platform_rear)",
    "front_hinge": "front_base (also platform_front)",
    "platform_base": "platform_base",
}

STRUCTURE_FIELDS = (
    _f("boom_width_m", "Boom width (heel left/right spacing)", "m"),
    _f(
        "slewing_bearing_diameter_m",
        "Slewing bearing diameter",
        "m",
        note="optional; only bearing line loads use it",
    ),
) + tuple(
    _f(
        f"{point}_{axis}_m",
        f"{point.replace('_', ' ').capitalize()} {axis}",
        "m",
        note=f"node {_POINT_NODE[point]}",
    )
    for point in STRUCTURE_POINTS
    for axis in ("x", "z")
)

SCENE_FIELDS = (
    _f("hoist_id", "Hook-loaded hoist id", kind="text", note="a hoist with a fixed rope"),
    _f("boom_angle_deg", "Boom angle", "deg", note="from +x toward +z"),
    _f("hook_load_kN", "Hook load (payload + hook block) x DAF x g", "kN"),
    _f("tackle_length_m", "Tackle length (support sheave to hook)", "m"),
    _f("offlead_deg", "Offlead", "deg"),
    _f("sidelead_deg", "Sidelead", "deg"),
    _f("wind_speed_m_s", "Wind speed", "m/s"),
    _f("wind_direction", "Wind direction", kind="text", choices=WIND_DIRECTIONS),
    _f("accel_x_m_s2", "Vessel acceleration ax", "m/s^2"),
    _f("accel_y_m_s2", "Vessel acceleration ay", "m/s^2"),
    _f("accel_z_m_s2", "Vessel acceleration az", "m/s^2"),
    _f("pitch_accel_rad_s2", "Pitch angular acceleration", "rad/s^2"),
    _f("roll_accel_rad_s2", "Roll angular acceleration", "rad/s^2"),
    _f("vessel_roll_deg", "Vessel roll", "deg", note="positive to starboard"),
    _f("vessel_pitch_deg", "Vessel pitch", "deg", note="positive bow-down"),
    _f("crane_slewing_angle_deg", "Crane slewing angle", "deg"),
)

MASS_POINT_FIELDS = (
    _ACTIVE,
    _f("id", "Id", kind="text"),
    _f("body", "Body", kind="text", choices=BODIES),
    _f("frame", "Frame", kind="text", choices=POINT_FRAMES, note="boom_local uses u/v/w"),
    _f("mass_t", "Mass", "t"),
    _f("u_m", "u (along boom)", "m"),
    _f("v_m", "v (lateral)", "m"),
    _f("w_m", "w (boom normal)", "m"),
    _f("x_m", "x", "m"),
    _f("y_m", "y", "m"),
    _f("z_m", "z", "m"),
)

WIND_AREA_FIELDS = (
    _ACTIVE,
    _f("id", "Id", kind="text"),
    _f("body", "Body", kind="text", choices=BODIES),
    _f("frame", "Frame", kind="text", choices=POINT_FRAMES, note="boom_local uses u/w"),
    _f("cd", "Cd"),
    _f("area_x_m2", "Area for X wind", "m^2"),
    _f("area_y_m2", "Area for Y wind", "m^2"),
    _f("u_m", "u (along boom)", "m"),
    _f("w_m", "w (boom normal)", "m"),
    _f("x_m", "x", "m"),
    _f("z_m", "z", "m"),
)

NODE_FIELDS = (
    _ACTIVE,
    _f("id", "Id", kind="text"),
    _f("body", "Body", kind="text", choices=BODIES),
    _f("frame", "Frame", kind="text", choices=NODE_FRAMES),
    _f("x_m", "x", "m"),
    _f("z_m", "z", "m"),
    _f("u_m", "u (along boom)", "m"),
    _f("w_m", "w (boom normal)", "m"),
    _f("below_node_id", "Hangs below node", kind="text"),
    _f("hanging_drop_m", "Hanging drop", "m", note="idle hooks; the active hook uses tackle"),
    _f("spool_node", "Spool node", "1/0", "flag", note="holds the rope not reeved"),
)

SEGMENT_FIELDS = (
    _ACTIVE,
    _f("rope_id", "Rope id", kind="text"),
    _f("from_node_id", "From node", kind="text"),
    _f("to_node_id", "To node", kind="text"),
    _f("mult", "Parts (multiplier)"),
)

ROPE_FIELDS = (
    _ACTIVE,
    _f("id", "Id", kind="text"),
    _f(
        "role",
        "Role",
        kind="text",
        choices=ROPE_ROLES,
        note="solve = boom hoist (tension solved); fixed = hoist rope",
    ),
)

HOIST_FIELDS = (
    _ACTIVE,
    _f("id", "Id", kind="text"),
    _f("rope_id", "Rope id", kind="text"),
    _f("load_node_id", "Hook node", kind="text", note="boom hoist: its boom sheave"),
    _f("support_node_id", "Support node", kind="text", note="sheave the hook hangs below"),
    _f("falls", "Falls"),
    _f("hook_mass_t", "Hook block mass", "t"),
    _f("hook_daf", "Hook DAF"),
    _f("offlead_deg", "Offlead (document default)", "deg", note="scene value is used"),
    _f("sidelead_deg", "Sidelead (document default)", "deg", note="scene value is used"),
    _f("linear_mass_kg_m", "Rope linear mass", "kg/m"),
    _f("rope_length_m", "Total rope length (incl. spooled)", "m"),
    _f("max_hook_travel_m", "Max hook travel", "m", note="information only"),
    _f("lowest_hook_height_m", "Lowest hook height", "m", note="information only"),
    _f("splitable_block", "Splitable block", "1/0", "flag", note="split mode unsupported"),
    _f("split_falls", "Split falls", note="split mode unsupported"),
    _f("split_hook_mass_t", "Split hook mass", "t", note="split mode unsupported"),
)

# -- Geometry sheet ------------------------------------------------------------------

#: Sign and angle conventions printed at the top of the Geometry sheet.
GEOMETRY_NOTES: tuple[str, ...] = (
    "Crane (global) frame: x horizontal outboard, y lateral, z up; node positions are (x, z).",
    "Boom angle: degrees from +x toward +z, about the boom heel (node boom_heel). "
    "Boom-local (u, w): u along the boom, w normal (left of u). "
    "x = heel_x + u*cos(a) - w*sin(a); z = heel_z + u*sin(a) + w*cos(a).",
    "Hanging nodes sit directly below their parent node (same x, z lower by the drop). "
    "A missing drop counts as 1 m (the app's default). One level of hanging only "
    "(a hanging node whose parent is hanging trips the hanging_chain check).",
    "The active hook (the scene hoist's hook node) hangs the tackle length below its support "
    "node instead of its idle drop. Support node = the hook node's parent, else the hoist's "
    "support node. A negative tackle length counts as 0.",
    "Vessel frame: x forward, y port, z up. Pitch positive bow-down, roll positive to "
    "starboard; yaw drops out. Gravity in the vessel frame: (g sin p, -g sin r cos p, "
    "-g cos r cos p), g = |gravity|.",
    "Crane frame = vessel frame rotated about z by the slewing angle: a horizontal vessel "
    "vector (x, y) becomes (cos s x + sin s y, -sin s x + cos s y). z is unchanged.",
    "Load acceleration k = g - a (crane frame); the solver's equivalent reference "
    "acceleration is -k horizontally and -g - kz vertically (solver_ax/ay/az).",
)

GEOMETRY_SCENE_FIELDS = (
    _f("boom_angle_rad", "Boom angle", "rad"),
    _f("boom_cos", "cos(boom angle)"),
    _f("boom_sin", "sin(boom angle)"),
    _f("heel_row", "Row of node boom_heel in nodes", "row", note="0 = missing"),
    _f("heel_x_m", "Boom heel x", "m"),
    _f("heel_z_m", "Boom heel z", "m"),
    _f("tackle_m", "Tackle length used", "m", note="max(0, scene value)"),
    _f("hook_id", "Active hook node id", kind="text"),
    _f("hook_row", "Row of the hook node in nodes", "row", note="0 = missing"),
    _f("hook_parent_id", "Hook node's parent (below_node_id)", kind="text"),
    _f("support_id", "Hook support node id", kind="text"),
    _f("support_row", "Row of the support node in nodes", "row", note="0 = missing"),
    _f("support_z_m", "Support node z (before the hook moves)", "m"),
    _f("hook_moves", "Hook is lowered by the tackle", "1/0", "flag"),
)

GEOMETRY_MOTION_FIELDS = (
    _f("g_m_s2", "Gravity magnitude |g|", "m/s^2"),
    _f("roll_rad", "Vessel roll", "rad"),
    _f("pitch_rad", "Vessel pitch", "rad"),
    _f("slew_rad", "Slewing angle", "rad"),
    _f("slew_cos", "cos(slew)"),
    _f("slew_sin", "sin(slew)"),
    _f("gx_vessel", "Gravity x, vessel frame", "m/s^2"),
    _f("gy_vessel", "Gravity y, vessel frame", "m/s^2"),
    _f("gz_vessel", "Gravity z, vessel frame", "m/s^2"),
    _f("kx_vessel", "k x = g - a, vessel frame", "m/s^2"),
    _f("ky_vessel", "k y = g - a, vessel frame", "m/s^2"),
    _f("gx", "Gravity x, crane frame", "m/s^2"),
    _f("gy", "Gravity y, crane frame", "m/s^2"),
    _f("gz", "Gravity z, crane frame", "m/s^2"),
    _f("ax", "Vessel acceleration x, crane frame", "m/s^2"),
    _f("ay", "Vessel acceleration y, crane frame", "m/s^2"),
    _f("az", "Vessel acceleration z, crane frame", "m/s^2"),
    _f("kx", "Load acceleration kx = gx - ax", "m/s^2"),
    _f("ky", "Load acceleration ky = gy - ay", "m/s^2"),
    _f("kz", "Load acceleration kz = gz - az", "m/s^2"),
    _f("solver_ax", "Solver reference acceleration x (= -kx)", "m/s^2"),
    _f("solver_ay", "Solver reference acceleration y (= -ky)", "m/s^2"),
    _f("solver_az", "Solver reference acceleration z (= -g - kz)", "m/s^2"),
    _f("pitch_accel_crane", "Pitch angular acceleration, crane frame", "rad/s^2"),
    _f("roll_accel_crane", "Roll angular acceleration, crane frame", "rad/s^2"),
)

NODE_POSITION_FIELDS = (
    _f("active", "Active", "1/0", "flag", note="from Inputs"),
    _f("id", "Id", kind="text"),
    _f("frame", "Frame", kind="text"),
    _f("x_base_m", "x (boom-local rotated, or global; 0 if hanging)", "m"),
    _f("z_base_m", "z (boom-local rotated, or global; 0 if hanging)", "m"),
    _f("parent_row", "Row of the parent node (hanging)", "row", note="0 = none"),
    _f("drop_m", "Drop below parent (hanging)", "m"),
    _f("x_kin_m", "x (kinematics: hanging resolved)", "m"),
    _f("z_kin_m", "z (kinematics: hanging resolved)", "m"),
    _f("is_hook", "Active hook node", "1/0", "flag"),
    _f("x_m", "x global", "m", note="the position the solver uses"),
    _f("z_m", "z global", "m", note="the position the solver uses"),
)

# -- Loads sheet ---------------------------------------------------------------------

#: Notes printed at the top of the Loads sheet.
LOADS_NOTES: tuple[str, ...] = (
    "In-plane (x, z) loads on the four bodies, row by row, as the solver accumulates them "
    "(calculation/solver/crane_solver.py _accumulate_loads). Moments are about the origin: "
    "M = x Fz - z Fx.",
    "Mass load = weight m g' (Gravity) + inertia -m (a' + lever x pitch') (Inertia); their sum "
    "is the solver's inertia_force with k = g - a. dx = x - x_ref, dz = z - z_ref.",
    "Rope self-weight is lumped at nodes (calculation/rope_mass.py rope_mass_at_nodes) and "
    "loaded like a mass point (gravity + inertia, column group 'rope weight').",
    "Rope tension: the scene hoist's rope carries hook load / parts at the hook; an idle "
    "hoist's rope m_hook (|g| + az') / parts (az' = solver_az on Geometry). The solve (boom "
    "hoist) rope has an unknown tension: its unit-tension coefficients bh_* are listed and "
    "Statics multiplies them by the solved tension.",
    "Parts at the hook = sum of the multipliers of the rope's active segments touching the "
    "hook node (min 1), as the solver does outside split mode; the hoists' Falls column is "
    "not used here (equal to those parts for 22689).",
    "Split-block mode is NOT supported: the hoists' splitable / split falls / split hook "
    "mass columns are ignored (the app's normal mode).",
    "Spare and inactive rows read 0; a zero-length segment carries no force.",
)

#: Single-value cells shared by the Loads tables.
LOADS_SCENE_FIELDS = (
    _f("ref_x_m", "Vessel motion reference x", "m"),
    _f("ref_z_m", "Vessel motion reference z", "m"),
    _f("gx", "Gravity x, crane frame (g')", "m/s^2", note="Geometry"),
    _f("gz", "Gravity z, crane frame (g')", "m/s^2", note="Geometry"),
    _f("ax", "Vessel acceleration x, crane frame (a')", "m/s^2", note="Geometry"),
    _f("az", "Vessel acceleration z, crane frame (a')", "m/s^2", note="Geometry"),
    _f("pitch", "Pitch angular acceleration, crane frame", "rad/s^2", note="Geometry"),
    _f("idle_accel", "Idle rope acceleration |g| + solver_az", "m/s^2"),
    _f("wind_sign", "In-plane wind sign", "+1/-1/0", note="+X: 1, -X: -1, +Y/-Y: 0"),
    _f("wind_q_kN_m2", "0.5 rho V^2 / 1000", "kN/m^2"),
    _f("boom_wind_scale", "|sin(boom angle)| (body boom areas)"),
    _f("hook_kN", "Hook load", "kN", note="scene value, as the solver uses it"),
    _f("offlead_fx_kN", "Offlead force sin(offlead) x hook load", "kN", note="+x"),
    _f("hook_row", "Row of the hook node in nodes", "row", note="0 = missing"),
    _f(
        "anchor_row",
        "Row of the offlead node (hook's parent, else the hook)",
        "row",
        note="0 = missing",
    ),
    _f("scene_rope_id", "Rope of the scene hoist", kind="text"),
)

MASS_LOAD_FIELDS = (
    _f("active", "Active", "1/0", "flag", note="from Inputs"),
    _f("body", "Body", kind="text"),
    _f("x_m", "x global", "m", note="boom-local rotated about the heel"),
    _f("z_m", "z global", "m"),
    _f("mass_t", "Mass", "t"),
    _f("grav_fx", "Weight Fx = m gx'", "kN"),
    _f("grav_fz", "Weight Fz = m gz'", "kN"),
    _f("grav_m", "Weight moment", "kNm"),
    _f("inertia_fx", "Inertia Fx = -m (ax' + pitch' dz)", "kN"),
    _f("inertia_fz", "Inertia Fz = -m (az' - pitch' dx)", "kN"),
    _f("inertia_m", "Inertia moment", "kNm"),
    _f("fx", "Fx total", "kN", note="crane_solver inertia_force"),
    _f("fz", "Fz total", "kN"),
    _f("m", "Moment total", "kNm"),
)

WIND_LOAD_FIELDS = (
    _f("active", "Active", "1/0", "flag", note="from Inputs"),
    _f("body", "Body", kind="text"),
    _f("x_m", "x global", "m"),
    _f("z_m", "z global", "m"),
    _f("area_m2", "Area for X wind", "m^2"),
    _f("scale", "Area scale", note="|sin(boom angle)| on body boom, else 1"),
    _f("fx", "Wind Fx = sign q Cd A scale", "kN", note="crane_solver _wind_fx"),
    _f("m", "Wind moment = -z Fx", "kNm"),
)

ROPE_TENSION_FIELDS = (
    _f("active", "Active", "1/0", "flag", note="from Inputs"),
    _f("id", "Rope id", kind="text"),
    _f("id_key", "Rope id if active", kind="text", note="'' if spare"),
    _f("role", "Role", kind="text"),
    _f("is_solve", "Solve rope", "1/0", "flag"),
    _f("is_scene", "Scene hoist's rope", "1/0", "flag"),
    _f("hoist_row", "Row of its hoist in hoists", "row", note="first active hoist; 0 = none"),
    _f("hook_node_id", "Its hoist's hook node", kind="text"),
    _f("n_parts", "Parts at the hook", note="max(1, sum of mults touching the hook)"),
    _f("hook_mass_t", "Its hoist's hook mass", "t"),
    _f("tension_kN", "Tension", "kN", note="0 for the solve rope (solved on Statics)"),
)

HOIST_ROPE_FIELDS = (
    _f("active", "Active", "1/0", "flag", note="from Inputs"),
    _f("id_key", "Hoist id if active", kind="text"),
    _f("rope_key", "Rope id if active", kind="text"),
    _f("is_scene", "Scene hoist", "1/0", "flag"),
    _f("rope_ok", "Rope is an active rope", "1/0", "flag"),
    _f("linear_mass_kg_m", "Rope linear mass used", "kg/m", note="0 if no rope"),
    _f("hook_row", "Row of the hook node in nodes", "row", note="0 = missing"),
    _f("reeved_m", "Reeved length (sum length x parts)", "m"),
    _f("spool_node_id", "Spool node", kind="text", note="first flagged node on its rope"),
    _f("spooled_m", "Spooled length max(0, total - reeved)", "m"),
    _f("spooled_t", "Spooled rope mass", "t"),
    _f("idle_mass_t", "Idle hook block mass", "t", note="0 for the scene hoist"),
)

SEGMENT_LOAD_FIELDS = (
    _f("active", "Active", "1/0", "flag", note="from Inputs"),
    _f("rope_id", "Rope id", kind="text"),
    _f("role", "Rope role", kind="text", note="'' if the rope is missing"),
    _f("from_row", "Row of the from node", "row", note="0 = missing"),
    _f("to_row", "Row of the to node", "row", note="0 = missing"),
    _f("ok", "Segment used", "1/0", "flag", note="active, both nodes and rope found"),
    _f("xa_m", "From x", "m"),
    _f("za_m", "From z", "m"),
    _f("xb_m", "To x", "m"),
    _f("zb_m", "To z", "m"),
    _f("length_m", "Length", "m"),
    _f("ux", "Unit vector x (from -> to)", note="0 if length < 1e-9"),
    _f("uz", "Unit vector z (from -> to)"),
    _f("mult", "Parts (multiplier)"),
    _f("tension_kN", "Rope tension", "kN", note="fixed ropes"),
    _f("fx", "Force on from node Fx = T ux parts", "kN", note="to node gets -Fx"),
    _f("fz", "Force on from node Fz = T uz parts", "kN", note="to node gets -Fz"),
    _f("bh_fx", "Solve rope: ux parts", "kN/kN", note="per kN of solved tension"),
    _f("bh_fz", "Solve rope: uz parts", "kN/kN"),
    _f("reeved_m", "Reeved length = length x max(1, parts)", "m"),
    _f("linear_mass_kg_m", "Linear mass (its hoists)", "kg/m"),
    _f("half_mass_t", "Half the segment's rope mass (each end)", "t"),
    _f("spool_end", "Flagged spool node at an end", kind="text"),
    _f("has_spool", "Has a spool end", "1/0", "flag"),
    _f("spool_seq", "Spool ends so far on this rope", note="1 = first"),
    _f("spool_key", "Rope id if first spool end", kind="text"),
)

NODE_LOAD_FIELDS = (
    _f("active", "Active", "1/0", "flag", note="from Inputs"),
    _f("id", "Id", kind="text"),
    _f("body", "Body", kind="text"),
    _f("x_m", "x global", "m", note="Geometry"),
    _f("z_m", "z global", "m", note="Geometry"),
    _f("reeved_t", "Reeved rope mass (half of each segment)", "t"),
    _f("spooled_t", "Spooled rope mass", "t"),
    _f("rope_mass_t", "Rope mass at node", "t"),
    _f("rw_fx", "Rope weight + inertia Fx", "kN"),
    _f("rw_fz", "Rope weight + inertia Fz", "kN"),
    _f("rw_m", "Rope weight moment", "kNm"),
    _f("idle_mass_t", "Idle hook block mass", "t"),
    _f("idle_grav_fx", "Idle hook weight Fx", "kN"),
    _f("idle_grav_fz", "Idle hook weight Fz", "kN"),
    _f("idle_grav_m", "Idle hook weight moment", "kNm"),
    _f("idle_inertia_fx", "Idle hook inertia Fx", "kN"),
    _f("idle_inertia_fz", "Idle hook inertia Fz", "kN"),
    _f("idle_inertia_m", "Idle hook inertia moment", "kNm"),
    _f("hook_fz", "Hook load Fz = -hook load", "kN", note="at the hook node"),
    _f("offlead_fx", "Offlead Fx", "kN", note="at the hook's parent node"),
    _f("hook_m", "Hook load moment", "kNm"),
    _f("rope_fx", "Fixed-rope forces Fx", "kN", note="sum over segments"),
    _f("rope_fz", "Fixed-rope forces Fz", "kN"),
    _f("rope_m", "Fixed-rope moment", "kNm"),
    _f("bh_fx", "Solve rope coefficient Fx", "kN/kN"),
    _f("bh_fz", "Solve rope coefficient Fz", "kN/kN"),
    _f("bh_m", "Solve rope coefficient moment", "kNm/kN"),
    _f("fx", "Known load Fx (all but solve rope)", "kN"),
    _f("fz", "Known load Fz", "kN"),
    _f("m", "Known load moment", "kNm"),
)

#: Load categories of the body totals, named as ``core/drawn_loads.py`` names them.
LOAD_CATEGORIES: dict[str, str] = {
    "gravity": "Gravity",
    "rope_weight": "Rope weight",
    "idle_hook": "Idle hook mass",
    "hook": "Hook load",
    "wind": "Wind",
    "inertia": "Inertia",
    "rope": "Rope interface",
}

BODY_TOTAL_FIELDS = (
    (_f("body", "Body", kind="text"),)
    + tuple(
        _f(f"{cat}_{comp}", f"{title} {comp.upper()}", "kNm" if comp == "m" else "kN")
        for cat, title in LOAD_CATEGORIES.items()
        for comp in ("fx", "fz", "m")
    )
    + (
        _f("fx", "Known load Fx (sum)", "kN", note="solver ld Fx"),
        _f("fz", "Known load Fz (sum)", "kN", note="solver ld Fz"),
        _f("m", "Known load moment (sum)", "kNm", note="solver ld M"),
        _f("bh_fx", "Solve rope coefficient Fx", "kN/kN", note="solver bh Fx"),
        _f("bh_fz", "Solve rope coefficient Fz", "kN/kN", note="solver bh Fz"),
        _f("bh_m", "Solve rope coefficient moment", "kNm/kN", note="solver bh M"),
    )
)

#: (table name, title, fields, capacity source: an Inputs table or ``None`` for bodies).
_LOADS_TABLE_DEFS: tuple[tuple[str, str, tuple[Field, ...], str | None], ...] = (
    (
        "mass_loads",
        "Mass points (row i = Inputs mass points row i)",
        MASS_LOAD_FIELDS,
        "mass_points",
    ),
    (
        "wind_loads",
        "Wind areas, X wind (row i = Inputs wind areas row i)",
        WIND_LOAD_FIELDS,
        "wind_areas",
    ),
    ("rope_tensions", "Rope tensions (row i = Inputs ropes row i)", ROPE_TENSION_FIELDS, "ropes"),
    (
        "hoist_ropes",
        "Hoist rope mass and idle hooks (row i = Inputs hoists row i)",
        HOIST_ROPE_FIELDS,
        "hoists",
    ),
    (
        "segment_loads",
        "Rope segments (row i = Inputs segments row i)",
        SEGMENT_LOAD_FIELDS,
        "segments",
    ),
    ("node_loads", "Loads at nodes (row i = Inputs nodes row i)", NODE_LOAD_FIELDS, "nodes"),
    ("body_totals", "Body totals (Statics reads these)", BODY_TOTAL_FIELDS, None),
)

# -- Statics sheet -------------------------------------------------------------------

#: Notes printed at the top of the Statics sheet.
STATICS_NOTES: tuple[str, ...] = (
    "The app's in-plane statics, solved once with the actual loads "
    "(calculation/solver/crane_solver.py _run_statics): boom 3x3, then the leg frame 6x6, "
    "then the platform resultant. Moments are about the origin (M = x Fz - z Fx).",
    "Body loads = known loads (Loads body totals fx/fz/m) + T_bh x solve-rope coefficients "
    "(bh_fx/bh_fz/bh_m). Unknowns are the forces the supports exert on the body solved for "
    "(heel and leg-base reactions: weight gives positive Fz).",
    "Each system A x = b is solved with MMULT(MINVERSE(A), b) (a legacy array formula). The "
    "app calls np.linalg.solve and gives no result when it raises (an exactly singular "
    "matrix). Here a matrix is flagged singular when |det A| <= 1e-12 x the product of its "
    "row norms (Hadamard bound), or when MINVERSE fails; the solution column then reads 0 and "
    "Results shows a message.",
    "With no active solve rope the boom matrix's third column is all zero: the app shows no "
    "results (compute_analysis_point returns None); Results says so.",
)

STATICS_STATUS_FIELDS = (
    _f("solve_ropes", "Active solve ropes", "count", note="the app needs one"),
    _f("boom_singular", "Boom 3x3 singular", "1/0", "flag"),
    _f("leg_singular", "Leg frame 6x6 singular", "1/0", "flag"),
    _f("ok", "Statics solved", "1/0", "flag", note="a solve rope and no singular matrix"),
)

#: Fixed nodes ``_run_statics`` reads (``node_pos[...]``), in the order shown.
STATICS_NODES = (
    "boom_heel",
    "rear_base",
    "rear_top",
    "front_base",
    "front_top",
    "platform_heel",
    "platform_rear",
    "platform_front",
)
STATICS_NODE_FIELDS = tuple(
    _f(f"{node}_{axis}_m", f"Node {node} {axis}", "m", note="Geometry x_m/z_m; 0 if missing")
    for node in STATICS_NODES
    for axis in ("x", "z")
)

BOOM_UNKNOWNS = (
    _f("h_x", "Hx: heel on boom", "kN", note="reaction heel_point Fx"),
    _f("h_z", "Hz: heel on boom", "kN", note="reaction heel_point Fz"),
    _f("t_bh", "T_bh: solve-rope tension", "kN", note="boom hoist rope"),
)
BOOM_EQUATIONS = (
    "Boom: sum Fx = 0",
    "Boom: sum Fz = 0",
    "Boom: sum M about the origin = 0",
)

LEG_LOAD_FIELDS = tuple(
    _f(
        f"{leg}_{comp}",
        f"{leg.capitalize()} leg load {comp.upper()} = ld + T_bh bh",
        "kNm" if comp == "m" else "kN",
    )
    for leg in ("rear", "front")
    for comp in ("fx", "fz", "m")
)

LEG_UNKNOWNS = (
    _f("r_rb_x", "Rear base on rear leg x", "kN", note="reaction rear_hinge Fx"),
    _f("r_rb_z", "Rear base on rear leg z", "kN", note="reaction rear_hinge Fz"),
    _f("r_fb_x", "Front base on front leg x", "kN", note="reaction front_hinge Fx"),
    _f("r_fb_z", "Front base on front leg z", "kN", note="reaction front_hinge Fz"),
    _f("r_top_x", "Top joint x (on front leg; rear leg gets -)", "kN", note="upper_hinge Fx"),
    _f("r_top_z", "Top joint z (on front leg; rear leg gets -)", "kN", note="upper_hinge Fz"),
)
LEG_EQUATIONS = (
    "Rear leg: sum Fx = 0",
    "Rear leg: sum Fz = 0",
    "Rear leg: sum M about the origin = 0",
    "Front leg: sum Fx = 0",
    "Front leg: sum Fz = 0",
    "Front leg: sum M about the origin = 0",
)

PLATFORM_FIELDS = (
    _f("load_fx", "Platform load Fx = ld + T_bh bh", "kN"),
    _f("load_fz", "Platform load Fz = ld + T_bh bh", "kN"),
    _f("load_m", "Platform load M = ld + T_bh bh", "kNm"),
    _f("plat_fx", "Platform Fx incl. -Hx, -R_rb_x, -R_fb_x", "kN"),
    _f("plat_fz", "Platform Fz incl. -Hz, -R_rb_z, -R_fb_z", "kN"),
    _f(
        "plat_m",
        "Platform M incl. the reactions at platform_heel/_rear/_front",
        "kNm",
        note="x (-Fz) - z (-Fx) per node",
    ),
    _f("r_g_x", "Ground reaction Fx = -platform Fx", "kN", note="reaction platform_base Fx"),
    _f("r_g_z", "Ground reaction Fz = -platform Fz", "kN", note="reaction platform_base Fz"),
    _f("m_g", "Ground moment My = -platform M", "kNm", note="reaction platform_base My"),
)


def _leg_axis_fields(leg: str, base: str, top: str) -> tuple[Field, ...]:
    name = leg.capitalize()
    return (
        _f(f"{leg}_len_m", f"{name} leg length {base} -> {top}", "m"),
        _f(f"{leg}_ux", f"{name} leg axis ux", note="0 if length <= 1e-12"),
        _f(f"{leg}_uz", f"{name} leg axis uz", note="0 if length <= 1e-12"),
        _f(f"{leg}_axis_ok", f"{name} leg axis defined", "1/0", "flag"),
    )


LEG_AXIS_FIELDS = _leg_axis_fields("rear", "rear_base", "rear_top") + _leg_axis_fields(
    "front", "front_base", "front_top"
)

#: Status rows under each matrix block.
SYSTEM_STATUS_FIELDS = (
    _f("det", "det A (MDETERM)"),
    _f("norm_product", "Product of the row norms of A"),
    _f("rel_det", "|det A| / product of row norms", note="1 = orthogonal rows, 0 = singular"),
    _f("singular", "Singular", "1/0", "flag", note="rel_det <= 1e-12 or MINVERSE fails"),
)
#: Relative determinant at or below which a system counts as singular.
SINGULAR_REL_TOL = 1e-12

#: ``_run_statics`` output keys, in its order: the system unknowns and the platform resultant.
STATICS_UNKNOWNS: tuple[str, ...] = (
    "t_bh",
    "h_x",
    "h_z",
    "r_rb_x",
    "r_rb_z",
    "r_fb_x",
    "r_fb_z",
    "r_top_x",
    "r_top_z",
    "r_g_x",
    "r_g_z",
    "m_g",
)


@dataclass(frozen=True)
class MatrixSystem:
    """A linear system ``A x = b`` laid out as a visible block.

    Rows: title, header, one row per equation, then ``SYSTEM_STATUS_FIELDS`` (label in A,
    value in B). Columns: A the equation, then one column per unknown (A), the right-hand
    side b, the unknown's name, the raw MMULT(MINVERSE) result, the solution used (0 if
    singular) and the row norm of A.
    """

    name: str
    title: str
    sheet: str
    unknowns: tuple[Field, ...]
    equations: tuple[str, ...]
    title_row: int

    def __post_init__(self) -> None:
        if len(self.unknowns) != len(self.equations):
            raise ValueError(f"{self.name}: as many equations as unknowns are needed")

    @property
    def n(self) -> int:
        return len(self.unknowns)

    @property
    def header_row(self) -> int:
        return self.title_row + 1

    @property
    def first_row(self) -> int:
        return self.title_row + 2

    @property
    def last_row(self) -> int:
        return self.first_row + self.n - 1

    @property
    def end_row(self) -> int:
        return self.last_row + len(SYSTEM_STATUS_FIELDS)

    def _col(self, offset: int) -> str:
        """Column letter ``offset`` columns right of B."""
        return str(get_column_letter(2 + offset))

    def matrix_column(self, j: int) -> str:
        """Column of unknown ``j`` (1-based) in A."""
        return self._col(j - 1)

    @property
    def rhs_column(self) -> str:
        return self._col(self.n)

    @property
    def name_column(self) -> str:
        return self._col(self.n + 1)

    @property
    def raw_column(self) -> str:
        return self._col(self.n + 2)

    @property
    def x_column(self) -> str:
        return self._col(self.n + 3)

    @property
    def norm_column(self) -> str:
        return self._col(self.n + 4)

    def _span(self, col_a: str, col_b: str) -> str:
        return f"${col_a}${self.first_row}:${col_b}${self.last_row}"

    @property
    def a_range(self) -> str:
        """Local (same-sheet) range of A."""
        return self._span(self.matrix_column(1), self.matrix_column(self.n))

    @property
    def b_range(self) -> str:
        return self._span(self.rhs_column, self.rhs_column)

    @property
    def raw_range(self) -> str:
        return self._span(self.raw_column, self.raw_column)

    def row_of(self, key: str) -> int:
        for index, f in enumerate(self.unknowns):
            if f.key == key:
                return self.first_row + index
        raise KeyError(f"system {self.name!r} has no unknown {key!r}")

    def a_addr(self, i: int, j: int) -> str:
        """Equation ``i``, unknown ``j`` (1-based)."""
        return f"{self.sheet}!${self.matrix_column(j)}${self.first_row + i - 1}"

    def b_addr(self, i: int) -> str:
        return f"{self.sheet}!${self.rhs_column}${self.first_row + i - 1}"

    def raw_addr(self, key: str) -> str:
        return f"{self.sheet}!${self.raw_column}${self.row_of(key)}"

    def x_addr(self, key: str) -> str:
        """The solution used for unknown ``key`` (0 when the system is singular)."""
        return f"{self.sheet}!${self.x_column}${self.row_of(key)}"

    def norm_addr(self, i: int) -> str:
        return f"{self.sheet}!${self.norm_column}${self.first_row + i - 1}"

    def status_row(self, key: str) -> int:
        for index, f in enumerate(SYSTEM_STATUS_FIELDS, start=1):
            if f.key == key:
                return self.last_row + index
        raise KeyError(f"no status field {key!r}")

    def status_addr(self, key: str) -> str:
        return f"{self.sheet}!$B${self.status_row(key)}"


#: Statics sheet sections, top to bottom: ("block", name, title, fields) or
#: ("system", name, title, unknowns, equations).
_STATICS_SECTIONS: tuple[tuple, ...] = (
    ("block", "statics_status", "Status", STATICS_STATUS_FIELDS),
    ("block", "structure_nodes", "Structure node positions", STATICS_NODE_FIELDS),
    ("system", "boom_system", "Boom: [Hx, Hz, T_bh]", BOOM_UNKNOWNS, BOOM_EQUATIONS),
    ("block", "leg_loads", "Leg loads with the solved T_bh", LEG_LOAD_FIELDS),
    (
        "system",
        "leg_system",
        "Leg frame: [R_rb_x, R_rb_z, R_fb_x, R_fb_z, R_top_x, R_top_z]",
        LEG_UNKNOWNS,
        LEG_EQUATIONS,
    ),
    ("block", "platform", "Platform resultant at the ground (platform_base)", PLATFORM_FIELDS),
    ("block", "leg_axes", "Leg axes (for leg_axial / leg_normal)", LEG_AXIS_FIELDS),
)

# -- Results sheet -------------------------------------------------------------------

RESULTS_NOTES: tuple[str, ...] = (
    "What the Scene results table shows (core/analysis_services.py compute_result_rows), "
    "for the operating state on Inputs. Units: kN, kNm.",
    "Rope tensions: the solve rope's hoist reads T_bh (Statics); fixed ropes read their Loads "
    "tension (scene hoist: hook load / parts; idle hoists: hook mass x (|g| + az') / parts).",
    "Reactions (calculation/solver/crane_solver.py _reactions_from_raw): heel_point = (Hx, Hz), "
    "rear_hinge = R_rb, front_hinge = R_fb, upper_hinge = R_top, platform_base = (r_g_x, "
    "r_g_z, m_g). Support reactions: weight gives positive Fz. Pinned supports carry no "
    "moment.",
    "resultant = sqrt(Fx^2 + Fz^2); leg_axial = Fx ux + Fz uz and leg_normal = -Fx uz + Fz ux "
    "along base -> top (core/demand_extraction.py, calculation/engine.py "
    "resolve_connection_component_linear_response).",
    "When Statics has no solution (no solve rope, or a singular matrix) every value cell "
    "shows the reason instead of a number, as the app shows no results.",
)

RESULTS_STATUS_FIELDS = (
    _f("ok", "Results valid", "1/0", "flag", note="Statics ok"),
    _f("reason", "Short reason (shown in the value cells)", kind="text"),
    _f("message", "Status", kind="text"),
)

TENSION_RESULT_FIELDS = (
    _f("active", "Active", "1/0", "flag", note="from Inputs"),
    _f("hoist_id", "Hoist", kind="text", note="result key tension.<hoist>"),
    _f("rope_id", "Rope id", kind="text"),
    _f("role", "Rope role", kind="text", note="'' if the rope is missing"),
    _f("tension_kN", "Rope tension T", "kN"),
)

REACTION_RESULT_FIELDS = (
    _f("key", "Result key", kind="text", note="reaction.<entity>.<component>"),
    _f("entity", "Support", kind="text"),
    _f("component", "Component", kind="text"),
    _f("value", "Value", note="kN or kNm, see unit"),
    _f("unit", "Unit", kind="text"),
    _f("source", "From", kind="text"),
)

#: In-plane reaction rows (entity, component, unit, source text), in the order of the
#: app's default design-limit catalog. Task 7 appends the out-of-plane rows.
RESULT_ROWS: tuple[tuple[str, str, str, str], ...] = (
    ("heel_point", "fx", "kN", "Statics Hx"),
    ("heel_point", "fz", "kN", "Statics Hz"),
    ("heel_point", "resultant", "kN", "sqrt(Fx^2 + Fz^2)"),
    ("front_hinge", "fx", "kN", "Statics R_fb_x"),
    ("front_hinge", "fz", "kN", "Statics R_fb_z"),
    ("front_hinge", "resultant", "kN", "sqrt(Fx^2 + Fz^2)"),
    ("front_hinge", "leg_axial", "kN", "Fx ux + Fz uz, front_base -> front_top"),
    ("front_hinge", "leg_normal", "kN", "-Fx uz + Fz ux"),
    ("rear_hinge", "fx", "kN", "Statics R_rb_x"),
    ("rear_hinge", "fz", "kN", "Statics R_rb_z"),
    ("rear_hinge", "resultant", "kN", "sqrt(Fx^2 + Fz^2)"),
    ("rear_hinge", "leg_axial", "kN", "Fx ux + Fz uz, rear_base -> rear_top"),
    ("rear_hinge", "leg_normal", "kN", "-Fx uz + Fz ux"),
    ("upper_hinge", "fx", "kN", "Statics R_top_x"),
    ("upper_hinge", "fz", "kN", "Statics R_top_z"),
    ("upper_hinge", "resultant", "kN", "sqrt(Fx^2 + Fz^2)"),
    ("platform_base", "fx", "kN", "Statics r_g_x"),
    ("platform_base", "fz", "kN", "Statics r_g_z"),
    ("platform_base", "my", "kNm", "Statics m_g (in-plane base moment)"),
)

# -- checks ----------------------------------------------------------------------------

#: Check key -> description, in Checks-sheet order. Every check cell is a live count;
#: 0 means OK. Later tasks append their checks (e.g. singular matrices) here and give
#: ``build_checks`` a formula for each.
CHECK_DESCRIPTIONS: dict[str, str] = {
    "overflow": "Rows that do not fit a table (generator) or typed into a guard row",
    "duplicate_ids": "Active rows whose id is used by another active row of the same table",
    "blank_ids": "Active rows with a blank id (or blank rope id on a segment)",
    "node_references": (
        "References to a missing or inactive node (segment ends, hoist hook/support "
        "nodes, hanging nodes' parent)"
    ),
    "rope_references": "Segments or hoists referencing a missing or inactive rope",
    "hoist_without_segments": "Active hoists whose rope has no active segment",
    "multiple_solve_ropes": "Active solve ropes beyond the first (exactly one is allowed)",
    "no_solve_rope": "1 if no active rope has role solve (the app shows no results then)",
    "scene_hoist": "1 if the scene hoist is not an active hoist with a fixed rope",
    "wind_direction": "1 if the scene wind direction is not +X, -X, +Y or -Y",
    "fixed_nodes_missing": "Fixed structure node ids with no active node row",
    "hanging_chain": "Hanging nodes whose parent is itself hanging (only one level is resolved)",
    "singular_matrix": (
        "Singular Statics systems (boom 3x3, leg frame 6x6); the boom one is singular "
        "without a solve rope"
    ),
}

CHECKS_TITLE_ROW = 1
CHECKS_TOTAL_ROW = 3
CHECKS_HEADER_ROW = 5


@dataclass(frozen=True)
class Capacities:
    mass_points: int = MAX_MASS_POINTS
    wind_areas: int = MAX_WIND_AREAS
    nodes: int = MAX_NODES
    segments: int = MAX_SEGMENTS
    ropes: int = MAX_ROPES
    hoists: int = MAX_HOISTS


_TABLE_DEFS: tuple[tuple[str, str, tuple[Field, ...]], ...] = (
    ("mass_points", "Mass points (all bodies)", MASS_POINT_FIELDS),
    ("wind_areas", "Wind areas (all bodies)", WIND_AREA_FIELDS),
    ("nodes", "Nodes", NODE_FIELDS),
    ("segments", "Rope segments (reeving)", SEGMENT_FIELDS),
    ("ropes", "Ropes", ROPE_FIELDS),
    ("hoists", "Hoists", HOIST_FIELDS),
)
_BLOCK_DEFS: tuple[tuple[str, str, tuple[Field, ...]], ...] = (
    ("environment", "Environment", ENVIRONMENT_FIELDS),
    ("structure", "Structure points and widths", STRUCTURE_FIELDS),
    ("scene", "Scene state (one operating point)", SCENE_FIELDS),
)

INPUTS_FIRST_ROW = 4  # rows 1-3: title and colour legend
_GAP = 2  # blank rows between sections
#: Geometry sheet: row 1 title, then the notes, then the blocks.
GEOMETRY_FIRST_ROW = 3 + len(GEOMETRY_NOTES) + _GAP
#: Loads sheet: row 1 title, then the notes, then the scene block and the tables.
LOADS_FIRST_ROW = 3 + len(LOADS_NOTES) + _GAP
#: Statics and Results sheets: row 1 title, then the notes, then the sections.
STATICS_FIRST_ROW = 3 + len(STATICS_NOTES) + _GAP
RESULTS_FIRST_ROW = 3 + len(RESULTS_NOTES) + _GAP


@dataclass(frozen=True, eq=False)
class Layout:
    """Cell addresses for one set of table capacities."""

    capacities: Capacities = field(default_factory=Capacities)
    blocks: dict[str, Block] = field(init=False)
    tables: dict[str, Table] = field(init=False)
    #: Geometry-sheet blocks (``scene_geometry``, ``frame_motion``) and tables
    #: (``node_positions``); kept apart from the Inputs ones, which the writers iterate.
    geo_blocks: dict[str, Block] = field(init=False)
    geo_tables: dict[str, Table] = field(init=False)
    #: Loads-sheet block (``load_scene``) and tables (``_LOADS_TABLE_DEFS``).
    loads_blocks: dict[str, Block] = field(init=False)
    loads_tables: dict[str, Table] = field(init=False)
    #: Statics-sheet blocks and matrix systems (``_STATICS_SECTIONS``).
    statics_blocks: dict[str, Block] = field(init=False)
    statics_systems: dict[str, MatrixSystem] = field(init=False)
    #: Results-sheet block (``results_status``) and tables (``tensions``: row i = Inputs
    #: hoists row i; ``reactions``: one row per ``RESULT_ROWS`` entry).
    results_blocks: dict[str, Block] = field(init=False)
    results_tables: dict[str, Table] = field(init=False)

    def __post_init__(self) -> None:
        row = INPUTS_FIRST_ROW
        blocks: dict[str, Block] = {}
        for name, title, fields in _BLOCK_DEFS:
            blocks[name] = Block(name, title, INPUTS, fields, row)
            row = blocks[name].end_row + _GAP
        tables: dict[str, Table] = {}
        for name, title, fields in _TABLE_DEFS:
            capacity = int(getattr(self.capacities, name))
            if capacity < 1:
                raise ValueError(f"capacity of {name} must be >= 1")
            tables[name] = Table(name, title, INPUTS, fields, capacity, row)
            row = tables[name].end_row + _GAP
        object.__setattr__(self, "blocks", blocks)
        object.__setattr__(self, "tables", tables)

        row = GEOMETRY_FIRST_ROW
        geo_blocks: dict[str, Block] = {}
        for name, title, fields in (
            ("scene_geometry", "Boom rotation and active hook", GEOMETRY_SCENE_FIELDS),
            ("frame_motion", "Vessel-frame motion in the crane frame", GEOMETRY_MOTION_FIELDS),
        ):
            geo_blocks[name] = Block(name, title, GEOMETRY, fields, row)
            row = geo_blocks[name].end_row + _GAP
        geo_tables = {
            "node_positions": Table(
                "node_positions",
                "Node positions (row i = Inputs nodes row i)",
                GEOMETRY,
                NODE_POSITION_FIELDS,
                tables["nodes"].capacity,
                row,
            )
        }
        object.__setattr__(self, "geo_blocks", geo_blocks)
        object.__setattr__(self, "geo_tables", geo_tables)

        loads_blocks = {
            "load_scene": Block(
                "load_scene",
                "Scene values used by the loads",
                LOADS,
                LOADS_SCENE_FIELDS,
                LOADS_FIRST_ROW,
            )
        }
        row = loads_blocks["load_scene"].end_row + _GAP
        loads_tables: dict[str, Table] = {}
        for name, title, fields, source in _LOADS_TABLE_DEFS:
            capacity = len(BODIES) if source is None else tables[source].capacity
            loads_tables[name] = Table(name, title, LOADS, fields, capacity, row)
            row = loads_tables[name].end_row + _GAP
        object.__setattr__(self, "loads_blocks", loads_blocks)
        object.__setattr__(self, "loads_tables", loads_tables)

        row = STATICS_FIRST_ROW
        statics_blocks: dict[str, Block] = {}
        systems: dict[str, MatrixSystem] = {}
        for section in _STATICS_SECTIONS:
            if section[0] == "block":
                _kind, name, title, fields = section
                statics_blocks[name] = Block(name, title, STATICS, fields, row)
                row = statics_blocks[name].end_row + _GAP
            else:
                _kind, name, title, unknowns, equations = section
                systems[name] = MatrixSystem(name, title, STATICS, unknowns, equations, row)
                row = systems[name].end_row + _GAP
        object.__setattr__(self, "statics_blocks", statics_blocks)
        object.__setattr__(self, "statics_systems", systems)

        results_blocks = {
            "results_status": Block(
                "results_status", "Status", RESULTS, RESULTS_STATUS_FIELDS, RESULTS_FIRST_ROW
            )
        }
        row = results_blocks["results_status"].end_row + _GAP
        results_tables: dict[str, Table] = {}
        for name, title, fields, capacity in (
            (
                "tensions",
                "Rope tensions per hoist (row i = Inputs hoists row i)",
                TENSION_RESULT_FIELDS,
                tables["hoists"].capacity,
            ),
            ("reactions", "Support reactions", REACTION_RESULT_FIELDS, len(RESULT_ROWS)),
        ):
            results_tables[name] = Table(name, title, RESULTS, fields, capacity, row)
            row = results_tables[name].end_row + _GAP
        object.__setattr__(self, "results_blocks", results_blocks)
        object.__setattr__(self, "results_tables", results_tables)

    # -- inputs ---------------------------------------------------------------------

    def addr(self, table: str, key: str, row: int) -> str:
        """Sheet-qualified absolute address of ``key`` in data row ``row`` (1-based)."""
        return self.tables[table].addr(key, row)

    def col_range(self, table: str, key: str) -> str:
        """Sheet-qualified range of ``key`` over all ``capacity`` data rows."""
        return self.tables[table].col_range(key)

    def cell(self, block: str, key: str) -> str:
        """Sheet-qualified address of a single-value input (``environment``, ``structure``,
        ``scene``)."""
        return self.blocks[block].addr(key)

    # -- geometry -------------------------------------------------------------------

    def geo_addr(self, table: str, key: str, row: int) -> str:
        """Geometry-sheet address of ``key`` in data row ``row`` (1-based)."""
        return self.geo_tables[table].addr(key, row)

    def geo_col_range(self, table: str, key: str) -> str:
        """Geometry-sheet range of ``key`` over all rows."""
        return self.geo_tables[table].col_range(key)

    def geo_cell(self, block: str, key: str) -> str:
        """Geometry-sheet address of a single-value cell (``scene_geometry``,
        ``frame_motion``)."""
        return self.geo_blocks[block].addr(key)

    # -- loads ----------------------------------------------------------------------

    def loads_addr(self, table: str, key: str, row: int) -> str:
        """Loads-sheet address of ``key`` in data row ``row`` (1-based)."""
        return self.loads_tables[table].addr(key, row)

    def loads_col_range(self, table: str, key: str) -> str:
        """Loads-sheet range of ``key`` over all rows."""
        return self.loads_tables[table].col_range(key)

    def loads_cell(self, block: str, key: str) -> str:
        """Loads-sheet address of a single-value cell (``load_scene``)."""
        return self.loads_blocks[block].addr(key)

    def body_total(self, body: str, key: str) -> str:
        """Loads-sheet address of body ``body``'s total ``key`` (``body_totals`` fields:
        ``fx``/``fz``/``m`` known loads, ``bh_fx``/``bh_fz``/``bh_m`` solve-rope coefficients,
        ``<category>_fx``/``_fz``/``_m`` per ``LOAD_CATEGORIES``)."""
        return self.loads_addr("body_totals", key, BODIES.index(body) + 1)

    # -- statics --------------------------------------------------------------------

    def statics_cell(self, block: str, key: str) -> str:
        """Statics-sheet address of a single-value cell (``statics_status``,
        ``structure_nodes``, ``leg_loads``, ``platform``, ``leg_axes``)."""
        return self.statics_blocks[block].addr(key)

    def statics_flag(self, system: str) -> str:
        """The ``singular`` flag (1/0) of ``boom_system`` or ``leg_system``."""
        return self.statics_systems[system].status_addr("singular")

    def statics_value(self, key: str) -> str:
        """Address of ``_run_statics`` output ``key`` (``STATICS_UNKNOWNS``): the solution
        used of a system unknown, or the platform resultant."""
        for system in self.statics_systems.values():
            if key in {f.key for f in system.unknowns}:
                return system.x_addr(key)
        return self.statics_cell("platform", key)

    # -- results --------------------------------------------------------------------

    def results_cell(self, block: str, key: str) -> str:
        """Results-sheet address of a single-value cell (``results_status``)."""
        return self.results_blocks[block].addr(key)

    def results_addr(self, table: str, key: str, row: int) -> str:
        """Results-sheet address of ``key`` in data row ``row`` (``tensions``,
        ``reactions``)."""
        return self.results_tables[table].addr(key, row)

    @property
    def result_rows(self) -> tuple[tuple[str, str], ...]:
        """(entity, component) of each reaction row, in sheet order."""
        return tuple((entity, comp) for entity, comp, _unit, _src in RESULT_ROWS)

    def result_cell(self, entity: str, component: str) -> str:
        """Value cell of result ``reaction.<entity>.<component>``."""
        try:
            index = self.result_rows.index((entity, component))
        except ValueError:
            raise KeyError(f"no result row {entity}.{component}") from None
        return self.results_addr("reactions", "value", index + 1)

    # -- checks ---------------------------------------------------------------------

    def check_row(self, key: str) -> int:
        try:
            index = list(CHECK_DESCRIPTIONS).index(key)
        except ValueError:
            raise KeyError(f"no check {key!r}") from None
        return CHECKS_HEADER_ROW + 1 + index

    def check(self, key: str) -> str:
        """Address of the check's count cell (0 = OK)."""
        return f"{CHECKS}!$C${self.check_row(key)}"

    @property
    def total_issues_addr(self) -> str:
        return f"{CHECKS}!$C${CHECKS_TOTAL_ROW}"

    @property
    def checks_detail_row(self) -> int:
        """First free row below the check list (for the per-table breakdowns)."""
        return CHECKS_HEADER_ROW + len(CHECK_DESCRIPTIONS) + 1 + _GAP


DEFAULT_LAYOUT = Layout()


def split(address: str) -> tuple[str, str]:
    """``'Inputs!$B$5'`` -> ``('Inputs', 'B5')`` (for writing with openpyxl)."""
    sheet, coord = address.split("!")
    return sheet, coord.replace("$", "")


def addr(table: str, field: str, row: int) -> str:
    """``DEFAULT_LAYOUT.addr``: sheet-qualified address of a table cell."""
    return DEFAULT_LAYOUT.addr(table, field, row)


def col_range(table: str, field: str) -> str:
    """``DEFAULT_LAYOUT.col_range``: sheet-qualified range of a table column."""
    return DEFAULT_LAYOUT.col_range(table, field)


def cell(block: str, key: str) -> str:
    """``DEFAULT_LAYOUT.cell``: sheet-qualified address of a single-value input."""
    return DEFAULT_LAYOUT.cell(block, key)
