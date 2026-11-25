"""Edge distance and hole pitch checks from the hole rule, measured on tool-built parts."""

import pytest
from conftest import LIVE_PORT, listener_up, set_test_parameters
from replies import load

import server

pytestmark = pytest.mark.skipif(not listener_up(), reason=f"no FreeCAD listener on port {LIVE_PORT}")

PREFIX = "HoleRuleTest"
M10_HOLES = "cylindrical faces diameter 11"
M10_RULE = {"type": "calc", "tool": "calc_fasteners", "calc": "bolt_hole", "inputs": {"size": "M10"}}


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


def _rule_checks() -> list[dict]:
    m10 = _ok(server.calc_fasteners("bolt_hole", {"size": "M10"}))
    assert (m10["min_edge_distance_mm"], m10["min_hole_to_hole_mm"]) == (22, 22)
    limit = {"target": M10_HOLES, "unit": "mm", "op": "min", "source": M10_RULE}
    return [
        {"id": "edge", "kind": "edge_distance", "value": m10["min_edge_distance_mm"], **limit},
        {"id": "pitch", "kind": "hole_spacing", "value": m10["min_hole_to_hole_mm"], **limit},
    ]


def _rows(name: str) -> tuple[dict, dict]:
    report = _ok(server.verify_requirements(name))
    return report, {row["id"]: row for row in report["checks"]}


def _flange() -> None:
    """'Flange OD 160, bore 50, 12 thick, 6 x M10 holes on PCD 100.'"""
    _ok(server.create_document(f"{PREFIX}Flange"))
    params = {"FlangeD": "160 mm", "BoreD": "50 mm", "Thk": "12 mm", "PCD": "100 mm", "HoleD": "11 mm"}
    _ok(set_test_parameters({**params, "NHoles": 6}))
    for name, expr in (
        ("Disk", "Params.FlangeD / 2"),
        ("Bore", "Params.BoreD / 2"),
        ("BoltHole", "Params.HoleD / 2"),
    ):
        _ok(server.create_cylinder(radius=10, height=12, name=name))
        _ok(server.bind_parameters(name, {"Radius": expr, "Height": "Params.Thk"}))
    _ok(server.bind_parameters("BoltHole", {"Placement.Base.x": "Params.PCD / 2"}))
    array = _ok(server.pattern_polar("BoltHole", count=6))
    _ok(server.bind_parameters(array["name"], {"NumberPolar": "Params.NHoles"}))
    _ok(server.boolean("cut", base="Disk", tools=["Bore", array["name"]], label="Result"))


def test_flange_od_160_passes_and_od_120_fails_the_edge_distance():
    _flange()
    stored = _ok(server.set_requirements("Result", _rule_checks()))
    assert stored["ids"] == ["edge", "pitch"]
    report, rows = _rows("Result")
    assert report["all_pass"], report
    # Hole centre on PCD 100 to the OD 160 rim; the bore is an inner edge and does not count.
    assert rows["edge"]["measured"] == pytest.approx(30)
    assert len(rows["edge"]["used"]) == 6
    assert rows["pitch"]["measured"] == pytest.approx(50)  # chord of 60 degrees on PCD 100
    assert rows["edge"]["source"] == M10_RULE and "source_quote" not in rows["edge"]

    _ok(set_test_parameters({"FlangeD": "120 mm"}))
    report, rows = _rows("Result")
    assert not report["all_pass"] and report["counts"] == {"pass": 1, "fail": 1, "not_measured": 0}
    edge = rows["edge"]
    assert edge["status"] == "fail" and edge["op"] == "min"
    assert (edge["measured"], edge["required"], edge["unit"]) == (pytest.approx(10), 22, "mm")


def test_plate_with_m10_holes_8_mm_from_the_edge_fails():
    """'Plate 100 x 60 x 10, two M10 holes 8 mm from the short edges.'"""
    _ok(server.create_document(f"{PREFIX}Plate"))
    _ok(server.create_box(length=100, width=60, height=10, name="Plate"))
    for name, x in (("HoleA", 8), ("HoleB", 92)):
        _ok(server.create_cylinder(radius=5.5, height=10, name=name))
        _ok(server.set_placement(name, position=[x, 30, 0]))
    plate = _ok(server.boolean("cut", base="Plate", tools=["HoleA", "HoleB"], label="Result"))
    assert plate["valid"]
    _ok(server.set_requirements("Result", _rule_checks()))
    report, rows = _rows("Result")
    assert report["counts"] == {"pass": 1, "fail": 1, "not_measured": 0}
    edge = rows["edge"]
    assert edge["status"] == "fail"
    assert (edge["measured"], edge["required"]) == (pytest.approx(8), 22)
    assert rows["pitch"]["status"] == "pass" and rows["pitch"]["measured"] == pytest.approx(84)
