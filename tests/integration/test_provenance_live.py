"""Where Params values came from, min/max checks and exact sizes, on parts built with the tools."""

import pytest
from conftest import LIVE_PORT, listener_up, set_test_parameters
from test_requirements_live import (
    FLANGE_CHECKS,
    PREFIX,
    _flange,
    _new_document,
    _ok,
    _rows,
    tools_only,  # noqa: F401 - the same autouse fixture
)

import server
from cadkit import safety

pytestmark = pytest.mark.skipif(not listener_up(), reason=f"no FreeCAD listener on port {LIVE_PORT}")

REQUEST = "Flange 140 mm, bore 50, 6 x M10 holes on PCD 100, 12 mm thick"
M10 = {"type": "calc", "tool": "calc_fasteners", "calc": "bolt_hole", "inputs": {"size": "M10"}}
FLANGE_SOURCES = {
    "FlangeD": {"type": "prompt", "source_quote": "Flange 140 mm"},
    "BoreD": {"type": "prompt", "source_quote": "bore 50"},
    "Thk": {"type": "prompt", "source_quote": "12 mm thick"},
    "PCD": {"type": "prompt", "source_quote": "on PCD 100"},
    "HoleD": M10,
    "NHoles": {"type": "prompt", "source_quote": "6 x M10 holes"},
}


def _table(sheet: str = "Params") -> tuple[dict, dict]:
    out = _ok(server.explain_params(sheet))
    return out, {row["parameter"]: row for row in out["parameters"]}


def _build_flange() -> None:
    assert all(s["source_quote"] in REQUEST for s in FLANGE_SOURCES.values() if s["type"] == "prompt")
    _flange(FLANGE_SOURCES)
    extra = {"EdgeR": "1 mm", "ChamferS": "0.5 mm"}
    sources = {
        "EdgeR": {"type": "knowledge", "file": "conventions.md", "rule": "Fillets and chamfers"},
        "ChamferS": {"type": "default", "where": "chosen for deburring, not in the request"},
    }
    assert _ok(server.set_parameters(extra, sources))["sources"] == {
        "EdgeR": "knowledge",
        "ChamferS": "default",
    }


def test_a_flange_from_a_prompt_says_where_each_value_came_from():
    _new_document("Sources")
    _build_flange()
    out, rows = _table()
    assert [r["parameter"] for r in out["parameters"]] == [*FLANGE_SOURCES, "EdgeR", "ChamferS"]
    assert (rows["FlangeD"]["value"], rows["FlangeD"]["unit"]) == (140, "mm")
    assert (rows["NHoles"]["value"], rows["NHoles"]["unit"]) == (6, "")
    for name in ("FlangeD", "Thk", "NHoles"):
        assert rows[name]["source"] == "prompt"
    assert rows["Thk"]["detail"] == '"12 mm thick"' and rows["NHoles"]["detail"] == '"6 x M10 holes"'
    assert rows["HoleD"]["source"] == "calc" and rows["HoleD"]["value"] == 11
    assert rows["HoleD"]["detail"] == "calc_fasteners bolt_hole(size='M10')"
    assert rows["EdgeR"]["source"] == "knowledge"
    assert rows["EdgeR"]["detail"] == 'conventions.md, rule "Fillets and chamfers"'
    assert [a["parameter"] for a in out["assumptions"]] == ["ChamferS"]

    refused = server.set_parameters({"Thk": "14 mm"}, {"Thk": {"type": "prompt"}})
    assert _table()[1]["Thk"]["value"] == 12 and "source_quote" in refused


def test_an_edit_becomes_a_user_edit_and_sources_survive_save_and_reopen():
    doc = _new_document("Edit")
    _build_flange()
    # The user types a new value into the spreadsheet by hand.
    server._run(
        "_s = App.ActiveDocument.getObject('Params')\n"
        "_s.set(_s.getCellFromAlias('PCD'), '=104 mm')\n"
        "App.ActiveDocument.recompute()"
    )
    _, rows = _table()
    assert rows["PCD"]["source"] == "user edit" and rows["PCD"]["value"] == 104
    assert "from =100 mm to =104 mm" in rows["PCD"]["detail"]
    assert '(was prompt: "on PCD 100")' in rows["PCD"]["detail"]

    asked = {"Thk": {"type": "user edit", "source_quote": "make it 15 mm thick"}}
    assert _ok(server.set_parameters({"Thk": "15 mm"}, asked))["sources"] == {"Thk": "user edit"}
    before, rows = _table()
    assert rows["Thk"] == {
        "parameter": "Thk",
        "value": 15,
        "unit": "mm",
        "source": "user edit",
        "detail": '"make it 15 mm thick"',
    }

    path = safety.work_dir() / f"{PREFIX}_sources.FCStd"
    _ok(server.save_document(str(path)))
    server._run(f"App.closeDocument({doc!r})")
    try:
        _ok(server.open_document(path.name))
        after, _ = _table()
        assert after["parameters"] == before["parameters"]
        assert after["counts"]["prompt"] == 3 and after["counts"]["user edit"] == 2
    finally:
        path.unlink(missing_ok=True)


