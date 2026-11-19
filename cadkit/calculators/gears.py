"""Gear calculations - mirrors knowledge/domains/gears-power-transmission.md."""

from __future__ import annotations

import math

from ._checks import check

ISO54_SERIES_I = [1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 12, 16, 20, 25, 32, 40, 50]
ISO54_SERIES_II = [1.125, 1.375, 1.75, 2.25, 2.75, 3.5, 4.5, 5.5, 7, 9, 11, 14, 18, 22, 28, 36, 45]


def torque_from_power(power_kw: float, rpm: float) -> float:
    """T [N.m] = 9550 * P [kW] / n [rpm]"""
    return 9550.0 * power_kw / rpm


def nearest_module(m: float, series_ii: bool = False) -> float:
    pool = ISO54_SERIES_I + (ISO54_SERIES_II if series_ii else [])
    bigger = [x for x in sorted(pool) if x >= m - 1e-9]
    return bigger[0] if bigger else max(pool)


def z_min(alpha_deg: float = 20.0) -> float:
    """Minimum teeth without undercut: 2 / sin^2(alpha)."""
    return 2.0 / math.sin(math.radians(alpha_deg)) ** 2


def contact_ratio(
    m: float, z1: int, z2: int, alpha_deg: float = 20.0, x1: float = 0.0, x2: float = 0.0
) -> float:
    """Transverse contact ratio for external spur gears (standard centre distance
    when x1 = x2 = 0; with shift the operating centre distance is approximated as
    standard + (x1+x2)*m, adequate for concept checks)."""
    a = math.radians(alpha_deg)
    ra1 = m * (z1 + 2 + 2 * x1) / 2
    ra2 = m * (z2 + 2 + 2 * x2) / 2
    rb1 = m * z1 * math.cos(a) / 2
    rb2 = m * z2 * math.cos(a) / 2
    aw = m * (z1 + z2) / 2 + (x1 + x2) * m
    alpha_w = math.acos(min(1.0, (rb1 + rb2) / aw))
    path = math.sqrt(ra1**2 - rb1**2) + math.sqrt(ra2**2 - rb2**2) - aw * math.sin(alpha_w)
    return path / (math.pi * m * math.cos(a))


def lewis_y(z: int) -> float:
    """Lewis form factor Y (20 deg full depth), interpolated from the classic table."""
    table = [
        (12, 0.245),
        (13, 0.261),
        (14, 0.277),
        (15, 0.290),
        (16, 0.296),
        (17, 0.303),
        (18, 0.309),
        (19, 0.314),
        (20, 0.322),
        (21, 0.328),
        (22, 0.331),
        (24, 0.337),
        (26, 0.346),
        (28, 0.353),
        (30, 0.359),
        (34, 0.371),
        (38, 0.384),
        (43, 0.397),
        (50, 0.409),
        (60, 0.422),
        (75, 0.435),
        (100, 0.447),
        (150, 0.460),
        (300, 0.472),
        (400, 0.480),
    ]
    if z <= table[0][0]:
        return table[0][1]
    if z >= table[-1][0]:
        return table[-1][1]
    for (z0, y0), (z1, y1) in zip(table, table[1:], strict=False):
        if z0 <= z <= z1:
            return y0 + (y1 - y0) * (z - z0) / (z1 - z0)
    return 0.3


def _gear_geometry(m, z, x, alpha_rad):
    d = m * z
    return {
        "z": z,
        "d_mm": round(d, 3),
        "d_tip_mm": round(m * (z + 2 + 2 * x), 3),
        "d_root_mm": round(m * (z - 2.5 + 2 * x), 3),
        "d_base_mm": round(d * math.cos(alpha_rad), 3),
    }


