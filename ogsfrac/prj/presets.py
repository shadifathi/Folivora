"""Process presets: the defaults that were hardcoded in each `build()` method.

A case file overrides only what differs. Everything here is a plain dict, so
`ogsfrac.prj.presets.LIQUID_FLOW` can be printed, diffed, or edited without
reading any Python.
"""
from __future__ import annotations

from copy import deepcopy

# ---------------------------------------------------------------------------
# Shared blocks
# ---------------------------------------------------------------------------

NEWTON = {
    "nonlinear_solver": {
        "name": "basic_newton",
        "type": "Newton",
        "max_iter": 50,
        "linear_solver": "general_linear_solver",
    }
}

PICARD = {
    "nonlinear_solver": {
        "name": "basic_picard",
        "type": "Picard",
        "max_iter": 50,
        "linear_solver": "general_linear_solver",
    }
}

SPARSE_LU = {
    "linear_solver": {
        "name": "general_linear_solver",
        "eigen": {"solver_type": "SparseLU", "scaling": True},
    }
}

ITERATION_TIME_STEPPING = {
    "type": "IterationNumberBasedTimeStepping",
    "t_initial": 0.0,
    "t_end": 400.0,
    "initial_dt": 1.0,
    "minimum_dt": 5e-3,
    "maximum_dt": 20.0,
    "number_iterations": [2, 3, 6, 10, 12],
    "multiplier": [5.0, 2.5, 1.25, 1.01, 0.5],
}

VTK_OUTPUT = {
    "type": "VTK",
    "prefix": "result",
    "timesteps": {"pair": {"repeat": 1, "each_steps": 10}},
    "variables": None,
    "suffix": "_ts_{:timestep}_t_{:time}",
}


def _liquid_phase(viscosity=1e-3, density=1000.0):
    return {
        "phase": {
            "type": "AqueousLiquid",
            "properties": {
                "property": [
                    {"name": "viscosity", "type": "Constant", "value": viscosity},
                    {"name": "density", "type": "Constant", "value": density},
                ]
            },
        }
    }


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

LIQUID_FLOW = {
    "processes": {
        "process": {
            "name": "LiquidFlow",
            "type": "LIQUID_FLOW",
            "integration_order": 2,
            "specific_body_force": [0, 0, -9.81],
            "process_variables": {"process_variable": "pressure"},
            "secondary_variables": {
                "secondary_variable": {"@internal_name": "darcy_velocity", "@output_name": "v"}
            },
        }
    },
    "time_loop": {
        "processes": {
            "process": {
                "@ref": "LiquidFlow",
                "nonlinear_solver": "basic_newton",
                "convergence_criterion": {
                    "type": "PerComponentDeltaX",
                    "norm_type": "NORM2",
                    "abstols": 1e-6,
                },
                "time_discretization": {"type": "BackwardEuler"},
                "time_stepping": deepcopy(ITERATION_TIME_STEPPING),
            }
        },
        "output": deepcopy(VTK_OUTPUT),
    },
    "nonlinear_solvers": deepcopy(NEWTON),
    "linear_solvers": deepcopy(SPARSE_LU),
}

HYDRO_THERMAL = {
    "processes": {
        "process": {
            "name": "HeatTransportLiquidFlow",
            "type": "HT",
            "integration_order": 2,
            "specific_body_force": [0, 0, -9.81],
            "process_variables": {
                "temperature": "temperature",
                "pressure": "pressure",
            },
            "secondary_variables": {
                "secondary_variable": {"@internal_name": "darcy_velocity", "@output_name": "v"}
            },
        }
    },
    "time_loop": {
        "processes": {
            "process": {
                "@ref": "HeatTransportLiquidFlow",
                "nonlinear_solver": "basic_picard",
                "convergence_criterion": {
                    "type": "PerComponentDeltaX",
                    "norm_type": "NORM2",
                    "abstols": [1e-3, 1e-3],
                },
                "time_discretization": {"type": "BackwardEuler"},
                "time_stepping": deepcopy(ITERATION_TIME_STEPPING),
            }
        },
        "output": deepcopy(VTK_OUTPUT),
    },
    "nonlinear_solvers": deepcopy(PICARD),
    "linear_solvers": deepcopy(SPARSE_LU),
}

