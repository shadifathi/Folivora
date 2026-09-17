# ogsfrac 0.2.0 #Shadi-Fathi

*If you have more than one copy of this folder, `ogsfrac --version` tells you
which is which. Keep the highest. Don't merge them — an older `builder.py` or
`presets.py` copied over a newer one reinstates fixed bugs silently.*

One pipeline for H / TH / HM / THM simulations of fractured rock in OpenGeoSys:
**borehole data → fracture geometry → mesh → .prj → run**, driven by a single
YAML case file.

This consolidates eleven notebooks. Nothing here is new science — it is your own
code, deduplicated, parameterised, and tested.

## Why

`DesignModel.ipynb`, `DesignModel_-_Copy.ipynb`, `DesignModel_-_Copy__2_.ipynb`
and `HydroModel.ipynb` each carried a copy of the same framework
(`OGSProjectBase`, `LiquidFlowProject`, `FaultedCubeMesh`, `MeshConverter`, …).
`DesignModel_-_Copy` and `DesignModel_-_Copy__2_` are byte-identical;
`HydroModel.LiquidFlowProject` is byte-identical to `DesignModel`'s. There were
five copies of `OGSProjectBase`. Fixing a bug meant fixing it in five places,
and in practice it got fixed in one.

Everything variable was a literal in the middle of a function:

```python
# Grimsel_GM.ipynb, cell 1 — edit, run, copy the printed answer into cell 2
### B8509 ###
# A = [4.02,9.56,0.15]
### B8508 ###
A = [27.8,21.76,0.05]
B = [24.6,62.1,-28.8]
d = 13.8
```

Now:

```yaml
fractures:
  - name: FZ3
    points: [[-18.7, 20.1, -20.7], [-1.09, 36.18, -18.12], [16.03, 44.1, -15.9]]
    half_size: 100
    representation: surface
```

The alternatives coexist in one file instead of overwriting each other in a
comment block. Nothing outside a case file contains a coordinate.

## Start here

```bash
cd ogsfrac
git init && git add -A && git commit -m "ogsfrac 0.2.0"
```

Do this first. Everything below is easier once there is one authoritative copy
with a history, and "which folder is newest" stops being a question you can ask.

## Install

```bash
pip install -e .            # numpy, pandas, gmsh, meshio, lxml, pyyaml, openpyxl
pip install -e ".[ui]"      # + the case editor (streamlit, plotly)
```

gmsh needs system GL/X libraries. On Debian/Ubuntu:

```bash
sudo apt-get install libglu1-mesa libxft2 libxinerama1 libxcursor1 libxrender1 libfontconfig1
```

## Use

```bash
ogsfrac gui      cases/grimsel_lf.yml   # open the editor in a browser
ogsfrac geometry cases/grimsel_lf.yml   # planes, dips, borehole intersections
ogsfrac mesh     cases/grimsel_lf.yml   # .msh + bulk .vtu + subdomain .vtu
ogsfrac prj      cases/grimsel_lf.yml   # .prj
ogsfrac run      cases/grimsel_lf.yml   # calls OGS
ogsfrac all      cases/grimsel_lf.yml
```

Every stage is importable, so a notebook stays a perfectly good front end:

```python
from ogsfrac import Plane, Borehole, FracturedDomainMesh, build_prj

fz3 = Plane.from_3points([-18.7, 20.1, -20.7], [-1.09, 36.18, -18.12],
                         [16.03, 44.1, -15.9], name="FZ3")
fz3.dip_azimuth          # (6.75, 251.61)
fz3.corners(half_size=100)

bh = Borehole("B8508", [27.8, 21.76, 0.05], [24.6, 62.1, -28.8])
bh.point_at(13.8)        # replaces point_on_line + copy-paste
fz3.intersect_borehole(bh)
```


## The editor

```bash
ogsfrac gui                       # start from a blank case
ogsfrac gui cases/grimsel_lf.yml  # open an existing one
```

Seven tabs: **Domain**, **Fractures**, **Physics**, **Materials**,
**Parameters & BCs**, **Preview**, **Run**.

