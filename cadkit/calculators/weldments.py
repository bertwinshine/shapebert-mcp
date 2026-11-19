"""Fillet weld and profile calculations - mirrors knowledge/domains/weldments.md."""

from __future__ import annotations

import math

from ._checks import check

STEEL = {  # grade: (f_y MPa, f_u MPa, beta_w)   EN 1993-1-8 / EN 10025
    # S355 uses f_u = 470 MPa (conservative low end, same as weldments.md);
    # EN 1993-1-1 allows 510 MPa for t <= 40 mm.
    "S235": (235, 360, 0.80),
    "S275": (275, 430, 0.85),
    "S355": (355, 470, 0.90),
    "S420": (420, 520, 1.00),
    "S460": (460, 540, 1.00),
}
GAMMA_M2 = 1.25
STEEL_DENSITY = 7850.0  # kg/m^3


def leg_to_throat(z_mm: float) -> float:
    return z_mm / math.sqrt(2)


def throat_to_leg(a_mm: float) -> float:
    return a_mm * math.sqrt(2)


def fillet_weld(
    a_mm: float,
    length_mm: float,
    grade: str = "S355",
    force_kn: float | None = None,
    plate_t_mm: float | None = None,
    end_craters: bool = True,
) -> dict:
    """Simplified directional-free method (EN 1993-1-8 4.5.3.3).

    f_vw,d = (f_u / sqrt(3)) / (beta_w * gamma_M2);  F_w,Rd = f_vw,d * a * l_eff."""
    f_y, f_u, beta = STEEL[grade]
    fvwd = (f_u / math.sqrt(3)) / (beta * GAMMA_M2)
    l_eff = length_mm - (2 * a_mm if end_craters else 0)
    cap_kn = fvwd * a_mm * max(l_eff, 0) / 1000.0
    res = {
        "inputs": {
            "a_mm": a_mm,
            "leg_z_mm": round(throat_to_leg(a_mm), 2),
            "length_mm": length_mm,
            "grade": grade,
        },
        "f_vw_d_MPa": round(fvwd, 1),
        "l_eff_mm": round(l_eff, 1),
        "capacity_kN": round(cap_kn, 2),
        "capacity_per_mm_kN": round(fvwd * a_mm / 1000.0, 3),
        "weld_metal_volume_cm3": round(0.5 * throat_to_leg(a_mm) ** 2 * length_mm / 1000.0, 2),
    }
    checks = [
        check("a >= 3 mm", a_mm >= 3, f"a={a_mm:.1f}"),
        check(
            "l_eff >= max(30 mm, 6a)",
            l_eff >= max(30, 6 * a_mm),
            f"l_eff={l_eff:.0f}, need {max(30, 6 * a_mm):.0f}",
        ),
    ]
    if plate_t_mm:
        checks.append(
            check(
                "a <= 0.7 * thinner plate",
                a_mm <= 0.7 * plate_t_mm,
                f"a={a_mm:.1f} vs 0.7t={0.7 * plate_t_mm:.1f} [RULE]",
            )
        )
    if force_kn is not None:
        u = force_kn / cap_kn if cap_kn > 0 else float("inf")
        res["utilisation"] = round(u, 3)
        checks.append(check("utilisation <= 1.0", u <= 1.0, f"F={force_kn:.1f} kN / F_Rd={cap_kn:.1f} kN"))
    res["checks"] = checks
    res["notes"] = [
        "Static, conservative simplified method. Structures need a certified check incl. fatigue [CERT]."
    ]
    return res


def required_throat(force_kn: float, length_mm: float, grade: str = "S355") -> dict:
    f_y, f_u, beta = STEEL[grade]
    fvwd = (f_u / math.sqrt(3)) / (beta * GAMMA_M2)
    a = 0.0
    for _ in range(50):  # l_eff depends on a (end craters)
        l_eff = length_mm - 2 * a
        a_new = force_kn * 1000.0 / (fvwd * l_eff)
        if abs(a_new - a) < 1e-6:
            break
        a = a_new
    a_round = max(3, math.ceil(a))
    return {
        "a_required_mm": round(a, 2),
        "a_chosen_mm": a_round,
        "leg_z_mm": round(throat_to_leg(a_round), 1),
        "grade": grade,
    }


def tube_mass(
    outer_mm: float, wall_mm: float, length_mm: float, shape: str = "SHS", outer_b_mm: float | None = None
) -> dict:
    """Mass of SHS/RHS (sharp-corner approximation) or CHS."""
    if shape.upper() == "CHS":
        area = math.pi / 4 * (outer_mm**2 - (outer_mm - 2 * wall_mm) ** 2)
    else:
        b = outer_b_mm or outer_mm
        area = outer_mm * b - (outer_mm - 2 * wall_mm) * (b - 2 * wall_mm)
    mass = area * 1e-6 * length_mm * 1e-3 * STEEL_DENSITY
    return {
        "section_area_mm2": round(area, 1),
        "mass_per_m_kg": round(area * 1e-6 * STEEL_DENSITY, 3),
        "mass_kg": round(mass, 3),
        "notes": ["corner radii ignored -> ~2-4% heavier than EN 10219 tables"]
        if shape.upper() != "CHS"
        else [],
    }