def _geometry_checks(m, z1, z2, b, alpha_deg, x1, eps):
    zmin = z_min(alpha_deg)
    # The (17 - z) / 17 shift rule only holds for a 20 degree pressure angle.
    x_needed = max(0.0, (17 - z1) / 17) if abs(alpha_deg - 20) < 1e-6 else None
    no_undercut = z1 >= zmin - 3 or (x_needed is not None and x1 >= x_needed)
    module_note = "standard" if m in ISO54_SERIES_I else "non-preferred/special tool"
    return [
        check(
            "pinion undercut",
            no_undercut,
            f"z1={z1}, z_min={zmin:.1f} (14 ok with slight undercut at 20deg); x_min~{x_needed or 0:.2f}",
        ),
        check("contact ratio >= 1.2", eps >= 1.2, f"eps_alpha={eps:.2f} (aim 1.4+)"),
        check("ISO 54 module", m in ISO54_SERIES_I or m in ISO54_SERIES_II, f"m={m:g} {module_note}"),
        check("face width 8-16*m", 8 * m <= b <= 16 * m, f"b/m={b / m:.1f}"),
        check("ratio per spur stage <= 6", z2 / z1 <= 6, f"i={z2 / z1:.2f}"),
    ]


def _lewis(m, z1, z2, b, torque_nm, rpm, sigma_allow_mpa):
    """Lewis bending stress for pinion and wheel, plus the pass/fail checks."""
    d1 = m * z1
    ft = 2000.0 * torque_nm / d1
    load = {"torque_pinion_nm": round(torque_nm, 3), "Ft_N": round(ft, 1)}
    kv = 1.0
    if rpm:
        v = math.pi * d1 * rpm / 60000.0
        kv = (6.1 + v) / 6.1  # Barth factor for cut/milled teeth
        load["pitch_line_velocity_m_s"] = round(v, 3)
        load["Kv_barth"] = round(kv, 3)

    checks = []
    for tag, z in (("pinion", z1), ("wheel", z2)):
        y = lewis_y(z)
        sigma = ft * kv / (b * m * y)
        load[f"lewis_{tag}"] = {"Y": round(y, 3), "sigma_F_MPa": round(sigma, 1)}
        if sigma_allow_mpa:
            sf = sigma_allow_mpa / sigma
            load[f"lewis_{tag}"]["safety_factor"] = round(sf, 2)
            detail = f"sigma={sigma:.1f} MPa vs allow {sigma_allow_mpa:.0f} -> SF {sf:.2f}"
            checks.append(check(f"Lewis bending {tag} (SF>=1.4)", sf >= 1.4, detail))
    return load, checks


def spur_pair(
    m: float,
    z1: int,
    z2: int | None = None,
    ratio: float | None = None,
    alpha_deg: float = 20.0,
    face_width_mm: float | None = None,
    power_kw: float | None = None,
    torque_nm: float | None = None,
    rpm: float | None = None,
    sigma_allow_mpa: float | None = None,
    x1: float = 0.0,
    x2: float = 0.0,
) -> dict:
    """Geometry and checks for a spur pair. Give z2 or ratio; add a load for the Lewis check."""
    if z2 is None:
        if ratio is None:
            raise ValueError("give z2 or ratio")
        z2 = round(z1 * ratio)
    z1, z2 = int(z1), int(z2)
    b = face_width_mm or 10 * m
    eps = contact_ratio(m, z1, z2, alpha_deg, x1, x2)
    alpha_rad = math.radians(alpha_deg)

    result = {
        "inputs": {
            "m": m,
            "z1": z1,
            "z2": z2,
            "alpha_deg": alpha_deg,
            "x1": x1,
            "x2": x2,
            "face_width_mm": b,
        },
        "notes": [] if face_width_mm else ["face width b = 10*m default [RULE] (range 8-16*m)"],
        "geometry": {
            "pinion": _gear_geometry(m, z1, x1, alpha_rad),
            "wheel": _gear_geometry(m, z2, x2, alpha_rad),
        },
        "ratio": round(z2 / z1, 4),
        "centre_distance_mm": round(m * (z1 + z2) / 2 + (x1 + x2) * m, 3),
        "circular_pitch_mm": round(math.pi * m, 4),
        "whole_depth_mm": round(2.25 * m, 3),
        "contact_ratio": round(eps, 3),
    }
    checks = _geometry_checks(m, z1, z2, b, alpha_deg, x1, eps)

    if torque_nm is None and power_kw is not None and rpm:
        torque_nm = torque_from_power(power_kw, rpm)
    if torque_nm is not None:
        result["load"], lewis_checks = _lewis(m, z1, z2, b, torque_nm, rpm, sigma_allow_mpa)
        checks += lewis_checks
        result["notes"].append("Lewis is a concept-level check; ISO 6336 rating is [CERT].")
    result["checks"] = checks
    return result


