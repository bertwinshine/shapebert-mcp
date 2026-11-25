import json
import math
import os
import re
import time
import types
from pathlib import Path

import pytest

from cadkit import fea


def test_material_table_and_aliases():
    assert fea.material("Steel")["E_mpa"] == 210000
    assert fea.material("aluminum")["name"] == "aluminium"
    assert fea.material("petg")["density_kg_m3"] == 1270
    with pytest.raises(ValueError, match="choose one of"):
        fea.material("titanium")


def test_every_material_has_thermal_values_and_plastics_say_typical():
    for name, props in fea.MATERIALS.items():
        assert props["k_w_mk"] > 0 and props["cp_j_kgk"] > 0 and 0 < props["alpha_1_k"] < 1e-3
        assert (props.get("thermal_values") == "typical") == (name in {"PETG", "PLA"})
    assert fea.material("aluminium")["alpha_1_k"] == 23.6e-6


FORCE = {"type": "force", "faces": ["Face2"], "value_n": 100, "direction": [0, 0, -1]}


def test_valid_setup_passes():
    pressure = {"type": "pressure", "faces": ["Face6"], "value_mpa": -0.2}
    loads = fea.check_setup("static", 3, fixed_faces=["Face1"], loads=[FORCE, pressure])["loads"]
    assert loads[0]["direction"] == [0.0, 0.0, -1.0] and loads[1]["value_mpa"] == -0.2


@pytest.mark.parametrize(
    "fixed, loads, size, message",
    [
        ([], [FORCE], 3, "fixed_faces"),
        (["Face1; import os"], [FORCE], 3, "unknown face selector"),
        (["Face1"], [], 3, "at least one load"),
        (["Face1"], [{**FORCE, "direction": [0, 0, 0]}], 3, "non-zero"),
        (["Face1"], [{**FORCE, "value_n": -5}], 3, "flip the direction"),
        (["Face1"], [{**FORCE, "type": "moment"}], 3, "'force' or 'pressure'"),
        (["Face1"], [FORCE], 0, "mesh_size_mm"),
        (["Face1"], [FORCE], 0.04, "0.05 mm minimum"),
    ],
)
def test_bad_setup_is_refused(fixed, loads, size, message):
    with pytest.raises(ValueError, match=message):
        fea.check_setup("static", size, fixed_faces=fixed, loads=loads)


def test_modal_setup_needs_no_loads_and_refuses_them():
    checked = fea.check_setup("modal", 3, 6, fixed_faces=["Face1"])
    assert checked["loads"] == [] and checked["fixed_faces"] == ["Face1"]
    with pytest.raises(ValueError, match=r"does not use \['loads'\]"):
        fea.check_setup("modal", 3, fixed_faces=["Face1"], loads=[FORCE])
    with pytest.raises(ValueError, match="between 1 and 50"):
        fea.check_setup("modal", 3, 0, fixed_faces=["Face1"])
    with pytest.raises(ValueError, match="analysis_type must be one of"):
        fea.check_setup("acoustic", 3, fixed_faces=["Face1"])


HOT = {"faces": ["Face1"], "temperature_c": 100}


def test_thermal_steady_needs_temperatures_and_no_mechanics():
    temps = fea.check_setup("thermal_steady", 3, temperatures=[HOT])["temperatures"]
    assert temps == [{"faces": ["Face1"], "temperature_c": 100.0}]
    with pytest.raises(ValueError, match="at least one face temperature"):
        fea.check_setup("thermal_steady", 3)
    with pytest.raises(ValueError, match=r"\['fixed_faces', 'loads'\]"):
        fea.check_setup("thermal_steady", 3, fixed_faces=["Face1"], loads=[FORCE], temperatures=[HOT])
    with pytest.raises(ValueError, match="absolute zero"):
        fea.check_setup("thermal_steady", 3, temperatures=[{**HOT, "temperature_c": -300}])
    with pytest.raises(ValueError, match=r"does not use \['temperatures'\]"):
        fea.check_setup("static", 3, fixed_faces=["Face1"], loads=[FORCE], temperatures=[HOT])


