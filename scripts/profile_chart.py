"""Profile the load-chart sweep (``run_capacity_sweep``) on an example document.

Run uninstrumented (``--tool time``) before profiling; the profilers add overhead.

    .venv/Scripts/python.exe scripts/profile_chart.py --tool time
    .venv/Scripts/python.exe scripts/profile_chart.py --tool cprofile --top 30
    .venv/Scripts/python.exe scripts/profile_chart.py --tool pyinstrument --html chart.html
"""

from __future__ import annotations

import argparse
import cProfile
import pstats
import time
from pathlib import Path

from crane_statics.core import load_document
from crane_statics.core.sweep import run_capacity_sweep

ROOT = Path(__file__).resolve().parent.parent
VESSEL_LIMITS = {
    "accel_x_m_s2": 1.0,
    "accel_y_m_s2": 1.0,
    "accel_z_m_s2": 1.0,
    "roll_angular_accel_rad_s2": 0.1,
    "pitch_angular_accel_rad_s2": 0.1,
    "roll_deg": 5.0,
    "pitch_deg": 5.0,
}
LIMITS: dict[str, dict] = {"boom_hoist": {"T": 5000.0}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--doc", type=Path, default=ROOT / "examples" / "crane_input_GT283.yaml")
    parser.add_argument("--hoist", default="MH")
    parser.add_argument("--step", type=float, default=2.0, help="outreach step [m]")
    parser.add_argument("--wind", type=float, help="max wind speed [m/s]")
    parser.add_argument("--no-vessel", action="store_true", help="leave vessel motion unset")
    parser.add_argument("--tool", choices=["time", "cprofile", "pyinstrument"], default="time")
    parser.add_argument("--repeat", type=int, default=5, help="runs for --tool time")
    parser.add_argument("--top", type=int, default=25, help="rows for --tool cprofile")
    parser.add_argument("--html", type=Path, help="write a pyinstrument HTML report")
    args = parser.parse_args()

    doc = load_document(args.doc)
    if not args.no_vessel:
        for field, value in VESSEL_LIMITS.items():
            setattr(doc.environment.vessel_motion, field, value)
    if args.wind is not None:
        doc.environment.max_wind_speed_m_s = args.wind

    def sweep() -> dict:
        return run_capacity_sweep(doc, args.hoist, LIMITS, args.step, {})

    sweep()  # warm-up: caches, imports
    if args.tool == "time":
        times = []
        for _ in range(args.repeat):
            start = time.perf_counter()
            result = sweep()
            times.append(time.perf_counter() - start)
        print(f"{result['n_points']} points; min {min(times):.3f} s, max {max(times):.3f} s")
    elif args.tool == "cprofile":
        prof = cProfile.Profile()
        prof.runcall(sweep)
        pstats.Stats(prof).sort_stats("cumulative").print_stats(args.top)
    else:
        from pyinstrument import Profiler

        profiler = Profiler(interval=0.0002)
        profiler.start()
        sweep()
        profiler.stop()
        print(profiler.output_text(unicode=False, color=False))
        if args.html:
            args.html.write_text(profiler.output_html(), encoding="utf-8")


if __name__ == "__main__":
    main()
