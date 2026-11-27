"""Parts built with free-form code switched off, through the structured tools only."""

import math

import pytest
from conftest import LIVE_PORT, listener_up, set_test_parameters
from replies import load

import server

pytestmark = pytest.mark.skipif(not listener_up(), reason=f"no FreeCAD listener on port {LIVE_PORT}")

DOC = "StructuredTest"


@pytest.fixture(autouse=True)
def code_off_document(monkeypatch):
    server._run(f"App.setActiveDocument(App.newDocument({DOC!r}).Name)")
    monkeypatch.delenv("FREECAD_MCP_ALLOW_CODE", raising=False)
    yield
    server._run(f"if {DOC!r} in App.listDocuments():\n    App.closeDocument({DOC!r})")


def _ok(reply: str) -> dict:
    data = load(reply)
    assert data.get("ok") is not False, data
    return data


def _cylinder(name: str, radius: float, height: float, radius_expr: str) -> None:
    created = _ok(server.create_cylinder(radius=radius, height=height, name=name))
    assert created["result"]["name"] == name
    _ok(server.bind_parameters(name, {"Radius": radius_expr, "Height": "Params.Thk"}))


def _build_flange() -> dict:
    hole_d = load(server.calc_fasteners("bolt_hole", {"size": "M10"}))["clearance_hole_mm"]["chosen"]
    _ok(
        set_test_parameters(
            {
                "FlangeD": "100 mm",
                "BoreD": "50 mm",
                "Thk": "12 mm",
                "PCD": "75 mm",
                "HoleD": f"{hole_d} mm",
                "NHoles": 4,
            }
        )
    )
    _cylinder("Disk", 50, 12, "Params.FlangeD / 2")
    _cylinder("Bore", 25, 12, "Params.BoreD / 2")
    _cylinder("BoltHole", hole_d / 2, 12, "Params.HoleD / 2")
    _ok(server.set_placement("BoltHole", position=[37.5, 0, 0]))
    _ok(server.bind_parameters("BoltHole", {"Placement.Base.x": "Params.PCD / 2"}))
    array = _ok(server.pattern_polar("BoltHole", count=4))
    _ok(server.bind_parameters(array["name"], {"NumberPolar": "Params.NHoles"}))
    return _ok(server.boolean("cut", base="Disk", tools=["Bore", array["name"]], label="Result"))


def test_flange_builds_with_free_form_code_off():
    assert load(server.run_freecad_code("result = 1"))["ok"] is False
    flange = _build_flange()
    expected = math.pi / 4 * (100**2 - 50**2 - 4 * 11**2) * 12
    assert expected == pytest.approx(66_125, abs=5)
    assert flange["valid"] and flange["solids"] == 1
    assert flange["volume_mm3"] == pytest.approx(expected, rel=1e-6)
    assert flange["size_mm"] == pytest.approx([100, 100, 12])

    holes = load(server.measure("Result"))
    assert holes["cylindrical_faces_by_diameter_mm"] == {"11.0": 4, "50.0": 1, "100.0": 1}
    assert {c["axis_from_center_mm"] for c in holes["cylinders"] if c["diameter_mm"] == 11.0} == {37.5}
    assert load(server.check_geometry("Result"))["valid"]
    assert load(server.check_model_structure())["score"] >= 90


def test_flange_follows_params_changes():
    _build_flange()
    _ok(set_test_parameters({"NHoles": 6, "Thk": "15 mm"}))
    m = load(server.measure("Result"))
    assert m["cylindrical_faces_by_diameter_mm"]["11.0"] == 6
    assert m["volume_mm3"] == pytest.approx(math.pi / 4 * (100**2 - 50**2 - 6 * 11**2) * 15, rel=1e-6)


def test_linear_slots_fuse_and_fillet():
    _ok(set_test_parameters({"Thk": "10 mm"}))
    _ok(server.create_box(length=100, width=40, height=10, name="Plate"))
    _ok(server.bind_parameters("Plate", {"Height": "Params.Thk"}))
    _ok(server.create_cylinder(radius=3, height=10, name="Hole"))
    _ok(server.set_placement("Hole", position=[20, 20, 0]))
    row = _ok(server.pattern_linear("Hole", count=3, spacing=30))
    assert row["solids"] == 3
    plate = _ok(server.boolean("cut", base="Plate", tools=[row["name"]]))
    rounded = _ok(server.fillet_edges(plate["name"], radius=2, edges="vertical", label="Result"))
    # Four corner edges; the hole walls are seams and are skipped.
    assert len(rounded["edges"]) == 4
    corner_loss = 4 * (2**2 - math.pi * 2**2 / 4) * 10
    expected = 100 * 40 * 10 - 3 * math.pi * 3**2 * 10 - corner_loss
    assert rounded["volume_mm3"] == pytest.approx(expected, rel=1e-6)
    assert load(server.check_geometry("Result"))["valid"]


