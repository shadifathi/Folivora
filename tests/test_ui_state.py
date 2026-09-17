"""The editor's logic is testable because none of it imports streamlit."""
import pytest

from ogsfrac.ui import state as S


def _case():
    c = S.sync_all(S.default_case("t"))
    c["fractures"] = [S.new_fracture(1)]
    return S.sync_all(c)


def test_default_case_is_valid_apart_from_missing_bcs():
    report = S.validation_report(S.sync_all(S.default_case()))
    assert not [m for lvl, m in report if lvl == S.ERROR]


def test_adding_a_fracture_creates_its_medium():
    c = _case()
    assert {m["id"] for m in c["materials"]} == {0, 1}
    assert "permeability" in c["materials"][1]


def test_removing_a_fracture_drops_its_medium():
    c = _case()
    c["fractures"] = []
    c = S.sync_all(c)
    assert {m["id"] for m in c["materials"]} == {0}


def test_edited_material_values_survive_a_resync():
    c = _case()
    c["materials"][1]["permeability"] = "1e-9"
    c = S.sync_all(c)
    assert c["materials"][1]["permeability"] == "1e-9"


def test_switching_process_adds_the_new_variables_and_keeps_pressure_ic():
    c = _case()
    c["process_variables"]["pressure"]["initial_condition"] = "p0"
    c["process"]["type"] = "THERMO_RICHARDS_MECHANICS"
    c = S.sync_all(c)
    assert set(c["process_variables"]) == {"temperature", "pressure", "displacement"}
    assert c["process_variables"]["displacement"]["components"] == 3
    assert c["process_variables"]["pressure"]["initial_condition"] == "p0"
    # THM needs the mechanical parameters
    assert {"E", "nu", "u0", "T0"} <= set(c["parameters"])
    # and the solid phase properties appear on every medium
    assert "thermal_expansion" in c["materials"][0]


def test_switching_process_keeps_bcs():
    c = _case()
    c["process_variables"]["pressure"]["boundary_conditions"] = [
        {"mesh": "FZ1", "type": "Dirichlet", "parameter": "p_inj"}
    ]
    c["process"]["type"] = "HT"
    c = S.sync_all(c)
    assert c["process_variables"]["pressure"]["boundary_conditions"][0]["mesh"] == "FZ1"


def test_meshes_follow_the_bcs():
    c = _case()
    c["process_variables"]["pressure"]["boundary_conditions"] = [
        {"mesh": "FZ1", "type": "Dirichlet", "parameter": "p_inj"}
    ]
    c = S.sync_all(c)
    assert c["meshes"] == ["t.vtu", "FZ1.vtu"]


def test_bc_on_unknown_parameter_is_an_error():
    c = _case()
    c["process_variables"]["pressure"]["boundary_conditions"] = [
        {"mesh": "FZ1", "type": "Dirichlet", "parameter": "nope"}
    ]
    c = S.sync_all(c)
    assert any(lvl == S.ERROR and "nope" in m for lvl, m in S.validation_report(c))


def test_validation_surfaces_the_real_mesher_error():
    """The UI must not have its own opinion about what is legal."""
    c = _case()
    c["fractures"] = [
        {"name": "A", "dip": 0.0, "azimuth": 0.0, "point": [0, 0, -20],
         "half_size": 30.0, "representation": "surface", "conform": "embed",
         "material_id": 1},
        {"name": "B", "dip": 40.0, "azimuth": 90.0, "point": [0, 0, -20],
         "half_size": 30.0, "representation": "surface", "conform": "embed",
         "material_id": 2},
    ]
    c = S.sync_all(c)
    msgs = [m for lvl, m in S.validation_report(c) if lvl == S.ERROR]
    assert any("fragment" in m for m in msgs)


def test_duplicate_material_id_is_reported():
    c = _case()
    c["fractures"][0]["material_id"] = 0  # clashes with the matrix
    c = S.sync_all(c)
    assert any(lvl == S.ERROR for lvl, _ in S.validation_report(c))


def test_gravity_along_y_is_flagged():
    c = _case()
    c["overrides"] = {"processes": {"process": {"specific_body_force": [0, -9.81, 0]}}}
    assert any("sideways" in m for lvl, m in S.validation_report(c))


def test_element_estimate_reacts_to_refinement():
    c = _case()
    coarse = S.estimate_elements(c)
    c["fractures"][0]["refine"] = {"size_min": 1.0, "size_max": 8.0,
                                   "dist_min": 1.0, "dist_max": 20.0}
    assert S.estimate_elements(c) > coarse * 10


def test_yaml_roundtrip_drops_private_keys():
    c = _case()
    c["_dir"] = "/tmp"
    text = S.case_to_yaml(c)
    assert "_dir" not in text
    back = S.yaml_to_case(text)
    assert back["name"] == c["name"]
    assert back["fractures"][0]["name"] == "FZ1"


def test_saved_case_runs_through_the_cli_loader(tmp_path):
    from ogsfrac.config import load_case, mesh_inputs_from_case
    c = _case()
    p = S.save_case(c, tmp_path / "c.yml")
    loaded = load_case(p)
    domain, fractures, tunnel, options, obs = mesh_inputs_from_case(loaded)
    assert fractures[0].name == "FZ1"


def test_fracture_table_reports_orientation():
    c = _case()
    c["fractures"][0] = {
        "name": "FZ3", "half_size": 100,
        "points": [[-18.7, 20.1, -20.7], [-1.09, 36.18, -18.12], [16.03, 44.1, -15.9]],
        "material_id": 1,
    }
    row = S.fracture_table(c)[0]
    assert row["dip"] == pytest.approx(6.75, abs=0.01)
    assert row["azimuth"] == pytest.approx(251.61, abs=0.01)