def test_thermal_transient_needs_temperatures_and_time():
    checked = fea.check_setup("thermal_transient", 3, temperatures=[HOT], time_end_s=1000, time_step_s=50)
    assert checked["time_end_s"] == 1000.0 and checked["time_step_s"] == 50.0
    with pytest.raises(ValueError, match="time_end_s and time_step_s"):
        fea.check_setup("thermal_transient", 3, temperatures=[HOT])
    with pytest.raises(ValueError, match="at most 500 time steps"):
        fea.check_setup("thermal_transient", 3, temperatures=[HOT], time_end_s=1000, time_step_s=1)
    with pytest.raises(ValueError, match="not be larger"):
        fea.check_setup("thermal_transient", 3, temperatures=[HOT], time_end_s=10, time_step_s=50)
    with pytest.raises(ValueError, match=r"does not use \['time_end_s'\]"):
        fea.check_setup("thermal_steady", 3, temperatures=[HOT], time_end_s=10)


def test_buckling_needs_supports_and_loads():
    checked = fea.check_setup("buckling", 3, 4, fixed_faces=["Face5"], loads=[FORCE])
    assert checked["loads"][0]["value_n"] == 100
    with pytest.raises(ValueError, match="at least one load"):
        fea.check_setup("buckling", 3, fixed_faces=["Face5"])
    with pytest.raises(ValueError, match="between 1 and 50"):
        fea.check_setup("buckling", 3, 99, fixed_faces=["Face5"], loads=[FORCE])
    assert set(fea.NOTES) == set(fea.ANALYSIS_TYPES)


def test_thermomechanical_needs_supports_and_temperatures_loads_optional():
    checked = fea.check_setup("thermomechanical", 3, sliding_faces=["Face1", "Face3"], temperatures=[HOT])
    assert checked["sliding_faces"] == ["Face1", "Face3"] and checked["loads"] == []
    with_load = fea.check_setup(
        "thermomechanical", 3, fixed_faces=["Face1"], loads=[FORCE], temperatures=[HOT]
    )
    assert with_load["loads"][0]["value_n"] == 100
    with pytest.raises(ValueError, match="or sliding_faces"):
        fea.check_setup("thermomechanical", 3, temperatures=[HOT])
    with pytest.raises(ValueError, match="at least one face temperature"):
        fea.check_setup("thermomechanical", 3, fixed_faces=["Face1"])


def test_analysis_names_are_plain_identifiers():
    assert fea.check_name("Bracket_FEA2") == "Bracket_FEA2"
    for bad in ("../x", "a b", "1st", "x" * 41):
        with pytest.raises(ValueError):
            fea.check_name(bad)


STATIC_DAT = """
                        S T E P       1

 total force (fx,fy,fz) for set FEA_FIXED and time  0.1000000E+01

        1.040884E-11  3.154366E-12  4.999779E+03
"""
BUCKLING_DAT = """
     B U C K L I N G   F A C T O R   O U T P U T

 MODE NO       BUCKLING
                FACTOR

      1   0.1728460E+04
      2   0.1728470E+04
"""
MODAL_DAT = """
     E I G E N V A L U E   O U T P U T

 MODE NO    EIGENVALUE                       FREQUENCY
                                     REAL PART            IMAGINARY PART
                           (RAD/TIME)      (CYCLES/TIME     (RAD/TIME)

      1   0.1234567E+08   0.3513642E+04   0.5592178E+03   0.0000000E+00
"""
STATIC_STA = """SUMMARY OF JOB INFORMATION
  STEP      INC     ATT  ITRS     TOT TIME     STEP TIME      INC TIME
     1          1     1     1  0.100000E+01  0.100000E+01  0.100000E+01
"""
EIGEN_STA = """SUMMARY OF JOB INFORMATION
  STEP      INC     ATT  ITRS     TOT TIME     STEP TIME      INC TIME
"""
FINISHED = """
 STEP            1

 Job finished
"""


