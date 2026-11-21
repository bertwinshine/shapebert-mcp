"""Off switch for free-form code, the work-folder limit and the code log."""

import json
import re
from pathlib import Path

import pytest

from cadkit import safety

server = pytest.importorskip("server")


@pytest.fixture
def work(tmp_path, monkeypatch):
    monkeypatch.setenv("FREECAD_MCP_WORKDIR", str(tmp_path / "work"))
    return (tmp_path / "work").resolve()


def test_code_is_off_unless_switched_on(monkeypatch):
    monkeypatch.delenv("FREECAD_MCP_ALLOW_CODE", raising=False)
    reply = json.loads(server.run_freecad_code("result = 1"))
    assert reply["ok"] is False and "switched off" in reply["error"]


def test_saving_a_verified_example_needs_code_switched_on(monkeypatch):
    monkeypatch.delenv("FREECAD_MCP_ALLOW_CODE", raising=False)
    reply = json.loads(server.save_example("t", "p", "result = 1"))
    assert reply["ok"] is False and "switched off" in reply["error"]


@pytest.mark.parametrize("value", ["0", "", "no", "false"])
def test_only_clear_yes_values_switch_code_on(monkeypatch, value):
    monkeypatch.setenv("FREECAD_MCP_ALLOW_CODE", value)
    assert not safety.code_allowed()


def test_relative_paths_land_in_the_work_folder(work):
    assert safety.safe_path("parts/plate.step", safety.MODEL_FILES) == work / "parts" / "plate.step"


@pytest.mark.parametrize("path", ["../outside.step", "parts/../../outside.step"])
def test_paths_cannot_climb_out_of_the_work_folder(work, path):
    with pytest.raises(safety.SafetyError):
        safety.safe_path(path, safety.MODEL_FILES)


def test_absolute_paths_outside_the_work_folder_are_refused(work, tmp_path):
    with pytest.raises(safety.SafetyError):
        safety.safe_path(str(tmp_path / "elsewhere.step"), safety.MODEL_FILES)


def test_symlinks_cannot_point_out_of_the_work_folder(work, tmp_path):
    (tmp_path / "secret").mkdir()
    work.mkdir(parents=True, exist_ok=True)
    try:
        (work / "link").symlink_to(tmp_path / "secret", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks need extra rights on this system")
    with pytest.raises(safety.SafetyError):
        safety.safe_path("link/x.step", safety.MODEL_FILES)


def test_only_listed_file_types_are_allowed(work):
    with pytest.raises(safety.SafetyError):
        safety.safe_path("notes.py", safety.MODEL_FILES)


def test_export_outside_the_work_folder_is_refused_before_freecad_is_called(work):
    reply = json.loads(server.export_model("../../etc/x.stl"))
    assert reply["ok"] is False and "outside the work folder" in reply["error"]


def test_free_form_code_is_logged(work):
    safety.log_code("run_freecad_code", "result = 42")
    record = json.loads((work / "logs" / "code_log.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["code"] == "result = 42" and len(record["sha256"]) == 64


@pytest.mark.parametrize(
    "code",
    [
        "import os\nos.remove('x')",
        "import subprocess",
        "from urllib.request import urlopen",
        "import socket as s",
        "open('../secret.txt').read()",
        "eval('1')",
        "__import__('os')",
        "().__class__.__bases__[0].__subclasses__()",
    ],
)
def test_system_access_is_found(code):
    assert safety.system_access(code)


@pytest.mark.parametrize(
    "code",
    [
        "import nt",
        "import posix",
        "import asyncio",
        "import code",
        "import io",
        "import _io",
        "import codecs",
        "import operator",
        "import linecache",
        "import sqlite3",
        "import zipfile",
        "import xmlrpc.client",
        "import concurrent.futures",
        "import numpy",
        "from numpy import ctypeslib",
        "from . import helper",
        "FreeCADGui.doCommand('x')",
        "Gui.doCommand('x')",
        "Gui.runCommand('Std_Macro')",
        "run = Gui.doCommandGui",
        "getattr(print, ''.join(['__','self','__']))",
        "vars(print)",
        "dir(print)",
        "locals()",
        "print.__self__",
        "from FreeCAD import __builtins__",
        "import collections\ncollections._sys.modules['os']",
        "import random\nrandom._os.system('x')",
        "import typing\ntyping.get_type_hints(f)",
    ],
)
def test_anything_outside_the_allow_list_is_refused(code):
    assert safety.system_access(code)


EXAMPLE_DIRS = [Path(__file__).parent.parent / d / "examples" for d in ("knowledge", "knowledge-private")]
SAVED_EXAMPLES = sorted(p for d in EXAMPLE_DIRS if d.is_dir() for p in d.glob("*.md"))


@pytest.mark.parametrize("path", SAVED_EXAMPLES, ids=lambda p: p.name)
def test_saved_examples_pass_the_allow_list(path):
    for code in re.findall(r"```python\n(.*?)```", path.read_text(encoding="utf-8"), re.S):
        assert safety.system_access(code) == [], path.name


def test_plain_cad_code_passes():
    code = (
        "import math\nimport Part\nimport FreeCAD as App\nfrom FreeCAD import Vector\n"
        "import freecad.gears.commands as gears\nb = Part.makeBox(1, 2, 3)\nresult = math.pi\n"
        "if __name__ == 'x':\n    super().__init__()"
    )
    assert safety.system_access(code) == []


def test_code_with_system_access_is_refused_and_logged(work, monkeypatch):
    monkeypatch.setenv("FREECAD_MCP_ALLOW_CODE", "1")
    monkeypatch.delenv("FREECAD_MCP_ALLOW_SYSTEM", raising=False)
    reply = json.loads(server.run_freecad_code("import subprocess"))
    assert reply["ok"] is False and "subprocess" in reply["error"]
    record = json.loads((work / "logs" / "code_log.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["blocked"] is True


def test_examples_with_system_access_are_never_saved(monkeypatch):
    monkeypatch.setenv("FREECAD_MCP_ALLOW_SYSTEM", "1")
    reply = json.loads(server.save_example("t", "p", "import os", verify_in_freecad=False))
    assert reply["saved"] is False and "os" in reply["reason"]


def test_tool_hints_mark_code_as_risky_and_lookups_as_read_only():
    tools = {t.name: t.annotations for t in server.mcp._tool_manager.list_tools()}
    assert tools["run_freecad_code"].destructiveHint and not tools["run_freecad_code"].readOnlyHint
    assert tools["read_knowledge"].readOnlyHint
    assert not tools["create_box"].readOnlyHint
    for name in ("fea_setup", "fea_run"):
        assert tools[name].destructiveHint and not tools[name].readOnlyHint
    assert tools["fea_results"].readOnlyHint and not tools["fea_results"].destructiveHint


def test_fea_analysis_name_cannot_leave_the_work_folder():
    for name in ("../evil", "a/b", "C:\\x", "FEA.inp", ""):
        assert json.loads(server.fea_run(name))["ok"] is False
