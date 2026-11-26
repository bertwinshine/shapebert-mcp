"""FEA reference cases: setup from each case folder, analytical values from the formulas here."""

import datetime
import json
import math
import platform
from pathlib import Path

import replies

HERE = Path(__file__).resolve().parent
FIXTURE_REL_TOL = 1e-6
FIXTURE_ABS_TOL = 1e-9


def load_cases() -> list[dict]:
    cases = []
    for path in sorted(HERE.glob("*/case.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        cases.append({"id": path.parent.name, **case})
    return cases


def modelled(all_cases: list[dict]) -> list[dict]:
    """Cases the FEA tools can set up; the others carry a `not_modelled` reason."""
    return [c for c in all_cases if "not_modelled" not in c]


def load_fixture(case_id: str) -> dict:
    path = HERE / case_id / "fixture.json"
    if not path.exists():
        return {"environments": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _box(case):
    return case["box_mm"]


def _second_moment(case):
    """I about the bending axis of a b x h section (load along z, so h is the z size)."""
    _, b, h = _box(case)
    return b * h**3 / 12


def _area(case):
    _, b, h = _box(case)
    return b * h


def _force(case):
    return case["fea_setup"]["loads"][0]["value_n"]


def _mat(case, key):
    return case["material_values"][key]


def _probe(res, i):
    return res["probes"][i]


def clamped_free_eigenvalue(mode: int = 1) -> float:
    """Root of cos(x) cosh(x) + 1 = 0, the clamped-free beam's frequency parameter."""
    # One root in each interval ((n - 1) pi, n pi).
    lo, hi = (mode - 1) * math.pi, mode * math.pi
    f = lambda x: math.cos(x) * math.cosh(x) + 1  # noqa: E731
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(lo) * f(mid) > 0 else (lo, mid)
    return (lo + hi) / 2


def _tip_deflection(case, res):
    length = _box(case)[0]
    return _force(case) * length**3 / (3 * _mat(case, "E_mpa") * _second_moment(case))


def _bending_stress(case, res):
    # At the probe's node, which can sit up to a mesh size from mid-length.
    x, _, z = _probe(res, 1)["node_at_mm"]
    length, _, h = _box(case)
    return _force(case) * (length - x) * abs(z - h / 2) / _second_moment(case)


def _axial_stress(case, res):
    return _force(case) / _area(case)


def _elongation(case, res):
    return _force(case) * _box(case)[0] / (_mat(case, "E_mpa") * _area(case))


def _first_bending_hz(case, res):
    length = _box(case)[0]
    rho = _mat(case, "density_kg_m3") * 1e-12  # t/mm^3 keeps N, mm, MPa consistent
    lam = clamped_free_eigenvalue(1)
    return (
        lam**2
        / (2 * math.pi)
        * math.sqrt(_mat(case, "E_mpa") * _second_moment(case) / (rho * _area(case) * length**4))
    )


def _euler_fixed_free(case, res):
    length = _box(case)[0]
    return math.pi**2 * _mat(case, "E_mpa") * _second_moment(case) / (4 * length**2)


def _temps(case):
    hot, cold = (t["temperature_c"] for t in case["fea_setup"]["temperatures"])
    return hot, cold


def _temperature_at(i):
    def formula(case, res):
        hot, cold = _temps(case)
        x = _probe(res, i)["node_at_mm"][0]
        return hot - (hot - cold) * x / _box(case)[0]

    return formula


def _temperature_span(case, res):
    hot, cold = _temps(case)
    return hot - cold


def _heat_flow(case, res):
    hot, cold = _temps(case)
    area_m2 = _area(case) * 1e-6
    return _mat(case, "k_w_mk") * area_m2 * (hot - cold) / (_box(case)[0] * 1e-3)


def _delta_t(case):
    return case["fea_setup"]["temperatures"][0]["temperature_c"] - case["fea_setup"]["initial_temperature_c"]


def _thermal_elongation(case, res):
    return _mat(case, "alpha_1_k") * _delta_t(case) * _box(case)[0]


def _clamped_thermal_stress(case, res):
    return _mat(case, "E_mpa") * _mat(case, "alpha_1_k") * _delta_t(case)


def _zero(case, res):
    return 0.0


def _published(quantity_id):
    def value(case, res):
        return next(q for q in case["quantities"] if q["id"] == quantity_id)["published_value"]

    return value


def _remote_stress(case):
    """The pull on the loaded end (a negative pressure pulls)."""
    return -case["fea_setup"]["loads"][0]["value_mpa"]


def _kirsch_peak(case, res):
    # Kirsch: s_theta at the hole edge = s (1 - 2 cos 2 theta); theta = 90 deg is across the load.
    return _remote_stress(case) * (1 - 2 * math.cos(2 * math.pi / 2))


def _lame_constants(case):
    geo = case["geometry"]
    a, b = geo["inner_radius_mm"], geo["outer_radius_mm"]
    p = case["fea_setup"]["loads"][0]["value_mpa"]
    return a, b, p * a**2 / (b**2 - a**2), p * a**2 * b**2 / (b**2 - a**2)


def _lame_radial_displacement(at):
    """u(r) = ((1 - nu) A r + (1 + nu) B / r) / E: open ends, so the axial stress is zero."""

    def formula(case, res):
        a, b, big_a, big_b = _lame_constants(case)
        r = {"inner": a, "outer": b}[at]
        nu, e = _mat(case, "nu"), _mat(case, "E_mpa")
        return ((1 - nu) * big_a * r + (1 + nu) * big_b / r) / e

    return formula


def _lame_hoop_inner(case, res):
    a, _, big_a, big_b = _lame_constants(case)
    return big_a + big_b / a**2


# quantity id -> (FEA value from the fea_results reply, analytical value, value the
# error is relative to; None means the analytical value itself).
QUANTITIES = {
    "cantilever_static": {
        "tip_deflection_mm": (lambda r: -_probe(r, 0)["displacement_mm"][2], _tip_deflection, None),
        "bending_stress_mid_mpa": (lambda r: _probe(r, 1)["von_mises_mpa"], _bending_stress, None),
    },
    "tension_bar": {
        "axial_stress_mpa": (lambda r: _probe(r, 0)["von_mises_mpa"], _axial_stress, None),
        "elongation_mm": (lambda r: _probe(r, 1)["displacement_mm"][0], _elongation, None),
    },
    "cantilever_modal": {
        "mode1_hz": (lambda r: r["modes"][0]["frequency_hz"], _first_bending_hz, None),
        "mode2_hz": (lambda r: r["modes"][1]["frequency_hz"], _first_bending_hz, None),
    },
    "cantilever_buckling": {
        "critical_load_mode1_n": (lambda r: r["modes"][0]["critical_load_n"], _euler_fixed_free, None),
        "critical_load_mode2_n": (lambda r: r["modes"][1]["critical_load_n"], _euler_fixed_free, None),
    },
    "thermal_bar": {
        "temperature_x25_c": (lambda r: _probe(r, 0)["temperature_c"], _temperature_at(0), _temperature_span),
        "temperature_x50_c": (lambda r: _probe(r, 1)["temperature_c"], _temperature_at(1), _temperature_span),
        "temperature_x75_c": (lambda r: _probe(r, 2)["temperature_c"], _temperature_at(2), _temperature_span),
        "heat_flow_w": (lambda r: r["heat_flow_by_face"][0]["heat_flow_in_w"], _heat_flow, None),
    },
    "thermomech_free_bar": {
        "elongation_mm": (lambda r: _probe(r, 0)["displacement_mm"][0], _thermal_elongation, None),
        "max_von_mises_mpa": (lambda r: r["max_von_mises_mpa"], _zero, _clamped_thermal_stress),
    },
    "nafems_le1": {
        "sigma_yy_d_coarse_mpa": (
            lambda r: _probe(r, 0)["stress_mpa"]["yy"],
            _published("sigma_yy_d_coarse_mpa"),
            None,
        ),
        "sigma_yy_d_fine_mpa": (
            lambda r: _probe(r, 0)["stress_mpa"]["yy"],
            _published("sigma_yy_d_fine_mpa"),
            None,
        ),
    },
    "nafems_le10": {
        "sigma_yy_d_mpa": (lambda r: _probe(r, 0)["stress_mpa"]["yy"], _published("sigma_yy_d_mpa"), None),
    },
    "kirsch_plate": {
        "hole_edge_stress_mpa": (lambda r: _probe(r, 0)["stress_mpa"]["xx"], _kirsch_peak, None),
        "peak_stress_away_mpa": (
            lambda r: r["max_von_mises_away_from_singularities_mpa"],
            _kirsch_peak,
            None,
        ),
    },
    "lame_cylinder": {
        "radial_displacement_inner_mm": (
            lambda r: _probe(r, 0)["displacement_mm"][0],
            _lame_radial_displacement("inner"),
            None,
        ),
        "radial_displacement_outer_mm": (
            lambda r: _probe(r, 1)["displacement_mm"][0],
            _lame_radial_displacement("outer"),
            None,
        ),
        "hoop_stress_inner_mpa": (lambda r: _probe(r, 0)["stress_mpa"]["yy"], _lame_hoop_inner, None),
    },
}


def _kirsch_inputs(case):
    geo = case["geometry"]
    return {
        "remote_stress_mpa": _remote_stress(case),
        "hole_diameter_mm": geo["hole_diameter_mm"],
        "plate_width_mm": 2 * geo["half_width_mm"],
    }


def _lame_inputs(case):
    a, b, *_ = _lame_constants(case)
    return {
        "inner_radius_mm": a,
        "outer_radius_mm": b,
        "inner_pressure_mpa": case["fea_setup"]["loads"][0]["value_mpa"],
    }


# quantity id -> (calc_hand_check case, its inputs from the case, result key); only
# where a closed-form check applies.
HAND_CHECKS = {
    "kirsch_plate": {
        "hole_edge_stress_mpa": ("kirsch_hole", _kirsch_inputs, "peak_stress_mpa"),
        "peak_stress_away_mpa": ("kirsch_hole", _kirsch_inputs, "peak_stress_mpa"),
    },
    "lame_cylinder": {
        "hoop_stress_inner_mpa": ("thick_cylinder", _lame_inputs, "hoop_stress_inner_mpa"),
    },
}


def environment(server, results: dict) -> str:
    """FreeCAD, CalculiX and Gmsh versions and the OS: a frozen result holds only here."""
    freecad = json.loads(server.doctor()).get("freecad_version", "unknown")
    block = results["assumptions"]
    return f"FreeCAD {freecad}, CalculiX {block['solver']['version']}, {block['mesh']['mesher']}, {platform.system()}"


def fresh_document(server) -> None:
    server.run_freecad_code(
        "for n in list(App.listDocuments()):\n    App.closeDocument(n)\n"
        "App.newDocument('MCP_Validation'); App.setActiveDocument('MCP_Validation')"
    )


def reply(text: str) -> dict:
    out = replies.load(text)
    if out.get("ok") is False:
        raise RuntimeError(out.get("error"))
    return out


ELLIPTIC_PLATE = """import Part
def _elliptic_prism(a, b):
    edge = Part.Ellipse(App.Vector(0, 0, 0), a, b).toShape()
    return Part.Face(Part.Wire(edge)).extrude(App.Vector(0, 0, {t}))
quadrant = Part.makeBox(2 * {a2}, 2 * {b2}, {t})
shape = _elliptic_prism({a2}, {b2}).cut(_elliptic_prism({a1}, {b1})).common(quadrant)
App.ActiveDocument.addObject("Part::Feature", "Part").Shape = shape
App.ActiveDocument.recompute()
"""


def _elliptic_quarter_plate(server, geo):
    (a1, b1), (a2, b2) = geo["inner_semi_axes_mm"], geo["outer_semi_axes_mm"]
    code = ELLIPTIC_PLATE.format(a1=a1, b1=b1, a2=a2, b2=b2, t=geo["thickness_mm"])
    reply(server.run_freecad_code(code))


def _plate_with_hole(server, geo):
    t = geo["thickness_mm"]
    reply(server.create_box(geo["half_length_mm"], geo["half_width_mm"], t, name="Plate"))
    reply(server.create_cylinder(geo["hole_diameter_mm"] / 2, t, name="Hole"))
    reply(server.boolean("cut", "Plate", ["Hole"], name="Part"))


def _quarter_tube(server, geo):
    a, b, length = geo["inner_radius_mm"], geo["outer_radius_mm"], geo["length_mm"]
    reply(server.create_cylinder(b, length, name="Outer"))
    reply(server.create_box(b, b, length, name="Quadrant"))
    reply(server.boolean("common", "Outer", ["Quadrant"], name="Quarter"))
    reply(server.create_cylinder(a, length, name="Bore"))
    reply(server.boolean("cut", "Quarter", ["Bore"], name="Part"))


BUILDERS = {
    "elliptic_quarter_plate": _elliptic_quarter_plate,
    "plate_with_hole": _plate_with_hole,
    "quarter_tube": _quarter_tube,
}
# No selector picks an elliptic face, so the case names this placeholder and solve()
# puts in the face list_faces reports as the largest non-planar one.
LARGEST_CURVED_FACE = "<largest curved face>"


def _largest_curved_face(server) -> str:
    faces = reply(server.list_faces("Part"))["faces"]
    return max((f for f in faces if f["type"] != "plane"), key=lambda f: f["area_mm2"])["name"]


def _resolved_setup(server, case: dict, mesh_size_mm: float) -> dict:
    setup = {**case["fea_setup"], "mesh_size_mm": mesh_size_mm}
    if any(LARGEST_CURVED_FACE in load["faces"] for load in setup.get("loads", [])):
        face = _largest_curved_face(server)
        setup["loads"] = [
            {**load, "faces": [face if f == LARGEST_CURVED_FACE else f for f in load["faces"]]}
            for load in setup["loads"]
        ]
    return setup


def mesh_sizes(case: dict) -> list[float]:
    """Every mesh size the case's quantities are read at; the setup's own one first."""
    main = case["fea_setup"]["mesh_size_mm"]
    return [main] + sorted(
        {q["mesh_size_mm"] for q in case["quantities"] if q.get("mesh_size_mm", main) != main}
    )


def solve(server, case: dict, mesh_size_mm: float | None = None) -> dict:
    """Build the case's part, solve it with the ShapeBert tools and return fea_results,
    with the setup that was sent under `fea_setup_used`."""
    fresh_document(server)
    if "box_mm" in case:
        reply(server.create_box(*case["box_mm"], name="Part"))
    else:
        BUILDERS[case["geometry"]["kind"]](server, case["geometry"])
    setup = _resolved_setup(server, case, mesh_size_mm or case["fea_setup"]["mesh_size_mm"])
    reply(server.fea_setup("Part", case["material"], **setup))
    reply(server.fea_run(timeout_s=600))
    return {**reply(server.fea_results(probes=case.get("probes"))), "fea_setup_used": setup}


def solve_all(server, case: dict) -> dict[float, dict]:
    """fea_results at every mesh size the case asks for, keyed by mesh size."""
    return {mesh: solve(server, case, mesh) for mesh in mesh_sizes(case)}


def hand_check(server, case: dict, quantity_id: str) -> dict | None:
    """calc_hand_check's value for a quantity, or None where no closed form applies."""
    entry = HAND_CHECKS.get(case["id"], {}).get(quantity_id)
    if entry is None:
        return None
    name, inputs, key = entry
    out = reply(server.calc_hand_check(name, inputs(case)))
    return {"case": name, "value": out["results"][key], "source": out.get("source")}


def compare(case: dict, runs: dict[float, dict], server=None) -> list[dict]:
    """One row per quantity; `runs` maps mesh size to fea_results (see solve_all).
    With `server`, rows also carry the calc_hand_check value where one applies."""
    rows = []
    main = case["fea_setup"]["mesh_size_mm"]
    for spec in case["quantities"]:
        mesh = spec.get("mesh_size_mm", main)
        results = runs[mesh]
        fea_value, analytical, reference = QUANTITIES[case["id"]][spec["id"]]
        expected = analytical(case, results)
        measured = fea_value(results)
        base = reference(case, results) if reference else expected
        error = abs(measured - expected) / abs(base) * 100
        rows.append(
            {
                **spec,
                "mesh_size_mm": mesh,
                "analytical": expected,
                "fea": measured,
                "error_pct": error,
                "passed": error <= spec["tolerance_pct"],
                "hand": hand_check(server, case, spec["id"]) if server else None,
            }
        )
    return rows


def frozen_mismatches(case_id: str, env: str, rows: list[dict]) -> list[str] | None:
    """Quantities that moved beyond the tight band; None when nothing is frozen for `env`."""
    frozen = load_fixture(case_id)["environments"].get(env)
    if frozen is None:
        return None
    out = []
    for row in rows:
        old = frozen["values"].get(row["id"])
        if old is None or not math.isclose(row["fea"], old, rel_tol=FIXTURE_REL_TOL, abs_tol=FIXTURE_ABS_TOL):
            out.append(f"{row['id']}: frozen {old}, now {row['fea']}")
    return out


def freeze(case_id: str, env: str, rows: list[dict], reason: str) -> None:
    """Accept this run's FEA values as the frozen result for `env`."""
    fixture = load_fixture(case_id)
    fixture["environments"][env] = {
        "frozen": datetime.date.today().isoformat(),
        "reason": reason,
        "values": {row["id"]: row["fea"] for row in rows},
    }
    path = HERE / case_id / "fixture.json"
    path.write_text(json.dumps(fixture, indent=1, sort_keys=True) + "\n", encoding="utf-8")
