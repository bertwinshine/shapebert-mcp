"""Checks written from a request, measured on parts built with the tools only."""

import math
from pathlib import Path

import pytest
from conftest import LIVE_PORT, listener_up
from replies import load

import server
from cadkit import safety

pytestmark = pytest.mark.skipif(not listener_up(), reason=f"no FreeCAD listener on port {LIVE_PORT}")

PREFIX = "ReqTest"


@pytest.fixture(autouse=True)
def tools_only(monkeypatch):
    """No free-form code: a refused script or an approval dialog fails the test."""
    monkeypatch.delenv("FREECAD_MCP_ALLOW_CODE", raising=False)

    def no_dialog(*args, **kwargs):
        pytest.fail("a ShapeBert tool asked for free-form code approval")

    monkeypatch.setattr(server, "_run_approved", no_dialog)
    yield
    server._run(
        "for _n in list(App.listDocuments()):\n"
        f"    if _n.startswith({PREFIX!r}):\n"
        "        App.closeDocument(_n)"
    )


def _ok(reply: str) -> dict:
    data = load(reply)
    assert data.get("ok") is not False, data
    return data


def _new_document(name: str) -> str:
    doc = _ok(server.create_document(f"{PREFIX}{name}"))["document"]
    assert doc.startswith(f"{PREFIX}{name}")
    return doc


def _rows(name: str) -> tuple[dict, dict]:
    report = _ok(server.verify_requirements(name))
    return report, {row["id"]: row for row in report["checks"]}


def _flange() -> None:
    """'Flange 140 mm, bore 50, 6 x M10 holes on PCD 100, 12 mm thick.'"""
    hole_d = load(server.calc_fasteners("bolt_hole", {"size": "M10"}))["clearance_hole_mm"]["chosen"]
    assert hole_d == 11
    _ok(
        server.set_parameters(
            {
                "FlangeD": "140 mm",
                "BoreD": "50 mm",
                "Thk": "12 mm",
                "PCD": "100 mm",
                "HoleD": f"{hole_d} mm",
                "NHoles": 6,
            }
        )
    )
    for name, radius, expr in (
        ("Disk", 70, "Params.FlangeD / 2"),
        ("Bore", 25, "Params.BoreD / 2"),
        ("BoltHole", 5.5, "Params.HoleD / 2"),
    ):
        _ok(server.create_cylinder(radius=radius, height=12, name=name))
        _ok(server.bind_parameters(name, {"Radius": expr, "Height": "Params.Thk"}))
    _ok(server.bind_parameters("BoltHole", {"Placement.Base.x": "Params.PCD / 2"}))
    array = _ok(server.pattern_polar("BoltHole", count=6))
    _ok(server.bind_parameters(array["name"], {"NumberPolar": "Params.NHoles"}))
    _ok(server.boolean("cut", base="Disk", tools=["Bore", array["name"]], label="Result"))


FLANGE_CHECKS = [
    {
        "id": "holes",
        "kind": "hole_count",
        "target": "cylindrical faces diameter 11",
        "value": 6,
        "unit": "count",
        "source_quote": "6 x M10 holes",
    },
    {
        "id": "hole_d",
        "kind": "hole_diameter",
        "target": "cylindrical faces diameter 11",
        "value": 11,
        "unit": "mm",
        "source_quote": "M10 holes",
    },
    {
        "id": "pcd",
        "kind": "pitch_circle_diameter",
        "target": "cylindrical faces diameter 11",
        "value": 100,
        "unit": "mm",
        "source_quote": "on PCD 100",
    },
    {
        "id": "thk",
        "kind": "thickness",
        "target": "top",
        "value": 12,
        "unit": "mm",
        "source_quote": "12 mm thick",
    },
    {"id": "od", "kind": "size", "axis": "X", "value": 140, "unit": "mm", "source_quote": "Flange 140 mm"},
]


def test_flange_meets_its_request_and_fails_when_holes_go_missing():
    _new_document("Flange")
    _flange()
    stored = _ok(server.set_requirements("Result", FLANGE_CHECKS))
    assert stored["ids"] == ["holes", "hole_d", "pcd", "thk", "od"]
    report, rows = _rows("Result")
    assert report["all_pass"], report
    assert rows["holes"]["measured"] == 6 and len(rows["holes"]["used"]) == 6
    assert rows["pcd"]["measured"] == pytest.approx(100) and rows["thk"]["measured"] == 12
    assert len(rows["thk"]["used"]) == 2
    assert rows["holes"]["source_quote"] == "6 x M10 holes"

    _ok(server.set_parameters({"NHoles": 4}))
    report, rows = _rows("Result")
    assert not report["all_pass"] and report["counts"] == {"pass": 4, "fail": 1, "not_measured": 0}
    holes = rows["holes"]
    assert holes["status"] == "fail" and holes["measured"] == 4 and holes["required"] == 6
    assert rows["pcd"]["status"] == "pass"


def test_a_selector_that_matches_nothing_fails_with_candidates():
    _new_document("Miss")
    _flange()
    wrong = {**FLANGE_CHECKS[0], "id": "m12", "target": "cylindrical faces diameter 13"}
    _ok(server.set_requirements("Result", [wrong]))
    report, rows = _rows("Result")
    assert rows["m12"]["status"] == "fail" and rows["m12"]["measured"] == "not found"
    assert "5.5" in rows["m12"]["error"] and rows["m12"]["candidates"]
    assert report["counts"]["fail"] == 1


