"""Metric fasteners and ISO 286 fits - mirrors knowledge/domains/fasteners-fits.md.

Tables are the common published values (ISO 273, ISO 261/965 coarse pitch,
ISO 4762 / DIN 974-1, ISO 286-2). Check against the standard or a supplier
catalogue before production drawings.
"""

from __future__ import annotations

from cadkit import hole_rules

# size: (pitch, tap drill, clearance fine/medium/coarse, SHCS head dk, counterbore dia)
METRIC = {
    "M2": (0.40, 1.6, 2.2, 2.4, 2.6, 3.8, 4.4),
    "M2.5": (0.45, 2.05, 2.7, 2.9, 3.1, 4.5, 5.5),
    "M3": (0.50, 2.5, 3.2, 3.4, 3.6, 5.5, 6.5),
    "M4": (0.70, 3.3, 4.3, 4.5, 4.8, 7.0, 8.0),
    "M5": (0.80, 4.2, 5.3, 5.5, 5.8, 8.5, 10.0),
    "M6": (1.00, 5.0, 6.4, 6.6, 7.0, 10.0, 11.0),
    "M8": (1.25, 6.8, 8.4, 9.0, 10.0, 13.0, 15.0),
    "M10": (1.50, 8.5, 10.5, 11.0, 12.0, 16.0, 18.0),
    "M12": (1.75, 10.2, 13.0, 13.5, 14.5, 18.0, 20.0),
    "M16": (2.00, 14.0, 17.0, 17.5, 18.5, 24.0, 26.0),
    "M20": (2.50, 17.5, 21.0, 22.0, 24.0, 30.0, 33.0),
}

# thread engagement length as multiple of d, by material of the TAPPED part [RULE]
ENGAGEMENT = {
    "steel": 1.0,
    "cast_iron": 1.25,
    "aluminium": 1.5,
    "aluminium_soft": 2.0,
    "brass": 1.25,
    "plastic": 2.0,
}


def _norm(size: str) -> str:
    s = size.upper().replace(" ", "")
    if not s.startswith("M"):
        s = "M" + s
    if s not in METRIC:
        raise ValueError(f"unknown size {size}; known: {', '.join(METRIC)}")
    return s


def edge_distance(hole_d_mm: float, rule: str = "machined") -> dict:
    """Minimum hole centre to edge and centre to centre distance for a hole diameter."""
    return hole_rules.limits(hole_d_mm, rule)


def bolt_hole(
    size: str,
    fit: str = "medium",
    tapped_material: str | None = None,
    head: str = "socket",
    rule: str = "machined",
) -> dict:
    """Everything needed to model holes for one metric screw size."""
    s = _norm(size)
    p, tap, fine, med, coarse, dk, cb = METRIC[s]
    d = float(s[1:])
    clearance = {"fine": fine, "medium": med, "coarse": coarse}[fit]
    spacing = hole_rules.limits(clearance, rule)
    out = {
        "size": s,
        "nominal_d_mm": d,
        "pitch_mm": p,
        "clearance_hole_mm": {"fine": fine, "medium": med, "coarse": coarse, "chosen": clearance},
        "tap_drill_mm": tap,
        "min_edge_distance_mm": spacing["min_edge_distance_mm"],
        "min_hole_to_hole_mm": spacing["min_hole_to_hole_mm"],
        "spacing_rule": {k: spacing[k] for k in ("rule", "factors_x_d0", "source", "verification")},
        "notes": [f"edge distance and hole pitch for d0 = {clearance} mm: {spacing['source']}"],
    }
    if head == "socket":
        out["counterbore"] = {
            "diameter_mm": cb,
            "depth_mm": round(d + 0.4, 2),
            "head_dk_mm": dk,
            "note": "ISO 4762 head (k = d), DIN 974-1 counterbore",
        }
    elif head == "countersunk":
        out["countersink"] = {
            "angle_deg": 90,
            "diameter_mm": round(2 * d + 0.4, 2),
            "note": "ISO 10642 head dk ~= 2d; csk dia ~= 2d + 0.4 [RULE]",
        }
    if tapped_material:
        k = ENGAGEMENT.get(tapped_material, 1.5)
        out["thread_engagement_min_mm"] = round(k * d, 1)
        out["tapped_hole_depth_mm"] = round(k * d + 3 * p, 1)
        out["drill_depth_mm"] = round(k * d + 3 * p + 0.5 * d, 1)
        out["notes"].append(f"engagement {k:.2g} x d in {tapped_material} [RULE]")
    return out


