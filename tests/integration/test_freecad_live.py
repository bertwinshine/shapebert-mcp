"""Tests against a running FreeCAD listener; skipped when none is reachable.

They close every open FreeCAD document, so save your work first. Start a headless
listener as the README's Tests section shows.
"""

import math
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from conftest import LIVE_PORT, ROOT, listener_up, set_test_parameters
from replies import load

pytestmark = pytest.mark.skipif(not listener_up(), reason=f"no FreeCAD listener on port {LIVE_PORT}")

server = pytest.importorskip("server")


def J(s):
    return load(s)


@pytest.fixture(autouse=True)
def fresh_doc():
    server.run_freecad_code(
        "for n in list(App.listDocuments()):\n    App.closeDocument(n)\n"
        "App.newDocument('MCP_Test'); App.setActiveDocument('MCP_Test')"
    )
    yield
    # leave nothing behind: test objects must never mix with the user's work
    server.run_freecad_code("if 'MCP_Test' in App.listDocuments():\n    App.closeDocument('MCP_Test')")


def test_ping_reports_matching_protocol():
    rep = J(server.ping_freecad())
    assert rep["ok"] and "warning" not in rep


def test_box_volume_and_auto_report():
    rep = J(server.create_box(10, 20, 30))
    assert rep["ok"] and rep["result"]["volume_mm3"] == 6000
    obj = rep["new_objects"][0]
    assert obj["valid"] and obj["bbox_mm"] == [10, 20, 30]


def test_failed_code_is_rolled_back():
    rep = J(
        server.run_freecad_code(
            "import Part\nd = App.ActiveDocument\nd.addObject('Part::Box', 'Half')\n"
            "d.recompute()\nraise RuntimeError('fail after creating an object')"
        )
    )
    assert rep["ok"] is False and any("Half" in r for r in rep["rolled_back"])
    names = [o["name"] for o in J(server.get_document_info())["objects"]]
    assert "Half" not in names


def test_success_is_reported_truthfully():
    """Reply must say ok when the object exists, and list it."""
    rep = J(server.create_cylinder(5, 10, name="Cyl"))
    names = [o["name"] for o in J(server.get_document_info())["objects"]]
    assert rep["ok"] and "Cyl" in names


def test_print_output_always_returned():
    for i in range(10):
        rep = J(server.run_freecad_code(f"print('line', {i})"))
        assert rep["stdout"].strip() == f"line {i}"


def test_parallel_object_creation_no_losses():
    """20 concurrent creates: all objects exist, all replies ok."""

    def make(i):
        return J(server.create_box(1 + i, 1, 1, name=f"P{i:02d}"))

    with ThreadPoolExecutor(20) as ex:
        reps = list(ex.map(make, range(20)))
    assert all(r["ok"] for r in reps)
    names = {o["name"] for o in J(server.get_document_info())["objects"]}
    assert {f"P{i:02d}" for i in range(20)} <= names


def test_invalid_shape_is_flagged():
    J(
        server.run_freecad_code(
            "import Part\nd = App.ActiveDocument\n"
            "w = Part.makePolygon([App.Vector(0,0,0), App.Vector(10,0,0), App.Vector(10,10,0)])\n"
            "o = d.addObject('Part::Feature', 'Open'); o.Shape = w\nd.recompute()"
        )
    )
    chk = J(server.check_geometry("Open"))
    assert chk["valid"] is False and chk["issues"]


def test_measure_counts_holes():
    J(
        server.run_freecad_code(
            "import Part\nd = App.ActiveDocument\np = Part.makeBox(60, 30, 5)\n"
            "for x in (10, 50):\n    p = p.cut(Part.makeCylinder(3.3, 5, App.Vector(x, 15, 0)))\n"
            "o = d.addObject('Part::Feature', 'Plate'); o.Shape = p; d.recompute()"
        )
    )
    m = J(server.measure("Plate", density_kg_m3=2700))
    assert m["cylindrical_faces_by_diameter_mm"] == {"6.6": 2}
    assert m["mass_kg"] == pytest.approx((9000 - 2 * 3.14159 * 3.3**2 * 5) * 2.7e-6, rel=1e-3)


