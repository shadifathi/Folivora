"""3D preview. Pure: builds a figure, renders nothing.

Uses the same `Plane.corners()` the mesher uses, so what you see is the patch
that will be meshed — not an approximation of it.
"""
from __future__ import annotations

import numpy as np

from ..config import boreholes_from_case, planes_from_case

_COLORS = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2", "#EECA3B", "#B279A2"]


def case_figure(case: dict, show_boreholes=True):
    import plotly.graph_objects as go

    fig = go.Figure()
    d = case["domain"]
    fig.add_trace(_box_wireframe(go, d))

    planes = {p.name: p for p in planes_from_case(case)}
    for i, spec in enumerate(case.get("fractures", [])):
        p = planes.get(spec["name"])
        if p is None:
            continue
        c = p.corners(half_size=spec.get("half_size", 50.0), center=spec.get("center"))
        color = _COLORS[i % len(_COLORS)]
        dip, azi = p.dip_azimuth
        fig.add_trace(
            go.Mesh3d(
                x=c[:, 0], y=c[:, 1], z=c[:, 2],
                i=[0, 0], j=[1, 2], k=[2, 3],
                color=color,
                opacity=0.45 if spec.get("representation") == "surface" else 0.75,
                name=f"{spec['name']} ({spec.get('representation', 'surface')})",
                showlegend=True,
                hovertext=f"{spec['name']}<br>dip {dip:.1f}° / azimuth {azi:.1f}°",
            )
        )
        # outline, so a patch leaving the box is obvious
        loop = np.vstack([c, c[0]])
        fig.add_trace(
            go.Scatter3d(x=loop[:, 0], y=loop[:, 1], z=loop[:, 2], mode="lines",
                         line=dict(color=color, width=4), showlegend=False, hoverinfo="skip")
        )

    if show_boreholes:
        try:
            holes = boreholes_from_case(case)
        except Exception:
            holes = []
        for bh in holes:
            seg = np.vstack([bh.A, bh.B])
            fig.add_trace(
                go.Scatter3d(x=seg[:, 0], y=seg[:, 1], z=seg[:, 2], mode="lines+text",
                             line=dict(color="#333", width=3), text=[bh.name, ""],
                             name=bh.name, showlegend=False)
            )

    obs = case.get("observation_points") or {}
    if isinstance(obs, dict) and obs:
        pts = np.array(list(obs.values()), dtype=float)
        fig.add_trace(
            go.Scatter3d(x=pts[:, 0], y=pts[:, 1], z=pts[:, 2], mode="markers",
                         marker=dict(size=3, color="#000"), text=list(obs),
                         name="observation points")
        )

    fig.update_layout(
        scene=dict(
            xaxis_title="x [m]", yaxis_title="y [m]", zaxis_title="z [m]",
            aspectmode="data",
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        height=560,
        legend=dict(orientation="h", yanchor="bottom", y=1.0),
    )
    return fig


def _box_wireframe(go, d):
    x0, x1 = d["xmin"], d["xmax"]
    y0, y1 = d["ymin"], d["ymax"]
    z0, z1 = d["zmin"], d["zmax"]
    corners = np.array([
        [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
    ], float)
    edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
             (0, 4), (1, 5), (2, 6), (3, 7)]
    xs, ys, zs = [], [], []
    for a, b in edges:
        xs += [corners[a, 0], corners[b, 0], None]
        ys += [corners[a, 1], corners[b, 1], None]
        zs += [corners[a, 2], corners[b, 2], None]
    return go.Scatter3d(x=xs, y=ys, z=zs, mode="lines",
                        line=dict(color="#999", width=2),
                        name=d.get("name", "Rock"), hoverinfo="skip")
