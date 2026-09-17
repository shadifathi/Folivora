"""Regression tests pinning ogsfrac to the numbers the notebooks produced."""
import numpy as np
import pytest

from ogsfrac import Borehole, Plane, are_coplanar

# The three-point triples and the resulting normals are taken from the comments
# in Grimsel_GM.ipynb cell 2, so these tests fail if a refactor changes the
# geometry that the published Grimsel model was built on.
FZ = {
    "FZ1": ([[-7.0, 18.5, -9.4], [1.13, 28.95, -8.8], [16.9, 33.1, -8.07]],
            [0.03916387, 0.02688234, -0.99887113]),
    "FZ2": ([[-15.92, 26.7, -18.1], [-0.54, 34.37, -15.8], [16.21, 41.73, -14.23]],
            [-0.22684143, 0.66752969, -0.70918762]),
    "FZ3": ([[-18.7, 20.1, -20.7], [-1.09, 36.18, -18.12], [16.03, 44.1, -15.9]],
            [0.11160535, 0.03710966, -0.99305947]),
}


@pytest.mark.parametrize("name", list(FZ))
def test_normals_match_notebook(name):
    pts, expected = FZ[name]
    p = Plane.from_3points(*pts, name=name)
    n = p.normal if np.dot(p.normal, expected) > 0 else -p.normal
    np.testing.assert_allclose(n, expected, atol=1e-7)


def test_corners_are_a_simple_quad():
    """The old plane_rectangle_from_3points emitted a bowtie; corners() must not."""
    p = Plane.from_3points(*FZ["FZ3"][0], name="FZ3")
    c = p.corners(half_size=100.0)
    sides = [np.linalg.norm(c[(i + 1) % 4] - c[i]) for i in range(4)]
    diags = [np.linalg.norm(c[2] - c[0]), np.linalg.norm(c[3] - c[1])]
    # in a square, all sides equal and both diagonals are longer than any side
    np.testing.assert_allclose(sides, [200.0] * 4, rtol=1e-9)
    assert min(diags) > max(sides)


def test_corners_lie_on_the_plane():
    p = Plane.from_3points(*FZ["FZ2"][0], name="FZ2")
    assert np.abs(p.signed_distance(p.corners(50.0))).max() < 1e-9


def test_point_on_line_matches_notebook():
    """Grimsel_GM cell 1: A=[27.8,21.76,0.05] B=[24.6,62.1,-28.8] d=13.8."""
    bh = Borehole("B8508", [27.8, 21.76, 0.05], [24.6, 62.1, -28.8])
    np.testing.assert_allclose(bh.point_at(13.8), [26.911, 32.962, -7.961], atol=1e-3)


def test_fit_recovers_an_exact_plane():
    pts, expected = FZ["FZ1"]
    extra = np.vstack([pts, np.mean(pts, axis=0)])  # 4th point on the plane
    p = Plane.fit(extra, name="FZ1")
    n = p.normal if np.dot(p.normal, expected) > 0 else -p.normal
    np.testing.assert_allclose(n, expected, atol=1e-6)
    assert p.residual < 1e-9


def test_fit_reports_misfit():
    pts = np.array(FZ["FZ1"][0] + [[5.0, 25.0, -5.0]])  # off-plane point
    assert Plane.fit(pts).residual > 0.1


def test_are_coplanar():
    p = Plane.from_3points(*FZ["FZ3"][0])
    assert are_coplanar(p.corners(30.0))
    assert not are_coplanar(np.vstack([p.corners(30.0)[:3], [0, 0, 999]]))


def test_borehole_rejects_degenerate():
    with pytest.raises(ValueError):
        Borehole("bad", [1, 2, 3], [1, 2, 3])


def test_dip_azimuth_roundtrip():
    p = Plane.from_dip_azimuth(35.0, 120.0, [0, 0, 0])
    dip, azi = p.dip_azimuth
    assert abs(dip - 35.0) < 1e-6 and abs(azi - 120.0) < 1e-6