_RANGES = [3, 6, 10, 18, 30, 50, 80, 120, 180, 250, 315, 400, 500]  # upper limits (mm)
IT = {  # micrometres
    5: [4, 5, 6, 8, 9, 11, 13, 15, 18, 20, 23, 25, 27],
    6: [6, 8, 9, 11, 13, 16, 19, 22, 25, 29, 32, 36, 40],
    7: [10, 12, 15, 18, 21, 25, 30, 35, 40, 46, 52, 57, 63],
    8: [14, 18, 22, 27, 33, 39, 46, 54, 63, 72, 81, 89, 97],
    9: [25, 30, 36, 43, 52, 62, 74, 87, 100, 115, 130, 140, 155],
    10: [40, 48, 58, 70, 84, 100, 120, 140, 160, 185, 210, 230, 250],
    11: [60, 75, 90, 110, 130, 160, 190, 220, 250, 290, 320, 360, 400],
}
# shaft fundamental deviations (micrometres): f, g -> upper (es); k, m, n, p -> lower (ei)
SHAFT_ES = {
    "f": [-6, -10, -13, -16, -20, -25, -30, -36, -43, -50, -56, -62, -68],
    "g": [-2, -4, -5, -6, -7, -9, -10, -12, -14, -15, -17, -18, -20],
    "h": [0] * 13,
}
SHAFT_EI = {
    "k": [0, 1, 1, 1, 2, 2, 2, 3, 3, 4, 4, 4, 5],  # valid for IT4..IT7
    "m": [2, 4, 6, 7, 8, 9, 11, 13, 15, 17, 20, 21, 23],
    "n": [4, 8, 10, 12, 15, 17, 20, 23, 27, 31, 34, 37, 40],
    "p": [6, 12, 15, 18, 22, 26, 32, 37, 43, 50, 56, 62, 68],
}
COMMON_FITS = {
    "H11/c11": "loose running (not tabulated here)",
    "H8/f7": "running fit - shafts in plain bearings, good lubrication",
    "H7/g6": "sliding fit - locating, accurate guiding, can move",
    "H7/h6": "locational clearance - parts assemble by hand, located accurately",
    "H7/k6": "transition - light press/mallet, e.g. gears/couplings with key",
    "H7/n6": "transition-to-interference - firm location, press",
    "H7/p6": "light press (interference) - permanent location without key",
}


def _range_index(d: float) -> int:
    if d <= 0 or d > 500:
        raise ValueError("ISO 286 table here covers 0 < d <= 500 mm")
    for i, top in enumerate(_RANGES):
        if d <= top:
            return i
    raise ValueError("out of range")


def tolerance(d_mm: float, zone: str) -> dict:
    """Limits of one tolerance zone, e.g. ('25', 'H7') or ('25', 'g6'). Units: mm."""
    letter = zone.rstrip("0123456789")
    grade = int(zone[len(letter) :])
    i = _range_index(d_mm)
    it = IT[grade][i]
    if letter == "H":
        lo, hi = 0, it
    elif letter == "JS" or letter == "js":
        lo, hi = -it / 2, it / 2
    elif letter in SHAFT_ES:
        hi = SHAFT_ES[letter][i]
        lo = hi - it
    elif letter in SHAFT_EI:
        lo = SHAFT_EI[letter][i]
        if letter == "k" and grade > 7:
            lo = 0
        hi = lo + it
    else:
        raise ValueError(f"zone {zone} not tabulated (have H, JS/js, f, g, h, k, m, n, p)")
    return {
        "zone": zone,
        "nominal_mm": d_mm,
        "IT_um": it,
        "lower_dev_um": lo,
        "upper_dev_um": hi,
        "min_mm": round(d_mm + lo / 1000.0, 4),
        "max_mm": round(d_mm + hi / 1000.0, 4),
    }


def fit(d_mm: float, fit_code: str = "H7/g6") -> dict:
    hole_z, shaft_z = fit_code.split("/")
    hole, shaft = tolerance(d_mm, hole_z), tolerance(d_mm, shaft_z)
    max_clear = (hole["upper_dev_um"] - shaft["lower_dev_um"]) / 1000.0
    min_clear = (hole["lower_dev_um"] - shaft["upper_dev_um"]) / 1000.0
    kind = "clearance" if min_clear >= 0 else "interference" if max_clear <= 0 else "transition"
    return {
        "fit": fit_code,
        "nominal_mm": d_mm,
        "hole": hole,
        "shaft": shaft,
        "max_clearance_mm": round(max_clear, 4),
        "min_clearance_mm": round(min_clear, 4),
        "type": kind,
        "use": COMMON_FITS.get(fit_code, ""),
        "notes": [
            "CAD: model at nominal; put the fit on the drawing. For 3D printing "
            "use the fdm domain clearances instead (ISO fits are for machining)."
        ],
    }
