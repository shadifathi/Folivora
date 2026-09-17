"""Dict <-> OGS XML.

The mapping is deliberately transparent: what you write in YAML is what lands in
the .prj. You keep the OGS schema knowledge you already have; you stop writing
`ET.SubElement` calls to express it.

    {"process": {"name": "LiquidFlow", "type": "LIQUID_FLOW"}}
    ->  <process><name>LiquidFlow</name><type>LIQUID_FLOW</type></process>

Conventions:
    "@attr"  -> XML attribute            {"medium": {"@id": 0}} -> <medium id="0"/>
    "#text"  -> element text with attrs  {"mesh": {"#text": "a.vtu"}}
    list     -> repeated sibling elements
    None     -> self-closing element
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path


# A YAML list is ambiguous in XML: for <mesh> it means "repeat the element",
# for <specific_body_force> it means "one element holding a space-separated
# vector". OGS's schema decides which, so the vector-valued tags are listed
# here explicitly. Anything not listed repeats.
VECTOR_TAGS = frozenset({
    "specific_body_force",
    "abstols",
    "reltols",
    "number_iterations",
    "multiplier",
    "values",
    "coords",
    "repeat",
    "each_steps",
    "constant_parameter",
})


def dict_to_xml(parent: ET.Element, data: dict) -> ET.Element:
    for key, value in data.items():
        if key.startswith("@"):
            parent.set(key[1:], _fmt(value))
        elif key == "#text":
            parent.text = _fmt(value)
        elif isinstance(value, list) and key not in VECTOR_TAGS:
            for item in value:
                _append(parent, key, item)
        else:
            _append(parent, key, value)
    return parent


def _append(parent: ET.Element, tag: str, value):
    el = ET.SubElement(parent, tag)
    if isinstance(value, dict):
        dict_to_xml(el, value)
    elif value is None:
        pass
    else:
        el.text = _fmt(value)
    return el


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        # avoid 1e-06 style drift vs. what OGS examples use
        return repr(v) if v != int(v) else str(v)
    if isinstance(v, (list, tuple)):
        return " ".join(_fmt(x) for x in v)
    return str(v)


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge `override` into `base`. Lists are replaced, not concatenated.

    This is what lets a case file say only what differs from the process preset.
    """
    out = deepcopy(base)
    for k, v in (override or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def write_prj(tree_dict: dict, filename, encoding="ISO-8859-1") -> Path:
    """Serialise to a .prj. Encoding matches the files your notebooks emitted."""
    root = ET.Element("OpenGeoSysProject")
    dict_to_xml(root, tree_dict)
    ET.indent(ET.ElementTree(root), space="  ")
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding=encoding, xml_declaration=True)
    return path


# ----------------------------------------------------------------------------
# Editing an existing prj (kept from your notebooks, hardened)
# ----------------------------------------------------------------------------

def update_parameter(prj_file, param_name, new_value) -> Path:
    """Set <parameter><name>param_name</name><value>...  Raises if not found."""
    prj_file = Path(prj_file)
    tree = ET.parse(prj_file)
    hits = 0
    for param in tree.getroot().findall(".//parameter"):
        name = param.find("name")
        if name is not None and name.text == param_name:
            value = param.find("value")
            if value is None:
                raise ValueError(
                    f"parameter '{param_name}' has no <value> (type is "
                    f"'{param.findtext('type')}' — MeshNode/Function params "
                    f"cannot be set this way)"
                )
            value.text = _fmt(new_value)
            hits += 1
    if hits == 0:
        raise ValueError(f"parameter '{param_name}' not found in {prj_file}")
    tree.write(prj_file, encoding="ISO-8859-1", xml_declaration=True)
    return prj_file


def change_output_filename(prj_file, new_output_name, backup=True) -> Path:
    prj_file = Path(prj_file)
    if backup:
        prj_file.with_suffix(prj_file.suffix + ".bak").write_bytes(prj_file.read_bytes())
    tree = ET.parse(prj_file)
    prefix = tree.getroot().find(".//time_loop/output/prefix")
    if prefix is None:
        raise ValueError(f"no <time_loop><output><prefix> in {prj_file}")
    prefix.text = str(new_output_name)
    tree.write(prj_file, encoding="ISO-8859-1", xml_declaration=True)
    return prj_file
