"""Closed-form estimates to compare FEA with - mirrors knowledge/domains/fea-mechanics.md.

Units: mm, N, MPa, kg/m^3, W/(m K), K and °C. Each result names its formula, its
assumptions, how 3D FEA usually differs, the validity checks and the source.
"""

from __future__ import annotations

import math

from ._checks import check

KNOWLEDGE = "knowledge/domains/fea-mechanics.md"
MECHANICS = "Timoshenko & Gere, Mechanics of Materials, edition/section to be checked"
ELASTICITY = "Timoshenko & Goodier, Theory of Elasticity, edition to be checked"
STABILITY = "Timoshenko & Gere, Theory of Elastic Stability, 2nd ed., McGraw-Hill 1961"
VIBRATION = "Timoshenko, Young & Weaver, Vibration Problems in Engineering, 4th ed., Wiley 1974"
INCROPERA = "Incropera et al., Fundamentals of Heat and Mass Transfer, edition/section to be checked"
ROARK = "Roark's Formulas for Stress and Strain, edition/section to be checked"
# Shear coefficient of a rectangular section (topic 2 of the knowledge file).
K_RECTANGLE = 5 / 6
# Effective length factors K for an Euler column (topic 7).
END_CONDITIONS = {"fixed-free": 2.0, "pinned-pinned": 1.0, "fixed-pinned": 0.7, "fixed-fixed": 0.5}
BEAM_SUPPORTS = ("clamped-free", "pinned-pinned", "clamped-clamped", "free-free")
SLENDER_L_OVER_H = 10
THIN_WALL_R_OVER_T = 10


def _positive(**values: float) -> None:
    for name, value in values.items():
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"{name} must be a number > 0, not {value!r}")


def _reply(case, topic, results, formula, assumptions, fea_differs, source, checks=()) -> dict:
    return {
        "case": case,
        "results": {
            k: round(v, 6) + 0.0 if isinstance(v, float) else v for k, v in results.items()
        },  # no -0.0
        "formula": formula,
        "assumptions": assumptions,
        "fea_differs": fea_differs,
        "checks": list(checks),
        "source": f"{KNOWLEDGE}, topic {topic}; {source}",
    }


def axial_bar(force_n: float, area_mm2: float, length_mm: float, E_mpa: float) -> dict:
    """Prismatic bar under an axial load through the centroid."""
    _positive(force_n=force_n, area_mm2=area_mm2, length_mm=length_mm, E_mpa=E_mpa)
    return _reply(
        "axial_bar",
        1,
        {"stress_mpa": force_n / area_mm2, "elongation_mm": force_n * length_mm / (E_mpa * area_mm2)},
        "s = F/A, d = F L / (E A)",
        ["linear elastic, small strain", "prismatic bar", "load through the centroid"],
        "Matches closely beyond the Saint-Venant zone, about one width from the load and the "
        "supports; a support that stops lateral contraction raises the stress next to it.",
        MECHANICS + " (axially loaded members)",
    )


def _rectangle(width_mm, height_mm):
    """Area, second moment about the axis across the height, and the extreme fibre distance."""
    return width_mm * height_mm, width_mm * height_mm**3 / 12, height_mm / 2


def cantilever(
    force_n: float, length_mm: float, width_mm: float, height_mm: float, E_mpa: float, nu: float = 0.3
) -> dict:
    """Rectangular cantilever with an end load across the height, with the shear term."""
    _positive(force_n=force_n, length_mm=length_mm, width_mm=width_mm, height_mm=height_mm, E_mpa=E_mpa)
    if not 0 <= nu < 0.5:
        raise ValueError(f"nu must be in [0, 0.5), not {nu!r}")
    area, inertia, c = _rectangle(width_mm, height_mm)
    shear_modulus = E_mpa / (2 * (1 + nu))
    bending = force_n * length_mm**3 / (3 * E_mpa * inertia)
    shear = force_n * length_mm / (K_RECTANGLE * shear_modulus * area)
    slenderness = length_mm / height_mm
    return _reply(
        "cantilever",
        2,
        {
            "tip_deflection_bending_mm": bending,
            "tip_deflection_shear_mm": shear,
            "tip_deflection_mm": bending + shear,
            "root_bending_stress_mpa": force_n * length_mm * c / inertia,
            "max_shear_stress_mpa": 1.5 * force_n / area,
            "length_over_height": slenderness,
        },
        "d = F L^3 / (3 E I) + F L / (k G A), k = 5/6; s = M c / I with M = F L",
        ["plane sections stay plane", "small deflection", "linear elastic", "clamp fully rigid"],
        "3D FEA comes out slightly softer than Euler-Bernoulli (a few tenths of a percent at "
        "L/h = 10). The root stress in FEA is singular at the clamped edges: compare it a "
        "little away from the support.",
        MECHANICS + " (beam deflection, shear deflection)",
        [
            check(
                "slender beam",
                slenderness >= SLENDER_L_OVER_H,
                f"L/h = {slenderness:.1f}; beam theory needs about {SLENDER_L_OVER_H} or more",
            )
        ],
    )