def test_step_roundtrip_is_identical():
    J(server.create_box(40, 20, 10, name="Blk"))
    path = "mcp_roundtrip.step"  # relative: lands in the work folder
    assert J(server.export_model(path, ["Blk"]))["bytes"] > 0
    cmp_ = J(server.compare_shapes("Blk", path))
    assert cmp_["iou"] == pytest.approx(1.0, abs=1e-6)


def test_stl_export():
    J(server.create_box(10, 10, 10))
    path = "mcp_box.stl"
    assert J(server.export_model(path))["bytes"] > 0


def test_parameters_drive_geometry():
    J(set_test_parameters({"L": 100}))
    J(
        server.run_freecad_code(
            "b = App.ActiveDocument.addObject('Part::Box', 'PB')\n"
            "b.setExpression('Length', 'Params.L')\nApp.ActiveDocument.recompute()"
        )
    )
    J(set_test_parameters({"L": 140}))
    size = J(server.measure("PB"))["bbox"]["size_mm"][0]
    assert size == pytest.approx(140)


def test_length_parameters_keep_their_unit():
    J(set_test_parameters({"TubeLength": "100 mm", "NHoles": 6}))
    J(
        server.run_freecad_code(
            "b = App.ActiveDocument.addObject('Part::Box', 'UB')\n"
            "b.setExpression('Length', 'Params.TubeLength + 2 mm')\n"
            "b.setExpression('Width', 'Params.NHoles * 1 mm')\n"
            "App.ActiveDocument.recompute()"
        )
    )
    size = J(server.measure("UB"))["bbox"]["size_mm"]
    assert size[:2] == [pytest.approx(102), pytest.approx(6)]


def test_rejected_alias_is_reported_not_hidden():
    """FreeCAD refuses unit names like 'W' as aliases; the tool must say so."""
    rep = J(set_test_parameters({"W": 60, "PlateW": 60}))
    assert rep["ok"] is False and rep["rejected_aliases"] == ["W"]
    assert "PlateW" in rep["set"]


def test_hydrostatics_open_box_hull_hand_calc():
    """2000 x 1000 open box, 10 mm walls, 400 kg fresh water:
    draft = 0.4 m^3 / 2 m^2 = 200 mm; KB = 100; BM = B^2/(12T) = 416.7 mm."""
    J(
        server.run_freecad_code(
            "import Part\nd = App.ActiveDocument\n"
            "s = Part.makeBox(2000, 1000, 500).cut(Part.makeBox(1980, 980, 500, App.Vector(10, 10, 10)))\n"
            "o = d.addObject('Part::Feature', 'Hull'); o.Shape = s; d.recompute()"
        )
    )
    h = J(server.hydrostatics("Hull", mass_kg=400, kg_mm=150))
    assert h["draft_mm"] == pytest.approx(200, abs=1)
    assert h["KB_mm"] == pytest.approx(100, abs=1)
    assert h["BM_mm"] == pytest.approx(416.7, abs=2)
    assert h["GM_mm"] == pytest.approx(366.7, abs=3)
    assert J(server.hydrostatics("Hull", mass_kg=5000))["floats"] is False


def test_hydrostatics_catamaran_two_hulls():
    J(
        server.run_freecad_code(
            "import Part\nd = App.ActiveDocument\n"
            "s = Part.makeBox(2000, 300, 400).fuse(Part.makeBox(2000, 300, 400, App.Vector(0, 1200, 0)))\n"
            "o = d.addObject('Part::Feature', 'Cat'); o.Shape = s; d.recompute()"
        )
    )
    h = J(server.hydrostatics("Cat", mass_kg=300))
    assert h["draft_mm"] == pytest.approx(250, abs=1)
    assert h["BM_mm"] == pytest.approx(1470, rel=0.01)


def test_printability_flags_overhang_and_thin_walls():
    J(
        server.run_freecad_code(
            "import Part\nd = App.ActiveDocument\n"
            "t = Part.makeBox(50, 50, 10).fuse(Part.makeBox(50, 10, 10, App.Vector(0, 0, 10)))"
            ".fuse(Part.makeBox(50, 50, 5, App.Vector(0, 0, 20)))\n"
            "o = d.addObject('Part::Feature', 'T'); o.Shape = t\n"
            "w = d.addObject('Part::Feature', 'Thin'); w.Shape = Part.makeBox(40, 0.6, 20)\n"
            "d.recompute()"
        )
    )
    p = J(server.check_printability("T", build_volume_mm=[256, 256, 256]))
    assert p["needs_support"] is True and p["overhang_area_mm2"] == pytest.approx(2000, rel=0.01)
    assert p["fits_build_volume"] is True
    thin = J(server.check_printability("Thin"))
    assert thin["wall_min_mm"] == pytest.approx(0.6, abs=0.05)
    assert thin["thin_wall_samples_pct"] > 0


