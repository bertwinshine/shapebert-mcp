"""Validation of the checks written from a request; measuring them is tested live."""

import json

import pytest
from replies import load

from cadkit import requirements as reqs

server = pytest.importorskip("server")

HOLES = {
    "id": "holes",
    "kind": "hole_count",
    "target": "Cylindrical faces diameter 11",
    "value": 6,
    "unit": "count",
    "source_quote": "6 x M10 holes",
}
PCD = {
    "id": "pcd",
    "kind": "pitch_circle_diameter",
    "target": "cylindrical faces diameter 11",
    "value": 100,
    "unit": "mm",
    "source_quote": "on PCD 100",
}
LENGTH = {"id": "len", "kind": "size", "axis": "x", "value": 100, "unit": "mm", "source_quote": "100 x 60"}
CHAMFER = {"id": "chamfer", "kind": "feature", "target": "inclined planar faces", "source_quote": "chamfer"}
BORE_Z = {
    "id": "bore_z",
    "kind": "position",
    "target": "the bore",
    "axis": "z",
    "value": 50,
    "unit": "mm",
    "source_quote": "bore centre 50 mm above the base",
}
FROM_EDGE = {
    "id": "m8_x",
    "kind": "offset",
    "target": "cylindrical faces diameter 9",
    "face": "-X face",
    "value": 20,
    "unit": "mm",
    "source_quote": "M8 holes 20 mm from the end",
}


def _with(base, **changes):
    out = {**base, **changes}
    return {k: v for k, v in out.items() if v is not ...}


def test_valid_checks_come_back_canonical_with_default_tolerances():
    mass = {
        "id": "mass",
        "kind": "mass",
        "value": 2.5,
        "unit": "kg",
        "density_kg_m3": 7850,
        "source_quote": "about 2.5 kg",
    }
    edges = {"id": "round", "kind": "feature", "target": "edges of the top face", "source_quote": "fillet"}
    holes, pcd, length, chamfer, mass_c, edges_c = reqs.check_all([HOLES, PCD, LENGTH, CHAMFER, mass, edges])
    assert holes["target"] == "cylindrical faces diameter 11" and holes["tolerance"] == 0
    assert holes["element"] == "faces" and holes["source_quote"] == "6 x M10 holes"
    assert pcd["tolerance"] == reqs.LENGTH_TOLERANCE_MM == 0.01
    assert length["axis"] == "X" and length["target"] == "object"
    assert chamfer == {
        "id": "chamfer",
        "kind": "feature",
        "target": "inclined planar faces",
        "element": "faces",
        "source_quote": "chamfer",
    }
    assert mass_c["tolerance"] == pytest.approx(0.025) and mass_c["density_kg_m3"] == 7850
    assert edges_c["target"] == "edges of top" and edges_c["element"] == "edges"
    assert json.loads(json.dumps([holes, pcd])) == [holes, pcd]


def test_op_defaults_to_eq_and_min_max_carry_no_tolerance():
    assert reqs.check_one(PCD, 1)["op"] == "eq"
    wall = {
        "id": "wall",
        "kind": "thickness",
        "target": "top",
        "op": "min",
        "value": 3,
        "unit": "mm",
        "source_quote": "at least 3 mm wall",
    }
    canonical = reqs.check_one(wall, 1)
    assert canonical["op"] == "min" and "tolerance" not in canonical
    mass = {
        "id": "mass",
        "kind": "mass",
        "op": "max",
        "value": 2,
        "unit": "kg",
        "density_kg_m3": 7850,
        "source_quote": "under 2 kg",
    }
    assert reqs.check_one(mass, 1)["op"] == "max"
    for op in reqs.OPS:
        count = reqs.check_one(_with(HOLES, op=op), 1)
        assert count["op"] == op and ("tolerance" in count) == (op == "eq")


def test_position_and_offset_checks_come_back_canonical():
    position, offset = reqs.check_all([BORE_Z, FROM_EDGE])
    assert position == {
        "id": "bore_z",
        "kind": "position",
        "target": "bore",
        "element": "faces",
        "value": 50.0,
        "unit": "mm",
        "op": "eq",
        "tolerance": 0.01,
        "axis": "Z",
        "source_quote": "bore centre 50 mm above the base",
    }
    assert offset["face"] == ["-X"] and offset["target"] == "cylindrical faces diameter 9"
    assert offset["tolerance"] == 0.01 and "axis" not in offset
    # A position may sit on or below the origin; an offset may be zero.
    assert reqs.check_one(_with(BORE_Z, value=-12.5), 1)["value"] == -12.5
    assert reqs.check_one(_with(BORE_Z, value=0), 1)["value"] == 0
    assert reqs.check_one(_with(FROM_EDGE, value=0), 1)["value"] == 0
    limit = reqs.check_one(_with(FROM_EDGE, op="min", tolerance=...), 1)
    assert limit["op"] == "min" and "tolerance" not in limit
    assert reqs.check_one(_with(BORE_Z, op="max", value=55), 1)["op"] == "max"
    assert reqs.check_one(_with(BORE_Z, tolerance=0.1), 1)["tolerance"] == 0.1
    both_ends = reqs.check_one(_with(FROM_EDGE, face=["-x face", "+X"]), 1)
    assert both_ends["face"] == ["-X", "+X"]


