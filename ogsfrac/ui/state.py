"""UI logic, with no UI in it.

Everything here is a pure function over the case dict, so the editor can be
tested headlessly and the same checks can run in CI or from a notebook. The
Streamlit app in `app.py` is a thin rendering layer over this module.
"""
from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import yaml

from ..config import mesh_inputs_from_case, planes_from_case
from ..meshing.builder import FracturedDomainMesh

__all__ = ["FracturedDomainMesh"]
from ..prj.presets import PROCESS_INFO

ERROR, WARNING, OK = "error", "warning", "ok"


def default_case(name="new_case") -> dict:
    return {
        "name": name,
        "workdir": f"work/{name}",
        "domain": {
            "xmin": -150.0, "xmax": 150.0,
            "ymin": -120.0, "ymax": 200.0,
            "zmin": -100.0, "zmax": 0.0,
            "lc": 20.0, "name": "Rock", "material_id": 0,
        },
        "fractures": [],
        "mesh_options": {"msh_version": 2.2},
        "process": {"type": "LIQUID_FLOW"},
        "meshes": [f"{name}.vtu"],
        "t_initial": 0.0,
        "t_end": 400.0,
        "output_prefix": "result",
        "output_variables": ["pressure", "v"],
        "materials": [],
        "parameters": {},
        "process_variables": {},
    }


def new_fracture(index: int) -> dict:
    return {
        "name": f"FZ{index}",
        "points": [[0.0, 0.0, -10.0], [10.0, 0.0, -10.0], [0.0, 10.0, -10.0]],
        "half_size": 50.0,
        "representation": "surface",
        "conform": "fragment",
        "lc": 6.0,
        "material_id": index,
    }


# ----------------------------------------------------------------------------
# Keeping the case internally consistent
# ----------------------------------------------------------------------------

def sync_materials(case: dict) -> dict:
    """One material per material_id in use, seeded from the process defaults.

    Adding a fracture should not mean remembering to add a medium. Values the
    user already set are preserved; properties the new process needs are added;
    materials whose id no longer exists are dropped.
    """
    case = copy.deepcopy(case)
    info = PROCESS_INFO[case["process"]["type"]]
    defaults = {p.name: p.default for p in info["medium"]}

    used = {case["domain"]["material_id"]: case["domain"].get("name", "Rock")}
    for i, f in enumerate(case.get("fractures", [])):
        mid = f.get("material_id")
        if mid is None:
            mid = i + 1
            f["material_id"] = mid
        used[mid] = f["name"]

    existing = {m["id"]: m for m in case.get("materials", [])}
    materials = []
    for mid, label in sorted(used.items()):
        m = existing.get(mid, {})
        merged = {"id": mid, "name": label}
        for key, dflt in defaults.items():
            merged[key] = m.get(key, dflt)
        # keep any extra properties the user added by hand
        for key, val in m.items():
            if key not in merged and key not in ("id", "name"):
                merged[key] = val
        materials.append(merged)
    case["materials"] = materials
    return case


def sync_process_variables(case: dict) -> dict:
    """Match process variables and parameters to the selected coupling."""
    case = copy.deepcopy(case)
    info = PROCESS_INFO[case["process"]["type"]]

    params = dict(case.get("parameters") or {})
    for name, val in info["parameters"].items():
        params.setdefault(name, val)
    case["parameters"] = params

    pvs = dict(case.get("process_variables") or {})
    out = {}
    for name, spec in info["variables"].items():
        prev = pvs.get(name, {})
        out[name] = {
            "components": spec["components"],
            "order": prev.get("order", 1),
            "initial_condition": prev.get("initial_condition", spec["ic"]),
            "boundary_conditions": prev.get("boundary_conditions", []),
        }
    case["process_variables"] = out
    return case


def sync_meshes(case: dict) -> dict:
    """<meshes> = bulk mesh + every submesh referenced by a BC.

    OGS matches a BC's <mesh> to a file stem listed in <meshes>. Forgetting to
    list one is an error you otherwise only find when OGS aborts.
    """
    case = copy.deepcopy(case)
    bulk = f"{case['name']}.vtu"
    meshes = [bulk]
    for spec in (case.get("process_variables") or {}).values():
        for bc in spec.get("boundary_conditions") or []:
            vtu = f"{bc['mesh']}.vtu"
            if vtu not in meshes:
                meshes.append(vtu)
    case["meshes"] = meshes
    return case


def sync_all(case: dict) -> dict:
    return sync_meshes(sync_process_variables(sync_materials(case)))


# ----------------------------------------------------------------------------
# Reporting
# ----------------------------------------------------------------------------

def fracture_table(case: dict) -> list[dict]:
    """Orientation readout: what the notebooks printed and pasted into comments."""
    rows = []
    try:
        planes = planes_from_case(case)
    except (ValueError, KeyError) as exc:
        return [{"name": "-", "error": str(exc)}]
    by_name = {p.name: p for p in planes}
    for spec in case.get("fractures", []):
        p = by_name.get(spec["name"])
        if p is None:
            continue
        dip, azi = p.dip_azimuth
        rows.append({
            "name": p.name,
            "dip": round(dip, 2),
            "azimuth": round(azi, 2),
            "normal": np.round(p.normal, 6).tolist(),
            "fit_rms": None if p.residual is None else round(p.residual, 4),
            "representation": spec.get("representation", "surface"),
            "material_id": spec.get("material_id"),
        })
    return rows


