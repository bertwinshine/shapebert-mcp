"""Sheet-metal calculations - mirrors knowledge/domains/sheet-metal.md."""

from __future__ import annotations

import math

# Starting K-factors for air bending (US K = t_n / t). A test bend beats any table.
K_TABLE = [  # (max R/t, K)
    (0.5, 0.33),
    (1.0, 0.38),
    (2.0, 0.41),
    (3.0, 0.44),
    (5.0, 0.47),
    (float("inf"), 0.50),
]


def k_factor_estimate(r_mm: float, t_mm: float) -> float:
    rt = r_mm / t_mm
    for limit, k in K_TABLE:
        if rt <= limit:
            return k
    return 0.5


def bend(t_mm: float, r_mm: float, angle_deg: float = 90.0, k: float | None = None) -> dict:
    """Bend allowance, outside setback and bend deduction for one bend."""
    if k is None:
        k = k_factor_estimate(r_mm, t_mm)
        k_note = "K estimated from R/t table [RULE] - replace with a test-bend value"
    else:
        k_note = "K given"
    a = angle_deg
    ba = math.pi / 180.0 * a * (r_mm + k * t_mm)
    ossb = math.tan(math.radians(a / 2)) * (r_mm + t_mm)
    bd = 2 * ossb - ba
    return {
        "inputs": {"t_mm": t_mm, "R_mm": r_mm, "angle_deg": a, "K": round(k, 3)},
        "bend_allowance_mm": round(ba, 3),
        "outside_setback_mm": round(ossb, 3),
        "bend_deduction_mm": round(bd, 3),
        "neutral_radius_mm": round(r_mm + k * t_mm, 3),
        "notes": [k_note],
    }


def flat_length(
    outside_flanges_mm: list, t_mm: float, r_mm: float, angles_deg: list | None = None, k: float | None = None
) -> dict:
    """Flat blank length from OUTSIDE flange dimensions (n flanges, n-1 bends)."""
    n_bends = len(outside_flanges_mm) - 1
    angles = angles_deg or [90.0] * n_bends
    if len(angles) != n_bends:
        raise ValueError("need one angle per bend (flanges - 1)")
    bends = [bend(t_mm, r_mm, a, k) for a in angles]
    total_bd = sum(b["bend_deduction_mm"] for b in bends)
    flat = sum(outside_flanges_mm) - total_bd
    return {
        "inputs": {
            "outside_flanges_mm": outside_flanges_mm,
            "t_mm": t_mm,
            "R_mm": r_mm,
            "angles_deg": angles,
            "K": bends[0]["inputs"]["K"] if bends else k,
        },
        "flat_length_mm": round(flat, 3),
        "sum_bend_deduction_mm": round(total_bd, 3),
        "per_bend": bends,
    }


def k_from_test_bend(ba_mm: float, angle_deg: float, t_mm: float, r_mm: float) -> float:
    return (180.0 * ba_mm) / (math.pi * angle_deg * t_mm) - r_mm / t_mm


def press_brake(t_mm: float, length_m: float, rm_mpa: float, v_die_mm: float | None = None) -> dict:
    """Air-bending tonnage F[kN] ~= 1.42 * Rm * t^2 * L / V, V default 8*t."""
    v = v_die_mm if v_die_mm else 8 * t_mm
    f = 1.42 * rm_mpa * t_mm**2 * length_m / v
    return {
        "inputs": {"t_mm": t_mm, "length_m": length_m, "Rm_MPa": rm_mpa, "V_mm": v},
        "force_kN": round(f, 1),
        "force_tonnes": round(f / 9.81, 2),
        "inside_radius_air_mm": round(0.16 * v, 2),
        "min_flange_mm": round(0.77 * v, 2),
        "notes": [
            "V = 8*t default [RULE]; R_i ~0.16 V for mild steel (304 ~0.21 V)",
            "bottoming up to ~5x, coining 5-30x this force",
        ],
    }
