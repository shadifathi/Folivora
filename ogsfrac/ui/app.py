"""ogsfrac case editor.

Launch with `ogsfrac gui [case.yml]`.

This is a rendering layer only: every check it shows and every artefact it
writes comes from the same code the CLI runs. Editing here is editing the case
YAML — there is no separate project format, and you can go back to the command
line at any point.
"""
from __future__ import annotations

import io
import sys
import traceback
from pathlib import Path

import streamlit as st

from ogsfrac.prj.presets import BC_TYPES, PROCESS_INFO
from ogsfrac.ui import state as S

st.set_page_config(page_title="ogsfrac", layout="wide", page_icon="⛏")

PROC_TYPES = list(PROCESS_INFO)


# ---------------------------------------------------------------------------
# session
# ---------------------------------------------------------------------------

def _init():
    if "case" in st.session_state:
        return
    arg = next((a for a in sys.argv[1:] if a.endswith((".yml", ".yaml"))), None)
    if arg and Path(arg).exists():
        st.session_state.case = S.yaml_to_case(Path(arg).read_text())
        st.session_state.path = str(arg)
    else:
        st.session_state.case = S.sync_all(S.default_case())
        st.session_state.path = "cases/new_case.yml"
    st.session_state.log = ""


_init()
case = st.session_state.case


def touch():
    """Re-sync the case and keep the module-level alias pointing at it.

    `sync_all` is pure (it returns a new dict), so rebinding session_state
    without rebinding `case` leaves every later tab writing to a stale object.
    That is not hypothetical: it silently dropped edits and, on the Physics
    tab, span an infinite rerun loop. The tests in tests/test_ui_app.py exist
    because of this bug.
    """
    global case
    st.session_state.case = S.sync_all(st.session_state.case)
    case = st.session_state.case


# ---------------------------------------------------------------------------
# sidebar: file + validation, always visible
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("ogsfrac")
    st.caption("case editor")

    st.session_state.path = st.text_input("Case file", st.session_state.path)
    c1, c2 = st.columns(2)
    if c1.button("Load", width="stretch"):
        p = Path(st.session_state.path)
        if p.exists():
            st.session_state.case = S.yaml_to_case(p.read_text())
            st.rerun()
        else:
            st.error("not found")
    if c2.button("Save", type="primary", width="stretch"):
        S.save_case(case, st.session_state.path)
        st.success(f"saved {st.session_state.path}")

    st.download_button("Download YAML", S.case_to_yaml(case),
                       file_name=f"{case['name']}.yml", width="stretch")

    st.divider()
    st.subheader("Validation")
    for level, msg in S.validation_report(case):
        {"error": st.error, "warning": st.warning, "ok": st.success}[level](msg)

    st.divider()
    st.caption(f"~{S.estimate_elements(case):.1e} elements (rough)")


# ---------------------------------------------------------------------------
# tabs
# ---------------------------------------------------------------------------

tabs = st.tabs(["Domain", "Fractures", "Physics", "Materials",
                "Parameters & BCs", "Preview", "Run"])

# --- Domain ---------------------------------------------------------------
with tabs[0]:
    st.subheader("Model domain")
    case["name"] = st.text_input("Case name", case["name"])
    d = case["domain"]
    cols = st.columns(3)
    for i, axis in enumerate("xyz"):
        with cols[i]:
            d[f"{axis}min"] = st.number_input(f"{axis}min [m]", value=float(d[f"{axis}min"]))
            d[f"{axis}max"] = st.number_input(f"{axis}max [m]", value=float(d[f"{axis}max"]))
    c1, c2, c3 = st.columns(3)
    d["lc"] = c1.number_input("Far-field element size lc [m]", value=float(d["lc"]), min_value=0.01)
    d["name"] = c2.text_input("Matrix name", d.get("name", "Rock"))
    d["material_id"] = c3.number_input("Matrix material_id", value=int(d.get("material_id", 0)),
                                       step=1)

    st.subheader("Mesh options")
    mo = case.setdefault("mesh_options", {})
    c1, c2, c3 = st.columns(3)
    mo["algorithm_3d"] = c1.selectbox("3D algorithm", [1, 4, 7, 9, 10],
                                      index=[1, 4, 7, 9, 10].index(mo.get("algorithm_3d", 1)),
                                      help="1 = Delaunay, 10 = HXT (fast, parallel)")
    mo["optimize"] = c2.number_input("Optimize passes", value=int(mo.get("optimize", 2)), step=1)
    mo["msh_version"] = c3.selectbox("MSH version", [2.2, 4.1],
                                     index=0 if mo.get("msh_version", 2.2) == 2.2 else 1,
                                     help="meshio reads 2.2 most reliably")
    touch()

