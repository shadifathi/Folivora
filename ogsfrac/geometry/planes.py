"""Fracture planes: construction, fitting, orientation, intersection.

Consolidates `plane_from_3pts`, `plane_rectangle_from_3points`, `are_coplanar`,
`vector_to_dip_azimuth`, `dip_azimuth_to_normal` and `line_plane_intersection`,
which were scattered across DesignModel.ipynb and Grimsel_GM.ipynb.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Plane:
    """Infinite plane, stored as unit normal + point. Cartesian form: n.x + d = 0."""

    normal: np.ndarray
    point: np.ndarray
    name: str = "plane"
    residual: float | None = None  # RMS fit misfit [m], None if exact

    def __post_init__(self):
        self.normal = np.asarray(self.normal, dtype=float)
        n = np.linalg.norm(self.normal)
        if n < 1e-12:
            raise ValueError(f"{self.name}: degenerate normal")
        self.normal = self.normal / n
        self.point = np.asarray(self.point, dtype=float)

    @property
    def d(self) -> float:
        return float(-np.dot(self.normal, self.point))

    @property
    def cartesian(self) -> tuple[float, float, float, float]:
        """(a, b, c, d) as returned by the old `plane_from_3pts`."""
        a, b, c = self.normal
        return float(a), float(b), float(c), self.d

    @property
    def dip_azimuth(self) -> tuple[float, float]:
        """(dip, dip-azimuth) in degrees, geological convention.

        Dip in [0, 90]; azimuth is the downdip direction, clockwise from north (+y).
        """
        n = self.normal if self.normal[2] >= 0 else -self.normal
        dip = np.degrees(np.arccos(np.clip(n[2], -1.0, 1.0)))
        if np.isclose(dip, 0.0, atol=1e-9):
            return 0.0, 0.0
        # downdip direction = steepest descent in the plane
        downdip = np.array([n[0], n[1], 0.0])
        downdip /= np.linalg.norm(downdip)
        azi = np.degrees(np.arctan2(downdip[0], downdip[1])) % 360.0
        return float(dip), float(azi)

    def signed_distance(self, pts) -> np.ndarray:
        pts = np.atleast_2d(np.asarray(pts, dtype=float))
        return pts @ self.normal + self.d

    # ---- construction -------------------------------------------------
    @classmethod
    def from_3points(cls, P1, P2, P3, name="plane") -> "Plane":
        P1, P2, P3 = (np.asarray(p, float) for p in (P1, P2, P3))
        n = np.cross(P2 - P1, P3 - P1)
        if np.linalg.norm(n) < 1e-8:
            raise ValueError(f"{name}: points are collinear; no unique plane")
        return cls(normal=n, point=(P1 + P2 + P3) / 3.0, name=name, residual=0.0)

    @classmethod
    def from_dip_azimuth(cls, dip_deg, azimuth_deg, point, name="plane") -> "Plane":
        dip = np.radians(dip_deg)
        azi = np.radians(azimuth_deg)
        n = np.array(
            [np.sin(dip) * np.sin(azi), np.sin(dip) * np.cos(azi), np.cos(dip)]
        )
        return cls(normal=n, point=point, name=name)

    @classmethod
    def fit(cls, points, name="plane") -> "Plane":
        """Least-squares fit through >=3 points via SVD.

        Preferred over `from_3points` when boreholes give more than three
        intersections: it uses all the data and reports the misfit, instead of
        forcing a plane through three hand-picked points and hiding the rest.
        """
        P = np.atleast_2d(np.asarray(points, dtype=float))
        if P.shape[0] < 3:
            raise ValueError(f"{name}: need >=3 points to fit a plane, got {P.shape[0]}")
        centroid = P.mean(axis=0)
        _, sv, vh = np.linalg.svd(P - centroid)
        normal = vh[2]  # direction of least variance
        plane = cls(normal=normal, point=centroid, name=name)
        plane.residual = float(np.sqrt(np.mean(plane.signed_distance(P) ** 2)))
        return plane

    # ---- geometry -----------------------------------------------------
    def basis(self) -> tuple[np.ndarray, np.ndarray]:
        """Orthonormal (u, v) spanning the plane. Stable for any normal."""
        seed = np.array([1.0, 0.0, 0.0])
        if abs(np.dot(seed, self.normal)) > 0.9:
            seed = np.array([0.0, 1.0, 0.0])
        u = np.cross(self.normal, seed)
        u /= np.linalg.norm(u)
        v = np.cross(self.normal, u)
        return u, v

    def corners(self, half_size=100.0, center=None) -> np.ndarray:
        """Four corners of a square patch, ordered so they form a valid loop.

        NOTE: the old `plane_rectangle_from_3points` built corners with a
        nested loop over [-h, h] x [-h, h], which emits them in the order
        (--, -+, +-, ++). That is a bowtie, not a quad: connecting them in
        sequence crosses over. It worked in gmsh only because
        `addSurfaceFilling` tolerated it. This returns proper CCW order.
        """
        u, v = self.basis()
        c = self.point if center is None else np.asarray(center, float)
        h = half_size
        return np.array(
            [c - h * u - h * v, c + h * u - h * v, c + h * u + h * v, c - h * u + h * v]
        )

    def intersect_segment(self, p0, p1, extend=False):
        """Intersection with segment p0->p1. Returns None if no hit.

        With `extend=False` the hit must lie within the segment (the old
        `intersect_line_plane` behaviour, i.e. inside the drilled length).
        """
        p0 = np.asarray(p0, float)
        p1 = np.asarray(p1, float)
        u = p1 - p0
        denom = float(np.dot(self.normal, u))
        if np.isclose(denom, 0.0):
            return None  # parallel
        t = -(float(np.dot(self.normal, p0)) + self.d) / denom
        if not extend and not (0.0 <= t <= 1.0):
            return None
        return p0 + t * u

    def intersect_borehole(self, bh, extend=False):
        return self.intersect_segment(bh.A, bh.B, extend=extend)


def are_coplanar(points, tol=1e-6) -> bool:
    """True if all points lie on a common plane within `tol` (RMS)."""
    P = np.atleast_2d(np.asarray(points, dtype=float))
    if P.shape[0] <= 3:
        return True
    return Plane.fit(P).residual <= tol


def intersect_boreholes(planes, boreholes, extend=False):
    """Every (plane, borehole) intersection as a tidy DataFrame.

    Replaces the loop in DesignModel.ipynb cell 1 that wrote
    `borehole_fault_intersections.xlsx`.
    """
    import pandas as pd

    rows = []
    for pl in planes:
        for bh in boreholes:
            pt = pl.intersect_borehole(bh, extend=extend)
            if pt is None:
                continue
            depth = float(np.dot(pt - bh.A, bh.unit))
            rows.append(
                {
                    "borehole": bh.name,
                    "fracture": pl.name,
                    "x": pt[0], "y": pt[1], "z": pt[2],
                    "depth_along_hole": depth,
                }
            )
    return pd.DataFrame(rows, columns=["borehole", "fracture", "x", "y", "z", "depth_along_hole"])