def euler_column(
    length_mm: float,
    E_mpa: float,
    width_mm: float,
    height_mm: float,
    end_condition: str = "fixed-free",
    nu: float = 0.3,
    yield_mpa: float | None = None,
) -> dict:
    """Elastic buckling load of a rectangular column; end_condition sets K."""
    _positive(length_mm=length_mm, E_mpa=E_mpa, width_mm=width_mm, height_mm=height_mm)
    if end_condition not in END_CONDITIONS:
        raise ValueError(f"end_condition must be one of {list(END_CONDITIONS)}, not {end_condition!r}")
    k_factor = END_CONDITIONS[end_condition]
    thin, thick = sorted((width_mm, height_mm))
    area, inertia = thin * thick, thick * thin**3 / 12
    effective = k_factor * length_mm
    euler = math.pi**2 * E_mpa * inertia / effective**2
    shear_stiffness = K_RECTANGLE * E_mpa / (2 * (1 + nu)) * area
    slenderness = effective / math.sqrt(inertia / area)
    results = {
        "K": k_factor,
        "critical_load_n": euler,
        "critical_load_with_shear_n": euler / (1 + euler / shear_stiffness),
        "critical_stress_mpa": euler / area,
        "slenderness_KL_over_r": slenderness,
    }
    checks = []
    if yield_mpa is not None:
        _positive(yield_mpa=yield_mpa)
        limit = math.sqrt(2 * math.pi**2 * E_mpa / yield_mpa)
        checks.append(
            check(
                "elastic (Euler) range",
                slenderness >= limit,
                f"KL/r = {slenderness:.0f}; below {limit:.0f} the column yields first (Johnson parabola)",
            )
        )
    return _reply(
        "euler_column",
        7,
        results,
        "P = pi^2 E I / (K L)^2, I about the weaker axis; with shear (Engesser) P / (1 + P / (k G A))",
        ["perfectly straight, load through the centroid", "linear elastic", f"ideal {end_condition} ends"],
        "Linear-buckling FEA lands near the Engesser value, slightly below Euler. Real columns "
        "with imperfections buckle much lower than either.",
        STABILITY + ", Section 2.1 (Euler), Section 2.17 (Engesser shear correction); K for other "
        "end conditions: section to be checked",
        checks,
    )


def thin_cylinder(pressure_mpa: float, mean_radius_mm: float, thickness_mm: float) -> dict:
    """Thin-walled closed cylinder under internal pressure."""
    _positive(pressure_mpa=pressure_mpa, mean_radius_mm=mean_radius_mm, thickness_mm=thickness_mm)
    ratio = mean_radius_mm / thickness_mm
    return _reply(
        "thin_cylinder",
        4,
        {
            "hoop_stress_mpa": pressure_mpa * mean_radius_mm / thickness_mm,
            "axial_stress_mpa": pressure_mpa * mean_radius_mm / (2 * thickness_mm),
            "radius_over_thickness": ratio,
        },
        "s_hoop = p r / t, s_axial = p r / (2 t)",
        ["membrane stress, uniform through the wall", "closed ends", "away from the end caps"],
        "FEA shows bending at the end caps and nozzles that the membrane formula leaves out; "
        "compare in the middle of the shell.",
        ROARK + " (thin-walled pressure vessels)",
        [
            check(
                "thin wall",
                ratio >= THIN_WALL_R_OVER_T,
                f"r/t = {ratio:.1f}; below about {THIN_WALL_R_OVER_T} use thick_cylinder (Lame)",
            )
        ],
    )