It edits the case YAML and nothing else. There is no project format, no
database, no hidden state — press Save and you get a file `ogsfrac all` can
consume, and you can hand-edit that file afterwards and reopen it. The editor
is a convenience, not a dependency.

**It calls the real code.** The dip/azimuth readout comes from `Plane`, the
validation panel constructs the actual `FracturedDomainMesh`, and the .prj
preview is `build_prj` output. Nothing is reimplemented for the UI, so the
checks you see are the checks that run — which was the whole point of
collapsing the notebooks in the first place. `ogsfrac/ui/state.py` imports no
streamlit and is unit-tested.

What it catches before you wait on a mesh:

- fractures that intersect while set to `conform: embed` (the `Untitled-1` bug),
  quoting the real error
- duplicate `material_id`, or a mesh material with no medium
- a BC pointing at a mesh that isn't in `<meshes>`, or a parameter that doesn't exist
- a process variable with no BCs at all
- fracture patches that leave the domain and will be trimmed
- gravity along y when z is the vertical axis
- a rough element count, so `size_min: 1` over a 200 m patch is visible as
  ~10⁷ elements *before* you start meshing

Switching the coupling in **Physics** rewrites process variables, parameters
and media to match, keeping the values you already set — LIQUID_FLOW → THM adds
`temperature` and `displacement`, the `E`/`nu`/`u0` parameters, and
`biot_coefficient`/`thermal_expansion` on every medium. Adding a fracture
creates its medium automatically.

The property defaults per process come from your own builders (`PROCESS_INFO`
in `prj/presets.py`) — HT's 4180 / 0.6 / 2650 / 800 / 2.5, TRM's
`biot_coefficient` and `thermal_expansion`. Correct them there, once.

## Layout

| Module | Replaces |
|---|---|
| `geometry/boreholes.py` | `point_on_line`, the decimal-comma cleanup, manual `A`/`B` editing |
| `geometry/planes.py` | `plane_from_3pts`, `plane_rectangle_from_3points`, `are_coplanar`, `vector_to_dip_azimuth`, `line_plane_intersection` |
| `meshing/builder.py` | `FaultedCubeMesh`, `create_fracture_volume`, `build_tunnel_volume`, the loose gmsh cells in `Untitled-1` |
| `meshing/convert.py` | `MeshConverter`, `VtuMaterialMapper`, `MeshInspector`, `save_mesh_ogs_compatible` |
| `prj/presets.py` | the hardcoded defaults inside every `build()` |
| `prj/build.py` | `LiquidFlowProject`, `HydroThermalProject`, `HydroMechProject`, `ThermoRichardsMechanicsProject`, `ThermoMechanicsProject` |
| `prj/xmlutil.py` | `_indent`, `update_parameter`, `change_output_filename` |
| `run.py` | `OGSSimulation` |
| `ui/state.py` | — (case validation, UI-free and testable) |
| `ui/app.py` | — (the editor) |

## Fractures: both representations

Set per fracture, in the same model:

```yaml
- name: FZ1
  representation: surface     # 2D elements in a 3D mesh (mixed-dimensional)
  conform: fragment           # imprint intersections with other fractures
- name: FZ2
  representation: volume      # thin 3D layer, extruded along the normal
  thickness: 0.1
```

`conform: embed` is faster but only legal when the fracture crosses nothing.
`conform: fragment` is required as soon as fractures intersect. If you pick
wrong, you get a clear error before meshing starts rather than tetgen's
`PLC Error: A segment and a facet intersect`.

## The .prj stays XML

You hand-edit XML, so the YAML *is* the prj tree, not an abstraction over it:

```yaml
overrides:
  time_loop:
    processes:
      process:
        time_stepping:
          maximum_dt: 20.0
```

`"@attr"` becomes an attribute, a list becomes repeated sibling elements, and
`overrides` is deep-merged last, so anything the presets don't cover you write
directly. Presets in `prj/presets.py` are plain dicts — print one, diff it,
edit it.

## Bugs this found in the notebook code

1. **Bowtie fracture corners.** `plane_rectangle_from_3points` looped
   `for du in [-h, h]: for dv in [-h, h]`, emitting corners in the order
   (−−, −+, +−, ++). Joined in sequence that is a self-intersecting quad.
   `addSurfaceFilling` tolerated it; `addPlaneSurface` would not have.
