"""Involute spur and ring gear outlines as plain 2D segments, without FreeCAD.

fc_tools.py turns the segments into edges inside FreeCAD; keeping the maths here
means it can be tested anywhere.
"""

import math


def _involute(angle):
    return math.tan(angle) - angle


def _polar(r, angle):
    return (r * math.cos(angle), r * math.sin(angle))


def spur_radii(module, teeth, profile_shift=0.0, pressure_angle_deg=20.0):
    """Pitch, base, tip and root radii (ISO 21771, bottom clearance 0.25 m)."""
    alpha = math.radians(pressure_angle_deg)
    pitch = module * teeth / 2
    return {
        "pitch": pitch,
        "base": pitch * math.cos(alpha),
        "tip": pitch + module * (1 + profile_shift),
        "root": pitch - module * (1.25 - profile_shift),
    }


def ring_radii(module, teeth, profile_shift=0.0, pressure_angle_deg=20.0):
    """Internal (ring) gear radii. The tip circle is the INNER one, the root circle the
    outer one. Sign of the shift as for the mating planet: a ring and a planet with the
    same x keep the standard centre distance m * (z_ring - z_planet) / 2 and the
    standard 0.25 m clearance at both tip circles."""
    alpha = math.radians(pressure_angle_deg)
    pitch = module * teeth / 2
    return {
        "pitch": pitch,
        "base": pitch * math.cos(alpha),
        "tip": pitch - module * (1 - profile_shift),
        "root": pitch + module * (1.25 + profile_shift),
    }


def spur_outline(module, teeth, profile_shift=0.0, pressure_angle_deg=20.0, flank_points=15):
    """Closed outline, counter-clockwise, as ("spline", [points]), ("arc", start, mid, end)
    and ("line", start, end) segments. Below the base circle the flank is a radial
    line, so undercut is not modelled: use profile shift for small tooth counts."""
    if teeth < 6:
        raise ValueError("at least 6 teeth are needed for a usable spur gear")
    radii = spur_radii(module, teeth, profile_shift, pressure_angle_deg)
    return _toothed_outline(
        teeth,
        profile_shift,
        pressure_angle_deg,
        radii["base"],
        radii["tip"],
        radii["root"],
        flank_points,
        pointed="pointed teeth: reduce the profile shift or the addendum",
        overlap="teeth overlap at the root: check module, teeth and profile shift",
    )


def ring_cutter_outline(module, teeth, profile_shift=0.0, pressure_angle_deg=20.0, flank_points=15):
    """Outline of the space INSIDE a ring gear (its tooth gaps included), as the same
    segment list as spur_outline. A disk minus this face is the ring gear.

    An internal gear's tooth gap has the shape of an external tooth: on the pitch
    circle it is as wide as the mating planet's tooth, m * (pi/2 + 2 x tan(alpha)),
    and it narrows outwards along involutes of the same base circle."""
    if teeth < 20:
        raise ValueError("a ring gear needs at least 20 teeth")
    radii = ring_radii(module, teeth, profile_shift, pressure_angle_deg)
    return _toothed_outline(
        teeth,
        profile_shift,
        pressure_angle_deg,
        radii["base"],
        radii["root"],
        radii["tip"],
        flank_points,
        pointed="tooth gaps close before the root circle: reduce the profile shift",
        overlap="ring teeth are pointed at the tip circle: increase the profile shift",
    )


def _toothed_outline(teeth, x, pressure_angle_deg, rb, ra, rf, flank_points, pointed, overlap):
    """Teeth between rf and ra whose half angle follows the involute of rb."""
    alpha = math.radians(pressure_angle_deg)
    # Half the tooth's angular thickness on the pitch circle, then along the involute.
    half_pitch = (math.pi / 2 + 2 * x * math.tan(alpha)) / teeth

    def half_angle(r):
        return half_pitch + _involute(alpha) - _involute(math.acos(min(1.0, rb / r)))

    r0 = max(rb, rf)
    if half_angle(ra) <= 0.0:
        raise ValueError(pointed)
    pitch_angle = 2 * math.pi / teeth
    if pitch_angle - 2 * half_angle(r0) <= 0.0:
        raise ValueError(overlap)

    radii_on_flank = [r0 + (ra - r0) * i / (flank_points - 1) for i in range(flank_points)]
    segments = []
    for k in range(teeth):
        c = k * pitch_angle
        if rf < r0:
            segments.append(("line", _polar(rf, c - half_angle(r0)), _polar(r0, c - half_angle(r0))))
        segments.append(("spline", [_polar(r, c - half_angle(r)) for r in radii_on_flank]))
        segments.append(
            ("arc", _polar(ra, c - half_angle(ra)), _polar(ra, c), _polar(ra, c + half_angle(ra)))
        )
        segments.append(("spline", [_polar(r, c + half_angle(r)) for r in reversed(radii_on_flank)]))
        if rf < r0:
            segments.append(("line", _polar(r0, c + half_angle(r0)), _polar(rf, c + half_angle(r0))))
        next_c = c + pitch_angle
        segments.append(
            (
                "arc",
                _polar(rf, c + half_angle(r0)),
                _polar(rf, c + pitch_angle / 2),
                _polar(rf, next_c - half_angle(r0)),
            )
        )
    return segments


def segment_ends(segment):
    kind = segment[0]
    if kind == "spline":
        return segment[1][0], segment[1][-1]
    if kind == "arc":
        return segment[1], segment[3]
    return segment[1], segment[2]
