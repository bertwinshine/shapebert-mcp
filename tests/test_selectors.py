"""Face and edge selector parsing; resolution needs FreeCAD and is tested live."""

import pytest
from replies import load

import shapebert_selectors as sel
from cadkit import fea

server = pytest.importorskip("server")


@pytest.mark.parametrize(
    "text, canonical",
    [
        ("top", "top"),
        ("Top Face", "top"),
        ("  +Z  ", "top"),
        ("-z side", "bottom"),
        ("+x side", "+X"),
        ("-Y", "-Y"),
        ("+y faces", "+Y"),
        ("largest planar face", "largest planar face"),
        ("Largest flat face", "largest planar face"),
        ("bore", "bore"),
        ("the bore", "bore"),
        ("cylindrical faces radius 4", "cylindrical faces radius 4"),
        ("cylindrical faces radius 4.0 mm", "cylindrical faces radius 4"),
        ("cylinders diameter 11", "cylindrical faces diameter 11"),
        ("cylindrical face radius .5", "cylindrical faces radius 0.5"),
        ("cylindrical faces radius 3.3000001", "cylindrical faces radius 3.3000001"),
    ],
)
def test_face_selectors_have_one_canonical_form(text, canonical):
    assert sel.parse_face(text) == canonical
    assert sel.parse_face(canonical) == canonical


@pytest.mark.parametrize(
    "text, canonical",
    [
        ("all", "all"),
        ("All Edges", "all"),
        ("vertical", "vertical"),
        ("vertical edges", "vertical"),
        ("concave edges", "concave edges"),
        ("top", "edges of top"),
        ("bottom", "edges of bottom"),
        ("edges of top face", "edges of top"),
        ("edges of the +X side", "edges of +X"),
        ("edges of bore", "edges of bore"),
        ("edges of cylindrical faces radius 4", "edges of cylindrical faces radius 4"),
    ],
)
def test_edge_selectors_have_one_canonical_form(text, canonical):
    assert sel.parse_edges(text) == canonical
    assert sel.parse_edges(canonical) == canonical


@pytest.mark.parametrize(
    "text, message",
    [
        ("outer", "unknown face selector"),
        ("top; import os", "unknown face selector"),
        ("+W", "unknown face selector"),
        ("cylindrical faces radius 0", "greater than 0"),
        ("cylindrical faces radius -4", "unknown face selector"),
        ("cylindrical faces radius 4 inch", "unknown face selector"),
        ("Face3", "face numbers change"),
        ("", "1 to 100 characters"),
        ("   ", "1 to 100 characters"),
        ("top" * 40, "1 to 100 characters"),
        ("top\nbottom", "control characters"),
        (7, "1 to 100 characters"),
    ],
)
def test_bad_face_selectors_are_refused(text, message):
    with pytest.raises(sel.SelectorError, match=message):
        sel.parse_face(text)


@pytest.mark.parametrize(
    "text, message",
    [
        ("outer", "unknown edge selector"),
        ("Edge4", "edge number"),
        ("edges of Face2", "face numbers change"),
        ("edges of nothing", "unknown face selector"),
        ("convex edges", "unknown edge selector"),
    ],
)
def test_bad_edge_selectors_are_refused(text, message):
    with pytest.raises(sel.SelectorError, match=message):
        sel.parse_edges(text)


def test_face_names_pass_only_where_allowed():
    assert sel.parse_face("face12", allow_names=True) == "Face12"
    with pytest.raises(sel.SelectorError):
        sel.parse_face("Face0", allow_names=True)


def test_selector_lists_are_bounded_and_deduplicated():
    assert sel.parse_list(["top", "Top face", "+Z"], sel.parse_face, "faces") == ["top"]
    assert sel.parse_list("bore", sel.parse_face, "faces") == ["bore"]
    for bad in ([], ["top"] * (sel.MAX_SELECTORS + 1), {"top": 1}, None):
        with pytest.raises(sel.SelectorError):
            sel.parse_list(bad, sel.parse_face, "faces")


def test_selector_errors_are_value_errors_for_the_argument_checks():
    assert issubclass(sel.SelectorError, ValueError)
    assert sel.SelectorError("x", [{"name": "Face1"}]).candidates == [{"name": "Face1"}]


def test_fea_faces_take_selectors_and_names_in_canonical_form():
    force = {"type": "force", "faces": ["top face", "Face2"], "value_n": 10, "direction": [0, 0, -1]}
    checked = fea.check_setup("static", 3, fixed_faces=["-X side", "face1"], loads=[force])
    assert checked["fixed_faces"] == ["-X", "Face1"]
    assert checked["loads"][0]["faces"] == ["top", "Face2"]
    with pytest.raises(ValueError, match="fixed_faces: unknown face selector"):
        fea.check_setup("static", 3, fixed_faces=["the end"], loads=[force])


def test_list_faces_is_read_only_and_checks_its_argument(monkeypatch):
    assert "list_faces" in server.READ_ONLY_TOOLS
    monkeypatch.setattr(server, "_fc", lambda *a, **k: pytest.fail("reached FreeCAD"))
    assert load(server.list_faces("bad\nname"))["ok"] is False


def test_freecad_gets_the_selector_source_with_every_tool_call():
    assert server.FC_TOOLS_SRC.startswith("SELECTORS_SOURCE = ")
    assert server.FEA_TOOLS_SRC.startswith(server.FC_TOOLS_SRC)
    namespace = {}
    exec(server.FC_TOOLS_SRC.splitlines()[0], namespace)
    assert namespace["SELECTORS_SOURCE"] == server.SELECTORS_SRC
    assert "class RoundEdges" in server.SELECTORS_SRC
