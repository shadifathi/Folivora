"""Boreholes: load from file, evaluate points along the trace.

Replaces the manual workflow in Grimsel_GM.ipynb cell 1, where `A`, `B` and `d`
were edited by hand and the printed result pasted into the next cell.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class Borehole:
    """A straight borehole trace from collar `A` to end `B`.

    Curved traces are not supported yet; see `from_survey` for the hook.
    """

    name: str
    A: np.ndarray  # collar, shape (3,)
    B: np.ndarray  # end,    shape (3,)
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        self.A = np.asarray(self.A, dtype=float)
        self.B = np.asarray(self.B, dtype=float)
        if self.A.shape != (3,) or self.B.shape != (3,):
            raise ValueError(f"{self.name}: A and B must be 3-vectors")
        if self.length == 0.0:
            raise ValueError(f"{self.name}: collar and end coincide")

    @property
    def length(self) -> float:
        return float(np.linalg.norm(self.B - self.A))

    @property
    def unit(self) -> np.ndarray:
        return (self.B - self.A) / self.length

    @property
    def azimuth_dip(self) -> tuple[float, float]:
        """(azimuth, dip) in degrees. Azimuth clockwise from +y (north), dip
        positive downward. Matches the convention in the commented-out
        `borehole_end_point` helper in Grimsel_GM.
        """
        u = self.unit
        azi = np.degrees(np.arctan2(u[0], u[1])) % 360.0
        dip = np.degrees(np.arcsin(-u[2]))
        return float(azi), float(dip)

    def point_at(self, d: float) -> np.ndarray:
        """Point at measured depth `d` along the trace. (Was `point_on_line`.)"""
        return self.A + d * self.unit

    def points_at(self, depths) -> np.ndarray:
        depths = np.asarray(depths, dtype=float).reshape(-1, 1)
        return self.A + depths * self.unit

    @classmethod
    def from_collar_azimuth_dip(cls, name, collar, azimuth_deg, dip_deg, length, **meta):
        azi = np.radians(azimuth_deg)
        dip = np.radians(dip_deg)
        d = np.array([np.sin(azi) * np.cos(dip), np.cos(azi) * np.cos(dip), -np.sin(dip)])
        collar = np.asarray(collar, dtype=float)
        return cls(name=name, A=collar, B=collar + length * d, meta=meta)

    @classmethod
    def from_survey(cls, name, collar, survey_df):
        raise NotImplementedError(
            "Deviated traces (minimum-curvature desurveying) not implemented. "
            "Supply collar/end points, or open an issue with a sample survey file."
        )


# ----------------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------------

_COORD_COLS = ["x_start", "y_start", "z_start", "x_end", "y_end", "z_end"]


def _clean_european_numbers(s: pd.Series) -> pd.Series:
    """Handle '667.425,15' -> 667425.15.

    This is the fix that was inline in DesignModel.ipynb cell 1. It strips '.'
    as a thousands separator and maps ',' to the decimal point. Applied only
    when the column is not already numeric, so clean files pass through
    untouched (the old code would have destroyed them).
    """
    if pd.api.types.is_numeric_dtype(s):
        return s.astype(float)
    return (
        s.astype(str)
        .str.strip()
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )


def load_boreholes(path, sheet=None, sep="\t", name_col="borehole_name") -> list[Borehole]:
    """Load boreholes from CSV or Excel.

    Expected columns: `borehole_name`, x_start, y_start, z_start,
    x_end, y_end, z_end. Decimal commas and thousands separators are handled.
    """
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        df = pd.read_excel(path, sheet_name=sheet or 0)
    else:
        df = pd.read_csv(path, sep=sep)

    missing = [c for c in _COORD_COLS if c not in df.columns]
    if missing:
        raise ValueError(
            f"{path.name} is missing columns {missing}. Found: {list(df.columns)}"
        )
    for col in _COORD_COLS:
        df[col] = _clean_european_numbers(df[col])

    holes = []
    for _, row in df.iterrows():
        holes.append(
            Borehole(
                name=str(row.get(name_col, f"BH{len(holes) + 1}")),
                A=row[["x_start", "y_start", "z_start"]].to_numpy(float),
                B=row[["x_end", "y_end", "z_end"]].to_numpy(float),
                meta={k: row[k] for k in df.columns if k not in _COORD_COLS + [name_col]},
            )
        )
    return holes