HYDRO_MECHANICS = {
    "processes": {
        "process": {
            "name": "HydroMechanics",
            "type": "HYDRO_MECHANICS",
            "integration_order": 3,
            "dimension": 3,
            "constitutive_relation": {
                "type": "LinearElasticIsotropic",
                "youngs_modulus": "E",
                "poissons_ratio": "nu",
            },
            "specific_body_force": [0, 0, 0],
            "process_variables": {
                "pressure": "pressure",
                "displacement": "displacement",
            },
            "secondary_variables": {
                "secondary_variable": [
                    {"@internal_name": "sigma", "@output_name": "sigma"},
                    {"@internal_name": "epsilon", "@output_name": "epsilon"},
                    {"@internal_name": "velocity", "@output_name": "v"},
                ]
            },
        }
    },
    "time_loop": {
        "processes": {
            "process": {
                "@ref": "HydroMechanics",
                "nonlinear_solver": "basic_newton",
                "convergence_criterion": {
                    "type": "PerComponentDeltaX",
                    "norm_type": "NORM2",
                    "abstols": [1e-6, 1e-10, 1e-10, 1e-10],
                },
                "time_discretization": {"type": "BackwardEuler"},
                "time_stepping": deepcopy(ITERATION_TIME_STEPPING),
            }
        },
        "output": deepcopy(VTK_OUTPUT),
    },
    "nonlinear_solvers": deepcopy(NEWTON),
    "linear_solvers": deepcopy(SPARSE_LU),
}

THERMO_RICHARDS_MECHANICS = {
    "processes": {
        "process": {
            "name": "ThermoRichardsMechanics",
            "type": "THERMO_RICHARDS_MECHANICS",
            "integration_order": 3,
            "dimension": 3,
            "constitutive_relation": {
                "type": "LinearElasticIsotropic",
                "youngs_modulus": "E",
                "poissons_ratio": "nu",
            },
            "specific_body_force": [0, 0, 0],
            "process_variables": {
                "temperature": "temperature",
                "pressure": "pressure",
                "displacement": "displacement",
            },
            "secondary_variables": {
                "secondary_variable": [
                    {"@internal_name": "sigma", "@output_name": "sigma"},
                    {"@internal_name": "epsilon", "@output_name": "epsilon"},
                    {"@internal_name": "velocity", "@output_name": "v"},
                    {"@internal_name": "saturation", "@output_name": "saturation"},
                ]
            },
        }
    },
    "time_loop": {
        "processes": {
            "process": {
                "@ref": "ThermoRichardsMechanics",
                "nonlinear_solver": "basic_newton",
                "convergence_criterion": {
                    "type": "PerComponentDeltaX",
                    "norm_type": "NORM2",
                    "abstols": [1e-3, 1e-3, 1e-10, 1e-10, 1e-10],
                },
                "time_discretization": {"type": "BackwardEuler"},
                "time_stepping": deepcopy(ITERATION_TIME_STEPPING),
            }
        },
        "output": deepcopy(VTK_OUTPUT),
    },
    "nonlinear_solvers": deepcopy(NEWTON),
    "linear_solvers": deepcopy(SPARSE_LU),
}

PRESETS = {
    "LIQUID_FLOW": LIQUID_FLOW,
    "HT": HYDRO_THERMAL,
    "HYDRO_MECHANICS": HYDRO_MECHANICS,
    "THERMO_RICHARDS_MECHANICS": THERMO_RICHARDS_MECHANICS,
}


def get_preset(process_type: str) -> dict:
    try:
        return deepcopy(PRESETS[process_type])
    except KeyError:
        raise KeyError(
            f"no preset for process type '{process_type}'. "
            f"Available: {sorted(PRESETS)}. Add one to ogsfrac/prj/presets.py — "
            f"it is a plain dict."
        ) from None


# ---------------------------------------------------------------------------
# Process metadata — what each coupling needs.
#
# The property lists and default values below are lifted from the builders in
# your notebooks (DesignModel.LiquidFlowProject / HydroMechProject,
# HydroModel.HydroThermalProject / ThermoRichardsMechanicsProject), so the UI
# prompts with the numbers you already use. Correct them here, once.
# ---------------------------------------------------------------------------

from dataclasses import dataclass


@dataclass(frozen=True)
class PropertyDef:
    name: str
    default: float
    unit: str = ""
    note: str = ""