# --- Fractures ------------------------------------------------------------
with tabs[1]:
    left, right = st.columns([3, 2])

    with left:
        st.subheader("Fractures")
        if st.button("➕ Add fracture"):
            case["fractures"].append(S.new_fracture(len(case["fractures"]) + 1))
            touch()
            st.rerun()

        for i, f in enumerate(list(case["fractures"])):
            with st.expander(f"**{f['name']}** — {f.get('representation', 'surface')}",
                             expanded=len(case["fractures"]) <= 2):
                c1, c2, c3 = st.columns([2, 1, 1])
                f["name"] = c1.text_input("Name", f["name"], key=f"n{i}")
                f["material_id"] = c2.number_input("material_id", value=int(f.get("material_id", i + 1)),
                                                   step=1, key=f"m{i}")
                if c3.button("🗑 Remove", key=f"d{i}"):
                    case["fractures"].pop(i)
                    touch()
                    st.rerun()

                mode = st.radio(
                    "Defined by", ["3 points", "fit to points", "dip + azimuth"],
                    index=0 if "points" in f else (1 if "fit_points" in f else 2),
                    horizontal=True, key=f"mode{i}",
                    help="'fit to points' uses least squares over all borehole "
                         "intersections and reports the misfit, instead of forcing "
                         "a plane through three hand-picked ones.",
                )

                if mode == "3 points":
                    f.pop("fit_points", None); f.pop("dip", None); f.pop("azimuth", None)
                    pts = f.setdefault("points", S.new_fracture(i + 1)["points"])
                    for r in range(3):
                        cc = st.columns(3)
                        for a in range(3):
                            pts[r][a] = cc[a].number_input(
                                f"P{r + 1}{'xyz'[a]}", value=float(pts[r][a]),
                                key=f"p{i}_{r}_{a}", label_visibility="visible")
                elif mode == "fit to points":
                    f.pop("points", None); f.pop("dip", None); f.pop("azimuth", None)
                    txt = st.text_area(
                        "Points, one 'x y z' per line", key=f"fp{i}",
                        value="\n".join(" ".join(str(v) for v in p)
                                        for p in f.get("fit_points", [])),
                        help="Paste borehole–fracture intersections here.")
                    try:
                        f["fit_points"] = [[float(v) for v in ln.split()]
                                           for ln in txt.strip().splitlines() if ln.strip()]
                    except ValueError:
                        st.error("could not parse — expected three numbers per line")
                else:
                    f.pop("points", None); f.pop("fit_points", None)
                    c1, c2 = st.columns(2)
                    f["dip"] = c1.number_input("Dip [°]", value=float(f.get("dip", 30.0)),
                                               key=f"dip{i}")
                    f["azimuth"] = c2.number_input("Dip azimuth [°]",
                                                   value=float(f.get("azimuth", 90.0)),
                                                   key=f"az{i}")
                    pt = f.setdefault("point", [0.0, 0.0, -10.0])
                    cc = st.columns(3)
                    for a in range(3):
                        pt[a] = cc[a].number_input(f"through {'xyz'[a]}", value=float(pt[a]),
                                                   key=f"pt{i}_{a}")

                st.markdown("**Representation**")
                c1, c2 = st.columns(2)
                f["representation"] = c1.selectbox(
                    "Type", ["surface", "volume"],
                    index=0 if f.get("representation", "surface") == "surface" else 1,
                    key=f"rep{i}",
                    help="surface = 2D elements in the 3D mesh (mixed-dimensional). "
                         "volume = thin 3D layer extruded along the normal.")
                if f["representation"] == "surface":
                    f.pop("thickness", None)
                    f["conform"] = c2.selectbox(
                        "Conform", ["fragment", "embed"],
                        index=0 if f.get("conform", "fragment") == "fragment" else 1,
                        key=f"cf{i}",
                        help="embed is faster but illegal if this fracture crosses "
                             "another one. fragment imprints the intersection.")
                else:
                    f.pop("conform", None)
                    f["thickness"] = c2.number_input(
                        "Aperture [m]", value=float(f.get("thickness", 0.01)),
                        format="%.4f", min_value=1e-6, key=f"th{i}")

                c1, c2 = st.columns(2)
                f["half_size"] = c1.number_input("Half size [m]",
                                                 value=float(f.get("half_size", 50.0)),
                                                 key=f"hs{i}")
                f["lc"] = c2.number_input("Element size on fracture [m]",
                                          value=float(f.get("lc", 6.0)), key=f"lc{i}")

                use_ref = st.checkbox("Refine around fracture", value="refine" in f,
                                      key=f"ur{i}")
                if use_ref:
                    r = f.setdefault("refine", {"size_min": 4.0, "size_max": 20.0,
                                                "dist_min": 4.0, "dist_max": 25.0})
                    cc = st.columns(4)
                    for j, k in enumerate(["size_min", "size_max", "dist_min", "dist_max"]):
                        r[k] = cc[j].number_input(k, value=float(r[k]), key=f"r{i}{k}")
                else:
                    f.pop("refine", None)
        touch()

    with right:
        st.subheader("Preview")
        try:
            from ogsfrac.ui.plot import case_figure
            st.plotly_chart(case_figure(case), width="stretch")
        except ImportError:
            st.info("Install plotly for the 3D preview:  pip install 'ogsfrac[ui]'")
        except Exception as exc:
            st.warning(f"preview unavailable: {exc}")

        rows = S.fracture_table(case)
        if rows:
            st.dataframe(rows, width="stretch", hide_index=True)
            st.caption("dip / azimuth / normal are computed by the same code the "
                       "mesher uses.")