def thick_cylinder(
    inner_radius_mm: float, outer_radius_mm: float, inner_pressure_mpa: float, outer_pressure_mpa: float = 0.0
) -> dict:
    """Lame solution for a thick-walled cylinder; axial stress for closed ends."""
    _positive(inner_radius_mm=inner_radius_mm, outer_radius_mm=outer_radius_mm)
    if outer_radius_mm <= inner_radius_mm:
        raise ValueError("outer_radius_mm must be larger than inner_radius_mm")
    if inner_pressure_mpa < 0 or outer_pressure_mpa < 0:
        raise ValueError("pressures must be >= 0")
    a2, b2 = inner_radius_mm**2, outer_radius_mm**2
    big_a = (inner_pressure_mpa * a2 - outer_pressure_mpa * b2) / (b2 - a2)
    big_b = (inner_pressure_mpa - outer_pressure_mpa) * a2 * b2 / (b2 - a2)
    wall = outer_radius_mm - inner_radius_mm
    return _reply(
        "thick_cylinder",
        5,
        {
            "hoop_stress_inner_mpa": big_a + big_b / a2,
            "hoop_stress_outer_mpa": big_a + big_b / b2,
            "radial_stress_inner_mpa": big_a - big_b / a2,
            "radial_stress_outer_mpa": big_a - big_b / b2,
            "axial_stress_closed_ends_mpa": big_a,
            "thin_wall_hoop_mpa": inner_pressure_mpa * (inner_radius_mm + outer_radius_mm) / 2 / wall,
        },
        "s_theta = A + B/r^2, s_r = A - B/r^2, A = (pi a^2 - po b^2)/(b^2 - a^2), "
        "B = (pi - po) a^2 b^2 / (b^2 - a^2)",
        ["long cylinder, away from the ends", "linear elastic", "axisymmetric load"],
        "Matches closely in the middle of a long cylinder; end caps and nozzles add local bending.",
        ELASTICITY + ", Section 28",
    )


def kirsch_hole(
    remote_stress_mpa: float, hole_diameter_mm: float | None = None, plate_width_mm: float | None = None
) -> dict:
    """Peak stress at a circular hole in a plate under uniaxial tension."""
    _positive(remote_stress_mpa=remote_stress_mpa)
    results = {
        "Kt": 3.0,
        "peak_stress_mpa": 3 * remote_stress_mpa,
        "stress_at_hole_along_load_mpa": -remote_stress_mpa,
    }
    if hole_diameter_mm is not None and plate_width_mm is not None:
        _positive(hole_diameter_mm=hole_diameter_mm, plate_width_mm=plate_width_mm)
        if hole_diameter_mm >= plate_width_mm:
            raise ValueError("hole_diameter_mm must be smaller than plate_width_mm")
        results["d_over_w"] = hole_diameter_mm / plate_width_mm
        results["net_section_stress_mpa"] = (
            remote_stress_mpa * plate_width_mm / (plate_width_mm - hole_diameter_mm)
        )
    return _reply(
        "kirsch_hole",
        6,
        results,
        "Kt = 3, s_peak = 3 s at the hole edge across the load; -s where the load axis meets the hole",
        ["infinite plate", "uniaxial remote tension", "linear elastic, plane stress"],
        "A finite plate raises Kt above 3 as d/W grows; take finite-width and other notch "
        "factors from the charts. FEA needs several elements around the hole to reach the peak.",
        ELASTICITY + ", Section 35 (Kirsch 1898); finite width and other notches: " + ROARK,
    )


def _frequency_root(supports: str, mode: int) -> float:
    """beta_n L for a uniform beam with the given end supports."""
    if supports == "pinned-pinned":
        return mode * math.pi
    if supports == "clamped-free":
        f, lo, hi = (lambda x: math.cos(x) * math.cosh(x) + 1), (mode - 1) * math.pi, mode * math.pi
    else:  # clamped-clamped and free-free share cos cosh = 1 (free-free without rigid modes)
        f, lo, hi = (lambda x: math.cos(x) * math.cosh(x) - 1), mode * math.pi, (mode + 1) * math.pi
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(lo) * f(mid) > 0 else (lo, mid)
    return (lo + hi) / 2


