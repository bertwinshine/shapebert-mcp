"""The hole edge-distance and pitch rule: values, validation, and no copies in the knowledge files."""

import math
import re
from pathlib import Path

import pytest
from pytest import approx
from replies import load

from cadkit import hole_rules, provenance
from cadkit.calculators import fasteners

server = pytest.importorskip("server")

ROOT = Path(__file__).resolve().parents[1]


def test_machined_default_is_two_hole_diameters():
    r = hole_rules.limits(11, "machined")
    assert r["min_edge_distance_mm"] == 22 and r["min_hole_to_hole_mm"] == 22
    assert r["factors_x_d0"] == {"edge": 2.0, "pitch": 2.0}
    assert "not a standard" in r["source"]
    assert hole_rules.limits(11) == r


def test_steel_structure_follows_en_1993_1_8_table_3_3():
    r = hole_rules.limits(22, "steel_structure")
    assert r["factors_x_d0"] == {"edge": 1.2, "pitch": 2.4, "p1": 2.2, "p2": 2.4}
    assert r["min_edge_distance_mm"] == approx(26.4)
    assert r["min_pitch_p1_mm"] == approx(48.4) and r["min_pitch_p2_mm"] == approx(52.8)
    # Load direction unknown: the check uses the larger spacing.
    assert r["min_hole_to_hole_mm"] == r["min_pitch_p2_mm"]
    assert "EN 1993-1-8" in r["source"] and "Table 3.3" in r["source"]
    assert r["verification"].startswith("unverified")


@pytest.mark.parametrize(
    "hole_d, rule, message",
    [
        (0, "machined", "above 0"),
        (-11, "machined", "above 0"),
        (math.nan, "machined", "above 0"),
        (math.inf, "machined", "above 0"),
        (True, "machined", "above 0"),
        ("11", "machined", "above 0"),
        (None, "machined", "above 0"),
        (1001, "machined", "up to 1000"),
        (11, "sheet_metal", "unknown rule"),
        (11, "", "unknown rule"),
    ],
)
def test_bad_inputs_are_refused(hole_d, rule, message):
    with pytest.raises(ValueError, match=message):
        hole_rules.limits(hole_d, rule)


def test_calc_fasteners_takes_its_numbers_from_the_rule():
    m10 = fasteners.bolt_hole("M10")
    assert m10["clearance_hole_mm"]["chosen"] == 11
    assert m10["min_edge_distance_mm"] == 22 and m10["min_hole_to_hole_mm"] == 22
    assert m10["spacing_rule"]["rule"] == "machined"
    steel = fasteners.bolt_hole("M10", rule="steel_structure")
    assert steel["min_edge_distance_mm"] == approx(13.2) and steel["min_hole_to_hole_mm"] == approx(26.4)
    assert fasteners.edge_distance(18) == hole_rules.limits(18)


def test_calc_tool_and_provenance_know_the_new_calc():
    assert load(server.calc_fasteners("edge_distance", {"hole_d_mm": 11}))["min_edge_distance_mm"] == 22
    assert load(server.calc_fasteners("edge_distance", {"hole_d_mm": -1}))["ok"] is False
    assert load(server.calc_fasteners("bolt_hole", {"size": "M10", "rule": "nope"}))["ok"] is False
    source = {"type": "calc", "tool": "calc_fasteners", "calc": "edge_distance", "inputs": {"hole_d_mm": 11}}
    assert provenance.check_source(source, "s") == source


# A line (or a line and the next, for wrapped sentences) about edge distance or hole
# spacing that names a multiple of the hole diameter repeats the rule instead of
# pointing at it.
TOPIC = re.compile(r"(?i)edge|rim\b|between (two )?holes|hole[- ]to[- ]hole|pitch|spacing|\bweb\b")
FACTOR = re.compile(
    r"(?i)\d+(?:\.\d+)?\s*(?:-\s*\d+(?:\.\d+)?\s*)?(?:x|\*|×)?\s*(?:d0?|dia(?:meter)?|hole\s+dia(?:meter)?)\b"
)


def _stray_rules(text):
    lines = [line.strip() for line in text.splitlines()] + [""]
    return [
        f"{n}: {lines[n - 1]}"
        for n in range(1, len(lines))
        if TOPIC.search(w := f"{lines[n - 1]} {lines[n]}") and FACTOR.search(w)
    ]


def test_the_scan_finds_the_old_copies_of_the_rule():
    assert _stray_rules("- Edge distance: a hole centre must be at least 2 x hole diameter.")
    assert _stray_rules("rim >= ~1.1-1.5 x hole diameter is normal practice")
    assert _stray_rules("edge distance = 2 x hole\ndiameter; features centred")
    assert _stray_rules('"Edge": "9 mm",  # edge distance = 2 x hole diameter')
    assert _stray_rules("avoid tapping < 1 d from an edge")
    assert not _stray_rules("hole-edge to part-edge >= 1.5*t; hole to hole >= 2*t")
    assert not _stray_rules("pitch diameter d = m*z ; circular pitch p = pi*m")


def test_knowledge_files_hold_no_copy_of_the_edge_distance_rule():
    folders = [ROOT / "knowledge", ROOT / "knowledge-private"]
    files = [p for folder in folders if folder.is_dir() for p in sorted(folder.rglob("*.md"))]
    assert files
    stray = {
        str(p.relative_to(ROOT)): found
        for p in files
        if (found := _stray_rules(p.read_text(encoding="utf-8")))
    }
    assert stray == {}, "point to calc_fasteners / cadkit/hole_rules.py instead of repeating numbers"