# --- Physics --------------------------------------------------------------
with tabs[2]:
    st.subheader("Coupling")
    labels = [PROCESS_INFO[p]["label"] for p in PROC_TYPES]
    cur = PROC_TYPES.index(case["process"]["type"])
    pick = st.radio("Process", range(len(PROC_TYPES)), index=cur,
                    format_func=lambda i: labels[i], horizontal=True)
    if PROC_TYPES[pick] != case["process"]["type"]:
        case["process"]["type"] = PROC_TYPES[pick]
        touch()
        st.rerun()

    info = PROCESS_INFO[case["process"]["type"]]
    st.caption(f"Solves for: {', '.join(info['variables'])} · "
               f"defaults taken from `{info['source']}`")

    st.subheader("Time")
    c1, c2, c3 = st.columns(3)
    case["t_initial"] = c1.number_input("t_initial [s]", value=float(case.get("t_initial", 0.0)))
    case["t_end"] = c2.number_input("t_end [s]", value=float(case.get("t_end", 400.0)))
    case["output_prefix"] = c3.text_input("Output prefix", case.get("output_prefix", "result"))

    st.subheader("Gravity")
    ov = case.setdefault("overrides", {})
    body = (ov.get("processes", {}).get("process", {}).get("specific_body_force")
            or [0.0, 0.0, -9.81])
    cc = st.columns(3)
    body = [cc[i].number_input(f"g{'xyz'[i]} [m/s²]", value=float(body[i]), key=f"g{i}")
            for i in range(3)]
    ov.setdefault("processes", {}).setdefault("process", {})["specific_body_force"] = body
    st.caption("Your notebooks used `0 -9.81 0`. With z as the vertical axis that "
               "points gravity sideways.")

    st.subheader("Output variables")
    case["output_variables"] = st.multiselect(
        "Written to VTK",
        sorted(set(list(info["variables"]) + ["v", "sigma", "epsilon", "saturation"])),
        default=case.get("output_variables", list(info["variables"])))
    touch()

# --- Materials ------------------------------------------------------------
with tabs[3]:
    st.subheader("Media")
    st.caption("One medium per material_id in the mesh. Matrix and fractures are "
               "kept in sync automatically. A **number** becomes a Constant; a "
               "**name** becomes a Parameter reference (e.g. a MeshNode field).")
    info = PROCESS_INFO[case["process"]["type"]]
    units = {p.name: p.unit for p in info["medium"]}

    for m in case["materials"]:
        with st.expander(f"**id {m['id']}** — {m.get('name', '')}", expanded=True):
            for key in [k for k in m if k not in ("id", "name", "fluid", "solid")]:
                unit = units.get(key, "")
                m[key] = st.text_input(f"{key} [{unit}]" if unit else key,
                                       value=str(m[key]), key=f"mat{m['id']}{key}")
            with st.popover("Phase properties"):
                st.caption("Leave empty to use the process defaults shown.")
                for phase, defs in (("fluid", info["fluid"]), ("solid", info["solid"])):
                    if not defs:
                        continue
                    st.markdown(f"**{phase}**")
                    d = m.setdefault(phase, {})
                    for pd in defs:
                        d[pd.name] = st.text_input(
                            f"{pd.name} [{pd.unit}]", value=str(d.get(pd.name, pd.default)),
                            key=f"{phase}{m['id']}{pd.name}")
    touch()