def beam_frequency(
    length_mm: float,
    width_mm: float,
    height_mm: float,
    E_mpa: float,
    density_kg_m3: float,
    supports: str = "clamped-free",
    mode: int = 1,
) -> dict:
    """Bending natural frequency of a rectangular beam, vibrating across its height."""
    _positive(
        length_mm=length_mm, width_mm=width_mm, height_mm=height_mm, E_mpa=E_mpa, density_kg_m3=density_kg_m3
    )
    if supports not in BEAM_SUPPORTS:
        raise ValueError(f"supports must be one of {list(BEAM_SUPPORTS)}, not {supports!r}")
    if not isinstance(mode, int) or not 1 <= mode <= 10:
        raise ValueError("mode must be a whole number from 1 to 10")
    area, inertia, _ = _rectangle(width_mm, height_mm)
    root = _frequency_root(supports, mode)
    rho = density_kg_m3 * 1e-12  # t/mm^3 keeps N, mm, MPa consistent
    frequency = root**2 / (2 * math.pi * length_mm**2) * math.sqrt(E_mpa * inertia / (rho * area))
    slenderness = length_mm / height_mm
    return _reply(
        "beam_frequency",
        8,
        {"beta_L": root, "frequency_hz": frequency, "length_over_height": slenderness},
        "f_n = (beta_n L)^2 / (2 pi L^2) sqrt(E I / (rho A))",
        ["Euler-Bernoulli beam", "uniform section", "ideal supports", "no added mass"],
        "3D FEA comes out slightly lower: shear and rotary inertia, more so for higher modes "
        "and short beams. Real supports are softer, so real frequencies are lower still.",
        VIBRATION + ", Section 5.3 (clamped-free; other supports: section to be checked)",
        [
            check(
                "slender beam",
                slenderness >= SLENDER_L_OVER_H,
                f"L/h = {slenderness:.1f}; beam theory needs about {SLENDER_L_OVER_H} or more",
            )
        ],
    )


def plane_wall(k_w_mk: float, area_mm2: float, thickness_mm: float, t_hot_c: float, t_cold_c: float) -> dict:
    """Steady 1D conduction through a wall (or a bar with insulated sides)."""
    _positive(k_w_mk=k_w_mk, area_mm2=area_mm2, thickness_mm=thickness_mm)
    if t_hot_c <= t_cold_c:
        raise ValueError("t_hot_c must be above t_cold_c")
    area_m2, length_m = area_mm2 * 1e-6, thickness_mm * 1e-3
    return _reply(
        "plane_wall",
        9,
        {
            "heat_flow_w": k_w_mk * area_m2 * (t_hot_c - t_cold_c) / length_m,
            "thermal_resistance_k_w": length_m / (k_w_mk * area_m2),
            "gradient_k_per_mm": (t_hot_c - t_cold_c) / thickness_mm,
        },
        "q = k A (T_hot - T_cold) / L, R = L / (k A); T linear through the wall",
        ["steady state", "constant k", "1D: other faces insulated", "fixed face temperatures"],
        "Exact for a bar with insulated sides; FEA reproduces it to solver precision. With "
        "convection, h is an input the user has to give.",
        INCROPERA + " (plane wall, Fourier's law)",
    )


def thermal_expansion(
    alpha_1_k: float, delta_t_k: float, length_mm: float, E_mpa: float | None = None
) -> dict:
    """Free elongation of a uniformly heated bar, and the stress if fully restrained."""
    _positive(alpha_1_k=alpha_1_k, length_mm=length_mm)
    if not isinstance(delta_t_k, (int, float)) or isinstance(delta_t_k, bool) or not math.isfinite(delta_t_k):
        raise ValueError(f"delta_t_k must be a number, not {delta_t_k!r}")
    results = {"strain": alpha_1_k * delta_t_k, "free_elongation_mm": alpha_1_k * delta_t_k * length_mm}
    if E_mpa is not None:
        _positive(E_mpa=E_mpa)
        results["fully_restrained_stress_mpa"] = -E_mpa * alpha_1_k * delta_t_k
    return _reply(
        "thermal_expansion",
        10,
        results,
        "e = alpha dT, d = alpha dT L; fully restrained (uniaxial) s = -E alpha dT",
        ["uniform temperature change", "constant alpha", "linear elastic"],
        "A free (statically determinate) part expands without stress in FEA too; fully fixed "
        "faces also block the sideways expansion, which adds local peaks at those faces.",
        ELASTICITY + " (thermal stress chapter), section to be checked",
    )
