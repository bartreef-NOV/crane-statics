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