def _plate_checks() -> list[dict]:
    """'100 x 60 x 10 plate, 3 x 6 mm holes 20 mm apart, chamfer the top edges 1 mm.'"""
    size = [
        ("len", "X", 100, "100 x 60 x 10"),
        ("wid", "Y", 60, "100 x 60 x 10"),
        ("hgt", "Z", 10, "x 10 plate"),
    ]
    checks = [
        {"id": i, "kind": "size", "axis": a, "value": v, "unit": "mm", "source_quote": q}
        for i, a, v, q in size
    ]
    holes = "cylindrical faces diameter 6"
    return checks + [
        {
            "id": "holes",
            "kind": "hole_count",
            "target": holes,
            "value": 3,
            "unit": "count",
            "source_quote": "3 x 6 mm holes",
        },
        {
            "id": "pitch",
            "kind": "hole_spacing",
            "target": holes,
            "value": 20,
            "unit": "mm",
            "source_quote": "20 mm apart",
        },
        {
            "id": "volume",
            "kind": "volume",
            "value": 60_000 - 3 * math.pi * 9 * 10,
            "unit": "mm3",
            "source_quote": "100 x 60 x 10 plate, 3 x 6 mm holes",
        },
        {
            "id": "chamfer",
            "kind": "feature",
            "target": "inclined planar faces",
            "source_quote": "chamfer the top edges 1 mm",
        },
    ]


def _plate() -> str:
    _ok(server.set_parameters({"PlateL": "100 mm", "PlateW": "60 mm", "Thk": "10 mm", "NHoles": 3}))
    _ok(server.create_box(length=100, width=60, height=10, name="Plate"))
    _ok(
        server.bind_parameters(
            "Plate", {"Length": "Params.PlateL", "Width": "Params.PlateW", "Height": "Params.Thk"}
        )
    )
    _ok(server.create_cylinder(radius=3, height=10, name="Hole"))
    _ok(server.set_placement("Hole", position=[30, 30, 0]))
    row = _ok(server.pattern_linear("Hole", count=3, spacing=20))
    _ok(server.bind_parameters(row["name"], {"NumberX": "Params.NHoles"}))
    return _ok(server.boolean("cut", base="Plate", tools=[row["name"]]))["name"]


def test_a_missing_chamfer_and_a_wrong_length_are_reported():
    _new_document("Plate")
    plate = _plate()
    _ok(server.set_requirements(plate, _plate_checks()))
    report, rows = _rows(plate)
    assert report["missing_features"] == [
        {"id": "chamfer", "target": "inclined planar faces", "source_quote": "chamfer the top edges 1 mm"}
    ]
    assert [r["id"] for r in report["checks"] if r["status"] != "pass"] == ["chamfer"]
    assert rows["pitch"]["measured"] == 20 and rows["volume"]["status"] == "pass"

    _ok(server.set_parameters({"PlateL": "105 mm"}))
    _, rows = _rows(plate)
    assert rows["len"]["status"] == "fail"
    assert (rows["len"]["measured"], rows["len"]["required"], rows["len"]["unit"]) == (105, 100, "mm")

    _ok(server.set_parameters({"PlateL": "100 mm"}))
    chamfered = _ok(server.chamfer_edges(plate, size=1, edges="edges of top face", label="Result"))
    _ok(server.set_requirements("Result", [c for c in _plate_checks() if c["id"] != "volume"]))
    report, _ = _rows("Result")
    assert report["all_pass"] and report["missing_features"] == [], report
    assert chamfered["valid"]


def test_checks_survive_save_and_reopen():
    doc = _new_document("Saved")
    _flange()
    _ok(server.set_requirements("Result", FLANGE_CHECKS))
    path = safety.work_dir() / f"{PREFIX}_saved.FCStd"
    _ok(server.save_document(str(path)))
    server._run(f"App.closeDocument({doc!r})")
    try:
        # FreeCAD names a reopened document after its file; the fixture closes it.
        opened = _ok(server.open_document(path.name))
        assert opened["document"] == path.stem and Path(opened["file"]) == path
        report, rows = _rows("Result")
        assert report["all_pass"] and rows["holes"]["source_quote"] == "6 x M10 holes"
        _ok(server.set_parameters({"NHoles": 5}))
        assert _rows("Result")[1]["holes"]["measured"] == 5
        again = _ok(server.open_document(str(path)))
        assert again["already_open"] is True and again["document"] == path.stem
    finally:
        path.unlink(missing_ok=True)


def test_a_full_plate_build_needs_no_free_form_code(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "run_freecad_code", lambda *a, **k: calls.append(a) or "{}")
    _new_document("NoCode")
    _ok(server.set_parameters({"PlateL": "100 mm", "PlateW": "60 mm", "Thk": "10 mm", "FilletR": "2 mm"}))
    _ok(server.create_box(length=100, width=60, height=10, name="Plate"))
    _ok(
        server.bind_parameters(
            "Plate", {"Length": "Params.PlateL", "Width": "Params.PlateW", "Height": "Params.Thk"}
        )
    )
    _ok(server.fillet_edges("Plate", radius=2, edges="edges of top face", label="Result"))
    _ok(server.bind_parameters("Result", {"Size": "Params.FilletR"}))
    checks = [
        {
            "id": "len",
            "kind": "size",
            "axis": "X",
            "value": 100,
            "unit": "mm",
            "source_quote": "100 x 60 x 10 mm plate",
        },
        {
            "id": "thk",
            "kind": "thickness",
            "target": "top",
            "value": 10,
            "unit": "mm",
            "source_quote": "x 10 mm plate",
        },
        {
            "id": "fillet",
            "kind": "feature",
            "target": "cylindrical faces radius 2",
            "source_quote": "fillet the edges of the top face with 2 mm",
        },
    ]
    _ok(server.set_requirements("Result", checks))
    report, rows = _rows("Result")
    assert report["all_pass"], report
    assert len(rows["fillet"]["used"]) == 4
    assert _ok(server.check_model_structure())["score"] == 100
    assert calls == []
