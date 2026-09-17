"""Command line: ogsfrac <geometry|mesh|prj|run|all> case.yml"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import boreholes_from_case, load_case, mesh_inputs_from_case, planes_from_case
from .geometry.planes import intersect_boreholes
from .meshing.builder import FracturedDomainMesh
from .meshing.convert import extract_subdomain, inspect, msh_to_vtu
from .prj.build import build_prj
from .run import OGSSimulation


def _workdir(case) -> Path:
    wd = Path(case["_dir"]) / case.get("workdir", case["name"])
    wd.mkdir(parents=True, exist_ok=True)
    return wd


def cmd_geometry(case):
    planes = planes_from_case(case)
    for p in planes:
        dip, azi = p.dip_azimuth
        res = "exact" if not p.residual else f"rms={p.residual:.3f} m"
        print(f"{p.name:8s} dip={dip:6.2f}  azimuth={azi:7.2f}  n={p.normal.round(4)}  {res}")
    holes = boreholes_from_case(case)
    if holes and planes:
        df = intersect_boreholes(planes, holes)
        out = _workdir(case) / "intersections.xlsx"
        df.to_excel(out, index=False)
        print(f"\n{len(df)} intersections -> {out}")
        print(df.to_string(index=False))
    return planes


def cmd_mesh(case):
    domain, fractures, tunnel, options, obs = mesh_inputs_from_case(case)
    wd = _workdir(case)
    msh = wd / f"{case['name']}.msh"
    mesh = FracturedDomainMesh(domain, fractures, tunnel, obs, options)
    mesh.generate(msh)
    print(f"mesh -> {msh}")
    vtu = msh_to_vtu(msh, wd / f"{case['name']}.vtu")
    print(f"bulk -> {vtu}")
    for f in fractures:
        try:
            print(f"sub  -> {extract_subdomain(msh, f.name, wd / f'{f.name}.vtu')}")
        except (KeyError, ValueError) as exc:
            print(f"sub  -- {f.name}: {exc}")
    for k, v in inspect(msh).items():
        print(f"  {k}: {v}")
    return msh


def cmd_prj(case):
    wd = _workdir(case)
    prj = build_prj(case, wd / f"{case['name']}.prj")
    print(f"prj  -> {prj}")
    return prj


def cmd_run(case):
    wd = _workdir(case)
    prj = wd / f"{case['name']}.prj"
    sim = OGSSimulation(prj, case.get("ogs_executable", "ogs"), output_dir=wd / "out")
    res = sim.run(log_file=wd / "ogs.log")
    print(f"done rc={res.returncode} -> {res.output_dir}")
    return res


def cmd_gui(case_path=None):
    """Launch the Streamlit case editor."""
    import subprocess
    try:
        import streamlit  # noqa: F401
    except ImportError:
        raise SystemExit(
            "the editor needs streamlit:  pip install 'ogsfrac[ui]'"
        )
    app = Path(__file__).parent / "ui" / "app.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(app)]
    if case_path:
        cmd += ["--", str(case_path)]
    return subprocess.call(cmd)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ogsfrac")
    ap.add_argument("--version", action="version", version=f"ogsfrac {__version__}")
    ap.add_argument("stage", choices=["geometry", "mesh", "prj", "run", "all", "gui"])
    ap.add_argument("case", type=Path, nargs="?")
    args = ap.parse_args(argv)

    if args.stage == "gui":
        return cmd_gui(args.case)
    if args.case is None:
        ap.error("a case file is required")
    case = load_case(args.case)

    stages = ["geometry", "mesh", "prj", "run"] if args.stage == "all" else [args.stage]
    for s in stages:
        print(f"\n=== {s} ===")
        globals()[f"cmd_{s}"](case)
    return 0


if __name__ == "__main__":
    sys.exit(main())