def test_save_example_verifies_before_saving(kb_copy):
    good = (
        "import Part\nd = App.ActiveDocument\no = d.addObject('Part::Feature', 'B')\n"
        "o.Shape = Part.makeBox(10, 10, 10)\nd.recompute()\nresult = o.Shape.Volume\n"
    )
    rep = J(server.save_example("Cube 10", "a 10 mm cube", good, domain="general"))
    assert rep["saved"].endswith("cube_10.md") and rep["metrics"]["volume_mm3"] == 1000
    bad = "raise RuntimeError('nope')"
    rep = J(server.save_example("Bad", "bad", bad))
    assert rep["saved"] is False
    # the scratch document must be gone and the user's document untouched
    docs = J(server.get_status())["documents"]
    assert "MCPVerify" not in docs and "MCP_Test" in docs


def _example_code(md: Path):
    m = re.search(r"```python\n(.*?)```", md.read_text(encoding="utf-8"), re.S)
    return m.group(1) if m else None


EXAMPLES = sorted(
    [*(ROOT / "knowledge" / "examples").glob("*.md"), *(ROOT / "knowledge-private" / "examples").glob("*.md")]
)


@pytest.mark.parametrize("md", EXAMPLES, ids=[p.stem for p in EXAMPLES])
def test_saved_example_still_builds_valid_geometry(md):
    """Every saved example must still produce valid solids on this FreeCAD version."""
    code = _example_code(md)
    if code is None:
        pytest.skip("no python block")
    if "freecad.gears" in code or "import FCGear" in code:
        pytest.skip("needs the FCGear add-on")
    rep = J(server.run_freecad_code(code, timeout_s=300))
    assert rep["ok"], rep.get("error")
    shapes = [o for o in rep.get("new_objects", []) if "valid" in o]
    assert shapes, "example created no shapes"
    assert all(o["valid"] for o in shapes), [o for o in shapes if not o["valid"]]


def test_get_view_returns_png_in_gui_mode():
    if not J(server.get_status())["gui"]:
        pytest.skip("listener is headless - screenshots need the GUI")
    J(server.create_box(30, 20, 10))
    img = server.get_view("isometric", 400, 300)
    assert hasattr(img, "data") and img.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_spur_gear_is_one_valid_solid_with_the_right_size():
    rep = J(server.build_spur_gear(module=2, teeth=17, width=20, bore=10, keyway=[3, 1.4], name="Pinion"))
    assert rep["valid"] and rep["solids"] == 1 and rep["faces"] >= 60
    assert "undercut_warning" in rep
    # With an odd tooth count a tip always faces a gap, so the bounding box is a little
    # under the tip diameter; check the tip radius itself instead.
    tip = J(
        server.run_freecad_code(
            "s = App.ActiveDocument.getObject('Pinion').Shape\n"
            "result = max((v.X ** 2 + v.Y ** 2) ** 0.5 for v in s.Vertexes)"
        )
    )["result"]
    assert tip == pytest.approx(19.0, abs=0.01)
    m = J(server.measure("Pinion"))
    assert sorted(m["bbox"]["size_mm"]) == pytest.approx([20, 38, 38], abs=0.5)
    assert m["cylindrical_faces_by_diameter_mm"].get("10.0", 0) >= 1