_FLUID_H = [
    PropertyDef("viscosity", 1e-3, "Pa s"),
    PropertyDef("density", 1000.0, "kg/m3"),
]
_FLUID_TH = _FLUID_H + [
    PropertyDef("specific_heat_capacity", 4180.0, "J/kg/K"),
    PropertyDef("thermal_conductivity", 0.6, "W/m/K"),
]
_SOLID_TH = [
    PropertyDef("density", 2650.0, "kg/m3"),
    PropertyDef("specific_heat_capacity", 800.0, "J/kg/K"),
    PropertyDef("thermal_conductivity", 2.5, "W/m/K"),
]

PROCESS_INFO = {
    "LIQUID_FLOW": {
        "label": "Liquid flow (H)",
        "couplings": "H",
        "source": "DesignModel.LiquidFlowProject",
        "medium": [
            PropertyDef("permeability", 1e-14, "m2"),
            PropertyDef("porosity", 0.15, "-"),
            PropertyDef("storage", 1e-5, "1/Pa"),
            PropertyDef("reference_temperature", 303.0, "K"),
        ],
        "fluid": _FLUID_H,
        "solid": [],
        "variables": {"pressure": {"components": 1, "ic": "p0"}},
        "parameters": {"p0": 0.0, "p_inj": 8e5},
    },
    "HT": {
        "label": "Heat transport + liquid flow (TH)",
        "couplings": "TH",
        "source": "HydroModel.HydroThermalProject",
        "medium": [
            PropertyDef("permeability", 1e-14, "m2"),
            PropertyDef("porosity", 0.15, "-"),
            PropertyDef("storage", 1e-5, "1/Pa"),
            PropertyDef("reference_temperature", 303.0, "K"),
        ],
        "fluid": _FLUID_TH,
        "solid": _SOLID_TH,
        "variables": {
            "temperature": {"components": 1, "ic": "T0"},
            "pressure": {"components": 1, "ic": "p0"},
        },
        "parameters": {"T0": 303.0, "p0": 1e5},
    },
    "HYDRO_MECHANICS": {
        "label": "Hydro-mechanics (HM)",
        "couplings": "HM",
        "source": "DesignModel.HydroMechProject",
        "medium": [
            PropertyDef("permeability", 1e-14, "m2"),
            PropertyDef("porosity", 0.15, "-"),
            PropertyDef("storage", 1e-5, "1/Pa"),
            PropertyDef("biot_coefficient", 1.0, "-"),
            PropertyDef("reference_temperature", 303.0, "K"),
        ],
        "fluid": _FLUID_H,
        "solid": [PropertyDef("density", 2650.0, "kg/m3")],
        "variables": {
            "pressure": {"components": 1, "ic": "p0"},
            "displacement": {"components": 3, "ic": "u0"},
        },
        # E and nu are referenced by <constitutive_relation>, which the
        # notebook's HydroMechProject never emitted.
        "parameters": {"p0": 0.0, "p_inj": 8e5, "u0": [0, 0, 0], "E": 5e10, "nu": 0.25},
    },
    "THERMO_RICHARDS_MECHANICS": {
        "label": "Thermo-Richards-mechanics (THM, unsaturated)",
        "couplings": "THM",
        "source": "HydroModel.ThermoRichardsMechanicsProject",
        "medium": [
            PropertyDef("permeability", 1e-14, "m2"),
            PropertyDef("porosity", 0.15, "-"),
            PropertyDef("biot_coefficient", 1.0, "-"),
            PropertyDef("storage", 1e-6, "1/Pa"),
            PropertyDef("reference_temperature", 303.0, "K"),
            PropertyDef("thermal_expansion", 1e-5, "1/K", "volumetric, solid"),
        ],
        "fluid": _FLUID_TH,
        "solid": _SOLID_TH,
        "variables": {
            "temperature": {"components": 1, "ic": "T0"},
            "pressure": {"components": 1, "ic": "p0"},
            "displacement": {"components": 3, "ic": "u0"},
        },
        "parameters": {"T0": 303.0, "p0": 1e5, "u0": [0, 0, 0], "E": 5e10, "nu": 0.25},
    },
}

BC_TYPES = ["Dirichlet", "Neumann", "Robin", "NonuniformDirichlet", "NonuniformNeumann"]
