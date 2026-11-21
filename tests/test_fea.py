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
        (["Face1; import os"], [FORCE], 3, "not face names"),
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
    """fea_tools.py loaded as server.py ships it, with stand-ins for FreeCAD's console
    and its FEM preferences (prefs["cpus"] is the AnalysisNumCPUs setting)."""
    errors, prefs = [], {"cpus": 1}
    params = types.SimpleNamespace(GetInt=lambda key, default: prefs["cpus"])
    app = types.SimpleNamespace(
        Console=types.SimpleNamespace(PrintError=errors.append), ParamGet=lambda path: params
    )
    ns = {"re": re, "os": os, "math": math, "App": app, "FEM_PARAMS": "Fem", "_obj": _object_not_found}
    src = (Path(fea.__file__).with_name("fea_tools.py")).read_text(encoding="utf-8")
    exec(compile(src, "fea_tools.py", "exec"), ns)
    ns["console_errors"], ns["prefs"] = errors, prefs
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


@pytest.mark.parametrize("kind", ["buckling", "frequency"])
def test_eigenvalue_runs_use_one_thread(tools, kind):
    tools.prefs["cpus"] = 8
    assert tools._ccx_threads(kind) == 1


def test_static_and_thermal_runs_keep_freecads_thread_choice(tools):
    assert tools._ccx_threads("static") == (os.cpu_count() or 1)
    tools.prefs["cpus"] = 3
    assert tools._ccx_threads("thermomech") == 3


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