def test_ring_gear_meshes_with_a_planet_of_the_same_shift():
    # Planetary from the test prompts: m 1.5, ring 60, planet 24, x = -0.29, a = 27.
    ring = J(server.build_ring_gear(module=1.5, teeth=60, width=15, outer_diameter=125, profile_shift=-0.29))
    assert ring["valid"] and ring["solids"] == 1
    assert "warnings" not in ring
    J(server.build_spur_gear(module=1.5, teeth=24, width=15, profile_shift=-0.29, name="Planet"))
    tip_r = J(
        server.run_freecad_code(
            "s = App.ActiveDocument.getObject('RingGear').Shape\n"
            "result = min((v.X ** 2 + v.Y ** 2) ** 0.5 for v in s.Vertexes)"
        )
    )["result"]
    # Ring tip = pitch - m (1 - x) with x = -0.29: 0.25 m clearance to the planet root.
    assert tip_r == pytest.approx(45 - 1.5 * (1 - (-0.29)), abs=0.01)
    # A planet tooth faces a ring gap at angle 0, so on its pitch point the pair meshes
    # with no overlap; pushed 1 mm too far out it must collide.
    overlap = (
        "import Part\n"
        "ring = App.ActiveDocument.getObject('RingGear').Shape\n"
        "planet = App.ActiveDocument.getObject('Planet').Shape\n"
        "result = []\n"
        "for x in (27.0, 28.0):\n"
        "    p = planet.copy(); p.translate(App.Vector(x, 0, 0))\n"
        "    result.append(ring.common(p).Volume)\n"
    )
    at_pitch, pushed_out = J(server.run_freecad_code(overlap))["result"]
    assert at_pitch < 5.0
    assert pushed_out > 20.0


def test_sheet_profile_u_channel_matches_hand_calculation():
    rep = J(
        server.build_sheet_profile(
            thickness=2, inner_radius=3, flanges=[30, 50, 30], angles=[90, 90], length=200, name="Channel"
        )
    )
    assert rep["valid"] and rep["solids"] == 1
    assert rep["volume_mm3"] == pytest.approx(rep["expected_volume_mm3"], rel=1e-6)
    assert rep["bbox_mm"] == pytest.approx([30, 50, 200], abs=1e-3)
    from cadkit.calculators.sheet_metal import flat_length

    assert rep["flat_length_mm"] == flat_length([30, 50, 30], 2, 3, [90, 90])["flat_length_mm"]


def test_sheet_profile_z_shape_is_one_solid():
    rep = J(
        server.build_sheet_profile(
            thickness=1.5, inner_radius=2, flanges=[25, 40, 25], angles=[90, -90], length=100
        )
    )
    assert rep["valid"] and rep["solids"] == 1
    assert rep["volume_mm3"] == pytest.approx(rep["expected_volume_mm3"], rel=1e-6)


def test_doctor_reports_freecad_and_the_optional_addons():
    rep = J(server.doctor())
    assert rep["freecad"]["reachable"] and rep["freecad"]["protocol_ok"]
    assert set(rep["optional_addons"]) == {"FCGear (freecad.gears)", "SheetMetal", "Fasteners"}
    for addon in rep["optional_addons"].values():
        assert isinstance(addon["installed"], bool)
        assert addon["installed"] or "Addon manager" in addon["how_to_install"]
    assert rep["fem"]["fem_workbench"] is True
    for prog in ("calculix", "gmsh"):
        assert rep["fem"][prog] != "not found" or "Preferences > FEM" in rep["fem"][f"{prog}_how_to_install"]


def test_fem_mesh_shape_link_is_not_mistaken_for_geometry():
    # A Gmsh mesh object's Shape property is a link to the part, not a TopoShape.
    rep = J(
        server.run_freecad_code(
            "import ObjectsFem\nd = App.ActiveDocument\n"
            "b = d.addObject('Part::Box', 'Beam')\nd.recompute()\n"
            "a = ObjectsFem.makeAnalysis(d, 'Analysis')\n"
            "m = ObjectsFem.makeMeshGmsh(d, 'Mesh'); m.Shape = b; a.addObject(m)\nd.recompute()"
        )
    )
    assert rep["ok"], rep.get("error")
    rows = {o["name"]: o for o in J(server.get_document_info())["objects"]}
    assert rows["Beam"]["top_level"] and "volume_mm3" not in rows["Mesh"]
    assert J(server.check_model_structure())["top_level"] == ["Beam"]


@pytest.fixture(scope="session")
def fem_solvers():
    """Skip solver tests on a FreeCAD without CalculiX or Gmsh, as doctor reports it."""
    fem = server._fc("fem_programs")
    missing = [
        name for key, name in (("calculix", "CalculiX"), ("gmsh", "Gmsh")) if fem.get(key) == "not found"
    ]
    if missing:
        pytest.skip(f"{' and '.join(missing)} not installed")


needs_solver = pytest.mark.usefixtures("fem_solvers")

BEAM_L, BEAM_B, BEAM_H, STEEL_E = 100.0, 10.0, 10.0, 210000.0
BEAM_I = BEAM_B * BEAM_H**3 / 12


