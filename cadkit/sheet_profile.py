"""Cross-section of a bent sheet-metal profile (L, U, Z, hat ...) as plain 2D segments,
without FreeCAD. fc_tools.py extrudes it; keeping the maths here means it can be
tested anywhere.

Flange lengths are OUTSIDE (mould-line) dimensions, the same convention as
calc_sheet_metal flat_length, so the built part and the flat blank agree.
"""

import math

MAX_BEND_DEG = 150.0


def _rot(v, angle):
    c, s = math.cos(angle), math.sin(angle)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def _add(p, v, f=1.0):
    return (p[0] + f * v[0], p[1] + f * v[1])


def profile_layout(t, r_inner, flanges, angles):
    """Straight lengths between the bends and the centre-line length.

    angles: one signed angle per bend in degrees, positive bends to the left
    (counter-clockwise seen from +Z), negative to the right."""
    if t <= 0 or r_inner < 0:
        raise ValueError("thickness must be > 0 and inner radius >= 0")
    if len(flanges) < 2 or len(angles) != len(flanges) - 1:
        raise ValueError("need at least 2 flanges and one angle per bend (flanges - 1)")
    for a in angles:
        if not 0 < abs(a) <= MAX_BEND_DEG:
            raise ValueError(f"bend angles must be between 0 and {MAX_BEND_DEG} deg (signed)")
    setbacks = [(r_inner + t) * math.tan(math.radians(abs(a)) / 2) for a in angles]
    straights = []
    for i, length in enumerate(flanges):
        before = setbacks[i - 1] if i > 0 else 0.0
        after = setbacks[i] if i < len(setbacks) else 0.0
        s = length - before - after
        if s < -1e-9:
            raise ValueError(
                f"flange {i + 1} ({length} mm) is shorter than its bends need "
                f"({before + after:.3f} mm of outside setback)"
            )
        straights.append(max(s, 0.0))
    r_mid = r_inner + t / 2
    centre = sum(straights) + sum(r_mid * math.radians(abs(a)) for a in angles)
    return {"straights": straights, "outside_setbacks": setbacks, "centre_line_length": centre}


def profile_outline(t, r_inner, flanges, angles):
    """Closed outline of the cross-section as ("line", a, b) and ("arc", start, mid, end)
    segments. The first flange starts at the origin and runs along +X; the sheet is
    centred on that line (y from -t/2 to +t/2)."""
    layout = profile_layout(t, r_inner, flanges, angles)
    r_mid = r_inner + t / 2
    left, right = [], []  # sides at +t/2 and -t/2 of the centre line, walked forwards
    p, heading = (0.0, 0.0), 0.0

    def normal(h):
        return (-math.sin(h), math.cos(h))

    for i, s in enumerate(layout["straights"]):
        d = (math.cos(heading), math.sin(heading))
        q = _add(p, d, s)
        if s > 1e-12:
            for side, o in ((left, t / 2), (right, -t / 2)):
                side.append(("line", _add(p, normal(heading), o), _add(q, normal(heading), o)))
        p = q
        if i == len(angles):
            break
        theta = math.radians(angles[i])
        sign = 1.0 if theta > 0 else -1.0
        centre = _add(p, normal(heading), sign * r_mid)
        radial = (p[0] - centre[0], p[1] - centre[1])
        for side, o in ((left, t / 2), (right, -t / 2)):
            pts = []
            for f in (0.0, 0.5, 1.0):
                c_pt = _add(centre, _rot(radial, theta * f))
                pts.append(_add(c_pt, normal(heading + theta * f), o))
            if math.dist(pts[0], pts[2]) > 1e-9:  # zero inner radius: no arc on that side
                side.append(("arc", *pts))
        p = _add(centre, _rot(radial, theta))
        heading += theta

    def reverse(seg):
        return ("line", seg[2], seg[1]) if seg[0] == "line" else ("arc", seg[3], seg[2], seg[1])

    segments = list(left)
    segments.append(("line", _end(left[-1]), _end(right[-1])))
    segments += [reverse(seg) for seg in reversed(right)]
    segments.append(("line", _start(right[0]), _start(left[0])))
    return segments


def _start(seg):
    return seg[1]


def _end(seg):
    return seg[-1]
