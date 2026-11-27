"""FEA reference cases against analytical answers and frozen results; needs a FreeCAD listener.

They close every open FreeCAD document. tests/validation/report.py writes
docs/validation.md from the same cases and freezes accepted results.
"""

import json
import math

import cases
import pytest
from conftest import LIVE_PORT, listener_up

import shapebert_selectors as selectors

CASES = cases.load_cases()
MODELLED = cases.modelled(CASES)
BY_ID = {c["id"]: c for c in CASES}
CANTILEVER = BY_ID["cantilever_static"]


def test_every_case_names_its_source_tolerance_and_reason():
    assert len(CASES) == 10
    for case in CASES:
        assert set(cases.QUANTITIES[case["id"]]) == {q["id"] for q in case["quantities"]}, case["id"]
        for q in case["quantities"]:
            assert q["citation"] and q["formula"] and q["tolerance_reason"], (case["id"], q["id"])
            assert 0 < q["tolerance_pct"] <= 5
            assert bool(case.get("benchmark")) == ("published" in q), (case["id"], q["id"])


def test_a_case_the_tools_cannot_set_up_says_why_and_stays_listed():
    assert [c["id"] for c in CASES if c not in MODELLED] == ["nafems_le10"]
    le10 = BY_ID["nafems_le10"]
    assert "sliding_faces" in le10["not_modelled"] and "fea_setup" not in le10
    assert le10["description_check"] == "Boundary conditions to be checked against TNSB Rev. 3."


def test_published_targets_and_closed_forms():
    le1 = BY_ID["nafems_le1"]
    assert [cases.QUANTITIES["nafems_le1"][q["id"]][1](le1, {}) for q in le1["quantities"]] == [92.7, 92.7]
    assert cases.QUANTITIES["nafems_le10"]["sigma_yy_d_mpa"][1](BY_ID["nafems_le10"], {}) == -5.38
    assert cases.mesh_sizes(le1) == [100, 500]
    kirsch = BY_ID["kirsch_plate"]
    assert cases.QUANTITIES["kirsch_plate"]["hole_edge_stress_mpa"][1](kirsch, {}) == pytest.approx(300)
    geo = kirsch["geometry"]
    assert 2 * geo["half_width_mm"] >= 20 * geo["hole_diameter_mm"]
    # For b = 2a: u(a) = p a (5 + 3 nu) / (3 E), u(b) = 4 p a / (3 E), hoop at the bore = 5 p / 3.
    lame = BY_ID["lame_cylinder"]
    formulas = cases.QUANTITIES["lame_cylinder"]
    p, a, e, nu = 100, 50, 210000, 0.3
    assert formulas["radial_displacement_inner_mm"][1](lame, {}) == pytest.approx(
        p * a * (5 + 3 * nu) / (3 * e)
    )
    assert formulas["radial_displacement_outer_mm"][1](lame, {}) == pytest.approx(4 * p * a / (3 * e))
    assert formulas["hoop_stress_inner_mpa"][1](lame, {}) == pytest.approx(5 * p / 3)


@pytest.mark.parametrize(
    "case_id, quantity",
    [(c, q) for c, qs in cases.HAND_CHECKS.items() for q in qs],
    ids=lambda v: v,
)
def test_calc_hand_check_agrees_with_the_case_formula(case_id, quantity):
    server = pytest.importorskip("server")
    case = BY_ID[case_id]
    hand = cases.hand_check(server, case, quantity)
    # calc_hand_check rounds its results to 6 decimals.
    assert hand["value"] == pytest.approx(cases.QUANTITIES[case_id][quantity][1](case, {}), rel=1e-6)


def test_the_frequency_parameter_is_solved_not_copied():
    lam = cases.clamped_free_eigenvalue(1)
    assert math.cos(lam) * math.cosh(lam) + 1 == pytest.approx(0, abs=1e-9)
    assert lam == pytest.approx(1.875104, abs=1e-6)
    assert cases.clamped_free_eigenvalue(2) == pytest.approx(4.694091, abs=1e-6)


