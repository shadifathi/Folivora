"""Assemble a .prj from a case description.

The parts that were hardcoded per-notebook — media table, parameters, boundary
conditions — are generated here from the case dict. Everything else comes from
the process preset, and `overrides` in the case file wins over both.
"""
from __future__ import annotations

from pathlib import Path

from .presets import PROCESS_INFO, get_preset
from .xmlutil import deep_merge, write_prj


def _maybe_number(v):
    """Coerce '1e-13' -> 1e-13.

    YAML 1.1 (which PyYAML implements) only recognises an exponent float if it
    has a decimal point and a signed exponent: `1.0e-13` is a float, `1e-13`
    is a *string*. Permeabilities are written the second way by everyone, and
    a string here means "Parameter reference", so `permeability: 1e-13` would
    silently emit <type>Parameter</type><parameter_name>1e-13</parameter_name>
    and OGS would die looking for a parameter named "1e-13".
    """
    if not isinstance(v, str):
        return v
    try:
        return float(v)
    except ValueError:
        return v


def _phase(kind: str, props: dict) -> dict:
    return {
        "type": kind,
        "properties": {
            "property": [
                {"name": k, "type": "Constant", "value": _maybe_number(v)}
                for k, v in props.items()
            ]
        },
    }


def build_media(materials: list[dict], process_type: str = "LIQUID_FLOW") -> dict:
    """Media block from a flat material table.

    Each entry: {id, name, permeability, porosity, ...} plus optional `fluid`
    and `solid` dicts for the phase properties. Values that are strings are
    emitted as Parameter references (e.g. a MeshNode field); numbers become
    Constant properties. That distinction was previously made by hand in
    `add_medium(..., k_param_name="perm")`.

    The Solid phase matters: LiquidFlowProject only ever wrote AqueousLiquid,
    but HT and THERMO_RICHARDS_MECHANICS need solid density, heat capacity and
    conductivity too.
    """
    info = PROCESS_INFO.get(process_type, PROCESS_INFO["LIQUID_FLOW"])
    fluid_defaults = {p.name: p.default for p in info["fluid"]}
    solid_defaults = {p.name: p.default for p in info["solid"]}

    media = []
    for m in materials:
        props = []
        for key, val in m.items():
            if key in ("id", "name", "phases", "fluid", "solid"):
                continue
            val = _maybe_number(val)
            if isinstance(val, dict):
                props.append({"name": key, **val})
            elif isinstance(val, str):
                props.append({"name": key, "type": "Parameter", "parameter_name": val})
            else:
                props.append({"name": key, "type": "Constant", "value": val})

        if "phases" in m:
            phases = m["phases"]
        else:
            phase_list = []
            fluid = {**fluid_defaults, **(m.get("fluid") or {})}
            if fluid:
                phase_list.append(_phase("AqueousLiquid", fluid))
            solid = {**solid_defaults, **(m.get("solid") or {})}
            if solid:
                phase_list.append(_phase("Solid", solid))
            phases = {"phase": phase_list}

        media.append({"@id": m["id"], "phases": phases, "properties": {"property": props}})
    return {"medium": media}


def build_parameters(parameters: dict) -> dict:
    """Parameters block.

    Scalars -> Constant. Dicts pass through, so a MeshNode parameter is:
        perm: {type: MeshNode, mesh: mesh2, field_name: permeability}
    """
    out = []
    for name, spec in parameters.items():
        if isinstance(spec, dict):
            out.append({"name": name, **spec})
        else:
            out.append({"name": name, "type": "Constant", "value": _maybe_number(spec)})
    return {"parameter": out}


def build_process_variables(process_variables: dict) -> dict:
    """Process variables with their ICs and BCs.

    A BC entry is {mesh, type, parameter|component|value...}, which is close
    enough to the OGS schema that you can read it against the docs.
    """
    out = []
    for name, spec in process_variables.items():
        pv = {
            "name": name,
            "components": spec.get("components", 1),
            "order": spec.get("order", 1),
            "initial_condition": spec["initial_condition"],
        }
        bcs = spec.get("boundary_conditions") or []
        if bcs:
            pv["boundary_conditions"] = {"boundary_condition": bcs}
        sts = spec.get("source_terms") or []
        if sts:
            pv["source_terms"] = {"source_term": sts}
        out.append(pv)
    return {"process_variable": out}


def build_prj(case: dict, filename=None) -> Path:
    """Build a .prj from a case dict (see cases/*.yml).

    Order of precedence: preset < generated blocks < case["overrides"].
    """
    proc_type = case["process"]["type"]
    tree = get_preset(proc_type)

    # meshes
    meshes = case["meshes"]
    if isinstance(meshes, str):
        meshes = [meshes]
    tree = {"meshes": {"mesh": meshes}, **tree}

    # generated blocks
    if case.get("materials"):
        tree["media"] = build_media(case["materials"], proc_type)
    if case.get("parameters"):
        tree["parameters"] = build_parameters(case["parameters"])
    if case.get("process_variables"):
        tree["process_variables"] = build_process_variables(case["process_variables"])

    # time / output shortcuts so the common edits stay one-liners
    tl = tree["time_loop"]["processes"]["process"]
    if "t_end" in case:
        tl["time_stepping"]["t_end"] = case["t_end"]
    if "t_initial" in case:
        tl["time_stepping"]["t_initial"] = case["t_initial"]
    if "output_prefix" in case:
        tree["time_loop"]["output"]["prefix"] = case["output_prefix"]
    if "output_variables" in case:
        tree["time_loop"]["output"]["variables"] = {
            "variable": case["output_variables"]
        }

    # escape hatch: raw prj tree fragments, merged last
    tree = deep_merge(tree, case.get("overrides", {}))

    filename = filename or case.get("prj_file", "project.prj")
    return write_prj(tree, filename)