@pytest.fixture
def tools():
    """fea_tools.py loaded as server.py ships it, with a stand-in for FreeCAD's console."""
    errors = []
    app = types.SimpleNamespace(Console=types.SimpleNamespace(PrintError=errors.append))
    ns = {"re": re, "os": os, "math": math, "App": app, "FEM_PARAMS": "Fem", "_obj": _object_not_found}
    src = (Path(fea.__file__).with_name("fea_tools.py")).read_text(encoding="utf-8")
    exec(compile(src, "fea_tools.py", "exec"), ns)
    ns["console_errors"] = errors
    return types.SimpleNamespace(**ns)


def _write_run(folder, dat, sta, age_s=0.0):
    base = str(folder / "FEA_Mesh")
    for suffix, text in ((".dat", dat), (".sta", sta), (".frd", "frd"), (".cvg", "")):
        Path(base + suffix).write_text(text, encoding="utf-8")
        if age_s:
            old = time.time() - age_s
            os.utime(base + suffix, (old, old))
    return base


def test_stale_static_dat_is_never_returned_as_a_buckling_result(tools, tmp_path):
    base = _write_run(tmp_path, STATIC_DAT, STATIC_STA, age_s=3600)
    problem = tools._solver_problem(base, 0, time.time(), FINISHED, "buckling")
    assert problem and "older than this run" in problem


def test_fresh_static_dat_without_buckling_factors_is_refused(tools, tmp_path):
    started = time.time()
    base = _write_run(tmp_path, STATIC_DAT, STATIC_STA)
    assert "no buckling factors" in tools._solver_problem(base, 0, started, FINISHED, "buckling")


def test_buckling_heading_without_factors_is_refused(tools, tmp_path):
    started = time.time()
    base = _write_run(tmp_path, "     B U C K L I N G   F A C T O R   O U T P U T\n", EIGEN_STA)
    assert "no buckling factors" in tools._solver_problem(base, 0, started, FINISHED, "buckling")


@pytest.mark.parametrize(
    "kind, dat, sta",
    [
        ("buckling", BUCKLING_DAT, EIGEN_STA),
        ("frequency", MODAL_DAT, EIGEN_STA),
        ("static", STATIC_DAT, STATIC_STA),
    ],
)
def test_a_complete_fresh_run_is_accepted(tools, tmp_path, kind, dat, sta):
    started = time.time()
    base = _write_run(tmp_path, dat, sta)
    assert tools._solver_problem(base, 0, started, FINISHED, kind) is None


@pytest.mark.parametrize(
    "exit_code, stdout, kind, dat, sta, message",
    [
        (1, FINISHED, "buckling", BUCKLING_DAT, EIGEN_STA, "exit code 1"),
        (0, " STEP 1\n", "buckling", BUCKLING_DAT, EIGEN_STA, "Job finished"),
        (0, FINISHED, "frequency", STATIC_DAT, EIGEN_STA, "no eigenvalues"),
        (0, FINISHED, "static", STATIC_DAT, EIGEN_STA, "no finished step"),
    ],
)
def test_unfinished_or_failed_runs_are_refused(tools, tmp_path, exit_code, stdout, kind, dat, sta, message):
    started = time.time()
    base = _write_run(tmp_path, dat, sta)
    assert message in tools._solver_problem(base, exit_code, started, stdout, kind)


def test_missing_result_file_is_refused(tools, tmp_path):
    started = time.time()
    base = _write_run(tmp_path, BUCKLING_DAT, EIGEN_STA)
    os.remove(base + ".frd")
    assert "no FEA_Mesh.frd" in tools._solver_problem(base, 0, started, FINISHED, "buckling")


def test_old_result_files_are_removed_but_the_input_is_kept(tools, tmp_path):
    base = _write_run(tmp_path, STATIC_DAT, STATIC_STA)
    Path(base + ".inp").write_text("*NODE", encoding="utf-8")
    tools._remove_old_results(base)
    tools._remove_old_results(base)  # nothing left to remove is fine
    assert sorted(p.name for p in tmp_path.iterdir()) == ["FEA_Mesh.inp"]


