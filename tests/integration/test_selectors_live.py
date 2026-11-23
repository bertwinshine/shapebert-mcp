"""Face and edge selectors against a running FreeCAD listener."""

import math

import pytest
from conftest import LIVE_PORT, listener_up
from replies import load
from test_structured_build import _build_flange

import server
from cadkit import safety

pytestmark = pytest.mark.skipif(not listener_up(), reason=f"no FreeCAD listener on port {LIVE_PORT}")

DOC = "SelectorTest"


@pytest.fixture(autouse=True)
def selector_document():
    server._run(f"App.setActiveDocument(App.newDocument({DOC!r}).Name)")
    yield
    server._run(f"if {DOC!r} in App.listDocuments():\n    App.closeDocument({DOC!r})")


def _ok(reply: str) -> dict:
    data = load(reply)
    assert data.get("ok") is not False, data
    return data


def _value(code: str):
    reply = server._run(code)
    assert reply["ok"], reply
    return reply["result"]


def _plate_with_holes() -> str:
    """The demo plate: 100 x 40 x Thk with a row of NHoles holes; its top is Face3."""
    _ok(server.set_parameters({"Thk": "10 mm", "NHoles": 3}))
    _ok(server.create_box(length=100, width=40, height=10, name="Plate"))
    _ok(server.bind_parameters("Plate", {"Height": "Params.Thk"}))
    _ok(server.create_cylinder(radius=3, height=10, name="Hole"))
    _ok(server.bind_parameters("Hole", {"Height": "Params.Thk"}))
    _ok(server.set_placement("Hole", position=[20, 20, 0]))
    row = _ok(server.pattern_linear("Hole", count=3, spacing=15))
    _ok(server.bind_parameters(row["name"], {"NumberX": "Params.NHoles"}))
    return _ok(server.boolean("cut", base="Plate", tools=[row["name"]]))["name"]


def _faces(name: str) -> dict:
    return {f["name"]: f for f in _ok(server.list_faces(name))["faces"]}


def _static_setup(part: str, fixed: list[str], loaded: list[str]) -> dict:
    load_ = {"type": "pressure", "faces": loaded, "value_mpa": 1}
    return load(server.fea_setup(part, "steel", fixed, [load_], mesh_size_mm=5))


def test_list_faces_describes_every_face():
    faces = _faces(_plate_with_holes())
    assert len(faces) == 9
    assert faces["Face3"]["type"] == "plane" and faces["Face3"]["normal"] == [0, 0, 1]
    hole = faces["Face7"]
    assert hole["type"] == "cylinder" and hole["radius_mm"] == 3 and hole["internal"] is True
    assert hole["axis"] == [0, 0, 1] and hole["axis_point_mm"] == [20, 20, 0]
    assert faces["Face1"]["bbox_mm"] == {"min": [0, 0, 0], "max": [0, 40, 10]}


def test_demo_plate_top_resolves_to_the_plus_z_face_not_the_end_face():
    part = _plate_with_holes()
    faces = _faces(part)
    # The trap the selectors avoid: on this part Face6 is the +X end, not the top.
    assert faces["Face6"]["normal"] == [1, 0, 0]
    setup = _static_setup(part, ["-X"], ["top"])
    assert setup.get("ok") is not False, setup
    (top,) = setup["loads"][0]["face_info"]
    assert top["face"] == "Face3" and top["selector"] == "top"
    assert top["normal"] == [0, 0, 1] and top["centre_mm"][2] == pytest.approx(10)
    (fixed,) = setup["fixed_faces"]
    assert fixed["face"] == "Face1" and fixed["normal"] == [-1, 0, 0]
    assert setup["loads"][0]["faces"] == ["Face3"]


def test_ties_and_misses_are_refused_with_candidates():
    part = _plate_with_holes()
    tie = _static_setup(part, ["-X"], ["largest planar face"])
    assert tie["ok"] is False and "ambiguous" in tie["error"]
    assert {c["name"] for c in tie["candidates"]} == {"Face3", "Face5"}
    miss = _static_setup(part, ["-X"], ["cylindrical faces radius 4"])
    assert miss["ok"] is False and "[3.0]" in miss["error"]
    none = load(server.fillet_edges(part, radius=1, edges="concave edges"))
    assert none["ok"] is False and "no edges match 'concave edges'" in none["error"]
    analyses = "result = [o.Name for o in App.ActiveDocument.Objects if o.TypeId == 'Fem::FemAnalysis']"
    assert _value(analyses) == []