@pytest.mark.parametrize(
    "case_id, quantity, approx",
    [
        ("cantilever_static", "tip_deflection_mm", 0.95),
        ("tension_bar", "axial_stress_mpa", 100),
        ("cantilever_modal", "mode1_hz", 418),
        ("thermal_bar", "heat_flow_w", 8),
        ("thermomech_free_bar", "elongation_mm", 0.12),
    ],
)
def test_formulas_give_the_known_hand_values(case_id, quantity, approx):
    case = next(c for c in CASES if c["id"] == case_id)
    formula = cases.QUANTITIES[case_id][quantity][1]
    assert formula(case, {}) == pytest.approx(approx, rel=0.01)


def test_frozen_results_are_compared_in_a_tight_band(tmp_path, monkeypatch):
    monkeypatch.setattr(cases, "HERE", tmp_path)
    (tmp_path / "x").mkdir()
    rows = [{"id": "q", "fea": 1.0}]
    assert cases.frozen_mismatches("x", "env", rows) is None
    cases.freeze("x", "env", rows, "first accepted result")
    frozen = json.loads((tmp_path / "x" / "fixture.json").read_text(encoding="utf-8"))
    assert frozen["environments"]["env"]["reason"] == "first accepted result"
    assert cases.frozen_mismatches("x", "env", [{"id": "q", "fea": 1.0 + 5e-7}]) == []
    assert cases.frozen_mismatches("x", "env", [{"id": "q", "fea": 1.00001}]) == [
        "q: frozen 1.0, now 1.00001"
    ]
    assert cases.frozen_mismatches("x", "other env", rows) is None


live = pytest.mark.skipif(not listener_up(), reason=f"no FreeCAD listener on port {LIVE_PORT}")


@pytest.fixture(scope="module")
def solved():
    server = pytest.importorskip("server")
    fem = server._fc("fem_programs")
    if "not found" in (fem.get("calculix"), fem.get("gmsh")):
        pytest.skip("CalculiX or Gmsh not installed")
    out = {}
    for case in MODELLED:
        runs = cases.solve_all(server, case)
        results = runs[case["fea_setup"]["mesh_size_mm"]]
        out[case["id"]] = {
            "results": results,
            "runs": runs,
            "rows": cases.compare(case, runs, server),
            "env": cases.environment(server, results),
        }
    yield server, out
    server.run_freecad_code(
        "if 'MCP_Validation' in App.listDocuments():\n    App.closeDocument('MCP_Validation')"
    )


@live
@pytest.mark.parametrize(
    "case_id, quantity", [(c["id"], q["id"]) for c in MODELLED for q in c["quantities"]], ids=lambda v: v
)
def test_fea_matches_the_analytical_answer(solved, case_id, quantity):
    row = next(r for r in solved[1][case_id]["rows"] if r["id"] == quantity)
    assert row["passed"], f"FEA {row['fea']} vs analytical {row['analytical']}: {row['error_pct']:.3f} %"


@live
@pytest.mark.parametrize("case_id", [c["id"] for c in MODELLED])
def test_fea_result_has_not_moved_from_the_frozen_one(solved, case_id):
    run = solved[1][case_id]
    moved = cases.frozen_mismatches(case_id, run["env"], run["rows"])
    if moved is None:
        pytest.skip(f"no frozen result for {run['env']}")
    assert moved == [], "result changed; freeze again only on purpose (report.py --freeze)"


def _canonical(face):
    return selectors.parse_face(face, allow_names=True)


@live
@pytest.mark.parametrize("case", MODELLED, ids=lambda c: c["id"])
def test_assumptions_block_shows_what_was_solved(solved, case):
    results = solved[1][case["id"]]["results"]
    block = results["assumptions"]
    assert block["elements"] == {"type": "C3D10", "order": 2, "description": "10-node quadratic tetrahedra"}
    assert block["mesh"]["max_element_size_mm"] == case["fea_setup"]["mesh_size_mm"]
    assert block["mesh"]["nodes"] > 0 and block["mesh"]["elements"] > 0
    assert block["mesh"]["mesher"].startswith("Gmsh ") and block["solver"]["version"] != "unknown"
    used = {k: v["value"] for k, v in block["material"]["values"].items()}
    assert {k: used[k] for k in case["material_values"]} == case["material_values"]
    setup = results["fea_setup_used"]
    for kind in ("fixed", "sliding"):
        given = [_canonical(f) for f in setup.get(f"{kind}_faces", [])]
        assert [s["selector"] for s in block["supports"] if s["kind"] == kind] == given
    assert [f["selector"] for load in block["loads"] for f in load["faces"]] == [
        _canonical(face) for load in setup.get("loads", []) for face in load["faces"]
    ]
    codes = {w["code"] for w in block["warnings"]}
    assert "first_order_elements" not in codes and "defaults_used" in codes