def test_failure_shows_the_last_30_lines_and_goes_to_the_listener_log(tools, tmp_path):
    base = str(tmp_path / "FEA_Mesh")
    stdout = "\n".join(f"line {i}" for i in range(1, 51))
    error = tools._solver_failure(base, "CalculiX stopped with exit code 2", stdout, "")
    text = str(error)
    assert "exit code 2" in text and "line 21" in text and "line 50" in text and "line 20\n" not in text
    assert tools.console_errors and "line 50" in tools.console_errors[0]


def test_failure_falls_back_to_the_sta_file_when_ccx_printed_nothing(tools, tmp_path):
    base = _write_run(tmp_path, "", STATIC_STA)
    assert "SUMMARY OF JOB INFORMATION" in str(tools._solver_failure(base, "x", "", ""))


def _object_not_found(name):
    raise RuntimeError(f"Object {name!r} not found")


def test_calculix_runs_single_threaded_unless_the_user_opts_in(monkeypatch):
    monkeypatch.delenv("FREECAD_MCP_CCX_THREADS", raising=False)
    assert fea.ccx_threads() == 1
    monkeypatch.setenv("FREECAD_MCP_CCX_THREADS", " 4 ")
    assert fea.ccx_threads() == 4


@pytest.mark.parametrize("value", ["0", "-2", "four", "2.5"])
def test_a_bad_thread_setting_is_refused(monkeypatch, value):
    monkeypatch.setenv("FREECAD_MCP_CCX_THREADS", value)
    with pytest.raises(ValueError, match="FREECAD_MCP_CCX_THREADS"):
        fea.ccx_threads()


def test_fea_run_passes_the_thread_count_to_freecad(monkeypatch, tmp_path):
    server = pytest.importorskip("server")
    calls = []
    monkeypatch.setenv("FREECAD_MCP_WORKDIR", str(tmp_path))
    monkeypatch.setattr(server, "_fc", lambda func, **kw: calls.append(kw) or {"ok": True})
    monkeypatch.delenv("FREECAD_MCP_CCX_THREADS", raising=False)
    server.fea_run("FEA")
    monkeypatch.setenv("FREECAD_MCP_CCX_THREADS", "6")
    server.fea_run("FEA")
    assert [c["threads"] for c in calls] == [1, 6]
    monkeypatch.setenv("FREECAD_MCP_CCX_THREADS", "all")
    reply = json.loads(server.fea_run("FEA"))
    assert reply["ok"] is False and "FREECAD_MCP_CCX_THREADS" in reply["error"] and len(calls) == 2


@pytest.fixture
def fake_run(monkeypatch):
    import subprocess

    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, "CalculiX Version 2.21, Copyright\n Job finished\n", "")

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_single_thread_settings_go_to_ccx_only(tools, fake_run, tmp_path, monkeypatch):
    monkeypatch.setenv("OMP_NUM_THREADS", "16")
    monkeypatch.delenv("CCX_NPROC_EQUATION_SOLVER", raising=False)
    before = dict(os.environ)
    code, stdout, _ = tools._run_ccx("/opt/ccx", str(tmp_path / "FEA_Mesh.inp"), 1)
    (args, kwargs) = fake_run[0]
    assert code == 0 and "Job finished" in stdout
    assert args == ["/opt/ccx", "-i", "FEA_Mesh"] and kwargs["cwd"] == str(tmp_path)
    assert kwargs["env"]["OMP_NUM_THREADS"] == "1" and kwargs["env"]["CCX_NPROC_EQUATION_SOLVER"] == "1"
    assert dict(os.environ) == before


def test_multithreaded_runs_leave_the_equation_solver_setting_alone(tools, fake_run, tmp_path, monkeypatch):
    monkeypatch.delenv("CCX_NPROC_EQUATION_SOLVER", raising=False)
    tools._run_ccx("ccx", str(tmp_path / "FEA_Mesh.inp"), 4)
    env = fake_run[0][1]["env"]
    assert env["OMP_NUM_THREADS"] == "4" and "CCX_NPROC_EQUATION_SOLVER" not in env


class FakeSolver:
    def __init__(self):
        self.PropertiesList = ["AnalysisType"]

    def addProperty(self, kind, name, group, doc):
        self.PropertiesList.append(name)
        setattr(self, name, 0 if kind == "App::PropertyInteger" else "")


