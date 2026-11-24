"""Minimum hole edge distance and hole pitch: the one place these values are defined.
Sheet metal keeps its own thickness-based rule in domains/sheet-metal.md."""

from __future__ import annotations

import math

MAX_HOLE_MM = 1000.0

# Multiples of d0, the hole diameter. "pitch" is the minimum centre-to-centre distance
# a check can use without knowing the load direction.
RULES = {
    "machined": {
        "edge": 2.0,
        "pitch": 2.0,
        "source": "ShapeBert default for machined parts (not a standard)",
        "verification": "ShapeBert's own rule: matches calc_fasteners' 22 mm for an 11 mm M10 hole",
        "notes": [
            "edge distance = hole centre to the nearest outer edge",
            "pitch 2 x d0 leaves 1 x d0 of material between neighbouring holes",
        ],
    },
    "steel_structure": {
        "edge": 1.2,
        "pitch": 2.4,
        "p1": 2.2,
        "p2": 2.4,
        "source": "EN 1993-1-8:2005 Table 3.3, minimum end and edge distance e1, e2 and spacing p1, p2",
        "verification": (
            "unverified: not checked against the standard text; the same minimums appear in "
            "Hilti, SCIA and ArcelorMittal summaries of Table 3.3. Check the National Annex."
        ),
        "notes": [
            "e1 (end, along the load) and e2 (edge, across the load) are both 1.2 x d0",
            "p1 2.2 x d0 along the load, p2 2.4 x d0 across it; with the load direction "
            "unknown the check uses the larger p2",
            "minimums for structural steelwork; bearing resistance usually needs more",
        ],
    },
}


def limits(hole_d_mm: float, rule: str = "machined") -> dict:
    """Minimum edge distance and hole pitch for one hole diameter d0 (mm)."""
    if rule not in RULES:
        raise ValueError(f"unknown rule {rule!r}; known: {', '.join(RULES)}")
    if (
        isinstance(hole_d_mm, bool)
        or not isinstance(hole_d_mm, (int, float))
        or not math.isfinite(hole_d_mm)
        or not 0 < hole_d_mm <= MAX_HOLE_MM
    ):
        raise ValueError(f"hole_d_mm must be a number above 0 and up to {MAX_HOLE_MM:g} mm")
    r = RULES[rule]
    out = {
        "rule": rule,
        "hole_d0_mm": hole_d_mm,
        "min_edge_distance_mm": round(r["edge"] * hole_d_mm, 2),
        "min_hole_to_hole_mm": round(r["pitch"] * hole_d_mm, 2),
        "factors_x_d0": {k: r[k] for k in ("edge", "pitch", "p1", "p2") if k in r},
        "source": r["source"],
        "verification": r["verification"],
        "notes": list(r["notes"]),
    }
    if "p1" in r:
        out["min_pitch_p1_mm"] = round(r["p1"] * hole_d_mm, 2)
        out["min_pitch_p2_mm"] = round(r["p2"] * hole_d_mm, 2)
    return out
