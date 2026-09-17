import xml.etree.ElementTree as ET

import pytest

from ogsfrac.prj.build import build_media, build_prj
from ogsfrac.prj.xmlutil import deep_merge, update_parameter


def _case(tmp_path):
    return {
        "process": {"type": "LIQUID_FLOW"},
        "meshes": ["bulk.vtu", "FZ1.vtu"],
        "t_end": 900.0,
        "materials": [{"id": 0, "name": "rock", "permeability": "1e-17", "porosity": 0.01}],
        "parameters": {"p_inj": "8e5", "p0": 0.0},
        "process_variables": {
            "pressure": {
                "initial_condition": "p0",
                "boundary_conditions": [{"mesh": "FZ1", "type": "Dirichlet", "parameter": "p_inj"}],
            }
        },
    }


def test_yaml_exponent_strings_become_constants(tmp_path):
    """YAML 1.1 reads 1e-17 as a str; it must not become a Parameter ref."""
    prj = build_prj(_case(tmp_path), tmp_path / "t.prj")
    r = ET.parse(prj).getroot()
    perm = r.find(".//medium[@id='0']/properties/property[name='permeability']")
    assert perm.findtext("type") == "Constant"
    assert float(perm.findtext("value")) == 1e-17
    assert r.find(".//parameter[name='p_inj']").findtext("type") == "Constant"


def test_vector_tags_are_space_separated(tmp_path):
    prj = build_prj(_case(tmp_path), tmp_path / "t.prj")
    r = ET.parse(prj).getroot()
    assert r.findtext(".//specific_body_force") == "0 0 -9.81"
    assert len(r.findall(".//specific_body_force")) == 1
    assert r.findtext(".//number_iterations") == "2 3 6 10 12"


def test_repeated_tags_stay_repeated(tmp_path):
    prj = build_prj(_case(tmp_path), tmp_path / "t.prj")
    r = ET.parse(prj).getroot()
    assert [m.text for m in r.findall(".//meshes/mesh")] == ["bulk.vtu", "FZ1.vtu"]


def test_overrides_win(tmp_path):
    case = _case(tmp_path)
    case["overrides"] = {"processes": {"process": {"integration_order": 4}}}
    r = ET.parse(build_prj(case, tmp_path / "t.prj")).getroot()
    assert r.findtext(".//processes/process/integration_order") == "4"


def test_t_end_shortcut(tmp_path):
    r = ET.parse(build_prj(_case(tmp_path), tmp_path / "t.prj")).getroot()
    assert float(r.findtext(".//time_stepping/t_end")) == 900.0


def test_string_property_is_a_parameter_reference():
    media = build_media([{"id": 0, "permeability": "perm_field"}])
    prop = media["medium"][0]["properties"]["property"][0]
    assert prop["type"] == "Parameter" and prop["parameter_name"] == "perm_field"


def test_update_parameter_raises_when_missing(tmp_path):
    prj = build_prj(_case(tmp_path), tmp_path / "t.prj")
    update_parameter(prj, "p_inj", 1.2e6)
    assert float(ET.parse(prj).getroot().find(".//parameter[name='p_inj']").findtext("value")) == 1.2e6
    with pytest.raises(ValueError):
        update_parameter(prj, "nope", 1.0)


def test_deep_merge_is_recursive():
    assert deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"c": 3}}) == {"a": {"b": 1, "c": 3}}
    assert deep_merge({"a": {"b": 1}}, {})["a"]["b"] == 1