def test_the_ccx_run_is_recorded_on_the_solver_for_fea_results(tools):
    solver = FakeSolver()
    assert tools._ccx_info(solver) is None
    info = tools._record_ccx(solver, "/usr/bin/ccx", "CalculiX Version 2.21, Copyright(C)", 1)
    assert info == {"binary": "/usr/bin/ccx", "version": "2.21", "threads": 1}
    assert tools._ccx_info(solver) == info
    tools._record_ccx(solver, "/usr/bin/ccx", "no banner", 4)
    assert tools._ccx_info(solver) == {"binary": "/usr/bin/ccx", "version": "unknown", "threads": 4}


class FakeDoc:
    def __init__(self, *objects):
        self.objects = [types.SimpleNamespace(Name=n, Label=label) for n, label in objects]

    def getObject(self, name):
        return next((o for o in self.objects if o.Name == name), None)

    def getObjectsByLabel(self, label):
        return [o for o in self.objects if o.Label == label]


@pytest.mark.parametrize(
    "objects",
    [
        [("Box", "Column"), ("Box001", "Column")],  # two objects share the label
        [("Column", "Plate"), ("Box001", "Column")],  # one's Name is the other's Label
    ],
)
def test_fea_setup_refuses_an_ambiguous_part(tools, objects):
    with pytest.raises(RuntimeError, match="matches several objects"):
        tools._unique_obj(FakeDoc(*objects), "Column")


def test_fea_setup_finds_a_part_by_name_or_label(tools):
    doc = FakeDoc(("Box", "Column"), ("Box001", "Plate"))
    assert tools._unique_obj(doc, "Column").Name == "Box"
    assert tools._unique_obj(doc, "Box001").Name == "Box001"
    with pytest.raises(RuntimeError, match="not found"):
        tools._unique_obj(doc, "Missing")


FACE = {"face": "Face1", "selector": "-X", "centre_mm": [0, 5, 5], "normal": [-1, 0, 0], "area_mm2": 100}


def _record(analysis_type="static", element="C3D10", **extra):
    setup = {
        "fixed_faces": [FACE],
        "sliding_faces": [],
        "loads": [{"type": "force", "value_n": 100.0, "direction": [0, 0, -1], "face_info": [FACE]}],
        "temperatures": [],
        "initial_temperature_c": None,
        "modes": None,
        "material": fea.material("steel"),
        "defaults": [],
        **extra.pop("setup", {}),
    }
    run = {
        "element_type": element,
        "nodes": 1200,
        "elements": 600,
        "mesh_size_mm": 3.0,
        "mesher": "Gmsh 4.15.0",
        "mesh_s": 0.5,
        "solve_s": 1.5,
    }
    return {"setup": setup, "run": run, "ccx": {"version": "2.22", "threads": 1}, **extra}


def _codes(block):
    return [w["code"] for w in block["warnings"]]


def test_block_lists_elements_mesh_material_supports_loads_units_and_solver():
    block = fea.assumptions("static", _record())
    assert block["elements"] == {"type": "C3D10", "order": 2, "description": "10-node quadratic tetrahedra"}
    assert block["mesh"] == {
        "max_element_size_mm": 3.0,
        "nodes": 1200,
        "elements": 600,
        "mesher": "Gmsh 4.15.0",
    }
    assert set(block["material"]["values"]) == {"E_mpa", "nu", "yield_mpa"}
    e = block["material"]["values"]["E_mpa"]
    assert e["value"] == 210000 and e["unit"] == "MPa" and e["source"]["type"] == "default"
    assert "S235" in e["source"]["where"]
    assert block["supports"] == [{"kind": "fixed", **FACE}]
    assert block["loads"] == [{"type": "force", "faces": [FACE], "value_n": 100.0, "direction": [0, 0, -1]}]
    assert block["units"]["stress"] == "MPa"
    assert block["solver"] == {
        "name": "CalculiX",
        "version": "2.22",
        "threads": 1,
        "mesh_s": 0.5,
        "solve_s": 1.5,
    }
    assert _codes(block) == ["convergence_not_checked", "defaults_used"]


