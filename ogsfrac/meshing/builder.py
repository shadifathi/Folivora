"""Fractured-domain mesh generation with gmsh/OCC.

Unifies the two representations that lived in separate notebooks:

  * `representation="surface"` -> fracture is a 2D manifold embedded in the
    matrix (Untitled-1.ipynb: `gmsh.model.mesh.embed(2, [s1,s2,s3], 3, host)`).
  * `representation="volume"`  -> fracture is a thin 3D layer, extruded along
    its normal and fragmented into the host (DesignModel.ipynb `FaultedCubeMesh`).

Everything that was a literal inside `generate()` is now a field on a dataclass.
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

try:
    import gmsh
except ImportError:  # pragma: no cover
    gmsh = None


# ----------------------------------------------------------------------------
# Specs
# ----------------------------------------------------------------------------

@dataclass
class Refinement:
    """Distance+Threshold field around a fracture (was inlined per-fault)."""

    size_min: float = 1.0
    size_max: float = 4.0
    dist_min: float = 1.0
    dist_max: float = 8.0
    sampling: int = 100


@dataclass
class Domain:
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    zmin: float
    zmax: float
    lc: float = 8.0
    material_id: int = 0
    name: str = "Rock"

    @property
    def origin(self):
        return (self.xmin, self.ymin, self.zmin)

    @property
    def extent(self):
        return (self.xmax - self.xmin, self.ymax - self.ymin, self.zmax - self.zmin)

    def contains(self, pts, tol=0.0) -> np.ndarray:
        p = np.atleast_2d(np.asarray(pts, float))
        return (
            (p[:, 0] >= self.xmin - tol) & (p[:, 0] <= self.xmax + tol)
            & (p[:, 1] >= self.ymin - tol) & (p[:, 1] <= self.ymax + tol)
            & (p[:, 2] >= self.zmin - tol) & (p[:, 2] <= self.zmax + tol)
        )


@dataclass
class FractureSpec:
    name: str
    corners: np.ndarray            # (4,3), CCW — use Plane.corners()
    representation: str = "surface"  # "surface" | "volume"
    thickness: float = 0.01          # only for representation="volume"
    lc: float = 2.0
    material_id: int | None = None
    refine: Refinement | None = None
    conform: str = "embed"           # "embed" | "fragment"; surface only

    def __post_init__(self):
        self.corners = np.asarray(self.corners, dtype=float)
        if self.corners.shape != (4, 3):
            raise ValueError(f"{self.name}: corners must be (4,3), got {self.corners.shape}")
        if self.representation not in ("surface", "volume"):
            raise ValueError(f"{self.name}: representation must be 'surface' or 'volume'")
        if self.conform not in ("embed", "fragment"):
            raise ValueError(f"{self.name}: conform must be 'embed' or 'fragment'")

    @property
    def normal(self) -> np.ndarray:
        P = self.corners
        n = np.cross(P[1] - P[0], P[2] - P[0])
        return n / np.linalg.norm(n)


@dataclass
class TunnelSpec:
    """Polygon footprint extruded vertically, then cut from the domain."""

    name: str = "tunnel"
    polygon: np.ndarray = None    # (N,3) footprint at z = base_z
    height: float = 5.0
    lc: float = 1.0

    def __post_init__(self):
        if self.polygon is not None:
            self.polygon = np.asarray(self.polygon, dtype=float)
            if self.polygon.ndim != 2 or self.polygon.shape[1] != 3:
                raise ValueError("tunnel polygon must be (N,3)")


@dataclass
class MeshOptions:
    algorithm_2d: int = 6
    algorithm_3d: int = 1
    optimize: int = 2
    smoothing: int = 5
    size_from_curvature: bool = True
    geometry_tolerance: float = 1e-4
    delaunay_tolerance: float = 1e-4
    msh_version: float = 2.2       # msh2vtu/meshio expect 2.2


# ----------------------------------------------------------------------------
# Builder
# ----------------------------------------------------------------------------

class FracturedDomainMesh:
    """Build a fractured (optionally tunnelled) rock-mass mesh.

    Replaces `FaultedCubeMesh` and the free-floating gmsh cells. Boundary
    surfaces are auto-tagged left/right/front/back/up/down by bounding box,
    with everything else grouped as tunnel wall — same rule as Untitled-1, but
    reusable.
    """

    BOUNDARY_NAMES = ("left", "right", "front", "back", "up", "down")

    # gmsh only honours *positive* physical tags: addPhysicalGroup(tag=0) is
    # treated as "auto-assign", which silently collided Rock (material_id 0)
    # with whatever tag came next. So physical tag = material_id + OFFSET, and
    # the offset is undone in msh_to_vtu. Non-material groups live above
    # BOUNDARY_TAG_BASE so they can never collide with a material.
    MATERIAL_TAG_OFFSET = 1
    BOUNDARY_TAG_BASE = 1000
    OBS_TAG_BASE = 2000

    def __init__(
        self,
        domain: Domain,
        fractures: list[FractureSpec] | None = None,
        tunnel: TunnelSpec | None = None,
        observation_points: dict | None = None,
        options: MeshOptions | None = None,
        obs_lc: float = 0.1,
        bbox_tol: float = 1e-3,
    ):
        if gmsh is None:
            raise ImportError("gmsh is required: pip install gmsh")
        self.domain = domain
        self.fractures = list(fractures or [])
        self.tunnel = tunnel
        self.observation_points = dict(observation_points or {})
        self.options = options or MeshOptions()
        self.obs_lc = obs_lc
        self.bbox_tol = bbox_tol
        self.material_ids: dict[str, int] = {}
        self._validate()

    def _validate(self):
        names = [f.name for f in self.fractures]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate fracture names: {names}")
        # OGS keys media by MaterialIDs, so a duplicate silently merges two
        # materials into one medium.
        ids = {self.domain.name: self.domain.material_id}
        for i, f in enumerate(self.fractures):
            ids[f.name] = f.material_id if f.material_id is not None else i + 1
        dupes = {k: v for k, v in ids.items() if list(ids.values()).count(v) > 1}
        if dupes:
            raise ValueError(f"duplicate material_id across {dupes}")
        # Fail loudly rather than let gmsh emit a silently broken mesh.
        for f in self.fractures:
            if f.representation == "surface" and f.conform == "embed":
                inside = self.domain.contains(f.corners, tol=-1e-9)
                if not inside.all():
                    raise ValueError(
                        f"{f.name}: corners reach or exceed the domain boundary, so "
                        f"gmsh cannot embed the surface. Either shrink half_size, "
                        f"grow the domain, or set conform='fragment'."
                    )
        for name, xyz in self.observation_points.items():
            if not self.domain.contains(np.asarray(xyz, float).reshape(1, 3))[0]:
                raise ValueError(f"observation point {name} at {xyz} is outside the domain")
        self._check_embedded_intersections()

    def _check_embedded_intersections(self):
        """Embedded surfaces may not intersect each other.

        gmsh.mesh.embed does not imprint intersections, so two crossing
        embedded fractures reach tetgen as a broken PLC and fail with
        "A segment and a facet intersect at point" — which says nothing about
        which fractures are at fault. Catch it here instead.
        """
        emb = [f for f in self.fractures
               if f.representation == "surface" and f.conform == "embed"]
        for a in emb:
            for b in self.fractures:
                if b is a or not self._patches_may_cross(a, b):
                    continue
                raise ValueError(
                    f"fracture '{a.name}' (conform='embed') intersects '{b.name}'. "
                    f"embed() cannot imprint an intersection, so tetgen would fail with "
                    f"'A segment and a facet intersect'. Fix: set conform='fragment' on "
                    f"'{a.name}'"
                    + (f" and '{b.name}'" if b.representation == "surface"
                       and b.conform == "embed" else "")
                    + f", or reduce half_size so the patches no longer meet."
                )

    @staticmethod
    def _patches_may_cross(a: "FractureSpec", b: "FractureSpec") -> bool:
        """True if each patch straddles the other's plane (necessary condition)."""
        def straddles(patch, other):
            n = other.normal
            d = -float(np.dot(n, other.corners[0]))
            s = patch.corners @ n + d
            return s.min() < -1e-9 and s.max() > 1e-9
        return straddles(a, b) and straddles(b, a)

    # -- context management: never leak a gmsh session on error -------------
    @contextlib.contextmanager
    def _session(self, model_name="fractured_domain"):
        gmsh.initialize()
        try:
            gmsh.model.add(model_name)
            yield
        finally:
            gmsh.finalize()

    def generate(self, msh_file="mesh.msh", gui=False) -> Path:
        msh_file = Path(msh_file)
        with self._session():
            self._apply_options()
            host = self._build_host()
            host = self._cut_tunnel(host)
            host_pieces = self._add_fractures(host)
            self._tag_boundaries(host_pieces)
            self._add_observation_points(host_pieces)
            self._apply_refinement()
            gmsh.model.occ.synchronize()
            gmsh.model.mesh.generate(3)
            gmsh.option.setNumber("Mesh.MshFileVersion", self.options.msh_version)
            gmsh.write(str(msh_file))
            if gui:
                gmsh.fltk.run()
        return msh_file

    # -- steps -------------------------------------------------------------
    def _apply_options(self):
        o = self.options
        gmsh.option.setNumber("Mesh.Algorithm", o.algorithm_2d)
        gmsh.option.setNumber("Mesh.Algorithm3D", o.algorithm_3d)
        gmsh.option.setNumber("Mesh.Optimize", o.optimize)
        gmsh.option.setNumber("Mesh.Smoothing", o.smoothing)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 1 if o.size_from_curvature else 0)
        gmsh.option.setNumber("Geometry.Tolerance", o.geometry_tolerance)
        gmsh.option.setNumber("Mesh.ToleranceInitialDelaunay", o.delaunay_tolerance)

    def _build_host(self) -> int:
        d = self.domain
        vol = gmsh.model.occ.addBox(*d.origin, *d.extent)
        gmsh.model.occ.synchronize()
        return vol

    def _cut_tunnel(self, host: int) -> int:
        if self.tunnel is None or self.tunnel.polygon is None:
            return host
        pts = [gmsh.model.occ.addPoint(*p, self.tunnel.lc) for p in self.tunnel.polygon]
        lines = [
            gmsh.model.occ.addLine(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))
        ]
        loop = gmsh.model.occ.addCurveLoop(lines)
        surf = gmsh.model.occ.addSurfaceFilling(loop)
        gmsh.model.occ.synchronize()
        ext = gmsh.model.occ.extrude([(2, surf)], 0, 0, self.tunnel.height)
        tunnel_vol = next(t for (dim, t) in ext if dim == 3)
        gmsh.model.occ.synchronize()
        out, _ = gmsh.model.occ.cut(
            [(3, host)], [(3, tunnel_vol)], removeObject=True, removeTool=True
        )
        gmsh.model.occ.synchronize()
        return out[0][1]

    def _add_fractures(self, host: int):
        """Insert all fractures, then return the list of host volume tags.

        Volume fractures and `conform="fragment"` surfaces go into a *single*
        fragment call. Doing them one at a time (as the notebooks did) is both
        slower and wrong when fractures intersect each other: OCC needs to see
        all the tools at once to imprint every mutual intersection.
        """
        self._surface_tags: dict[str, list[int]] = {}
        next_mat = 1

        vol_specs = [f for f in self.fractures if f.representation == "volume"]
        frag_specs = [f for f in self.fractures
                      if f.representation == "surface" and f.conform == "fragment"]
        embed_specs = [f for f in self.fractures
                       if f.representation == "surface" and f.conform == "embed"]

        tools = [(3, self._make_fracture_volume(f)) for f in vol_specs]
        tools += [(2, self._make_fracture_surface(f)) for f in frag_specs]
        embed_tags = {f.name: self._make_fracture_surface(f) for f in embed_specs}
        gmsh.model.occ.synchronize()

        if tools:
            _, out_map = gmsh.model.occ.fragment([(3, host)], tools)
            gmsh.model.occ.synchronize()
            host_pieces = [t for (dim, t) in out_map[0] if dim == 3]

            for i, f in enumerate(vol_specs, start=1):
                pieces = self._drop_outside(3, [t for (dim, t) in out_map[i] if dim == 3], f.name)
                mat = f.material_id if f.material_id is not None else next_mat
                next_mat = max(next_mat, mat + 1)
                # a fragmented piece belongs to both inputs; the fracture wins
                host_pieces = [t for t in host_pieces if t not in pieces]
                self._add_material_group(3, pieces, mat, f.name)

            for j, f in enumerate(frag_specs, start=1 + len(vol_specs)):
                surfs = self._drop_outside(2, [t for (dim, t) in out_map[j] if dim == 2], f.name)
                self._surface_tags[f.name] = surfs
        else:
            host_pieces = [host]

        self._add_material_group(3, host_pieces, self.domain.material_id, self.domain.name)

        # embedded surfaces: each must sit strictly inside one host piece
        for name, tag in embed_tags.items():
            target = self._volume_containing(gmsh.model.occ.getCenterOfMass(2, tag), host_pieces)
            gmsh.model.mesh.embed(2, [tag], 3, target)
            self._surface_tags[name] = [tag]

        for f in frag_specs + embed_specs:
            mat = f.material_id if f.material_id is not None else next_mat
            next_mat = max(next_mat, mat + 1)
            self._add_material_group(2, self._surface_tags[f.name], mat, f.name)
        return host_pieces

    def _add_material_group(self, dim, tags, material_id, name):
        gmsh.model.addPhysicalGroup(dim, tags, material_id + self.MATERIAL_TAG_OFFSET,
                                    name=name)
        self.material_ids[name] = material_id

    def _drop_outside(self, dim, tags, name):
        """Discard entities whose centre of mass lies outside the domain.

        A fracture patch that overhangs the box leaves stray entities after
        fragment(); meshing them wastes elements and pollutes material groups.
        """
        inside, outside = [], []
        for t in tags:
            com = np.array(gmsh.model.occ.getCenterOfMass(dim, t)).reshape(1, 3)
            (inside if self.domain.contains(com, tol=1e-6)[0] else outside).append(t)
        if outside:
            gmsh.model.occ.remove([(dim, t) for t in outside], recursive=True)
            gmsh.model.occ.synchronize()
        if not inside:
            raise ValueError(f"{name}: lies entirely outside the domain")
        return inside

    def _volume_containing(self, point, candidates):
        for t in candidates:
            if gmsh.model.isInside(3, t, list(point)):
                return t
        return candidates[0]

    def _make_fracture_surface(self, f: FractureSpec) -> int:
        pts = [gmsh.model.occ.addPoint(*p, f.lc) for p in f.corners]
        lines = [gmsh.model.occ.addLine(pts[i], pts[(i + 1) % 4]) for i in range(4)]
        loop = gmsh.model.occ.addCurveLoop(lines)
        surf = gmsh.model.occ.addSurfaceFilling(loop)
        gmsh.model.occ.synchronize()
        return surf

    def _make_fracture_volume(self, f: FractureSpec) -> int:
        """Extrude the patch by `thickness` along its own normal.

        The old code offset the surface by a hand-tuned (dx, dy, dz) triple such
        as (0.2, 0.4, 0.2), which is neither normal to the plane nor of length
        `thickness`. Here the aperture is exactly `thickness`, measured normal
        to the fracture, and centred on the picked plane.
        """
        n = f.normal
        half = 0.5 * f.thickness * n
        base = f.corners - half
        pts = [gmsh.model.occ.addPoint(*p, f.lc) for p in base]
        lines = [gmsh.model.occ.addLine(pts[i], pts[(i + 1) % 4]) for i in range(4)]
        loop = gmsh.model.occ.addCurveLoop(lines)
        surf = gmsh.model.occ.addSurfaceFilling(loop)
        gmsh.model.occ.synchronize()
        ext = gmsh.model.occ.extrude([(2, surf)], *(f.thickness * n))
        vol = next(t for (dim, t) in ext if dim == 3)
        gmsh.model.occ.synchronize()
        return vol

    def _tag_boundaries(self, hosts: list[int]):
        d = self.domain
        tol = self.bbox_tol
        groups = {k: [] for k in self.BOUNDARY_NAMES}
        other = []
        seen = set()
        for dim, s in gmsh.model.getBoundary([(3, h) for h in hosts], oriented=False,
                                             combined=True):
            if dim != 2 or s in seen:
                continue
            seen.add(s)
            x0, y0, z0, x1, y1, z1 = gmsh.model.occ.getBoundingBox(2, s)
            if abs(x0 - d.xmin) < tol and abs(x1 - d.xmin) < tol:
                groups["left"].append(s)
            elif abs(x0 - d.xmax) < tol and abs(x1 - d.xmax) < tol:
                groups["right"].append(s)
            elif abs(y0 - d.ymin) < tol and abs(y1 - d.ymin) < tol:
                groups["back"].append(s)
            elif abs(y0 - d.ymax) < tol and abs(y1 - d.ymax) < tol:
                groups["front"].append(s)
            elif abs(z0 - d.zmin) < tol and abs(z1 - d.zmin) < tol:
                groups["down"].append(s)
            elif abs(z0 - d.zmax) < tol and abs(z1 - d.zmax) < tol:
                groups["up"].append(s)
            else:
                other.append(s)
        for i, (name, tags) in enumerate(groups.items()):
            if tags:
                gmsh.model.addPhysicalGroup(2, tags, self.BOUNDARY_TAG_BASE + i, name=name)
        if other:
            gmsh.model.addPhysicalGroup(2, other, self.BOUNDARY_TAG_BASE + 99,
                                        name="tunnel_surfaces")

    def _add_observation_points(self, hosts: list[int]):
        if not self.observation_points:
            return
        tags = {}
        for name, (x, y, z) in self.observation_points.items():
            tags[name] = gmsh.model.occ.addPoint(x, y, z, self.obs_lc)
        gmsh.model.occ.synchronize()
        for name, tag in tags.items():
            xyz = self.observation_points[name]
            gmsh.model.mesh.embed(0, [tag], 3, self._volume_containing(xyz, hosts))
        for i, (name, tag) in enumerate(tags.items()):
            gmsh.model.addPhysicalGroup(0, [tag], self.OBS_TAG_BASE + i, name=name)

    def _apply_refinement(self):
        fields = []
        for f in self.fractures:
            if f.refine is None:
                continue
            surfs = getattr(self, "_surface_tags", {}).get(f.name)
            if not surfs:
                continue
            dist = gmsh.model.mesh.field.add("Distance")
            gmsh.model.mesh.field.setNumbers(dist, "SurfacesList", surfs)
            gmsh.model.mesh.field.setNumber(dist, "Sampling", f.refine.sampling)
            th = gmsh.model.mesh.field.add("Threshold")
            gmsh.model.mesh.field.setNumber(th, "InField", dist)
            gmsh.model.mesh.field.setNumber(th, "SizeMin", f.refine.size_min)
            gmsh.model.mesh.field.setNumber(th, "SizeMax", f.refine.size_max)
            gmsh.model.mesh.field.setNumber(th, "DistMin", f.refine.dist_min)
            gmsh.model.mesh.field.setNumber(th, "DistMax", f.refine.dist_max)
            fields.append(th)
        if not fields:
            return
        # The old code called setAsBackgroundMesh once per field, so only the
        # last one survived. Min() combines them all.
        combined = gmsh.model.mesh.field.add("Min")
        gmsh.model.mesh.field.setNumbers(combined, "FieldsList", fields)
        gmsh.model.mesh.field.setAsBackgroundMesh(combined)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
