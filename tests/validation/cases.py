"""FEA reference cases: setup from each case folder, analytical values from the formulas here."""

import datetime
import json
import math
import platform
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE_REL_TOL = 1e-6
FIXTURE_ABS_TOL = 1e-9


def load_cases() -> list[dict]:
    cases = []
    for path in sorted(HERE.glob("*/case.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        cases.append({"id": path.parent.name, **case})
    return cases


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
    out = json.loads(text)
    if out.get("ok") is False:
        raise RuntimeError(out.get("error"))
    return out


def solve(server, case: dict) -> dict:
    """Build the case's part, solve it with the ShapeBert tools and return fea_results."""
    fresh_document(server)
    reply(server.create_box(*case["box_mm"], name="Part"))
    reply(server.fea_setup("Part", case["material"], **case["fea_setup"]))
    reply(server.fea_run(timeout_s=600))
    return reply(server.fea_results(probes=case.get("probes")))


def compare(case: dict, results: dict) -> list[dict]:
    rows = []
    for spec in case["quantities"]:
        fea_value, analytical, reference = QUANTITIES[case["id"]][spec["id"]]
        expected = analytical(case, results)
        measured = fea_value(results)
        base = reference(case, results) if reference else expected
        error = abs(measured - expected) / abs(base) * 100
        rows.append(
            {
                **spec,
                "analytical": expected,
                "fea": measured,
                "error_pct": error,
                "passed": error <= spec["tolerance_pct"],
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
