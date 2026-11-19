"""Boat sizing - mirrors knowledge/domains/boat-building-lsam.md (section 3)."""

from __future__ import annotations

import math

from ._checks import check

RHO = {"fresh": 1000.0, "salt": 1025.0}
G = 9.81
KNOT = 0.5144


def displacement(length_m: float, beam_m: float, draft_m: float, cb: float, water: str = "fresh") -> dict:
    rho = RHO[water]
    vol = length_m * beam_m * draft_m * cb
    return {
        "inputs": {"L_m": length_m, "B_m": beam_m, "T_m": draft_m, "Cb": cb, "water": water},
        "volume_m3": round(vol, 4),
        "displacement_kg": round(vol * rho, 1),
    }


def froude(speed_knots: float, length_m: float) -> dict:
    fn = speed_knots * KNOT / math.sqrt(G * length_m)
    regime = "displacement" if fn < 0.4 else "semi-displacement" if fn < 1.0 else "planing"
    hull_speed_kn = 1.34 * math.sqrt(length_m / 0.3048)
    return {"Fn": round(fn, 3), "regime": regime, "hull_speed_knots_displacement": round(hull_speed_kn, 2)}


def size_for_payload(
    payload_kg: float,
    light_mass_kg: float,
    cb: float = 0.45,
    l_over_b: float = 2.4,
    b_over_t: float = 4.0,
    water: str = "fresh",
    max_length_m: float | None = None,
    speed_knots: float | None = None,
) -> dict:
    """Solve L, B, T so that L*B*T*Cb*rho = light + payload.

    With L/B and B/T fixed:  V = L^3 * Cb / (LB^2 * BT)  ->  L = (V*LB^2*BT/Cb)^(1/3)."""
    rho = RHO[water]
    delta = payload_kg + light_mass_kg
    vol = delta / rho
    length = (vol * l_over_b**2 * b_over_t / cb) ** (1.0 / 3.0)
    beam = length / l_over_b
    draft = beam / b_over_t
    res = {
        "inputs": {
            "payload_kg": payload_kg,
            "light_mass_kg": light_mass_kg,
            "Cb": cb,
            "L/B": l_over_b,
            "B/T": b_over_t,
            "water": water,
        },
        "loaded_displacement_kg": round(delta, 1),
        "volume_m3": round(vol, 4),
        "waterline_length_m": round(length, 3),
        "waterline_beam_m": round(beam, 3),
        "draft_m": round(draft, 3),
        "notes": [
            "Waterline dimensions; add freeboard and overhangs for overall size.",
            "Verify with the hydrostatics tool on the real hull shape.",
        ],
    }
    checks = [
        check("Cb in typical range 0.35-0.85", 0.35 <= cb <= 0.85, f"Cb={cb:.2f}"),
        check("L/B 2-6 (stable small craft ~2-3.5)", 2 <= l_over_b <= 6, f"L/B={l_over_b:.2f}"),
    ]
    if max_length_m:
        checks.append(
            check("fits max length", length <= max_length_m, f"L={length:.2f} m vs max {max_length_m:.2f} m")
        )
    res["checks"] = checks
    if speed_knots:
        res["speed"] = froude(speed_knots, length)
    return res


def stability_box(beam_m: float, draft_m: float, kg_m: float, length_m: float = 1.0) -> dict:
    """Wall-sided box approximation: KB = T/2, BM = B^2/(12 T), GM = KB + BM - KG."""
    kb = draft_m / 2
    bm = beam_m**2 / (12 * draft_m)
    gm = kb + bm - kg_m
    return {
        "KB_m": round(kb, 4),
        "BM_m": round(bm, 4),
        "KM_m": round(kb + bm, 4),
        "KG_m": kg_m,
        "GM_m": round(gm, 4),
        "checks": [check("GM > 0 (initial stability)", gm > 0, f"GM={gm:.3f} m")],
        "notes": [
            "Box approximation only. Use hydrostatics on the real hull; "
            "ISO 12217 is the formal authority [CERT]."
        ],
    }