def validation_report(case: dict) -> list[tuple[str, str]]:
    """Everything checkable without meshing. Returns [(level, message)].

    This runs the real `FracturedDomainMesh` validator, so what the UI shows is
    exactly what the pipeline enforces — there is no second implementation to
    drift.
    """
    out: list[tuple[str, str]] = []

    try:
        domain, fractures, tunnel, options, obs = mesh_inputs_from_case(case)
    except Exception as exc:
        return [(ERROR, f"geometry: {exc}")]

    try:
        FracturedDomainMesh(domain, fractures, tunnel, obs, options)
    except Exception as exc:
        out.append((ERROR, f"mesh: {exc}"))

    # fracture patches leaving the domain get silently trimmed
    for f in fractures:
        if not domain.contains(f.corners).all():
            out.append((WARNING, f"{f.name}: patch extends past the domain and will be "
                                 f"trimmed — reduce half_size to control it explicitly"))

    # gravity direction vs. the vertical axis of the model
    body = (case.get("overrides", {}).get("processes", {})
            .get("process", {}).get("specific_body_force"))
    if body and len(body) == 3 and abs(float(body[2])) < 1e-9 and abs(float(body[1])) > 1e-9:
        out.append((WARNING, "specific_body_force points along y, but the domain's "
                             "vertical axis is z — gravity would act sideways"))

    # BCs must reference a listed mesh and an existing parameter
    listed = {Path(m).stem for m in case.get("meshes", [])}
    params = set(case.get("parameters") or {})
    frac_names = {f.name for f in fractures}
    for var, spec in (case.get("process_variables") or {}).items():
        if spec.get("initial_condition") not in params:
            out.append((ERROR, f"{var}: initial_condition "
                               f"'{spec.get('initial_condition')}' is not a parameter"))
        for bc in spec.get("boundary_conditions") or []:
            if bc.get("mesh") not in listed:
                out.append((ERROR, f"{var} BC on '{bc.get('mesh')}': not in <meshes>"))
            elif bc["mesh"] not in frac_names and bc["mesh"] not in (
                    list(FracturedDomainMesh.BOUNDARY_NAMES) + ["tunnel_surfaces"]):
                out.append((WARNING, f"{var} BC on '{bc['mesh']}': no such fracture or "
                                     f"boundary — the submesh may not exist"))
            if bc.get("parameter") and bc["parameter"] not in params:
                out.append((ERROR, f"{var} BC on '{bc.get('mesh')}': parameter "
                                   f"'{bc['parameter']}' is not defined"))
        if not (spec.get("boundary_conditions") or []):
            out.append((WARNING, f"{var}: no boundary conditions — the problem is "
                                 f"unconstrained"))

    # materials must cover every material id present in the mesh
    mat_ids = {m["id"] for m in case.get("materials", [])}
    needed = {domain.material_id} | {
        f.material_id for f in fractures if f.material_id is not None
    }
    for mid in sorted(needed - mat_ids):
        out.append((ERROR, f"material_id {mid} is used by the mesh but has no medium"))

    if case.get("t_end", 1) <= case.get("t_initial", 0):
        out.append((ERROR, "t_end must be greater than t_initial"))

    # a rough element-count estimate, because this is where hours get lost
    est = estimate_elements(case)
    if est > 5e6:
        out.append((WARNING, f"~{est:.1e} elements at these mesh sizes — expect a long "
                             f"meshing run and a large .vtu"))

    if not out:
        out.append((OK, "no problems found"))
    return out


def estimate_elements(case: dict) -> float:
    """Very rough tet count: domain volume / (lc^3 / 6), refined zones scaled.

    Not accurate — it is meant to catch the "size_min: 1 over a 200 m patch"
    class of mistake before you wait twenty minutes to discover it.
    """
    d = case["domain"]
    vol = (d["xmax"] - d["xmin"]) * (d["ymax"] - d["ymin"]) * (d["zmax"] - d["zmin"])
    lc = max(d.get("lc", 10.0), 1e-6)
    n = vol / (lc ** 3 / 6.0)
    for f in case.get("fractures", []):
        r = f.get("refine")
        if not r:
            continue
        half = f.get("half_size", 50.0)
        band = 2 * (2 * half) ** 2 * r.get("dist_max", 10.0)
        smin = max(r.get("size_min", 1.0), 1e-6)
        n += band / (smin ** 3 / 6.0)
    return float(n)


# ----------------------------------------------------------------------------
# Files
# ----------------------------------------------------------------------------

def case_to_yaml(case: dict) -> str:
    clean = {k: v for k, v in case.items() if not k.startswith("_")}
    return yaml.safe_dump(clean, sort_keys=False, default_flow_style=False, width=100)


def yaml_to_case(text: str) -> dict:
    case = yaml.safe_load(text)
    if not isinstance(case, dict):
        raise ValueError("case file must be a YAML mapping")
    case.setdefault("_dir", Path("."))
    return case


def save_case(case: dict, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(case_to_yaml(case))
    return path