# --- Parameters & BCs -----------------------------------------------------
with tabs[4]:
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Parameters")
        params = case.setdefault("parameters", {})
        for name in list(params):
            cc = st.columns([2, 3, 1])
            new = cc[0].text_input("name", name, key=f"pn{name}", label_visibility="collapsed")
            val = cc[1].text_input("value", str(params[name]), key=f"pv{name}",
                                   label_visibility="collapsed")
            if cc[2].button("🗑", key=f"pd{name}"):
                params.pop(name)
                st.rerun()
            if new != name:
                params[new] = params.pop(name)
            else:
                params[name] = val
        if st.button("➕ Add parameter"):
            params[f"param_{len(params) + 1}"] = 0.0
            st.rerun()

    with c2:
        st.subheader("Boundary conditions")
        targets = ([f["name"] for f in case["fractures"]]
                   + list(S.FracturedDomainMesh.BOUNDARY_NAMES) + ["tunnel_surfaces"])
        for var, spec in (case.get("process_variables") or {}).items():
            st.markdown(f"**{var}**  ({spec['components']} component"
                        f"{'s' if spec['components'] > 1 else ''})")
            spec["initial_condition"] = st.selectbox(
                "initial condition", list(case["parameters"]),
                index=(list(case["parameters"]).index(spec["initial_condition"])
                       if spec["initial_condition"] in case["parameters"] else 0),
                key=f"ic{var}")
            bcs = spec.setdefault("boundary_conditions", [])
            for j, bc in enumerate(list(bcs)):
                cc = st.columns([2, 2, 2, 1])
                bc["mesh"] = cc[0].selectbox(
                    "mesh", targets,
                    index=targets.index(bc["mesh"]) if bc.get("mesh") in targets else 0,
                    key=f"bm{var}{j}", label_visibility="collapsed")
                bc["type"] = cc[1].selectbox(
                    "type", BC_TYPES,
                    index=BC_TYPES.index(bc["type"]) if bc.get("type") in BC_TYPES else 0,
                    key=f"bt{var}{j}", label_visibility="collapsed")
                plist = list(case["parameters"])
                bc["parameter"] = cc[2].selectbox(
                    "parameter", plist,
                    index=plist.index(bc["parameter"]) if bc.get("parameter") in plist else 0,
                    key=f"bp{var}{j}", label_visibility="collapsed")
                if cc[3].button("🗑", key=f"bd{var}{j}"):
                    bcs.pop(j)
                    st.rerun()
            if st.button(f"➕ Add BC on {var}", key=f"ba{var}"):
                bcs.append({"mesh": targets[0], "type": "Dirichlet",
                            "parameter": list(case["parameters"])[0]})
                st.rerun()
            st.divider()
    touch()

# --- Preview --------------------------------------------------------------
with tabs[5]:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Case YAML")
        st.caption("This is the file. `ogsfrac all` consumes exactly this.")
        st.code(S.case_to_yaml(case), language="yaml")
    with c2:
        st.subheader("Generated .prj")
        try:
            from ogsfrac.prj.build import build_prj
            import tempfile
            with tempfile.TemporaryDirectory() as td:
                p = build_prj({**case, "_dir": Path(td)}, Path(td) / "preview.prj")
                st.code(p.read_text(encoding="ISO-8859-1"), language="xml")
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}")

# --- Run ------------------------------------------------------------------
with tabs[6]:
    st.subheader("Pipeline")
    st.caption("Same entry points as the CLI. Meshing blocks the UI — for long "
               "runs use `ogsfrac mesh` in a terminal.")
    case["ogs_executable"] = st.text_input("OGS executable",
                                           case.get("ogs_executable", "ogs"))
    cols = st.columns(4)
    stages = ["geometry", "mesh", "prj", "run"]
    for i, stage in enumerate(stages):
        if cols[i].button(stage, width="stretch",
                          type="primary" if stage == "mesh" else "secondary"):
            from ogsfrac import cli
            path = Path(st.session_state.path)
            S.save_case(case, path)
            buf = io.StringIO()
            old = sys.stdout
            sys.stdout = buf
            try:
                with st.spinner(f"running {stage}…"):
                    getattr(cli, f"cmd_{stage}")(S.yaml_to_case(path.read_text())
                                                 | {"_dir": path.parent})
            except Exception:
                buf.write("\n" + traceback.format_exc())
            finally:
                sys.stdout = old
            st.session_state.log = buf.getvalue()

    if st.session_state.log:
        st.code(st.session_state.log, language="text")