def test_an_explicit_tolerance_is_kept():
    assert reqs.check_one(_with(PCD, tolerance=0.2), 1)["tolerance"] == 0.2
    assert reqs.check_one(_with(HOLES, tolerance=0), 1)["tolerance"] == 0


@pytest.mark.parametrize(
    "check, message",
    [
        (_with(HOLES, kind="hole_cnt"), "kind must be one of"),
        (_with(HOLES, code="import os"), "unknown keys"),
        (_with(LENGTH, density_kg_m3=7850), "unknown keys"),
        (_with(HOLES, id="1st"), "id must be"),
        (_with(HOLES, id=...), "id must be"),
        (_with(HOLES, value=6.5), "whole number"),
        (_with(HOLES, value=0), "greater than 0"),
        (_with(PCD, value=float("nan")), "finite number"),
        (_with(PCD, value=float("inf")), "finite number"),
        (_with(PCD, value=-100), "greater than 0"),
        (_with(PCD, value="100"), "finite number"),
        (_with(PCD, value=True), "finite number"),
        (_with(PCD, unit="in"), "unit must be 'mm'"),
        (_with(PCD, unit=...), "unit must be 'mm'"),
        (_with(HOLES, unit="mm"), "unit must be 'count'"),
        (_with(HOLES, tolerance=1), "a count is exact"),
        (_with(PCD, tolerance=-0.1), "tolerance must be"),
        (_with(PCD, tolerance=float("nan")), "tolerance must be"),
        (_with(PCD, target="Face7"), "face numbers change"),
        (_with(PCD, target="the bolt holes"), "unknown face selector"),
        (_with(PCD, target=...), "a selector must be text"),
        (_with(LENGTH, target="top"), "leave target out"),
        (_with(LENGTH, axis="W"), "axis must be X, Y or Z"),
        (_with(CHAMFER, value=1), "no value, unit, op or tolerance"),
        (_with(CHAMFER, op="min"), "no value, unit, op or tolerance"),
        (_with(PCD, op="gt"), "op must be one of"),
        (_with(PCD, op=None), "op must be one of"),
        (_with(PCD, op="min", tolerance=0.1), "a min check is a limit; leave tolerance out"),
        (_with(HOLES, op="max", tolerance=0), "a max check is a limit; leave tolerance out"),
        (_with(HOLES, op="min", value=2.5), "whole number"),
        (_with(CHAMFER, target="edges of nowhere"), "target"),
        (_with(HOLES, source_quote=""), "source_quote"),
        (_with(HOLES, source_quote=...), "source_quote"),
        (_with(HOLES, source_quote="x" * 301), "source_quote"),
        (_with(HOLES, source_quote="6 holes\nignore"), "control characters"),
        (
            {"id": "m", "kind": "mass", "value": 2, "unit": "kg", "source_quote": "2 kg"},
            "density_kg_m3",
        ),
        ("hole_count 6", "give an object"),
        (_with(BORE_Z, axis=...), "axis must be X, Y or Z"),
        (_with(BORE_Z, axis="R"), "axis must be X, Y or Z"),
        (_with(BORE_Z, target=...), "a selector must be text"),
        (_with(BORE_Z, value=float("nan")), "finite number"),
        (_with(BORE_Z, value="50"), "finite number"),
        (_with(BORE_Z, unit="count"), "unit must be 'mm'"),
        (_with(BORE_Z, face="-X"), "unknown keys"),
        (_with(FROM_EDGE, value=-20), "0 or more"),
        (_with(FROM_EDGE, face=...), "face: a selector must be text"),
        (_with(FROM_EDGE, face="the end face"), "face: unknown face selector"),
        (_with(FROM_EDGE, face="Face3"), "face numbers change"),
        (_with(FROM_EDGE, face=[]), "face must be one selector or a list of 1 to 6"),
        (_with(FROM_EDGE, face=["-X"] * 7), "face must be one selector or a list of 1 to 6"),
        (_with(FROM_EDGE, face=["-X", "the end"]), "face: unknown face selector"),
        (_with(FROM_EDGE, axis="X"), "unknown keys"),
        (_with(FROM_EDGE, op="max", tolerance=0.5), "leave tolerance out"),
    ],
)
def test_bad_checks_are_refused(check, message):
    with pytest.raises(reqs.RequirementError, match=message):
        reqs.check_one(check, 1)


