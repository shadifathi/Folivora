"""Case files: YAML in, objects out.

One file describes a study end to end. Nothing else should contain coordinates.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

from .geometry.boreholes import load_boreholes
from .geometry.planes import Plane
from .meshing.builder import Domain, FractureSpec, MeshOptions, Refinement, TunnelSpec


def load_case(path) -> dict:
    path = Path(path)
    with path.open() as fh:
        case = yaml.safe_load(fh)
    case["_dir"] = path.parent
    case.setdefault("name", path.stem)
    return case


def _resolve(case, p):
    return (Path(case["_dir"]) / p).resolve() if not Path(p).is_absolute() else Path(p)


def planes_from_case(case) -> list[Plane]:
    """Build fracture planes from the case file.

    Each fracture is defined by exactly one of:
      points:        [[x,y,z] x3]        -> exact plane through 3 points
      fit_points:    [[x,y,z] xN]        -> least-squares plane + residual
      dip/azimuth + point                -> orientation-defined plane
      from_intersections: <borehole set> -> fit to borehole intersections
    """
    planes = []
    for spec in case.get("fractures", []):
        name = spec["name"]
        if "points" in spec:
            planes.append(Plane.from_3points(*spec["points"], name=name))
        elif "fit_points" in spec:
            planes.append(Plane.fit(spec["fit_points"], name=name))
        elif "dip" in spec and "azimuth" in spec:
            planes.append(Plane.from_dip_azimuth(spec["dip"], spec["azimuth"], spec["point"], name=name))
        else:
            raise ValueError(
                f"fracture '{name}': need one of points / fit_points / (dip, azimuth, point)"
            )
    return planes


def boreholes_from_case(case):
    bh = case.get("boreholes")
    if not bh:
        return []
    return load_boreholes(_resolve(case, bh["file"]), sheet=bh.get("sheet"), sep=bh.get("sep", "\t"))


def mesh_inputs_from_case(case):
    """-> (Domain, [FractureSpec], TunnelSpec|None, MeshOptions, obs_points)"""
    d = case["domain"]
    domain = Domain(**{k: d[k] for k in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax")},
                    lc=d.get("lc", 8.0),
                    material_id=d.get("material_id", 0),
                    name=d.get("name", "Rock"))

    planes = {p.name: p for p in planes_from_case(case)}
    fractures = []
    for spec in case.get("fractures", []):
        pl = planes[spec["name"]]
        corners = pl.corners(half_size=spec.get("half_size", 100.0), center=spec.get("center"))
        refine = Refinement(**spec["refine"]) if spec.get("refine") else None
        fractures.append(
            FractureSpec(
                name=spec["name"],
                corners=corners,
                representation=spec.get("representation", "surface"),
                thickness=spec.get("thickness", 0.01),
                lc=spec.get("lc", 2.0),
                material_id=spec.get("material_id"),
                refine=refine,
                conform=spec.get("conform", "embed"),
            )
        )

    tunnel = None
    if case.get("tunnel"):
        t = dict(case["tunnel"])
        if "file" in t:
            import pandas as pd
            df = pd.read_excel(_resolve(case, t.pop("file")), sheet_name=t.pop("sheet", "Tunnel"))
            t["polygon"] = df.iloc[:, 1:4].astype(float).dropna().values
        tunnel = TunnelSpec(**t)

    options = MeshOptions(**case.get("mesh_options", {}))

    obs = case.get("observation_points", {})
    if isinstance(obs, str):
        import pandas as pd
        df = pd.read_excel(_resolve(case, obs))
        obs = {str(r[0]): tuple(float(v) for v in r[1:4]) for r in df.itertuples(index=False)}

    return domain, fractures, tunnel, options, obs