def planetary(z_sun: int, z_planet: int | None = None, z_ring: int | None = None, n_planets: int = 3) -> dict:
    """Ring fixed, sun input, carrier output. Give z_planet or z_ring."""
    if z_ring is None and z_planet is None:
        raise ValueError("give z_planet or z_ring")
    if z_ring is None:
        z_ring = z_sun + 2 * z_planet
    if z_planet is None:
        z_planet = (z_ring - z_sun) / 2 if (z_ring - z_sun) % 2 else (z_ring - z_sun) // 2
    ratio = 1 + z_ring / z_sun
    coaxial = z_ring == z_sun + 2 * z_planet
    assembly = (z_sun + z_ring) % n_planets == 0
    adjacency = (z_planet + 2) < (z_sun + z_planet) * math.sin(math.pi / n_planets)
    return {
        "inputs": {"z_sun": z_sun, "z_planet": z_planet, "z_ring": z_ring, "n_planets": n_planets},
        "ratio_sun_to_carrier": round(ratio, 4),
        "checks": [
            check("coaxial z_R = z_S + 2 z_P", coaxial, f"{z_ring} = {z_sun} + 2*{z_planet}"),
            check(
                "equal-spacing assembly (z_S+z_R)/N integer",
                assembly,
                f"({z_sun}+{z_ring})/{n_planets} = {(z_sun + z_ring) / n_planets:.3f}",
            ),
            check(
                "adjacency (planets don't touch)",
                adjacency,
                f"z_P+2={z_planet + 2:.1f} < (z_S+z_P) sin(pi/N)={(z_sun + z_planet) * math.sin(math.pi / n_planets):.2f}",
            ),
            check("single-stage ratio 3-10", 3 <= ratio <= 10, f"i={ratio:.2f}"),
            check(
                "sun & planet z >= 14 (undercut, 20deg, x=0)",
                min(z_sun, z_planet) >= 14,
                f"min z = {min(z_sun, z_planet)}; below 17 accepts slight undercut, below 14 needs profile shift",
            ),
            check(
                "ring-planet tooth difference >= 10",
                z_ring - z_planet >= 10,
                f"z_R - z_P = {z_ring - z_planet} [RULE]",
            ),
        ],
    }


def solve_planetary(
    target_ratio: float, n_planets: int = 3, z_sun_min: int = 12, z_sun_max: int = 60, tolerance: float = 0.02
) -> list:
    """Search tooth counts that meet all planetary conditions near a target ratio."""
    hits = []
    for zs in range(z_sun_min, z_sun_max + 1):
        for zp in range(max(12, z_sun_min // 2), 3 * zs + 1):
            zr = zs + 2 * zp
            r = 1 + zr / zs
            if abs(r - target_ratio) / target_ratio > tolerance:
                continue
            p = planetary(zs, zp, zr, n_planets)
            if all(c["pass"] for c in p["checks"]):
                hits.append(
                    {
                        "z_sun": zs,
                        "z_planet": zp,
                        "z_ring": zr,
                        "ratio": round(r, 4),
                        "error_pct": round(100 * (r - target_ratio) / target_ratio, 2),
                    }
                )
    hits.sort(key=lambda h: (abs(h["error_pct"]), h["z_ring"]))
    return hits[:10]