2. **`embed` cannot handle intersecting fractures.** `Untitled-1` embeds FZ1,
   FZ2 and FZ3 into the host. FZ1 and FZ3 each cross FZ2, so tetgen sees a
   broken PLC. This is now checked upfront.
3. **Physical tag collision.** `addPhysicalGroup(dim, tags, tag=0)` — gmsh only
   honours *positive* tags, so `material_id: 0` (the rock) was silently
   auto-assigned, colliding with another group. Tags are now `material_id + 1`,
   with boundaries above 1000; the offset is undone during conversion.
4. **Surface fractures deleted on conversion.** Keeping only 3D cells when
   writing the `.vtu` drops every `representation: surface` fracture. The bulk
   mesh now keeps fracture triangles (with their MaterialIDs) and excludes
   boundary triangles.
5. **`1e-13` is a string in YAML 1.1.** Not caught, `permeability: 1e-13`
   becomes a *parameter reference* named `"1e-13"`. Numeric-looking strings are
   coerced.
6. **Only the last refinement field applied.** `setAsBackgroundMesh` was called
   once per fault, and each call replaces the previous. Fields are now combined
   with `Min`.
7. **Fracture aperture was not the aperture.** `FaultedCubeMesh` extruded by
   `(0.2, 0.4, 0.2)` — a direction that is neither normal to the fault nor of
   length `fault_thickness` (which was passed in, then ignored). Extrusion is
   now `thickness × unit normal`, centred on the picked plane.
8. **A failed OGS run looked like a successful one.** `OGSSimulation.run`
   printed stderr and returned; in a loop that is invisible. It now raises.
9. **`HydroMechProject` emits no `<constitutive_relation>`.** It puts
   `youngs_modulus` and `poissons_ratio` in the *medium* properties instead.
   OGS's HYDRO_MECHANICS needs the constitutive relation; the preset has it,
   with `E`/`nu` as parameters.
10. **Gravity points sideways.** `LiquidFlowProject` and `HydroMechProject` both
    set `specific_body_force` to `0 -9.81 0`. The Grimsel domain has z as the
    vertical axis (`zmin: -100, zmax: 0`), so that is gravity along y. The
    presets use `0 0 -9.81` and the editor warns on the y-form. Worth checking
    against any results you have already published.

## Verification

`pytest tests` — 47 tests. If you get 26, you are in an old copy of the folder.
 The geometry tests pin the fracture normals to the
values in your `Grimsel_GM` comments:

```
FZ1  [ 0.03916387  0.02688234 -0.99887113]
FZ2  [-0.22684143  0.66752969 -0.70918762]
FZ3  [ 0.11160535  0.03710966 -0.99305947]
```

and `Borehole("B8508").point_at(13.8)` against the `C` that cell 1 printed.
So a refactor cannot quietly move the geometry the published model was built on.

The editor is tested too, through Streamlit's `AppTest`: `tests/test_ui_app.py`
runs `app.py` headlessly and clicks things. This is not ceremony — it caught a
real aliasing bug where `touch()` rebound `st.session_state.case` while the
tabs kept writing to the previous object, silently dropping edits and spinning
the Physics tab into an infinite rerun loop.

## Status

Working and tested: geometry, meshing, conversion, prj generation, the editor.
`run` is untested (no OGS binary in the environment this was built in) but is a
thin `subprocess` wrapper.

Not yet ported:
- **Post-processing** (`Grimsel_PS`, `HydroModel.OGSPostProcessorVTU`,
  `aftermeeting_simplesimulations`) — pyvista-based, deliberately deferred.
- **DFN generation** (`dfn.ipynb`) — the stochastic generators. These would
  become `Plane` factories feeding the same `FractureSpec` list, so the mesher
  needs no changes.
- **Property interpolation** (`MeshPropertyInterpolator`,
  `PermeabilityInterpolator` in `idea2d`) — needed for `MeshNode` parameters.
- Deviated borehole traces (`Borehole.from_survey` raises `NotImplementedError`).