def _solve_steel_beam(loads):
    J(server.create_box(BEAM_L, BEAM_B, BEAM_H, name="Beam"))
    setup = J(server.fea_setup("Beam", "steel", ["Face1"], loads, mesh_size_mm=3))
    assert setup.get("ok") is not False, setup
    assert setup["fixed_faces"][0]["centre_mm"] == [0, 5, 5]
    run = J(server.fea_run(timeout_s=300))
    assert run.get("ok") is not False, run
    results = J(server.fea_results())
    assert results["ccx"] == run["ccx"] and run["ccx"]["binary"] and run["ccx"]["threads"] == 1, run["ccx"]
    return setup, run, results


def test_fea_setup_refuses_a_part_name_that_matches_two_objects():
    J(server.create_box(BEAM_L, BEAM_B, BEAM_H, name="Alpha"))
    J(server.create_box(BEAM_L, BEAM_B, BEAM_H, name="Beta"))
    # Labels stay unique, but "Alpha" is now one object's Name and the other's Label.
    J(
        server.run_freecad_code(
            "doc = App.ActiveDocument\ndoc.Alpha.Label = 'Plate'\ndoc.Beta.Label = 'Alpha'"
        )
    )
    loads = [{"type": "force", "faces": ["Face2"], "value_n": 100, "direction": [0, 0, -1]}]
    setup = J(server.fea_setup("Alpha", "steel", ["Face1"], loads, mesh_size_mm=3))
    assert setup["ok"] is False and "matches several objects (Alpha, Beta)" in setup["error"], setup
    assert J(server.fea_setup("Beta", "steel", ["Face1"], loads, mesh_size_mm=3)).get("ok") is not False


def test_fea_setup_refuses_a_mesh_with_millions_of_elements():
    J(server.create_box(BEAM_L, BEAM_B, BEAM_H, name="Beam"))
    loads = [{"type": "force", "faces": ["Face2"], "value_n": 100, "direction": [0, 0, -1]}]
    setup = J(server.fea_setup("Beam", "steel", ["Face1"], loads, mesh_size_mm=0.1))
    assert setup["ok"] is False and "2,000,000 limit" in setup["error"], setup


@needs_solver
def test_fea_cantilever_point_load_matches_beam_theory():
    """100 x 10 x 10 steel, Face1 (x=0) fixed, 100 N down on Face2 (x=100):
    tip deflection F L^3 / (3 E I) = 0.1905 mm, root bending stress M / W = 60 MPa."""
    force = {"type": "force", "faces": ["Face2"], "value_n": 100, "direction": [0, 0, -1]}
    _, _, res = _solve_steel_beam([force])
    hand = 100 * BEAM_L**3 / (3 * STEEL_E * BEAM_I)
    assert res["max_displacement_mm"] == pytest.approx(hand, rel=0.03)
    assert res["max_displacement_at_mm"][0] == pytest.approx(BEAM_L)
    assert res["max_von_mises_mpa"] == pytest.approx(60, rel=0.10)
    assert res["reaction_force_sum_n"] == pytest.approx([0, 0, 100], abs=0.5)
    assert res["equilibrium_ok"] is True
    assert res["safety_factor_vs_yield"] == pytest.approx(235 / res["max_von_mises_mpa"], rel=0.01)
    assert res["units"]["stress"] == "MPa" and res["mesh_size_mm"] == 3 and "Simplified" in res["note"]


@needs_solver
def test_fea_cantilever_pressure_pushes_into_the_face():
    """0.1 MPa on the top face (Face6) = 1 N/mm down: w L^4 / (8 E I) = 0.0714 mm."""
    pressure = {"type": "pressure", "faces": ["Face6"], "value_mpa": 0.1}
    _, _, res = _solve_steel_beam([pressure])
    hand = 0.1 * BEAM_B * BEAM_L**4 / (8 * STEEL_E * BEAM_I)
    assert res["max_displacement_vector_mm"][2] < 0
    assert res["max_displacement_mm"] == pytest.approx(hand, rel=0.03)
    assert res["applied_force_sum_n"] == pytest.approx([0, 0, -100], abs=0.01)
    assert res["equilibrium_ok"] is True


