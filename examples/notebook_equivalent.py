"""The Grimsel workflow as a script, for when a notebook is the right front end.

Equivalent to `ogsfrac all cases/grimsel_lf.yml`, but spelled out so you can see
where to hook in. Compare with Grimsel_GM.ipynb cells 1-2 + Untitled-1.ipynb.
"""
from ogsfrac import Borehole, FracturedDomainMesh, Plane, build_prj, msh_to_vtu
from ogsfrac.meshing.builder import Domain, FractureSpec, Refinement

# --- 1. geometry: no copy-paste between cells ------------------------------
FZ = {
    "FZ1": [[-7.0, 18.5, -9.4], [1.13, 28.95, -8.8], [16.9, 33.1, -8.07]],
    "FZ2": [[-15.92, 26.7, -18.1], [-0.54, 34.37, -15.8], [16.21, 41.73, -14.23]],
    "FZ3": [[-18.7, 20.1, -20.7], [-1.09, 36.18, -18.12], [16.03, 44.1, -15.9]],
}
planes = {n: Plane.from_3points(*p, name=n) for n, p in FZ.items()}
for n, p in planes.items():
    dip, azi = p.dip_azimuth
    print(f"{n}: dip={dip:.2f} azimuth={azi:.2f} normal={p.normal.round(6)}")

# where does a borehole meet a fracture?
bh = Borehole("B8508", [27.8, 21.76, 0.05], [24.6, 62.1, -28.8])
print("B8508 x FZ3 :", planes["FZ3"].intersect_borehole(bh).round(3))
print("B8508 @ 13.8:", bh.point_at(13.8).round(3))

# --- 2. mesh ---------------------------------------------------------------
domain = Domain(-150, 150, -120, 200, -100, 0, lc=20.0)
fractures = [
    FractureSpec("FZ1", planes["FZ1"].corners(100), representation="surface",
                 conform="fragment", lc=6.0, material_id=1,
                 refine=Refinement(size_min=4, size_max=20, dist_min=4, dist_max=25)),
    FractureSpec("FZ2", planes["FZ2"].corners(20), representation="volume",
                 thickness=0.1, lc=6.0, material_id=2),
    FractureSpec("FZ3", planes["FZ3"].corners(100), representation="surface",
                 conform="fragment", lc=6.0, material_id=3,
                 refine=Refinement(size_min=4, size_max=20, dist_min=4, dist_max=25)),
]
mesh = FracturedDomainMesh(domain, fractures)   # validates before meshing
msh = mesh.generate("grimsel.msh")
msh_to_vtu(msh, "grimsel.vtu")

# --- 3. prj ----------------------------------------------------------------
build_prj(
    {
        "process": {"type": "LIQUID_FLOW"},
        "meshes": ["grimsel.vtu", "FZ1.vtu", "FZ3.vtu"],
        "t_end": 400.0,
        "materials": [
            {"id": 0, "permeability": 1e-17, "porosity": 0.01, "storage": 1e-9},
            {"id": 1, "permeability": 1e-13, "porosity": 0.4, "storage": 1e-5},
            {"id": 2, "permeability": 1e-13, "porosity": 0.4, "storage": 1e-5},
            {"id": 3, "permeability": 1e-13, "porosity": 0.4, "storage": 1e-5},
        ],
        "parameters": {"p_inj": 8e5, "p0": 0.0},
        "process_variables": {
            "pressure": {
                "initial_condition": "p0",
                "boundary_conditions": [
                    {"mesh": "FZ1", "type": "Dirichlet", "parameter": "p_inj"},
                    {"mesh": "FZ3", "type": "Dirichlet", "parameter": "p0"},
                ],
            }
        },
    },
    "grimsel.prj",
)
