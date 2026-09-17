import numpy as np
import pytest

from ogsfrac import Domain, FractureSpec, Plane

gmsh = pytest.importorskip("gmsh")
from ogsfrac.meshing.builder import FracturedDomainMesh  # noqa: E402


def _dom():
    return Domain(-50, 50, -50, 50, -50, 0, lc=25.0)


def _frac(name, dip, azi, z, half=20.0, **kw):
    p = Plane.from_dip_azimuth(dip, azi, [0, 0, z], name=name)
    return FractureSpec(name=name, corners=p.corners(half), **kw)


def test_crossing_embedded_fractures_are_rejected():
    a = _frac("A", 0.0, 0.0, -20.0, material_id=1)
    b = _frac("B", 40.0, 90.0, -20.0, material_id=2)
    with pytest.raises(ValueError, match="conform='fragment'"):
        FracturedDomainMesh(_dom(), [a, b])


def test_non_crossing_embedded_fractures_are_allowed():
    a = _frac("A", 0.0, 0.0, -10.0, half=5.0, material_id=1)
    b = _frac("B", 0.0, 0.0, -30.0, half=5.0, material_id=2)
    FracturedDomainMesh(_dom(), [a, b])  # must not raise


def test_duplicate_material_ids_are_rejected():
    a = _frac("A", 0.0, 0.0, -10.0, half=5.0, material_id=1)
    b = _frac("B", 0.0, 0.0, -30.0, half=5.0, material_id=1)
    with pytest.raises(ValueError, match="duplicate material_id"):
        FracturedDomainMesh(_dom(), [a, b])


def test_domain_material_id_cannot_clash_with_a_fracture():
    a = _frac("A", 0.0, 0.0, -10.0, half=5.0, material_id=0)
    with pytest.raises(ValueError, match="duplicate material_id"):
        FracturedDomainMesh(_dom(), [a])


def test_observation_point_outside_domain_is_rejected():
    with pytest.raises(ValueError, match="outside the domain"):
        FracturedDomainMesh(_dom(), [], observation_points={"P1": (0, 0, 500)})


def test_fracture_spec_validates_corner_shape():
    with pytest.raises(ValueError, match=r"\(4,3\)"):
        FractureSpec(name="x", corners=np.zeros((3, 3)))


def test_end_to_end_mesh_has_expected_groups(tmp_path):
    from ogsfrac.meshing.convert import inspect, msh_to_vtu
    f = _frac("A", 0.0, 0.0, -25.0, half=15.0, material_id=1, lc=15.0)
    m = FracturedDomainMesh(_dom(), [f])
    msh = m.generate(tmp_path / "m.msh")
    info = inspect(msh)
    assert info["physical_groups"]["Rock"] == 0 + FracturedDomainMesh.MATERIAL_TAG_OFFSET
    assert info["physical_groups"]["A"] == 1 + FracturedDomainMesh.MATERIAL_TAG_OFFSET
    assert info["physical_groups"]["left"] >= FracturedDomainMesh.BOUNDARY_TAG_BASE
    assert info["cells"]["tetra"] > 0

    vtu = msh_to_vtu(msh, tmp_path / "m.vtu")
    import meshio
    mesh = meshio.read(vtu)
    mids = np.concatenate(mesh.cell_data["MaterialIDs"])
    assert mids.dtype == np.int32
    # the embedded fracture survives conversion as triangles with its own id
    assert set(mids.tolist()) == {0, 1}
    assert any(b.type == "triangle" for b in mesh.cells)