def test_flange_bore_and_bolt_holes_found_by_selector():
    _build_flange()
    faces = _faces("Result")
    by_radius = sorted((f["radius_mm"], f["internal"]) for f in faces.values() if f["type"] == "cylinder")
    assert by_radius == [(5.5, True)] * 4 + [(25, True), (50, False)]
    setup = _static_setup("Result", ["bore"], ["cylindrical faces diameter 11"])
    assert setup.get("ok") is not False, setup
    (bore,) = setup["fixed_faces"]
    assert bore["selector"] == "bore" and bore["centre_mm"] == pytest.approx([0, 0, 6], abs=1e-6)
    holes = setup["loads"][0]["face_info"]
    assert len(holes) == 4
    assert all(math.hypot(*h["centre_mm"][:2]) == pytest.approx(37.5) for h in holes)

    _ok(server.set_parameters({"NHoles": 6}))
    setup = _static_setup("Result", ["bore"], ["cylindrical faces diameter 11"])
    assert len(setup["loads"][0]["face_info"]) == 6
    rims = _ok(server.chamfer_edges("Result", size=1, edges="edges of bore"))
    assert len(rims["edges"]) == 2


def _top_fillet_reference(base: str) -> dict:
    """makeFillet on the base's top face edges, found here by height, not by selector."""
    return _value(
        "s = App.ActiveDocument.getObject(" + repr(base) + ").Shape\n"
        "z = s.BoundBox.ZMax\n"
        "top = [f for f in s.Faces if abs(f.BoundBox.ZMin - z) < 1e-6 and abs(f.BoundBox.ZMax - z) < 1e-6]\n"
        "result = {'edges': len(top[0].Edges), 'volume': s.makeFillet(1, top[0].Edges).Volume}"
    )


def test_fillet_stays_on_the_same_edges_after_a_params_change():
    part = _plate_with_holes()
    fillet = _ok(server.fillet_edges(part, radius=1, edges="edges of top face", label="Result"))
    before = _top_fillet_reference(part)
    assert len(fillet["edges"]) == before["edges"] == 4 + 3
    assert fillet["volume_mm3"] == pytest.approx(before["volume"], abs=2e-3)

    _ok(server.set_parameters({"NHoles": 5}))
    after = _top_fillet_reference(part)
    resolved = _ok(server.inspect_object("Result"))["properties"]["ResolvedEdges"]
    assert len(resolved) == after["edges"] == 4 + 5
    assert resolved != fillet["edges"]
    m = _ok(server.measure("Result"))
    assert m["volume_mm3"] == pytest.approx(after["volume"], abs=2e-3)
    assert _ok(server.check_geometry("Result"))["valid"]

    _ok(server.bind_parameters("Result", {"Size": "Params.Thk / 5"}))
    again = _value(
        "App.ActiveDocument.getObject('Fillet').touch()\nApp.ActiveDocument.recompute()\n"
        "result = list(App.ActiveDocument.getObject('Fillet').ResolvedEdges)"
    )
    assert again == resolved


def test_concave_edges_of_an_l_bracket():
    _ok(server.create_box(length=20, width=20, height=5, name="Foot"))
    _ok(server.create_box(length=5, width=20, height=20, name="Wall"))
    bracket = _ok(server.boolean("fuse", base="Foot", tools=["Wall"]))
    inside = _ok(server.fillet_edges(bracket["name"], radius=2, edges="concave edges"))
    assert len(inside["edges"]) == 1
    # A fillet in an inside corner adds (r^2 - pi r^2 / 4) along the 20 mm edge.
    assert inside["volume_mm3"] - bracket["volume_mm3"] == pytest.approx((4 - math.pi) * 20, abs=2e-3)


def test_saved_documents_reopen_and_rebuild():
    part = _plate_with_holes()
    legacy = _ok(server.fillet_edges(part, radius=1, edges=["Edge1", "Edge3"]))
    chamfer = _ok(server.chamfer_edges(legacy["name"], size=0.5, edges="vertical", label="Result"))
    types = _value(
        f"d = App.ActiveDocument\nresult = [d.getObject({legacy['name']!r}).TypeId, "
        f"d.getObject({chamfer['name']!r}).TypeId]"
    )
    assert types == ["Part::Fillet", "Part::FeaturePython"]
    path = safety.work_dir() / "selector_reopen_test.FCStd"
    _ok(server.save_document(str(path)))
    reopened = _value(
        f"App.closeDocument({DOC!r})\nd = App.openDocument({str(path)!r})\n"
        "d.getObject('Params').set('Thk', '12 mm')\nd.recompute()\n"
        "result = {o.Name: [o.TypeId, o.Shape.isValid(), round(o.Shape.BoundBox.ZLength, 6), list(o.State)] "
        f"for o in d.Objects if o.Name in ({legacy['name']!r}, {chamfer['name']!r})}}\n"
        f"result['proxy'] = type(d.getObject({chamfer['name']!r}).Proxy).__module__\n"
        "App.closeDocument(d.Name)"
    )
    path.unlink(missing_ok=True)
    assert reopened[legacy["name"]][:3] == ["Part::Fillet", True, 12]
    assert reopened[chamfer["name"]][:3] == ["Part::FeaturePython", True, 12]
    assert not {"Invalid", "Error"} & set(reopened[legacy["name"]][3] + reopened[chamfer["name"]][3])
    assert reopened["proxy"] == "shapebert_selectors"
