"""The editability scoring against a parametric and a static part in real FreeCAD."""

import sys

import pytest
from conftest import LIVE_PORT, ROOT, listener_up
from replies import load

pytestmark = pytest.mark.skipif(not listener_up(), reason=f"no FreeCAD listener on port {LIVE_PORT}")
sys.path.insert(0, str(ROOT / "bench"))
import score  # noqa: E402

import server  # noqa: E402

CASE = {"id": "edit-test", "edit": {"from": 8, "to": 12, "bbox_sorted_mm": [[12, 60, 100], 0.5]}}

PARAMETRIC = """
doc = App.newDocument("EditTest")
sheet = doc.addObject("Spreadsheet::Sheet", "Params")
sheet.set("B1", "=100 mm"); sheet.setAlias("B1", "PlateL")
sheet.set("B2", "=8 mm"); sheet.setAlias("B2", "Thk")
plate = doc.addObject("Part::Box", "Plate")
plate.Label = "Result"
plate.Width = 60
plate.setExpression("Length", "Params.PlateL")
plate.setExpression("Height", "Params.Thk")
doc.recompute()
"""

STATIC = """
import Part
doc = App.newDocument("EditTest")
copy = doc.addObject("Part::Feature", "Result")
copy.Shape = Part.makeBox(100, 60, 8)
doc.recompute()
"""


@pytest.fixture(autouse=True)
def fresh_document():
    yield
    server.run_freecad_code("if 'EditTest' in App.listDocuments():\n    App.closeDocument('EditTest')")


def test_a_parametric_part_follows_the_edit_and_scores_well():
    assert load(server.run_freecad_code(PARAMETRIC))["ok"]
    assert score.score_structure()[0] >= 80
    assert score.score_edit(CASE)["edit_score"] == 1.0


def test_a_static_copy_scores_badly_and_cannot_be_edited():
    assert load(server.run_freecad_code(STATIC))["ok"]
    structure = load(server.check_model_structure())
    assert structure["score"] < 50 and structure["static_copies"] == ["Result"]
    assert score.score_edit(CASE)["edit_score"] == 0.0


def test_the_plate_example_models_copy_is_clean_and_editable():
    text = (ROOT / "knowledge" / "examples" / "plate_with_holes.md").read_text(encoding="utf-8")
    code = text.split("```python", 1)[1].split("```", 1)[0]
    server.run_freecad_code("App.setActiveDocument(App.newDocument('EditTest').Name)")
    assert load(server.run_freecad_code(code))["ok"]
    assert score.score_structure()[0] >= 80
    case = {"id": "example", "edit": {"from": 5, "to": 8, "bbox_sorted_mm": [[30, 38, 60], 0.5]}}
    assert score.score_edit(case)["edit_score"] == 1.0


def test_the_edit_changes_the_parameter_the_geometry_uses():
    # "L" holds the same 100 mm as PlateL but nothing reads it.
    code = PARAMETRIC.replace(
        'sheet.set("B2", "=8 mm")',
        'sheet.set("B3", "=100 mm"); sheet.setAlias("B3", "L")\nsheet.set("B2", "=8 mm")',
    )
    assert load(server.run_freecad_code(code))["ok"]
    structure = load(server.check_model_structure())
    assert structure["params_unused"] == ["L"]
    case = {"id": "dup", "edit": {"from": 100, "to": 120, "bbox_sorted_mm": [[8, 60, 120], 0.5]}}
    assert score.score_edit(case)["edit_score"] == 1.0


def test_origin_axes_and_planes_of_a_body_are_not_counted_as_leftovers():
    code = PARAMETRIC + "\nbody = doc.addObject('PartDesign::Body', 'Body')\ndoc.recompute()\n"
    assert load(server.run_freecad_code(code))["ok"]
    assert load(server.check_model_structure())["top_level"] == ["Result"]


def _example(name):
    text = (ROOT / "knowledge" / "examples" / f"{name}.md").read_text(encoding="utf-8")
    return text.split("```python", 1)[1].split("```", 1)[0]


def _build_example(name):
    server.run_freecad_code("App.setActiveDocument(App.newDocument('EditTest').Name)")
    rep = load(server.run_freecad_code(_example(name), timeout_s=120))
    assert rep["ok"], rep.get("error")
    structure = load(server.check_model_structure())
    assert structure["score"] >= 90, structure["issues"]


def test_counterbored_example_follows_a_thickness_change():
    _build_example("counterbored_plate")
    case = {"id": "cb", "edit": {"from": 12, "to": 16, "bbox_sorted_mm": [[16, 50, 80], 0.5]}}
    assert score.score_edit(case)["edit_score"] == 1.0
    holes = load(server.measure("Result"))["cylindrical_faces_by_diameter_mm"]
    assert holes.get("6.6", 0) >= 2 and holes.get("11.0", 0) >= 2


def test_keyed_shaft_example_keeps_the_keyway_centred_when_longer():
    _build_example("keyed_shaft")
    case = {"id": "key", "edit": {"from": 120, "to": 150, "bbox_sorted_mm": [[40, 40, 150], 0.3]}}
    assert score.score_edit(case)["edit_score"] == 1.0
    centre = load(server.measure("Result"))["center_of_mass_mm"]
    assert centre[2] == pytest.approx(75.0, abs=0.01)


def test_flange_example_changes_its_hole_count():
    _build_example("flange_bolt_circle")
    before = load(server.measure("Result"))["cylindrical_faces_by_diameter_mm"].get("13.5", 0)
    case = {"id": "pcd", "edit": {"from": 6, "to": 8, "bbox_sorted_mm": [[16, 160, 160], 0.5]}}
    assert score.score_edit(case)["edit_score"] == 1.0
    after = load(server.measure("Result"))["cylindrical_faces_by_diameter_mm"].get("13.5", 0)
    assert (before, after) == (6, 8)


def test_building_a_frozen_part_gets_a_structure_warning_in_the_reply():
    server.run_freecad_code("App.setActiveDocument(App.newDocument('EditTest').Name)")
    frozen = STATIC.replace('doc = App.newDocument("EditTest")', "doc = App.ActiveDocument")
    rep = load(server.run_freecad_code(frozen))
    assert rep["ok"] and rep["structure_warning"]["score"] < 80


def test_building_a_clean_part_gets_no_warning():
    rep = load(server.run_freecad_code(PARAMETRIC))
    assert rep["ok"] and "structure_warning" not in rep


def test_shs_frame_example_is_one_hollow_solid_with_the_right_volume():
    _build_example("shs_frame")
    m = load(server.measure("Result"))
    assert m["solids"] == 1
    assert m["volume_mm3"] == pytest.approx(1_766_400, rel=1e-6)
    case = {"id": "frame", "edit": {"from": 800, "to": 1000, "bbox_sorted_mm": [[50, 500, 1000], 0.5]}}
    assert score.score_edit(case)["edit_score"] == 1.0