def test_chamfer_common_and_turned_placement():
    _ok(server.create_box(length=20, width=20, height=20, name="Cube"))
    _ok(server.create_cylinder(radius=10, height=40, name="Rod"))
    turned = _ok(server.set_placement("Rod", position=[0, 10, 10], rotation_axis=[0, 1, 0], rotation_deg=90))
    assert turned["placement"]["rotation_deg"] == pytest.approx(90)
    common = _ok(server.boolean("common", base="Cube", tools=["Rod"]))
    # The rod now lies along X through the cube's centre and fills its full width.
    assert common["volume_mm3"] == pytest.approx(math.pi * 10**2 * 20, rel=1e-6)
    _ok(server.create_box(length=10, width=10, height=10, name="Block"))
    chamfered = _ok(server.chamfer_edges("Block", size=1, edges="top"))
    assert chamfered["volume_mm3"] == pytest.approx(1000 - 4 * 0.5 * 1 * 10 + 4 / 3, rel=1e-4)


def _build_ribs() -> dict:
    """Two triangular ribs against a wall: boxes cut by a cutter whose bottom face
    runs from the rib's top corner down its slope, turned by atan2(RibH, RibL)."""
    rib = {"WallT": "8 mm", "BaseT": "10 mm", "WallW": "80 mm", "RibT": "6 mm"}
    _ok(set_test_parameters({**rib, "RibL": "50 mm", "RibH": "50 mm"}))
    _ok(server.create_box(length=50, width=6, height=50, name="RibBox"))
    _ok(
        server.bind_parameters(
            "RibBox",
            {
                "Length": "Params.RibL",
                "Width": "Params.RibT",
                "Height": "Params.RibH",
                "Placement.Base.x": "Params.WallT",
                "Placement.Base.z": "Params.BaseT",
            },
        )
    )
    boxes = _ok(server.pattern_linear("RibBox", count=2, spacing=74, direction=[0, 1, 0]))
    _ok(server.bind_parameters(boxes["name"], {"IntervalX.y": "Params.WallW - Params.RibT"}))
    _ok(server.create_box(length=100, width=100, height=100, name="RibCutter"))
    _ok(server.set_placement("RibCutter", rotation_axis=[0, 1, 0], rotation_deg=45))
    _ok(
        server.bind_parameters(
            "RibCutter",
            {
                "Length": "Params.RibL + Params.RibH",
                "Width": "Params.WallW + 20 mm",
                "Height": "Params.RibL + Params.RibH",
                "Placement.Base.x": "Params.WallT",
                "Placement.Base.y": "-10 mm",
                "Placement.Base.z": "Params.BaseT + Params.RibH",
                "Placement.Rotation.Angle": "atan2(Params.RibH, Params.RibL)",
            },
        )
    )
    return _ok(server.boolean("cut", base=boxes["name"], tools=["RibCutter"], label="Result"))


@pytest.mark.parametrize("rib_l, rib_h", [(50, 50), (60, 30), (30, 70)])
def test_ribs_rebuild_when_their_length_and_height_differ(rib_l, rib_h):
    _build_ribs()
    _ok(set_test_parameters({"RibL": f"{rib_l} mm", "RibH": f"{rib_h} mm"}))
    ribs = load(server.measure("Result"))
    assert ribs["solids"] == 2
    assert ribs["volume_mm3"] == pytest.approx(2 * rib_l * rib_h / 2 * 6, rel=1e-6)
    assert ribs["bbox"]["min_mm"] == pytest.approx([8, 0, 10], abs=1e-6)
    assert ribs["bbox"]["max_mm"] == pytest.approx([8 + rib_l, 80, 10 + rib_h], abs=1e-6)
    # The ribs become one part only when fused to the wall.
    issues = load(server.check_geometry("Result"))["issues"]
    assert issues == ["2 separate solids - fuse them if this should be one part"]


def test_bad_binding_leaves_the_object_as_it_was():
    _ok(server.create_box(length=10, width=10, height=10, name="Block"))
    reply = load(server.bind_parameters("Block", {"Length": "Params.Missing"}))
    assert reply["ok"] is False
    assert load(server.inspect_object("Block"))["expressions"] == {}
    assert load(server.measure("Block"))["volume_mm3"] == pytest.approx(1000)
