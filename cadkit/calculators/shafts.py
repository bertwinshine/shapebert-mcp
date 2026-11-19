"""Shafts, keys and rolling bearings - mirrors knowledge/domains/shafts-bearings.md."""

from __future__ import annotations

import math

from ._checks import check

# DIN 6885-1 parallel keys: (shaft over, up to, b, h, t1 shaft groove, t2 hub groove)
DIN6885 = [
    (6, 8, 2, 2, 1.2, 1.0),
    (8, 10, 3, 3, 1.8, 1.4),
    (10, 12, 4, 4, 2.5, 1.8),
    (12, 17, 5, 5, 3.0, 2.3),
    (17, 22, 6, 6, 3.5, 2.8),
    (22, 30, 8, 7, 4.0, 3.3),
    (30, 38, 10, 8, 5.0, 3.3),
    (38, 44, 12, 8, 5.0, 3.3),
    (44, 50, 14, 9, 5.5, 3.8),
    (50, 58, 16, 10, 6.0, 4.3),
    (58, 65, 18, 11, 7.0, 4.4),
    (65, 75, 20, 12, 7.5, 4.9),
    (75, 85, 22, 14, 9.0, 5.4),
    (85, 95, 25, 14, 9.0, 5.4),
    (95, 110, 28, 16, 10.0, 6.4),
]
PREFERRED_SHAFT = [
    6,
    8,
    10,
    12,
    14,
    15,
    16,
    17,
    18,
    20,
    22,
    25,
    28,
    30,
    32,
    35,
    38,
    40,
    42,
    45,
    48,
    50,
    55,
    60,
    65,
    70,
    75,
    80,
    85,
    90,
    95,
    100,
    110,
    120,
]


def shaft_diameter(
    torque_nm: float,
    bending_nm: float = 0.0,
    tau_allow_mpa: float | None = None,
    material_yield_mpa: float | None = None,
    safety: float = 2.0,
    keyway: bool = True,
) -> dict:
    """First-pass diameter from combined bending + torsion (max shear stress theory).

    d = ( 16 / (pi * tau_allow) * sqrt(M^2 + T^2) )^(1/3)
    tau_allow defaults to 0.5 * f_y / safety (Tresca); a keyway knocks ~25 % off
    the allowable stress [RULE]."""
    if tau_allow_mpa is None:
        if material_yield_mpa is None:
            raise ValueError("give tau_allow_mpa or material_yield_mpa")
        tau_allow_mpa = 0.5 * material_yield_mpa / safety
    tau = tau_allow_mpa * (0.75 if keyway else 1.0)
    t_eq = math.sqrt(bending_nm**2 + torque_nm**2) * 1000.0  # N.mm
    d = (16.0 * t_eq / (math.pi * tau)) ** (1.0 / 3.0)
    pick = next((x for x in PREFERRED_SHAFT if x >= d), math.ceil(d))
    return {
        "inputs": {
            "torque_Nm": torque_nm,
            "bending_Nm": bending_nm,
            "tau_allow_MPa": round(tau_allow_mpa, 1),
            "keyway": keyway,
        },
        "d_min_mm": round(d, 2),
        "d_chosen_mm": pick,
        "notes": [
            "Static first pass. Fatigue (DIN 743 / Goodman with notch factors) "
            "usually governs rotating shafts [CERT]."
        ],
    }


def key(
    shaft_d_mm: float,
    torque_nm: float | None = None,
    hub_length_mm: float | None = None,
    p_allow_mpa: float = 100.0,
) -> dict:
    """Select a DIN 6885 parallel key and check surface pressure.

    p = 2T / (d * (h - t1) * l_eff), l_eff = l - b (rounded ends, form A).
    p_allow ~100 MPa steel hub, ~50-60 MPa cast iron / aluminium [RULE]."""
    row = next((r for r in DIN6885 if r[0] < shaft_d_mm <= r[1]), None)
    if row is None:
        raise ValueError("shaft diameter outside 6-110 mm table")
    _, _, b, h, t1, t2 = row
    out = {
        "shaft_d_mm": shaft_d_mm,
        "key_b_mm": b,
        "key_h_mm": h,
        "shaft_groove_t1_mm": t1,
        "hub_groove_t2_mm": t2,
    }
    if torque_nm and hub_length_mm:
        l_eff = hub_length_mm - b
        p = 2 * torque_nm * 1000 / (shaft_d_mm * (h - t1) * l_eff)
        out.update(
            {
                "l_eff_mm": l_eff,
                "surface_pressure_MPa": round(p, 1),
                "checks": [
                    check("key pressure <= p_allow", p <= p_allow_mpa, f"p={p:.1f} vs {p_allow_mpa:.0f} MPa")
                ],
            }
        )
        if p > p_allow_mpa:
            out["min_hub_length_mm"] = round(
                2 * torque_nm * 1000 / (shaft_d_mm * (h - t1) * p_allow_mpa) + b, 1
            )
    return out


def bearing_life(
    c_kn: float,
    p_kn: float,
    rpm: float,
    ball: bool = True,
    required_hours: float | None = None,
    reliability_a1: float = 1.0,
) -> dict:
    """Basic rating life ISO 281: L10 = (C/P)^p [10^6 rev], p = 3 ball, 10/3 roller."""
    p_exp = 3.0 if ball else 10.0 / 3.0
    l10 = reliability_a1 * (c_kn / p_kn) ** p_exp
    l10h = l10 * 1e6 / (60 * rpm)
    out = {
        "inputs": {
            "C_kN": c_kn,
            "P_kN": p_kn,
            "rpm": rpm,
            "type": "ball" if ball else "roller",
            "a1": reliability_a1,
        },
        "L10_million_rev": round(l10, 2),
        "L10h_hours": round(l10h, 0),
    }
    if required_hours:
        c_req = p_kn * (required_hours * 60 * rpm / 1e6 / reliability_a1) ** (1 / p_exp)
        out["C_required_kN"] = round(c_req, 2)
        out["checks"] = [
            check("L10h >= required", l10h >= required_hours, f"{l10h:.0f} h vs {required_hours:.0f} h")
        ]
    out["notes"] = [
        "Take C from the bearing maker's catalogue. Typical targets: hand tools "
        "~1-5 kh, 8 h/day machines 20-30 kh, gearboxes 20-50 kh [RULE]."
    ]
    return out


def equivalent_load(
    fr_kn: float, fa_kn: float = 0.0, x: float = 0.56, y: float = 1.5, e: float = 0.3
) -> dict:
    """Deep-groove ball bearing P = X Fr + Y Fa if Fa/Fr > e else Fr (catalogue X, Y, e)."""
    p = x * fr_kn + y * fa_kn if fr_kn > 0 and fa_kn / fr_kn > e else fr_kn
    return {
        "P_kN": round(p, 3),
        "Fa/Fr": round(fa_kn / fr_kn, 3) if fr_kn else None,
        "notes": ["X, Y, e depend on f0*Fa/C0 - read them from the catalogue table."],
    }
