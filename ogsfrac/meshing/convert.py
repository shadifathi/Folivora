"""msh -> OGS-ready vtu, plus subdomain extraction.

Consolidates MeshConverter / VtuMaterialMapper / MeshInspector /
save_mesh_ogs_compatible, which appeared in DesignModel, HydroModel and idea2d.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

try:
    import meshio
except ImportError:  # pragma: no cover
    meshio = None

# gmsh physical tags -> OGS MaterialIDs
_CELL_ORDER = ["tetra", "hexahedron", "wedge", "pyramid", "triangle", "quad", "line", "vertex"]


def _require_meshio():
    if meshio is None:
        raise ImportError("meshio is required: pip install meshio")


def msh_to_vtu(
    msh_file,
    vtu_file=None,
    dim=3,
    mixed=True,
    material_tag_offset=1,
    boundary_tag_base=1000,
    material_key="gmsh:physical",
) -> Path:
    """Convert a gmsh .msh to an OGS bulk .vtu with int32 MaterialIDs.

    Two things this gets right that the notebook version did not:

    1. `mixed=True` keeps lower-dimensional *material* elements (the fracture
       triangles) in the bulk mesh, while excluding boundary triangles
       (physical tag >= `boundary_tag_base`). Without this, a `representation:
       surface` fracture is written to the .msh and then silently dropped on
       conversion — the .vtu has no fractures in it at all.
    2. MaterialIDs are int32. meshio emits gmsh:physical as int64, which OGS
       rejects at load time.
    """
    _require_meshio()
    msh_file = Path(msh_file)
    vtu_file = Path(vtu_file) if vtu_file else msh_file.with_suffix(".vtu")
    mesh = meshio.read(msh_file)

    top = {3: ["tetra", "hexahedron", "wedge", "pyramid"], 2: ["triangle", "quad"]}[dim]
    lower = {3: ["triangle", "quad"], 2: ["line"]}[dim] if mixed else []

    cells, mat_ids = [], []
    for block in mesh.cells:
        tags = mesh.cell_data_dict.get(material_key, {}).get(block.type)
        if block.type in top:
            if tags is None:
                tags = np.full(len(block.data), material_tag_offset)
            keep = np.arange(len(block.data))
        elif block.type in lower and tags is not None:
            keep = np.where(np.asarray(tags) < boundary_tag_base)[0]
            if len(keep) == 0:
                continue
        else:
            continue
        cells.append(meshio.CellBlock(block.type, block.data[keep]))
        mat_ids.append(np.asarray(tags)[keep].astype(np.int32) - material_tag_offset)

    if not cells:
        raise ValueError(
            f"{msh_file.name} has no {dim}D cells of types {top}. "
            f"Present: {sorted({b.type for b in mesh.cells})}"
        )
    if (np.concatenate(mat_ids) < 0).any():
        raise ValueError(
            "negative MaterialIDs after removing the tag offset — the mesh was "
            "probably not written by FracturedDomainMesh. Pass material_tag_offset=0."
        )

    out = meshio.Mesh(points=mesh.points, cells=cells, cell_data={"MaterialIDs": mat_ids})
    out.write(vtu_file, file_format="vtu", binary=True)
    return vtu_file


def extract_subdomain(msh_file, name, vtu_file=None, tag=None) -> Path:
    """Write the mesh of one physical group as its own .vtu.

    OGS binds boundary conditions to submeshes listed in <meshes>, and matches
    them by *filename stem*. So `extract_subdomain(msh, "FZ1")` produces FZ1.vtu,
    and the BC refers to mesh "FZ1".

    The submesh carries bulk_node_ids / bulk_element_ids, which OGS needs to map
    the submesh back onto the bulk mesh.
    """
    _require_meshio()
    msh_file = Path(msh_file)
    mesh = meshio.read(msh_file)
    vtu_file = Path(vtu_file) if vtu_file else msh_file.parent / f"{name}.vtu"

    field = mesh.field_data.get(name)
    if field is None and tag is None:
        raise KeyError(
            f"physical group '{name}' not in {msh_file.name}. "
            f"Available: {sorted(mesh.field_data)}"
        )
    tag = tag if tag is not None else int(field[0])

    sel_cells, sel_types = [], []
    for block in mesh.cells:
        tags = mesh.cell_data_dict.get("gmsh:physical", {}).get(block.type)
        if tags is None:
            continue
        idx = np.where(np.asarray(tags) == tag)[0]
        if len(idx):
            sel_cells.append(block.data[idx])
            sel_types.append(block.type)
    if not sel_cells:
        raise ValueError(f"physical group '{name}' (tag {tag}) contains no cells")

    used = np.unique(np.concatenate([c.ravel() for c in sel_cells]))
    remap = -np.ones(len(mesh.points), dtype=np.int64)
    remap[used] = np.arange(len(used))

    out = meshio.Mesh(
        points=mesh.points[used],
        cells=[(t, remap[c]) for t, c in zip(sel_types, sel_cells)],
        point_data={"bulk_node_ids": used.astype(np.uint64)},
    )
    out.write(vtu_file, file_format="vtu", binary=True)
    return vtu_file


def inspect(msh_file) -> dict:
    """Summarise a mesh: physical groups, cell counts, bounds. (MeshInspector.)"""
    _require_meshio()
    mesh = meshio.read(Path(msh_file))
    info = {
        "n_points": len(mesh.points),
        "bounds": {
            "min": mesh.points.min(axis=0).tolist(),
            "max": mesh.points.max(axis=0).tolist(),
        },
        "cells": {b.type: len(b.data) for b in mesh.cells},
        "physical_groups": {k: int(v[0]) for k, v in mesh.field_data.items()},
    }
    return info
