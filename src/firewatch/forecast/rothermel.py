"""Rothermel (1972) surface rate-of-spread, the transparent physical prior (FR-FC-1).

This is a faithful implementation of the classic Rothermel surface-fire spread equations as
collected in Andrews (2018), "The Rothermel surface fire spread model and associated developments"
(RMRS-GTR-371), using the 13 standard Anderson (1982) fuel models. It returns head-fire ROS in
m/s together with an elliptical length-to-breadth ratio, from which `spread.py` derives ROS in any
direction.

Honesty note (CLAUDE.md principle 1): the goal is a *debuggable physical prior*, not to out-physics
WRF-SFIRE. Fuel-model constants are the standard published values; a unit test (tests/) checks a
benchmark ROS against a known BehavePlus-style case to guard against transcription errors. The
headline contribution is the assimilation that *corrects* this prior, not the prior itself.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# Unit helpers ------------------------------------------------------------------
FT_PER_M = 3.280839895
FTMIN_PER_MS = 196.850394  # (m/s) -> (ft/min)
MS_PER_FTMIN = 1.0 / FTMIN_PER_MS
MPH_PER_MS = 2.2369363


@dataclass(frozen=True)
class FuelModel:
    """Standard fuel-model parameters (English units, as Rothermel uses)."""

    number: int
    name: str
    load_dead_1h: float  # oven-dry load, lb/ft^2 (lumped dead fine fuel)
    depth_ft: float  # fuel-bed depth, ft
    sav: float  # characteristic surface-area-to-volume, 1/ft
    mx_dead: float  # dead fuel moisture of extinction, fraction
    burnable: bool = True


# Anderson (1982) 13 standard fuel models. Loads are lumped oven-dry dead fine-fuel loads
# (tons/acre -> lb/ft^2 via /21.78). Depth/SAV/Mx are the standard published values.
FUEL_MODELS: dict[int, FuelModel] = {
    0: FuelModel(0, "non-burnable", 0.0, 0.1, 1500, 0.10, burnable=False),
    1: FuelModel(1, "short grass", 0.034, 1.0, 3500, 0.12),
    2: FuelModel(2, "timber grass & understory", 0.092, 1.0, 3000, 0.15),
    3: FuelModel(3, "tall grass", 0.138, 2.5, 1500, 0.25),
    4: FuelModel(4, "chaparral", 0.230, 6.0, 2000, 0.20),
    5: FuelModel(5, "brush", 0.046, 2.0, 2000, 0.20),
    6: FuelModel(6, "dormant brush", 0.069, 2.5, 1750, 0.25),
    7: FuelModel(7, "southern rough", 0.052, 2.5, 1750, 0.40),
    8: FuelModel(8, "closed timber litter", 0.069, 0.2, 2000, 0.30),
    9: FuelModel(9, "hardwood litter", 0.134, 0.2, 2500, 0.25),
    10: FuelModel(10, "timber litter & understory", 0.138, 1.0, 2000, 0.25),
    11: FuelModel(11, "light logging slash", 0.069, 1.0, 1500, 0.15),
    12: FuelModel(12, "medium logging slash", 0.184, 2.3, 1500, 0.20),
    13: FuelModel(13, "heavy logging slash", 0.322, 3.0, 1500, 0.25),
}

# Physical constants (Rothermel 1972 / Albini 1976)
_ST = 0.0555  # total mineral content
_SE = 0.010  # effective mineral content
_RHO_P = 32.0  # oven-dry particle density, lb/ft^3
_HEAT = 8000.0  # low heat content, Btu/lb
_MIDFLAME_FACTOR = 0.4  # 10-m wind -> midflame wind (open canopy default)


@dataclass
class RothermelResult:
    ros_head_ms: float  # head-fire rate of spread (m/s)
    ros_base_ms: float  # no-wind, no-slope ROS (m/s), used for backing spread
    length_to_breadth: float  # ellipse LB ratio (>= 1)
    reaction_intensity: float  # IR, Btu/ft^2/min (diagnostic)


def length_to_breadth(midflame_wind_ms: float) -> float:
    """Elliptical length-to-breadth ratio from midflame wind (Anderson 1983)."""
    u = max(0.0, midflame_wind_ms) * MPH_PER_MS  # mph
    lb = 0.936 * math.exp(0.2566 * u) + 0.461 * math.exp(-0.1548 * u) - 0.397
    return float(min(max(lb, 1.0), 8.0))


def rothermel(
    fuel_model: int,
    dead_moisture: float,
    wind_speed_ms: float,
    slope_fraction: float,
    *,
    midflame_factor: float = _MIDFLAME_FACTOR,
) -> RothermelResult:
    """Compute head-fire ROS (m/s) for a cell.

    Parameters
    ----------
    fuel_model : Anderson 1-13 (0 = non-burnable).
    dead_moisture : dead fuel moisture fraction (e.g., 0.06 = 6%).
    wind_speed_ms : 10-m wind speed magnitude in the head direction (m/s).
    slope_fraction : rise/run in the upslope direction contributing to the head (>= 0).
    """
    fm = FUEL_MODELS.get(fuel_model, FUEL_MODELS[0])
    if not fm.burnable or fm.load_dead_1h <= 0:
        return RothermelResult(0.0, 0.0, 1.0, 0.0)

    wo, depth, sigma, mx = fm.load_dead_1h, fm.depth_ft, fm.sav, fm.mx_dead
    mf = max(0.005, dead_moisture)

    # packing ratio
    rho_b = wo / depth
    beta = rho_b / _RHO_P
    beta_op = 3.348 * sigma**-0.8189
    beta_ratio = beta / beta_op

    # reaction velocity
    gamma_max = sigma**1.5 / (495.0 + 0.0594 * sigma**1.5)
    a = 133.0 * sigma**-0.7913
    gamma = gamma_max * beta_ratio**a * math.exp(a * (1.0 - beta_ratio))

    # net fuel load and damping coefficients
    wn = wo / (1.0 + _ST)
    rm = min(mf / mx, 1.0)
    eta_m = max(0.0, 1.0 - 2.59 * rm + 5.11 * rm**2 - 3.52 * rm**3)
    eta_s = min(1.0, 0.174 * _SE**-0.19)

    # reaction intensity, propagating flux
    i_r = gamma * wn * _HEAT * eta_m * eta_s
    xi = math.exp((0.792 + 0.681 * sigma**0.5) * (beta + 0.1)) / (192.0 + 0.2595 * sigma)

    # heat sink
    epsilon = math.exp(-138.0 / sigma)
    q_ig = 250.0 + 1116.0 * mf
    heat_sink = rho_b * epsilon * q_ig

    ros_base_ftmin = i_r * xi / heat_sink if heat_sink > 0 else 0.0

    # wind & slope factors
    u_ftmin = max(0.0, wind_speed_ms) * midflame_factor * FTMIN_PER_MS
    c = 7.47 * math.exp(-0.133 * sigma**0.55)
    b = 0.02526 * sigma**0.54
    e = 0.715 * math.exp(-3.59e-4 * sigma)
    phi_w = c * (u_ftmin**b) * beta_ratio**-e if u_ftmin > 0 else 0.0
    phi_s = 5.275 * beta**-0.3 * max(0.0, slope_fraction) ** 2

    ros_head_ftmin = ros_base_ftmin * (1.0 + phi_w + phi_s)

    return RothermelResult(
        ros_head_ms=ros_head_ftmin * MS_PER_FTMIN,
        ros_base_ms=ros_base_ftmin * MS_PER_FTMIN,
        length_to_breadth=length_to_breadth(wind_speed_ms * midflame_factor),
        reaction_intensity=i_r,
    )
