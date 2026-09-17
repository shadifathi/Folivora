"""ogsfrac — geometry, meshing, project files and post-processing for
H/TH/HM/THM simulations of fractured rock in OpenGeoSys.
"""
__version__ = "0.2.0"

from .config import load_case
from .geometry.boreholes import Borehole, load_boreholes
from .geometry.planes import Plane, are_coplanar, intersect_boreholes
from .meshing.builder import Domain, FracturedDomainMesh, FractureSpec, MeshOptions, Refinement, TunnelSpec
from .meshing.convert import extract_subdomain, inspect, msh_to_vtu
from .prj.build import build_prj
from .run import OGSError, OGSSimulation

__all__ = [
    "Borehole", "load_boreholes", "Plane", "are_coplanar", "intersect_boreholes",
    "Domain", "FractureSpec", "TunnelSpec", "Refinement", "MeshOptions", "FracturedDomainMesh",
    "msh_to_vtu", "extract_subdomain", "inspect", "build_prj",
    "OGSSimulation", "OGSError", "load_case",
]