@needs_solver
def test_fea_modal_cantilever_matches_closed_form_frequencies():
    """Fixed-free 10 x 10 x 100 steel bar. 1st bending (y/z pair):
    (1.875^2 / 2 pi) sqrt(EI / (rho A L^4)) = 835.6 Hz; torsion sqrt(G J / (rho Ip)) / 4L
    with J = 0.1406 a^4, Ip = a^4 / 6: 7365 Hz; axial sqrt(E / rho) / 4L: 12930 Hz."""
    J(server.create_box(BEAM_L, BEAM_B, BEAM_H, name="Beam"))
    setup = J(server.fea_setup("Beam", "steel", ["Face1"], None, 3, analysis_type="modal", modes=6))
    assert setup["analysis_type"] == "modal" and setup["modes"] == 6
    assert J(server.fea_run(timeout_s=300)).get("ok") is not False
    res = J(server.fea_results())
    assert res["ccx"]["threads"] == 1, res["ccx"]
    f = [m["frequency_hz"] for m in res["modes"]]
    rho, a = 7850e-12, BEAM_B  # t/mm^3 keeps N, mm, MPa consistent
    e_mm = STEEL_E
    g_mm = STEEL_E / 2.6
    bend = 1.875104**2 / (2 * math.pi) * math.sqrt(e_mm * BEAM_I / (rho * a * a * BEAM_L**4))
    torsion = math.sqrt(g_mm * 0.1406 * a**4 / (rho * a**4 / 6)) / (4 * BEAM_L)
    axial = math.sqrt(e_mm / rho) / (4 * BEAM_L)
    assert len(f) == 6
    assert f[0] == pytest.approx(bend, rel=0.01) and f[1] == pytest.approx(bend, rel=0.01)
    assert res["modes"][0]["repeated_with_mode"] == 2
    assert f[4] == pytest.approx(torsion, rel=0.02)
    assert f[5] == pytest.approx(axial, rel=0.01)
    assert res["part_mass_kg"] == pytest.approx(0.0785, rel=1e-3)
    assert res["units"]["frequency"] == "Hz" and "modal check" in res["note"]


STEEL_K = 50.0  # W/(m K)


@needs_solver
def test_fea_thermal_steady_bar_matches_fourier():
    """Steel bar, Face1 (x=0) at 100 °C, Face2 (x=100) at 20 °C, sides insulated:
    linear profile, 60 °C at mid-length, q = k A dT / L = 50 * 1e-4 * 80 / 0.1 = 4 W."""
    J(server.create_box(BEAM_L, BEAM_B, BEAM_H, name="Bar"))
    temps = [{"faces": ["Face1"], "temperature_c": 100}, {"faces": ["Face2"], "temperature_c": 20}]
    setup = J(
        server.fea_setup("Bar", "steel", mesh_size_mm=3, analysis_type="thermal_steady", temperatures=temps)
    )
    assert setup.get("ok") is not False, setup
    assert J(server.fea_run(timeout_s=300)).get("ok") is not False
    res = J(server.fea_results(probes=[[50, 0, 0], [50, 5, 5], [25, 5, 5]]))
    hand_q = STEEL_K * (BEAM_B * BEAM_H * 1e-6) * 80 / (BEAM_L * 1e-3)
    assert res["probes"][0]["node_at_mm"] == [50, 0, 0]
    assert res["probes"][0]["temperature_c"] == pytest.approx(60, abs=0.01)
    # A probe reads the nearest node, which can lie up to a mesh size from the point.
    for probe in res["probes"]:
        hand_t = 100 - 80 * probe["node_at_mm"][0] / BEAM_L
        assert probe["temperature_c"] == pytest.approx(hand_t, abs=0.01)
    assert res["max_temperature_c"] == pytest.approx(100) and res["min_temperature_c"] == pytest.approx(20)
    hot, cold = res["heat_flow_by_face"]
    assert hot["heat_flow_in_w"] == pytest.approx(hand_q, rel=0.02)
    assert cold["heat_flow_in_w"] == pytest.approx(-hand_q, rel=0.02)
    assert res["heat_balance_ok"] is True and "insulated" in res["note"]


STEEL_ALPHA = 12e-6
BAR_AT_120C = [{"faces": [f"Face{i}" for i in range(1, 7)], "temperature_c": 120}]


