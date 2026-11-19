"""Involute outline maths behind build_spur_gear."""

import math

import pytest

from cadkit.gear_profile import ring_cutter_outline, ring_radii, segment_ends, spur_outline, spur_radii


def _close(a, b, tol=1e-9):
    return math.dist(a, b) < tol


@pytest.mark.parametrize("z, x", [(17, 0.0), (18, 0.0), (12, 0.3), (40, 0.0), (60, -0.2)])
def test_outline_is_one_closed_loop(z, x):
    segments = spur_outline(2.0, z, x)
    for current, following in zip(segments, segments[1:] + segments[:1], strict=True):
        assert _close(segment_ends(current)[1], segment_ends(following)[0])


def test_tip_and_root_diameters_match_iso():
    r = spur_radii(2.0, 17)
    assert 2 * r["tip"] == pytest.approx(38.0)
    assert 2 * r["root"] == pytest.approx(29.0)


def test_every_point_lies_between_root_and_tip():
    r = spur_radii(2.0, 17)
    for seg in spur_outline(2.0, 17):
        points = seg[1] if seg[0] == "spline" else seg[1:]
        for p in points:
            assert r["root"] - 1e-9 <= math.hypot(*p) <= r["tip"] + 1e-9


def test_tooth_thickness_on_pitch_circle_is_half_the_pitch():
    # Standard gear, no shift: tooth and gap are equal on the pitch circle.
    z, m = 20, 3.0
    pitch_r = spur_radii(m, z)["pitch"]
    spline = spur_outline(m, z, flank_points=400)[1][1]
    nearest = min(spline, key=lambda p: abs(math.hypot(*p) - pitch_r))
    half_angle = -math.atan2(nearest[1], nearest[0])
    assert 2 * half_angle * pitch_r == pytest.approx(math.pi * m / 2, rel=2e-3)


def test_pointed_teeth_are_refused():
    with pytest.raises(ValueError):
        spur_outline(2.0, 10, profile_shift=1.2)


@pytest.mark.parametrize("z, x", [(60, 0.0), (60, -0.29), (48, 0.2), (90, 0.0)])
def test_ring_cutter_outline_is_one_closed_loop(z, x):
    segments = ring_cutter_outline(1.5, z, x)
    for current, following in zip(segments, segments[1:] + segments[:1], strict=True):
        assert _close(segment_ends(current)[1], segment_ends(following)[0])


def test_ring_cutter_points_lie_between_ring_tip_and_root():
    r = ring_radii(1.5, 60, -0.29)
    for seg in ring_cutter_outline(1.5, 60, -0.29):
        points = seg[1] if seg[0] == "spline" else seg[1:]
        for p in points:
            assert r["tip"] - 1e-9 <= math.hypot(*p) <= r["root"] + 1e-9


@pytest.mark.parametrize("x", [0.0, -0.29, 0.3])
def test_ring_gap_on_pitch_circle_equals_the_planet_tooth(x):
    m, z, alpha = 1.5, 60, math.radians(20)
    pitch_r = ring_radii(m, z, x)["pitch"]
    segments = ring_cutter_outline(m, z, x, flank_points=400)
    spline = next(seg[1] for seg in segments if seg[0] == "spline")
    nearest = min(spline, key=lambda p: abs(math.hypot(*p) - pitch_r))
    gap = 2 * -math.atan2(nearest[1], nearest[0]) * pitch_r
    assert gap == pytest.approx(m * (math.pi / 2 + 2 * x * math.tan(alpha)), rel=2e-3)


@pytest.mark.parametrize("x", [0.0, -0.29])
def test_ring_and_planet_with_the_same_shift_keep_standard_clearance(x):
    # Planetary from the test prompts: m 1.5, planet 24, ring 60, centre distance 27.
    m = 1.5
    ring, planet = ring_radii(m, 60, x), spur_radii(m, 24, x)
    a = m * (60 - 24) / 2
    assert ring["root"] - (a + planet["tip"]) == pytest.approx(0.25 * m)
    assert ring["tip"] - (a + planet["root"]) == pytest.approx(0.25 * m)


def test_small_ring_is_refused():
    with pytest.raises(ValueError):
        ring_cutter_outline(2.0, 12)
