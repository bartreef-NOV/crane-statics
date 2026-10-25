"""Where the out-of-plane pass lives: the OutOfPlane sheet's blocks and tables.

Kept apart from ``layout`` (which re-exports it as ``Layout.oop``) so that module stays
manageable. Read the cells like this::

    oop = lay.oop                                   # the Layout passed to the writer
    oop.cell("oop_scene", "wind_y_sign")            # single-value blocks
    oop.addr("oop_masses", "fy_kN", 3)              # row i = Inputs mass points row i
    oop.moment("heel", "mx")                        # Mx of the applied loads about the heel
    oop.split_value("heel_left", "fz")              # left/right split
    oop.cell("platform", "fy_kN")                   # platform base Fy (support reaction)

Sheet layout, top to bottom: title and ``OOP_NOTES``, the blocks ``oop_scene`` and
``sidelead``, the per-row tables ``oop_masses`` (Inputs mass points), ``oop_lumped`` (Inputs
nodes: rope self-weight and idle hook blocks) and ``oop_winds`` (Inputs wind areas), then
``moments`` (one row per support group, ``OOP_GROUPS``), ``split`` (one row per side entity,
``OOP_SPLITS``) and the ``platform`` block.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .layout import _GAP, OUT_OF_PLANE, Block, Field, Table, _f

if TYPE_CHECKING:
    from .layout import Layout

#: Notes printed at the top of the OutOfPlane sheet.
OOP_NOTES: tuple[str, ...] = (
    "The app's out-of-plane (Y) pass (calculation/engine.py _out_of_plane_variants, "
    "_out_of_plane_geometry, _augment_point_with_out_of_plane_loads), evaluated once with "
    "the actual hook load. It does not change the in-plane solve; it adds the left/right "
    "support split and the platform base Fy and Mx.",
    "Y loads: every mass point and every lumped mass (rope self-weight, idle hook blocks; "
    "y = 0) carries Fy = -m (ay' - roll' (z - z_ref)) (crane-frame ay' = Geometry solver_ay, "
    "roll' = roll_accel_crane); Y wind Fy = sign q Cd A_y (the full Y area at any boom "
    "angle; only X wind on boom areas is scaled by |sin(boom angle)|); the sidelead force "
    "sin(sidelead) x hook load acts in +y at the scene hoist's support node (its hook node "
    "if the support is missing), at its kinematic position (before the tackle moves the "
    "hook).",
    "Moments of the applied loads about each support group origin (heel = boom_heel, "
    "front_leg = front_base, rear_leg = rear_base, platform_base = platform_heel): "
    "Mx = y Fz - (z - oz) Fy, Mz = (x - ox) Fy - y Fx. Mass Fx/Fz are the Loads mass "
    "loads (weight + inertia); wind and side forces have y = 0.",
    "Split: left (+Y, port) = 0.5 total - M / boom width, right (-Y, starboard) = 0.5 "
    "total + M / boom width, Fx using Mz and Fz using Mx; total = the in-plane reaction "
    "(Statics). A mass at +Y loads the left side.",
    "Platform base Fy and Mx are support reactions (the force the support exerts on the "
    "crane), like Fx, Fz and My: Fy = -(sum of all applied Fy), Mx = -(Mx of the applied "
    "loads about platform_heel). The front/rear leg splits are shown but the Scene does not "
    "report them.",
    "Boom width must be > 0: the app rejects 0 and its split divides by it; Results then "
    "shows a message (check zero_boom_width).",
)

OOP_SCENE_FIELDS = (
    _f("ref_z_m", "Vessel motion reference z (roll lever origin)", "m", note="Loads"),
    _f("ay", "Crane-frame Y acceleration ay' (= -ky)", "m/s^2", note="Geometry solver_ay"),
    _f("roll", "Roll angular acceleration, crane frame", "rad/s^2", note="Geometry"),
    _f("wind_y_sign", "Y wind sign", "+1/-1/0", note="+Y: 1, -Y: -1, X wind or speed 0: 0"),
    _f("wind_q_kN_m2", "0.5 rho V^2 / 1000", "kN/m^2", note="Loads"),
    _f("hook_kN", "Hook load", "kN", note="scene value"),
    _f("sidelead_kN", "Side force sin(sidelead) x hook load", "kN", note="+y"),
    _f("boom_width_m", "Boom width (heel left/right spacing)", "m", note="Inputs structure"),
    _f("width_ok", "Boom width > 0", "1/0", "flag", note="0 trips check zero_boom_width"),
    _f("bearing_d_m", "Slewing bearing diameter", "m", note="Inputs structure; may be blank"),
    _f("bearing_ok", "Bearing diameter > 0", "1/0", "flag", note="0: bearing rows are n/a"),
)

SIDELEAD_FIELDS = (
    _f("hoist_row", "Row of the scene hoist in hoists", "row", note="0 = missing"),
    _f("support_id", "Its support node", kind="text", note="Inputs hoists support_node_id"),
    _f("hook_id", "Its hook node (fallback)", kind="text", note="Inputs hoists load_node_id"),
    _f("support_row", "Row of the support node in nodes", "row", note="0 = missing"),
    _f("hook_row", "Row of the hook node in nodes", "row", note="0 = missing"),
    _f("node_row", "Row of the node the side force acts at", "row", note="support, else hook"),
    _f("x_m", "Its x (kinematics)", "m", note="Geometry x_kin_m"),
    _f("z_m", "Its z (kinematics)", "m", note="Geometry z_kin_m"),
    _f("fy_kN", "Side force Fy", "kN", note="0 if no node"),
)

OOP_MASS_FIELDS = (
    _f("active", "Active", "1/0", "flag", note="from Inputs"),
    _f("body", "Body", kind="text"),
    _f("frame", "Frame", kind="text"),
    _f("x_m", "x global", "m", note="Loads"),
    _f("y_m", "y (boom-local v, else y)", "m"),
    _f("z_m", "z global", "m", note="Loads"),
    _f("mass_t", "Mass", "t"),
    _f("fx_kN", "Fx = weight + inertia", "kN", note="Loads"),
    _f("fz_kN", "Fz = weight + inertia", "kN", note="Loads"),
    _f("fy_kN", "Fy = -m (ay' - roll' (z - z_ref))", "kN"),
)

OOP_LUMPED_FIELDS = (
    _f("active", "Active", "1/0", "flag", note="from Inputs"),
    _f("id", "Node id", kind="text"),
    _f("x_m", "x global", "m", note="Loads (with the tackle)"),
    _f("z_m", "z global", "m"),
    _f("rope_t", "Rope self-weight at node", "t", note="Loads rope_mass_t"),
    _f("idle_t", "Idle hook block mass", "t", note="Loads idle_mass_t"),
    _f("mass_t", "Lumped mass", "t"),
    _f("fy_kN", "Fy = -m (ay' - roll' (z - z_ref))", "kN"),
)

OOP_WIND_FIELDS = (
    _f("active", "Active", "1/0", "flag", note="from Inputs"),
    _f("body", "Body", kind="text"),
    _f("frame", "Frame", kind="text"),
    _f("x_m", "x global", "m", note="Loads"),
    _f("z_m", "z global", "m", note="Loads"),
    _f("cd", "Cd"),
    _f("area_y_m2", "Area for Y wind", "m^2", note="not scaled by the boom angle"),
    _f("fy_kN", "Wind Fy = sign q Cd A_y", "kN"),
)

#: Support groups of the engine's out-of-plane pass and their origin nodes.
OOP_GROUPS: tuple[tuple[str, str], ...] = (
    ("heel", "boom_heel"),
    ("front_leg", "front_base"),
    ("rear_leg", "rear_base"),
    ("platform_base", "platform_heel"),
)

MOMENT_FIELDS = (
    _f("group", "Support group", kind="text"),
    _f("node", "Origin node", kind="text"),
    _f("ox_m", "Origin x", "m", note="Statics structure nodes"),
    _f("oz_m", "Origin z", "m"),
    _f("mx_masses", "Mx mass points = SUM(y Fz) - SUM((z - oz) Fy)", "kNm"),
    _f("mx_lumped", "Mx lumped masses = -SUM((z - oz) Fy)", "kNm"),
    _f("mx_wind", "Mx wind = -SUM((z - oz) Fy)", "kNm"),
    _f("mx_side", "Mx side force = -(z - oz) Fy", "kNm"),
    _f("mx", "Mx total", "kNm"),
    _f("mz_masses", "Mz mass points = SUM((x - ox) Fy) - SUM(y Fx)", "kNm"),
    _f("mz_lumped", "Mz lumped masses = SUM((x - ox) Fy)", "kNm"),
    _f("mz_wind", "Mz wind = SUM((x - ox) Fy)", "kNm"),
    _f("mz_side", "Mz side force = (x - ox) Fy", "kNm"),
    _f("mz", "Mz total", "kNm"),
)

#: (side entity, support group, in-plane total entity, side sign). +Y is port (left looking
#: along +x), so the left side takes ``-M / width`` (sign -1) and the right side ``+M / width``.
OOP_SPLITS: tuple[tuple[str, str, str, int], ...] = (
    ("heel_left", "heel", "heel_point", -1),
    ("heel_right", "heel", "heel_point", 1),
    ("front_leg_left", "front_leg", "front_hinge", -1),
    ("front_leg_right", "front_leg", "front_hinge", 1),
    ("rear_leg_left", "rear_leg", "rear_hinge", -1),
    ("rear_leg_right", "rear_leg", "rear_hinge", 1),
)

SPLIT_FIELDS = (
    _f("entity", "Side support", kind="text"),
    _f("group", "Support group", kind="text"),
    _f("total_entity", "In-plane total", kind="text"),
    _f("side", "Side sign", "+1/-1", note="-1 left (+Y, port), +1 right (-Y)"),
    _f("total_fx", "Total Fx (in-plane reaction)", "kN", note="Statics"),
    _f("total_fz", "Total Fz (in-plane reaction)", "kN", note="Statics"),
    _f("mz", "Mz about the group", "kNm"),
    _f("mx", "Mx about the group", "kNm"),
    _f("fx", "Fx = 0.5 total Fx + side Mz / width", "kN", note="0 if width <= 0"),
    _f("fz", "Fz = 0.5 total Fz + side Mx / width", "kN", note="0 if width <= 0"),
)

PLATFORM_OOP_FIELDS = (
    _f("fy_masses", "Applied Fy of the mass points", "kN"),
    _f("fy_lumped", "Applied Fy of the lumped masses", "kN"),
    _f("fy_wind", "Applied Fy of the Y wind", "kN"),
    _f("fy_side", "Applied side force", "kN"),
    _f("fy_kN", "Platform base Fy = -(sum of applied Fy)", "kN", note="reaction.platform_base.fy"),
    _f(
        "mx_kNm",
        "Platform base Mx = -(applied Mx about platform_heel)",
        "kNm",
        note="reaction.platform_base.mx",
    ),
)

#: Sheet sections, top to bottom: (kind, name, title, fields, capacity source).
_OOP_SECTIONS: tuple[tuple[str, str, str, tuple[Field, ...], str], ...] = (
    ("block", "oop_scene", "Scene values used by the out-of-plane pass", OOP_SCENE_FIELDS, ""),
    ("block", "sidelead", "Sidelead force (scene hoist)", SIDELEAD_FIELDS, ""),
    (
        "table",
        "oop_masses",
        "Mass points (row i = Inputs mass points row i)",
        OOP_MASS_FIELDS,
        "mass_points",
    ),
    (
        "table",
        "oop_lumped",
        "Lumped masses at nodes (row i = Inputs nodes row i)",
        OOP_LUMPED_FIELDS,
        "nodes",
    ),
    (
        "table",
        "oop_winds",
        "Wind areas, Y wind (row i = Inputs wind areas row i)",
        OOP_WIND_FIELDS,
        "wind_areas",
    ),
    ("table", "moments", "Moments of the applied loads per support group", MOMENT_FIELDS, ""),
    ("table", "split", "Left/right split", SPLIT_FIELDS, ""),
    ("block", "platform", "Platform base Fy and Mx", PLATFORM_OOP_FIELDS, ""),
)

#: Fixed-row tables and their row counts.
_FIXED_ROWS = {"moments": len(OOP_GROUPS), "split": len(OOP_SPLITS)}

OOP_FIRST_ROW = 3 + len(OOP_NOTES) + _GAP


@dataclass(frozen=True, eq=False)
class OopLayout:
    """OutOfPlane-sheet addresses for one ``Layout`` (its table capacities)."""

    blocks: dict[str, Block]
    tables: dict[str, Table]

    @classmethod
    def build(cls, lay: Layout) -> OopLayout:
        row = OOP_FIRST_ROW
        blocks: dict[str, Block] = {}
        tables: dict[str, Table] = {}
        for kind, name, title, fields, source in _OOP_SECTIONS:
            if kind == "block":
                blocks[name] = Block(name, title, OUT_OF_PLANE, fields, row)
                row = blocks[name].end_row + _GAP
            else:
                capacity = _FIXED_ROWS[name] if not source else lay.tables[source].capacity
                tables[name] = Table(name, title, OUT_OF_PLANE, fields, capacity, row)
                row = tables[name].end_row + _GAP
        return cls(blocks, tables)

    def cell(self, block: str, key: str) -> str:
        """Address of a single-value cell (``oop_scene``, ``sidelead``, ``platform``)."""
        return self.blocks[block].addr(key)

    def addr(self, table: str, key: str, row: int) -> str:
        """Address of ``key`` in data row ``row`` (1-based)."""
        return self.tables[table].addr(key, row)

    def col_range(self, table: str, key: str) -> str:
        return self.tables[table].col_range(key)

    @property
    def groups(self) -> tuple[str, ...]:
        return tuple(group for group, _node in OOP_GROUPS)

    def moment(self, group: str, key: str) -> str:
        """``moments`` cell ``key`` (``mx``, ``mz``, ``mx_wind``, ...) of support ``group``."""
        return self.addr("moments", key, self.groups.index(group) + 1)

    def split_value(self, entity: str, key: str) -> str:
        """``split`` cell ``key`` (``fx``, ``fz``, ...) of side entity ``entity``."""
        index = [split[0] for split in OOP_SPLITS].index(entity)
        return self.addr("split", key, index + 1)
