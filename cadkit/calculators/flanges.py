"""EN 1092-1 flange connection sizes for PN16.

Outside diameter, bolt circle, number and size of bolt holes and bolt size, which
are the same for the common flange types (01, 05, 11). Thickness and hub sizes
depend on the type and material and are not listed.

Checked row by row against EN 1092-1:2018, Table 13 (PN 16), in November 2026.
"""

from __future__ import annotations

VERIFIED = True

# DN: (outside diameter D, bolt circle K, number of holes, hole diameter, bolt)
PN16 = {
    15: (95, 65, 4, 14, "M12"),
    20: (105, 75, 4, 14, "M12"),
    25: (115, 85, 4, 14, "M12"),
    32: (140, 100, 4, 18, "M16"),
    40: (150, 110, 4, 18, "M16"),
    50: (165, 125, 4, 18, "M16"),
    65: (185, 145, 8, 18, "M16"),
    80: (200, 160, 8, 18, "M16"),
    100: (220, 180, 8, 18, "M16"),
    125: (250, 210, 8, 18, "M16"),
    150: (285, 240, 8, 22, "M20"),
    200: (340, 295, 12, 22, "M20"),
    250: (405, 355, 12, 26, "M24"),
    300: (460, 410, 12, 26, "M24"),
}

TABLES = {16: PN16}

# Footnote b of Table 13: steel DN65 PN16 has 8 holes, but cast iron (EN 1092-2),
# copper alloy (EN 1092-3) and old DIN 2501/2633 flanges have 4. A 4-hole steel
# flange is only made by agreement, so mating an old flange needs a check.
NOTES = {
    (65, 16): "8 holes for steel to EN 1092-1. Cast iron, copper alloy and old DIN 2501/2633 "
    "flanges have 4 holes: if this mates with existing equipment, ask which one it has."
}


def en1092(dn: int, pn: int = 16) -> dict:
    """Connection sizes for one flange, e.g. en1092(dn=50, pn=16)."""
    if pn not in TABLES:
        raise ValueError(f"PN{pn} is not in the table yet; available: {sorted(TABLES)}")
    table = TABLES[pn]
    if dn not in table:
        raise ValueError(f"DN{dn} is not in the PN{pn} table; available: {sorted(table)}")
    outside, bolt_circle, holes, hole_d, bolt = table[dn]
    return {
        "standard": f"EN 1092-1 PN{pn}",
        "dn": dn,
        "outside_diameter_mm": outside,
        "bolt_circle_mm": bolt_circle,
        "holes": holes,
        "hole_diameter_mm": hole_d,
        "bolt": bolt,
        "verified_against_standard": VERIFIED,
        "note": "Thickness and hub depend on flange type and material: take them from the request or ask.",
        **({"warning": NOTES[(dn, pn)]} if (dn, pn) in NOTES else {}),
    }


def table(pn: int = 16) -> dict:
    """The whole table for one pressure rating."""
    if pn not in TABLES:
        raise ValueError(f"PN{pn} is not in the table yet; available: {sorted(TABLES)}")
    rows = [en1092(dn, pn) for dn in sorted(TABLES[pn])]
    return {"standard": f"EN 1092-1 PN{pn}", "verified_against_standard": VERIFIED, "rows": rows}