@pytest.mark.parametrize(
    "analysis_type, keys",
    [
        ("modal", {"E_mpa", "nu", "density_kg_m3"}),
        ("buckling", {"E_mpa", "nu"}),
        ("thermal_steady", {"k_w_mk"}),
        ("thermal_transient", {"k_w_mk", "density_kg_m3", "cp_j_kgk"}),
        ("thermomechanical", {"E_mpa", "nu", "alpha_1_k", "k_w_mk", "yield_mpa"}),
    ],
)
def test_block_shows_the_material_values_each_analysis_uses(analysis_type, keys):
    assert set(fea.assumptions(analysis_type, _record(analysis_type))["material"]["values"]) == keys


def test_typical_plastic_thermal_values_say_so_in_their_source():
    values = fea.material_values(fea.material("PLA"), "thermal_transient")
    assert "typical value" in values["k_w_mk"]["source"]["where"]
    assert (
        "typical value" not in fea.material_values(fea.material("PLA"), "modal")["E_mpa"]["source"]["where"]
    )


def test_first_order_elements_are_warned_about():
    assert _codes(fea.assumptions("static", _record(element="C3D4")))[0] == "first_order_elements"
    assert _codes(fea.assumptions("static", _record(element="C3D20R")))[0] == "unknown_element_type"


def test_peak_stress_next_to_a_fixed_face_is_a_singularity_with_the_value_away_from_it():
    peak = {
        "max_von_mises_mpa": 151.3,
        "band_mm": 6.0,
        "near": {"kind": "fixed face", "distance_mm": 1.7},
        "away": {"max_von_mises_mpa": 142.4, "at_mm": [8.1, 3.3, 20]},
    }
    probes = [{"node_at_mm": [0, 10, 20], "near_singularity": {"kind": "fixed face", "distance_mm": 0.0}}]
    block = fea.assumptions("static", _record(peak_stress=peak, probes=probes))
    first, second = block["warnings"][:2]
    assert first["code"] == "stress_at_singularity"
    assert (
        "151.3 MPa" in first["message"]
        and "142.4 MPa" in first["message"]
        and "not a real" in first["message"]
    )
    assert second["code"] == "probe_at_singularity" and "Probe 1" in second["message"]
    clean = {**peak, "near": None}
    assert "stress_at_singularity" not in _codes(fea.assumptions("static", _record(peak_stress=clean)))


def _conv(*values, stress=None, sizes=(6.75, 4.5, 3.0)):
    """A stored convergence record; `stress` adds the peak away from flagged zones."""
    runs = []
    for i, (size, value) in enumerate(zip(sizes, values, strict=True)):
        row = {"max_displacement_mm": value}
        if stress:
            row["max_von_mises_away_mpa"] = stress[i]
        runs.append({"mesh_size_mm": size, "nodes": 100 * (i + 1), "elements": 50 * (i + 1), "values": row})
    return {"runs": runs, "excluded_within_mm": 13.5 if stress else None}


def test_convergence_compares_the_last_two_meshes_against_two_percent():
    ok = fea.convergence_summary(_conv(1.10, 1.04, 1.03), 3.0)
    disp = ok["quantities"]["max_displacement_mm"]
    assert disp["change_pct"] == [5.455, 0.962] and disp["converged"] and ok["converged"]
    assert ok["applies_to_this_mesh"] and ok["converged_quantities"] == ["max_displacement_mm"]
    assert "values" not in ok["runs"][0] and disp["values"] == [1.10, 1.04, 1.03]
    bad = fea.convergence_summary(_conv(1.0, 1.05, 1.08), 3.0)
    assert not bad["converged"] and bad["quantities"]["max_displacement_mm"]["change_pct"][
        -1
    ] == pytest.approx(2.857, abs=1e-3)
    assert not fea.convergence_summary(_conv(1.0, 1.0, 1.0), 2.0)["applies_to_this_mesh"]