def _thermomech(**supports):
    J(server.create_box(BEAM_L, BEAM_B, BEAM_H, name="Bar"))
    setup = J(
        server.fea_setup(
            "Bar",
            "steel",
            mesh_size_mm=3,
            analysis_type="thermomechanical",
            temperatures=BAR_AT_120C,
            **supports,
        )
    )
    assert setup.get("ok") is not False, setup
    assert J(server.fea_run(timeout_s=300)).get("ok") is not False
    return J(server.fea_results(probes=[[100, 5, 5], [50, 0, 0]]))


@needs_solver
def test_fea_thermomechanical_free_bar_expands_without_stress():
    """+100 K from 20 °C, held by sliding faces x=0, y=0, z=0: dL = alpha dT L = 0.12 mm, no stress."""
    res = _thermomech(sliding_faces=["Face1", "Face3", "Face5"])
    assert res["probes"][0]["displacement_mm"][0] == pytest.approx(STEEL_ALPHA * 100 * BEAM_L, rel=0.01)
    assert res["max_von_mises_mpa"] < 1.0
    assert res["reaction_force_sum_n"] == pytest.approx([0, 0, 0], abs=0.5) and res["equilibrium_ok"]


@needs_solver
def test_fea_thermomechanical_clamped_bar_stress_is_e_alpha_dt():
    """Both ends held axially (sliding): sigma = E alpha dT = 252 MPa, end force 25.2 kN."""
    hand = STEEL_E * STEEL_ALPHA * 100
    res = _thermomech(sliding_faces=["Face1", "Face2", "Face3", "Face5"])
    assert res["max_von_mises_mpa"] == pytest.approx(hand, rel=0.01)
    assert res["probes"][1]["von_mises_mpa"] == pytest.approx(hand, rel=0.01)
    assert res["reaction_force_by_set_n"]["FEA_SLIDEFACE1"][0] == pytest.approx(hand * 100, rel=0.01)
    assert res["equilibrium_ok"] is True


@needs_solver
def test_fea_thermomechanical_fully_fixed_ends_close_to_e_alpha_dt_mid_length():
    # Fixed faces also block the sideways growth of the ends: higher local peaks there.
    res = _thermomech(fixed_faces=["Face1", "Face2"])
    assert res["probes"][1]["von_mises_mpa"] == pytest.approx(STEEL_E * STEEL_ALPHA * 100, rel=0.05)
    assert res["max_von_mises_mpa"] > 252


@needs_solver
def test_fea_thermal_transient_reaches_the_steady_state():
    """Bar at 20 °C, Face1 switched to 100 °C, Face2 held at 20 °C. The slowest mode
    decays with L^2 / (pi^2 a) = 73 s, so at 1000 s it is the steady state: 60 °C, 4 W."""
    J(server.create_box(BEAM_L, BEAM_B, BEAM_H, name="Bar"))
    temps = [{"faces": ["Face1"], "temperature_c": 100}, {"faces": ["Face2"], "temperature_c": 20}]
    setup = J(
        server.fea_setup(
            "Bar",
            "steel",
            mesh_size_mm=3,
            analysis_type="thermal_transient",
            temperatures=temps,
            time_end_s=1000,
            time_step_s=25,
        )
    )
    assert setup.get("ok") is not False, setup
    assert J(server.fea_run(timeout_s=600)).get("ok") is not False
    res = J(server.fea_results(probes=[[50, 0, 0]]))
    assert res["time_s"] == pytest.approx(1000) and res["time_steps"] == 40
    assert res["probes"][0]["temperature_c"] == pytest.approx(60, abs=0.01)
    hot, cold = res["heat_flow_by_face"]
    assert hot["heat_flow_in_w"] == pytest.approx(4.0, rel=0.01)
    assert cold["heat_flow_in_w"] == pytest.approx(-4.0, rel=0.01)
    history = [temp for _, temp in res["probes"][0]["history_s_c"]]
    assert history[0] < 30 and all(b >= a - 1e-6 for a, b in zip(history, history[1:], strict=False))


