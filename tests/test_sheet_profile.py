"""Bent sheet-metal profile maths behind build_sheet_profile."""

import math

import pytest

from cadkit.calculators.sheet_metal import flat_length
from cadkit.sheet_profile import profile_layout, profile_outline


def _area(segments, steps=2000):
    """Shoelace area of the outline, with arcs sampled finely."""
    pts = []
    for seg in segments:
        if seg[0] == "line":
            pts.append(seg[1])
            continue
        a, m, b = seg[1:]
        # circle through three points
        ax, ay = a
        bx, by = m
        cx, cy = b
        d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        ux = ((ax**2 + ay**2) * (by - cy) + (bx**2 + by**2) * (cy - ay) + (cx**2 + cy**2) * (ay - by)) / d
        uy = ((ax**2 + ay**2) * (cx - bx) + (bx**2 + by**2) * (ax - cx) + (cx**2 + cy**2) * (bx - ax)) / d
        r = math.dist((ux, uy), a)
        t0 = math.atan2(ay - uy, ax - ux)
        tm = math.atan2(by - uy, bx - ux)
        t1 = math.atan2(cy - uy, cx - ux)
        sweep = (t1 - t0) % (2 * math.pi)
        if (tm - t0) % (2 * math.pi) > sweep:
            sweep -= 2 * math.pi
        for k in range(steps):
            ang = t0 + sweep * k / steps
            pts.append((ux + r * math.cos(ang), uy + r * math.sin(ang)))
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1], strict=True))) / 2


CASES = [
    ([30, 50, 30], [90, 90]),  # U channel
    ([40, 60], [90]),  # L angle
    ([25, 40, 25], [90, -90]),  # Z profile
    ([15, 20, 40, 20, 15], [-90, 90, 90, -90]),  # hat
    ([50, 50], [45]),
]


@pytest.mark.parametrize("flanges, angles", CASES)
def test_outline_is_one_closed_loop(flanges, angles):
    segs = profile_outline(2.0, 3.0, flanges, angles)
    for current, following in zip(segs, segs[1:] + segs[:1], strict=True):
        assert math.dist(current[-1], following[1]) < 1e-9


@pytest.mark.parametrize("flanges, angles", CASES)
def test_area_is_thickness_times_centre_line(flanges, angles):
    t = 2.0
    layout = profile_layout(t, 3.0, flanges, angles)
    assert _area(profile_outline(t, 3.0, flanges, angles)) == pytest.approx(
        t * layout["centre_line_length"], rel=1e-5
    )


def test_u_channel_outside_size_matches_the_flanges():
    segs = profile_outline(2.0, 3.0, [30, 50, 30], [90, 90])
    pts = [p for s in segs for p in s[1:]]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    # first flange along +X, the 50 mm base along +Y, the last flange back along -X
    assert max(xs) - min(xs) == pytest.approx(30.0, abs=1e-9)
    assert max(ys) - min(ys) == pytest.approx(50.0, abs=1e-9)


def test_flat_length_with_k_half_equals_the_centre_line():
    layout = profile_layout(2.0, 3.0, [30, 50, 30], [90, 90])
    flat = flat_length([30, 50, 30], 2.0, 3.0, [90, 90], k=0.5)["flat_length_mm"]
    assert flat == pytest.approx(layout["centre_line_length"], abs=1e-3)


def test_zero_inner_radius_still_closes():
    segs = profile_outline(2.0, 0.0, [30, 30], [90])
    for current, following in zip(segs, segs[1:] + segs[:1], strict=True):
        assert math.dist(current[-1], following[1]) < 1e-9


@pytest.mark.parametrize(
    "flanges, angles",
    [([3, 50], [90]), ([30, 50, 30], [90]), ([30, 30], [170]), ([30, 30], [0])],
)
def test_bad_input_is_refused(flanges, angles):
    with pytest.raises(ValueError):
        profile_outline(2.0, 3.0, flanges, angles)
