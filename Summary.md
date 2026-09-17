---
title: 'ogsfrac: a declarative, validating pipeline from fracture geometry to OpenGeoSys simulations of fractured rock'
tags:
  - Python
  - OpenGeoSys
  - fractured rock
  - discrete fracture network
  - finite element method
  - mesh generation
  - geothermal energy
  - reproducibility
authors:
  - name: Shadi Fathi
---

# ogsfrac

`ogsfrac` turns a single human-readable case file into a complete, runnable
OpenGeoSys [@Kolditz2012; @Bilke2019] simulation of fractured rock. One YAML
document describes the model domain, the fractures (placed explicitly or drawn
from a stochastic discrete fracture network), the coupled process, the media,
and the initial and boundary conditions; from it the package derives fracture
plane orientations, generates a conforming gmsh [@Geuzaine2009] mesh, converts
it to the mesh files OpenGeoSys expects, writes the `.prj` project file, and
invokes the solver. The four stages — `geometry`, `mesh`, `prj`, `run` — are
available as a command-line pipeline, as importable Python functions, and
through a browser-based case editor.

Fractures may be represented per fracture, in the same model, either as
lower-dimensional surface elements embedded in the three-dimensional mesh or as
thin extruded volumes of a stated aperture, so that the two idealisations
common in the fractured-porous-media literature [@Berre2019] can be compared
without rebuilding the model. Model parameters, coupling and solver settings
are supplied as process presets that a case file overrides; anything the
presets do not cover can be written as a raw project-file subtree, which is
deep-merged last, so no part of the OpenGeoSys input schema is unreachable.

The distinctive design commitment is that every constraint the mesher or the
solver will eventually enforce is checked *before* meshing begins, by the same
code that performs the work, and reported against the named object at fault.