@needs_solver
def test_fea_buckling_fixed_free_column_matches_euler():
    """10 x 10 x 500 steel column, base fixed, 1 N down on top:
    P_cr = pi^2 E I / (4 L^2) = 1727 N; the second mode is 9 times that."""
    J(server.create_box(10, 10, 500, name="Column"))
    load = [{"type": "force", "faces": ["Face6"], "value_n": 1, "direction": [0, 0, -1]}]
    setup = J(server.fea_setup("Column", "steel", ["Face5"], load, 3, analysis_type="buckling", modes=4))
    assert setup["fixed_faces"][0]["centre_mm"] == [5, 5, 0], setup
    assert J(server.fea_run(timeout_s=600)).get("ok") is not False
    res = J(server.fea_results())
    assert res["ccx"]["threads"] == 1, res["ccx"]
    euler = math.pi**2 * STEEL_E * BEAM_I / (4 * 500**2)
    crit = [m["critical_load_n"] for m in res["modes"]]
    assert res["lowest_load_factor"] == pytest.approx(euler, rel=0.01), res["ccx"]
    assert crit[0] == pytest.approx(euler, rel=0.01) and crit[1] == pytest.approx(euler, rel=0.01)
    assert crit[2] == pytest.approx(9 * euler, rel=0.02)
    assert "imperfections" in res["note"]


TIP_LOAD = [{"type": "force", "faces": ["+X"], "value_n": 1000, "direction": [0, 0, -1]}]


def _cantilever_tip_load(part):
    """200 x 20 x 20 steel cantilever, x = 0 fixed, 1000 N down on the +X end face, 4 mm mesh."""
    setup = J(server.fea_setup(part, "steel", ["-X"], TIP_LOAD, mesh_size_mm=4))
    assert setup.get("ok") is not False, setup
    assert J(server.fea_run(timeout_s=300)).get("ok") is not False
    return setup, J(server.fea_results(probes=[[200, 10, 10]]))


@needs_solver
def test_fea_tip_load_on_a_small_face_is_flagged_as_a_concentrated_load():
    """8 mm chamfers on the end edges leave a 4 x 4 mm end face, 5.657 mm across its
    diagonal: less than 2 x 4 mm."""
    J(server.create_box(200, 20, 20, name="Beam"))
    J(server.chamfer_edges("Beam", 8, "edges of +X face", label="Tip"))
    setup, res = _cantilever_tip_load("Tip")
    assert setup["loads"][0]["face_info"][0]["area_mm2"] == pytest.approx(16)
    warnings = res["assumptions"]["warnings"]
    load = next(w["message"] for w in warnings if w["code"] == "load_singularity")
    assert "5.657 mm across" in load and "2 x mesh size = 8.0 mm" in load
    assert res["probes"][0]["near_singularity"] == {"kind": "small loaded face", "distance_mm": 0.0}
    assert "probe_at_singularity" in [w["code"] for w in warnings]


@needs_solver
def test_fea_same_load_spread_over_the_end_face_is_not_flagged():
    J(server.create_box(200, 20, 20, name="Beam"))
    setup, res = _cantilever_tip_load("Beam")
    assert setup["loads"][0]["face_info"][0]["area_mm2"] == pytest.approx(400)
    codes = [w["code"] for w in res["assumptions"]["warnings"]]
    assert "load_singularity" not in codes and "probe_at_singularity" not in codes
    assert "near_singularity" not in res["probes"][0]


def test_fea_setup_replaces_an_analysis_and_refuses_bad_faces():
    J(server.create_box(BEAM_L, BEAM_B, BEAM_H, name="Beam"))
    force = {"type": "force", "faces": ["Face2"], "value_n": 10, "direction": [0, 1, 0]}
    J(server.fea_setup("Beam", "PLA", ["Face1"], [force], 5))
    again = J(server.fea_setup("Beam", "PLA", ["Face1"], [force], 5))
    assert again["replaced_old_analysis"] is True
    names = [o["name"] for o in J(server.get_document_info())["objects"]]
    assert names.count("FEA") == 1 and "FEA001" not in names
    bad = J(server.fea_setup("Beam", "PLA", ["Face9"], [force], 5))
    assert bad["ok"] is False and "Face9 does not exist" in bad["error"]
    assert J(server.fea_results())["ok"] is False


def test_doctor_gives_install_steps_when_fem_programs_are_missing():
    code = server.FC_TOOLS_SRC + "\n_find_program = lambda *a: None\nresult = fem_programs()\n"
    fem = server._run(code)["result"]
    assert fem["calculix"] == fem["gmsh"] == "not found"
    assert "Preferences > FEM > CalculiX" in fem["calculix_how_to_install"]
    assert "Preferences > FEM > Gmsh" in fem["gmsh_how_to_install"]
    assert "never installs" in fem["gmsh_how_to_install"]