def test_convergence_says_which_quantity_converged():
    conv = fea.convergence_summary(_conv(1.10, 1.04, 1.03, stress=(120.0, 131.0, 140.0)), 3.0)
    assert conv["converged_quantities"] == ["max_displacement_mm"]
    assert conv["not_converged"] == ["max_von_mises_away_mpa"] and conv["converged"] is False
    assert conv["excluded_within_mm"] == 13.5
    block = fea.assumptions(
        "static", _record(convergence=_conv(1.10, 1.04, 1.03, stress=(120.0, 131.0, 140.0)))
    )
    warning = next(w for w in block["warnings"] if w["code"] == "mesh_not_converged")
    assert "max_von_mises_away_mpa changed 6.87 %" in warning["message"]
    assert "Converged: max_displacement_mm" in warning["message"]
    missing = fea.convergence_summary(_conv(1.10, 1.04, 1.03, stress=(120.0, 131.0, None)), 3.0)
    assert missing["quantities"]["max_von_mises_away_mpa"]["change_pct"] == [9.167, None]
    assert missing["not_converged"] == ["max_von_mises_away_mpa"]


@pytest.mark.parametrize(
    "values, mesh_mm, code",
    [
        ((1.10, 1.04, 1.03), 3.0, None),
        ((1.0, 1.05, 1.08), 3.0, "mesh_not_converged"),
        ((1.10, 1.04, 1.03), 2.0, "convergence_not_checked"),  # checked on another mesh
    ],
)
def test_block_reports_the_convergence_verdict(values, mesh_mm, code):
    record = _record(convergence=_conv(*values))
    record["run"]["mesh_size_mm"] = mesh_mm
    codes = [c for c in _codes(fea.assumptions("static", record)) if "converge" in c]
    assert codes == ([code] if code else [])


@pytest.mark.parametrize(
    "flagged, text",
    [
        (
            {"load": "FEA_Force1", "element": "Face2", "kind": "small loaded face", "area_mm2": 16.0},
            "Face2, a face of 16.0 mm^2, smaller than (2 x mesh size)^2 = 64.0 mm^2",
        ),
        (
            {"load": "FEA_Force1", "element": "Edge3", "kind": "load on an edge", "area_mm2": None},
            "Edge3 (load on an edge)",
        ),
        (
            {"load": "FEA_Force2", "element": "Vertex1", "kind": "load on a vertex", "area_mm2": None},
            "Vertex1",
        ),
    ],
)
def test_a_concentrated_load_is_flagged_as_a_singularity(flagged, text):
    peak = {"max_von_mises_mpa": 90.0, "band_mm": 8.0, "near": None, "away": None}
    block = fea.assumptions("static", _record(flagged_loads=[flagged], peak_stress=peak))
    warning = block["warnings"][0]
    assert warning["code"] == "load_singularity" and text in warning["message"]
    assert "singular" in warning["message"] and "outside 8.0 mm" in warning["message"]


def test_a_load_spread_over_a_large_face_is_not_flagged():
    peak = {"max_von_mises_mpa": 90.0, "band_mm": 8.0, "near": None, "away": None}
    assert "load_singularity" not in _codes(
        fea.assumptions("static", _record(flagged_loads=[], peak_stress=peak))
    )


def test_peak_next_to_a_small_loaded_face_names_it():
    peak = {
        "max_von_mises_mpa": 400.0,
        "band_mm": 8.0,
        "near": {"kind": "small loaded face", "distance_mm": 0.5},
        "away": {"max_von_mises_mpa": 150.0, "at_mm": [100, 10, 20]},
    }
    block = fea.assumptions("static", _record(peak_stress=peak))
    message = next(w["message"] for w in block["warnings"] if w["code"] == "stress_at_singularity")
    assert "from a small loaded face" in message and "150.0 MPa" in message