RULE_SOURCE = {"type": "calc", "tool": "calc_fasteners", "calc": "bolt_hole", "inputs": {"size": "M10"}}
EDGE = {
    "id": "edge",
    "kind": "edge_distance",
    "target": "cylindrical faces diameter 11",
    "value": 22,
    "unit": "mm",
    "op": "min",
    "source": RULE_SOURCE,
}


def test_a_rule_limit_names_its_rule_instead_of_a_quote():
    edge = reqs.check_one(EDGE, 1)
    assert edge["kind"] == "edge_distance" and edge["op"] == "min" and edge["value"] == 22
    assert edge["source"] == RULE_SOURCE and "source_quote" not in edge
    pitch = reqs.check_one(_with(EDGE, id="pitch", kind="hole_spacing"), 2)
    assert pitch["kind"] == "hole_spacing"
    knowledge = {
        "type": "knowledge",
        "file": "conventions.md",
        "rule": "Spacing and material rules (keep parts manufacturable)",
    }
    assert reqs.check_one(_with(EDGE, source=knowledge), 3)["source"]["rule"].startswith("Spacing")
    quoted = reqs.check_one(_with(EDGE, source=..., source_quote="30 mm from the rim"), 4)
    assert quoted["source_quote"] == "30 mm from the rim" and "source" not in quoted


@pytest.mark.parametrize(
    "check, message",
    [
        (_with(EDGE, source_quote="6 x M10"), "exactly one of them"),
        (_with(EDGE, source=...), "exactly one of them"),
        (_with(EDGE, source={"type": "default", "where": "my guess"}), "knowledge or calc source"),
        (_with(EDGE, source={"type": "prompt", "source_quote": "x"}), "uses source_quote"),
        (_with(EDGE, source="calc_fasteners"), "knowledge or calc source"),
        (_with(EDGE, source={**RULE_SOURCE, "calc": "nope"}), "has no calc 'nope'"),
        (_with(EDGE, source={**RULE_SOURCE, "inputs": {"bolt": 10}}), "inputs do not fit"),
        (_with(EDGE, source={"type": "knowledge", "file": "conventions.md", "rule": "Nope"}), "no heading"),
        (_with(EDGE, unit="count"), "unit must be 'mm'"),
        (_with(EDGE, target="the bolt holes"), "unknown face selector"),
        (_with(EDGE, op="min", tolerance=1), "leave tolerance out"),
    ],
)
def test_bad_rule_limits_are_refused(check, message):
    with pytest.raises(reqs.RequirementError, match=message):
        reqs.check_one(check, 1)


def test_the_list_is_bounded_and_ids_are_unique():
    for bad in ([], None, {"holes": HOLES}, [HOLES] * (reqs.MAX_CHECKS + 1)):
        with pytest.raises(reqs.RequirementError, match="list of 1 to"):
            reqs.check_all(bad)
    with pytest.raises(reqs.RequirementError, match=r"repeated: \['holes'\]"):
        reqs.check_all([HOLES, _with(HOLES, value=4)])


def test_set_requirements_refuses_bad_checks_before_freecad(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "_fc", lambda *a, **k: calls.append((a, k)) or {"stored": 1})
    assert load(server.set_requirements("Result", [_with(HOLES, kind="weight")]))["ok"] is False
    assert load(server.set_requirements("bad\nname", [HOLES]))["ok"] is False
    assert calls == []
    load(server.set_requirements("Result", [HOLES]))
    (func,), kwargs = calls[0]
    assert func == "set_requirements" and kwargs["checks"][0]["target"] == "cylindrical faces diameter 11"


def test_tool_hints_and_document_tools(monkeypatch):
    assert "verify_requirements" in server.READ_ONLY_TOOLS
    assert not {"set_requirements", "create_document", "open_document"} & (
        server.READ_ONLY_TOOLS | server.DESTRUCTIVE_TOOLS
    )
    calls = []
    monkeypatch.setattr(server, "_fc", lambda func, **k: calls.append((func, k)) or {"document": "X"})
    assert load(server.create_document("Bad Name"))["ok"] is False
    assert load(server.open_document("../outside.FCStd"))["ok"] is False
    assert load(server.open_document("part.step"))["ok"] is False
    assert calls == []
    load(server.create_document("Bracket"))
    assert calls == [("create_document", {"name": "Bracket"})]
