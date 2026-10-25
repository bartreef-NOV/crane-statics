"""The Conventions sheet: axes, angles and sign conventions, as the app's code has them."""

from __future__ import annotations

from openpyxl.worksheet.worksheet import Worksheet

from . import styles

#: (section title, [(text, source)]). Sources are paths under src/crane_statics/.
CONVENTIONS_TEXT: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Units",
        (
            ("Lengths m, masses t, forces kN, moments kNm, angles deg (inputs), rad/s^2.", ""),
            (
                "Weight = mass_t x |g| (kN, since t x m/s^2 = kN). Gravity is typed signed "
                "(-9.81) as authored; the calculation uses its magnitude.",
                "calculation/engine.py",
            ),
        ),
    ),
    (
        "Axes (crane frame)",
        (
            ("x: horizontal in the boom plane, positive toward the boom tip (outreach).", ""),
            ("z: up. y: lateral, completing a right-handed x-y-z frame.", ""),
            (
                "The crane frame is the vessel frame (x forward, y port, z up) rotated about z "
                "by the crane slewing angle; a vessel-frame horizontal vector (vx, vy) is "
                "(cos s vx + sin s vy, -sin s vx + cos s vy) in the crane frame.",
                "calculation/vessel_frame.py _vessel_to_crane",
            ),
            (
                "In-plane moments are about +y with M = x Fz - z Fx (a load's moment about the "
                "origin as the solver accumulates it: ld_m += -z Fx + x Fz).",
                "calculation/solver/crane_solver.py",
            ),
        ),
    ),
    (
        "Boom angle and boom-local coordinates",
        (
            ("Boom angle theta is measured at the boom heel from +x toward +z.", ""),
            (
                "Boom-local u runs along the boom from the heel, w is normal to it (u rotated "
                "+90 deg toward +z), v is lateral (= y). Global position: x = x_heel + u cos "
                "theta - w sin theta, z = z_heel + u sin theta + w cos theta.",
                "calculation/solver/crane_solver.py rotate_boom_local_point",
            ),
            (
                "Only body 'boom' rows use boom-local coordinates; other bodies are global.",
                "scripts/excel_workbook/reference.py (name-based rule 5)",
            ),
            (
                "Hanging nodes hang straight down (-z) from their parent node: the scene "
                "hoist's hook by the tackle length, idle hooks by their hanging drop.",
                "calculation/rope_mass.py active_hook_positions",
            ),
        ),
    ),
    (
        "Vessel attitude and accelerations",
        (
            (
                "Vessel pitch is positive bow-down, roll positive to starboard (intrinsic "
                "z-y-x). Gravity in the vessel frame: g (sin pitch, -sin roll cos pitch, "
                "-cos roll cos pitch) with g = |g|.",
                "calculation/vessel_frame.py gravity_in_vessel_frame",
            ),
            (
                "Load acceleration k = g_vessel - a (a = vessel accelerations ax, ay, az), "
                "rotated into the crane frame by the slewing angle; the equivalent crane-frame "
                "accelerations are ax' = -kx, ay' = -ky, az' = -|g| - kz.",
                "calculation/vessel_frame.py crane_frame_motion",
            ),
            (
                "Pitch and roll angular accelerations are rotated into the crane frame the same "
                "way: (roll', pitch') = rotate(roll, pitch).",
                "calculation/vessel_frame.py crane_frame_motion",
            ),
            (
                "Mass load (inertia + weight), with dx = x - x_ref, dz = z - z_ref (vessel "
                "motion reference): Fx = -m (ax' + pitch' dz), Fz = -m (|g| + az' - pitch' dx), "
                "Fy = -m (ay' - roll' dz). Pitch acceleration is right-handed about +y, roll "
                "acceleration right-handed about +x.",
                "calculation/solver/crane_solver.py inertia_force; calculation/engine.py",
            ),
        ),
    ),
    (
        "Wind",
        (
            (
                "Direction +X, -X, +Y or -Y is the direction the wind blows toward: +X wind "
                "pushes in +x. Any other text is treated as +X by the app (flagged on Checks).",
                "calculation/engine.py split_wind_speed_components",
            ),
            (
                "Force = sign x 0.5 rho Cd A V^2 / 1000 (kN). X wind uses 'Area for X wind', Y "
                "wind uses 'Area for Y wind'. Areas of body 'boom' are scaled by |sin theta| in "
                "both directions.",
                "calculation/solver/crane_solver.py _wind_fx; calculation/engine.py",
            ),
        ),
    ),
    (
        "Hook load, offlead and sidelead",
        (
            (
                "Hook load (kN) acts at the hook node in -z. Offlead adds sin(offlead) x hook "
                "load in +x at the node the hook hangs from (its parent node; the hook itself "
                "if it has none); sidelead adds sin(sidelead) x hook load in +y.",
                "calculation/solver/crane_solver.py _accumulate_loads; core/drawn_loads.py "
                "hook_load; calculation/engine.py; core/lead_channels.py",
            ),
        ),
    ),
    (
        "Ropes",
        (
            (
                "Role 'solve' marks the boom-hoist rope: its tension is an unknown of the boom "
                "solve (the app's rope with tension_mode 'solve', published as 'boom_hoist'). "
                "Exactly one active solve rope is required; without one the app shows no "
                "results.",
                "calculation/solver/crane_solver.py",
            ),
            (
                "Role 'fixed': the scene hoist's rope carries hook load / parts at the hook; an "
                "idle hoist's rope carries hook mass x (|g| + az') / parts.",
                "calculation/solver/crane_solver.py",
            ),
            (
                "Rope self-weight: each segment's length x parts x linear mass is split half to "
                "each end node; the rest of the hoist's total rope length (spooled) sits at its "
                "spool node (the 'Spool node' flag replaces the app's rule 'node id contains "
                "winch'). The hoist row's linear mass is the one used.",
                "calculation/rope_mass.py rope_mass_at_nodes",
            ),
            ("Split-block mode is not supported by this workbook.", ""),
        ),
    ),
    (
        "Reaction signs (as the app reports them)",
        (
            (
                "Fx, Fz and My of every support (heel point, hinges, platform base) are support "
                "reactions opposing the applied loads: weight gives positive Fz; a +X vessel "
                "acceleration gives positive Fx.",
                "scripts/excel_workbook/reference.py",
            ),
            (
                "Possible app sign bug, replicated: platform base Fy and Mx carry the sign of "
                "the applied loads, not of the reaction (a +Y wind gives positive Fy, and Mx = "
                "-z Fy).",
                "scripts/excel_workbook/reference.py",
            ),
            (
                "Possible app sign bug, replicated: heel_left behaves as the -Y side. "
                "heel_left = 0.5 total + M / boom width, heel_right = 0.5 total - M / boom "
                "width (Fz uses Mx, Fx uses Mz), with M the applied-load moment about the heel: "
                "Mx = y Fz - z Fy, Mz = x_rel Fy - y Fx. A mass at +Y loads heel_right. The "
                "heel moments include every mass and wind area of the crane.",
                "scripts/excel_workbook/reference.py; calculation/engine.py",
            ),
            ("Pinned connections (heel, hinges) carry no moment.", ""),
        ),
    ),
    (
        "Tables",
        (
            (
                "Every table has a fixed number of rows with an Active column (1 = in use, 0 = "
                "spare). Spare rows keep Active = 0 and every other cell blank; they change no "
                "result. Keep each table's red guard row blank; rows that do not fit are "
                "counted on Checks.",
                "",
            ),
            ("Ids are matched case-insensitively by Excel and must not contain * ? ~.", ""),
            (
                "The nine fixed node ids (boom_heel, platform_heel, rear_top, front_top, "
                "rear_base, platform_rear, front_base, platform_front, platform_base) take their "
                "x/z from the structure points by formula.",
                "data/models.py",
            ),
        ),
    ),
)


def write_conventions(ws: Worksheet) -> None:
    ws["A1"] = "Conventions -- axes, angles and signs (copied from the app's code)"
    ws["A1"].font = styles.TITLE_FONT
    styles.legend(ws, 2)
    row = 4
    for title, lines in CONVENTIONS_TEXT:
        ws[f"A{row}"] = title
        ws[f"A{row}"].font = styles.SECTION_FONT
        row += 1
        for text, source in lines:
            ws[f"A{row}"] = text
            if source:
                ws[f"B{row}"] = source
                ws[f"B{row}"].font = styles.KEY_FONT
            row += 1
        row += 1
    ws.column_dimensions["A"].width = 140
    ws.column_dimensions["B"].width = 60