def _plate() -> str:
    """'100 x 60 plate, wall at least 3 mm, under 0.2 kg in steel.'"""
    _ok(set_test_parameters({"PlateL": "100 mm", "PlateW": "60 mm", "Thk": "4 mm"}))
    _ok(server.create_box(length=100, width=60, height=4, name="Plate"))
    _ok(
        server.bind_parameters(
            "Plate", {"Length": "Params.PlateL", "Width": "Params.PlateW", "Height": "Params.Thk"}
        )
    )
    return "Plate"


LIMITS = [
    {
        "id": "wall",
        "kind": "thickness",
        "target": "top",
        "op": "min",
        "value": 3,
        "unit": "mm",
        "source_quote": "wall at least 3 mm",
    },
    {
        "id": "mass",
        "kind": "mass",
        "op": "max",
        "value": 0.2,
        "unit": "kg",
        "density_kg_m3": 7850,
        "source_quote": "under 0.2 kg in steel",
    },
]


def test_min_and_max_checks():
    _new_document("Limits")
    plate = _plate()
    _ok(server.set_requirements(plate, LIMITS))
    report, rows = _rows(plate)
    assert report["all_pass"], report
    assert (rows["wall"]["op"], rows["wall"]["measured"], rows["wall"]["required"]) == ("min", 4, 3)
    assert "tolerance" not in rows["wall"] and rows["mass"]["op"] == "max"
    assert rows["mass"]["measured"] == pytest.approx(0.1884)

    _ok(set_test_parameters({"Thk": "2 mm"}))
    _, rows = _rows(plate)
    assert (rows["wall"]["status"], rows["wall"]["measured"]) == ("fail", 2)
    assert rows["mass"]["status"] == "pass"

    _ok(set_test_parameters({"Thk": "5 mm"}))
    _, rows = _rows(plate)
    assert rows["wall"]["status"] == "pass"
    assert rows["mass"]["status"] == "fail" and rows["mass"]["measured"] == pytest.approx(0.2355)


def test_an_m10_hole_drilled_at_10_5_fails_with_the_measured_size():
    _new_document("Drill")
    _flange(hole_d=10.5)
    _ok(server.set_requirements("Result", FLANGE_CHECKS))
    report, rows = _rows("Result")
    assert {r["id"] for r in report["checks"] if r["status"] == "fail"} == {"holes", "hole_d", "pcd"}
    hole_d = rows["hole_d"]
    assert (hole_d["measured"], hole_d["required"]) == (10.5, 11)
    assert hole_d["nearest_holes"][0] == {"diameter_mm": 10.5, "count": 6}
    assert rows["holes"]["measured"] == 0 and rows["holes"]["nearest_holes"][0]["count"] == 6


def test_a_160_mm_disc_measures_160_across_x_and_y_after_meshing():
    _new_document("Disc")
    _ok(server.create_cylinder(radius=80, height=10, name="Disc"))
    # The GUI meshes every shape it shows; BoundBox then follows that mesh.
    server._run("App.ActiveDocument.getObject('Disc').Shape.tessellate(1.0)")
    sizes = [
        {
            "id": f"d{axis}",
            "kind": "size",
            "axis": axis,
            "value": 160,
            "unit": "mm",
            "source_quote": "160 mm disc",
        }
        for axis in ("X", "Y")
    ]
    _ok(server.set_requirements("Disc", sizes))
    report, rows = _rows("Disc")
    assert report["all_pass"], report
    for axis in ("X", "Y"):
        assert rows[f"d{axis}"]["measured"] == pytest.approx(160, abs=0.01)
    measured = _ok(server.measure("Disc"))["bbox"]["size_mm"]
    assert measured[:2] == pytest.approx([160, 160], abs=0.01)