@live
def test_peak_stress_at_the_clamped_end_is_flagged_as_a_singularity(solved):
    results = solved[1]["cantilever_static"]["results"]
    codes = [w["code"] for w in results["assumptions"]["warnings"]]
    assert "stress_at_singularity" in codes
    assert results["max_von_mises_away_from_singularities_at_mm"][0] > 8
    assert "near_singularity" not in results["probes"][1]


@live
def test_the_load_along_the_thin_le1_edge_is_not_taken_for_a_concentrated_load(solved):
    """The loaded outer face is 50 mm thick but metres long. By area (about 0.24 m^2)
    it is less than (2 x 500 mm)^2; across it is far more than 2 x 500 mm."""
    for mesh, results in solved[1]["nafems_le1"]["runs"].items():
        codes = {w["code"] for w in results["assumptions"]["warnings"]}
        assert "load_singularity" not in codes, mesh
        assert "near_singularity" not in results["probes"][0], mesh


@live
def test_mesh_convergence_on_the_cantilever(solved):
    """Solves at 9, 6 and 4 mm; the tip deflection and the peak stress outside the
    18 mm zone at the fixed end both settle inside 2 %."""
    server = solved[0]
    cases.solve(server, CANTILEVER)
    conv = cases.reply(server.fea_convergence(timeout_s=900))
    assert [r["mesh_size_mm"] for r in conv["runs"]] == [9, 6, 4] and conv["excluded_within_mm"] == 18
    assert conv["converged_quantities"] == ["max_displacement_mm", "max_von_mises_away_mpa"]
    assert conv["converged"] is True and conv["not_converged"] == []
    for q in conv["quantities"].values():
        assert len(q["change_pct"]) == 2 and q["change_pct"][-1] < 2
    block = cases.reply(server.fea_results())["assumptions"]
    assert block["convergence"]["applies_to_this_mesh"] is True
    assert "convergence_not_checked" not in {w["code"] for w in block["warnings"]}


@live
def test_probes_return_stress_components_in_the_part_axes(solved):
    bore, outside = solved[1]["lame_cylinder"]["results"]["probes"]
    assert set(bore["stress_mpa"]) == {"xx", "yy", "zz", "xy", "xz", "yz"}
    # On the y = 0 plane x is radial: -p at the bore, zero outside; open ends, so no axial stress.
    assert bore["stress_mpa"]["xx"] == pytest.approx(-100, rel=0.02)
    assert abs(outside["stress_mpa"]["xx"]) < 1 and abs(bore["stress_mpa"]["zz"]) < 1


@live
def test_the_hole_edge_is_not_taken_for_a_singularity(solved):
    results = solved[1]["kirsch_plate"]["results"]
    assert "stress_at_singularity" not in {w["code"] for w in results["assumptions"]["warnings"]}
    assert results["max_von_mises_away_from_singularities_mpa"] == results["max_von_mises_mpa"]
    x, y, _ = results["max_von_mises_at_mm"]
    assert math.hypot(x, y) == pytest.approx(5, abs=0.01) and x == pytest.approx(0, abs=0.01)
    assert "near_singularity" not in results["probes"][0]


@live
def test_mesh_convergence_on_the_plate_with_a_hole(solved):
    """Solves at 2.25, 1.5 and 1 mm; the peak at the hole edge settles inside 2 %."""
    server = solved[0]
    cases.solve(server, BY_ID["kirsch_plate"])
    conv = cases.reply(server.fea_convergence(timeout_s=900))
    assert [r["mesh_size_mm"] for r in conv["runs"]] == [2.25, 1.5, 1]
    assert conv["converged"] is True and conv["not_converged"] == []