def test_defaulted_initial_temperature_is_named_only_where_it_matters():
    setup = {"initial_temperature_c": 20.0, "defaults": ["initial_temperature_c"]}
    thermo = fea.assumptions("thermomechanical", _record("thermomechanical", setup=setup))
    assert thermo["initial_temperature_c"]["source"]["type"] == "default"
    defaults = thermo["warnings"][-1]
    assert defaults["code"] == "defaults_used" and "20.0 °C" in defaults["message"]
    assert "E_mpa 210000 MPa" in defaults["message"]
    steady = fea.assumptions("thermal_steady", _record("thermal_steady", setup=setup))
    assert "°C" not in steady["warnings"][-1]["message"]
    given = fea.assumptions(
        "thermomechanical", _record("thermomechanical", setup={"initial_temperature_c": 25.0})
    )
    assert given["initial_temperature_c"] == {
        "value": 25.0,
        "source": {"type": "input", "where": "initial_temperature_c given to fea_setup"},
    }


def test_an_analysis_without_records_says_so():
    assert _codes(fea.assumptions("static", {"setup": None, "run": None, "ccx": None})) == ["record_missing"]


def test_element_type_is_read_from_the_calculix_input(tools, tmp_path):
    inp = tmp_path / "FEA_Mesh.inp"
    inp.write_text("*Node\n1, 0, 0, 0\n*Element, TYPE=C3D10, ELSET=Evolumes\n1, 1\n", encoding="utf-8")
    assert tools._element_type(str(inp)) == "C3D10"
    inp.write_text("*NODE\n", encoding="utf-8")
    assert tools._element_type(str(inp)) == "unknown"


def test_a_missing_program_has_an_unknown_version(tools, tmp_path):
    assert tools._program_version("") == "unknown"
    assert tools._program_version(str(tmp_path / "gmsh.exe")) == "unknown"


def test_fea_results_turns_the_record_into_the_assumptions_block(monkeypatch):
    server = pytest.importorskip("server")
    calls = []

    def fake_fc(func, **kw):
        calls.append(kw)
        return {"analysis_type": "static", "material": "steel", "probes": [], "record": _record()}

    monkeypatch.setattr(server, "_fc", fake_fc)
    reply = json.loads(server.fea_results("FEA"))
    assert "record" not in reply and reply["assumptions"]["elements"]["type"] == "C3D10"
    assert calls[0]["band_mesh_sizes"] == fea.SINGULARITY_BAND_MESH_SIZES


def test_fea_setup_marks_a_missing_initial_temperature_as_a_default(monkeypatch):
    server = pytest.importorskip("server")
    calls = []
    monkeypatch.setattr(server, "_fc", lambda func, **kw: calls.append(kw) or {"ok": True})
    setup = {
        "part": "Bar",
        "material": "steel",
        "fixed_faces": ["Face1"],
        "mesh_size_mm": 3,
        "analysis_type": "thermomechanical",
        "temperatures": [{"faces": ["Face1"], "temperature_c": 120}],
    }
    server.fea_setup(**setup)
    server.fea_setup(**setup, initial_temperature_c=25)
    assert [(c["defaults"], c["initial_temperature_c"]) for c in calls] == [
        (["initial_temperature_c"], 20.0),
        ([], 25.0),
    ]


def test_fea_convergence_sends_the_refinement_and_summarises_the_runs(monkeypatch, tmp_path):
    server = pytest.importorskip("server")
    calls = []
    monkeypatch.setenv("FREECAD_MCP_WORKDIR", str(tmp_path))
    monkeypatch.delenv("FREECAD_MCP_CCX_THREADS", raising=False)

    def fake_fc(func, **kw):
        calls.append((func, kw))
        return {"analysis": "FEA", **_conv(1.10, 1.04, 1.03, stress=(120.0, 121.0, 121.5))}

    monkeypatch.setattr(server, "_fc", fake_fc)
    reply = json.loads(server.fea_convergence("FEA"))
    func, kw = calls[0]
    assert func == "fea_convergence" and kw["factor"] == 1.5 and kw["meshes"] == 3 and kw["threads"] == 1
    assert kw["band_mesh_sizes"] == fea.SINGULARITY_BAND_MESH_SIZES
    assert reply["converged"] is True and reply["converged_quantities"] == [
        "max_displacement_mm",
        "max_von_mises_away_mpa",
    ]
    assert reply["quantities"]["max_displacement_mm"]["change_pct"] == [5.455, 0.962]
    assert reply["excluded_within_mm"] == 13.5 and "applies_to_this_mesh" not in reply
