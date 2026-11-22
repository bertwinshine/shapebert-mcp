"""The documented headless launch runs this repository's listener, never an installed copy.

freecadcmd imports a .py argument by module name, and FreeCAD puts every Mod folder
first on sys.path, so `freecadcmd freecad_listener.py` runs Mod/FreeCADMCP's copy
(or an Addon Manager install) when there is one. The launch loads the file by path.
"""

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

import cadkit
from cadkit import protocol

ROOT = Path(__file__).resolve().parent.parent.parent
LAUNCH = "import runpy; runpy.run_path('freecad_listener.py', run_name='__main__')"
WINDOWS_FREECADCMD = Path("C:/Program Files/FreeCAD 1.1/bin/freecadcmd.exe")
FREECADCMD = (
    shutil.which("freecadcmd")
    or shutil.which("FreeCADCmd")
    or (str(WINDOWS_FREECADCMD) if WINDOWS_FREECADCMD.is_file() else None)
)
OLD_COPY = "from pathlib import Path\nPath(r'{marker}').write_text('the installed copy ran')\n"


def test_readme_and_ci_load_the_listener_by_path():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    for name, text in (("README.md", readme), ("tests.yml", workflow)):
        assert f'freecadcmd -c "{LAUNCH}"' in text or f'freecadcmd.exe" -c "{LAUNCH}"' in text, name
        bare = [
            line
            for line in text.splitlines()
            if "freecadcmd" in line and line.rstrip().endswith("freecad_listener.py")
        ]
        assert not bare, f"{name}: {bare}"


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _user_mod_dir(env):
    probe = "import FreeCAD; print('DATA=' + FreeCAD.getUserAppDataDir())"
    out = subprocess.run([FREECADCMD, "-c", probe], env=env, capture_output=True, text=True, timeout=120)
    data = next(line[5:].strip() for line in out.stdout.splitlines() if line.startswith("DATA="))
    return Path(data) / "Mod"


def _wait_for_port(proc, port, seconds=90):
    deadline = time.time() + seconds
    while time.time() < deadline:
        assert proc.poll() is None, f"freecadcmd exited with {proc.returncode} before listening"
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return
        except OSError:
            time.sleep(0.3)
    raise AssertionError(f"nothing listened on port {port} within {seconds} s")


@pytest.mark.skipif(FREECADCMD is None, reason="freecadcmd not installed")
def test_headless_launch_ignores_an_installed_older_listener(tmp_path):
    marker, port, token_file = tmp_path / "old_copy_ran", _free_port(), tmp_path / "token"
    env = {k: v for k, v in os.environ.items() if not k.startswith("FREECAD_MCP_")}
    home = tmp_path / "home"
    # FreeCAD ignores FREECAD_USER_HOME for a folder that doesn't exist and falls back
    # to the real user folder, which this test must never write to.
    home.mkdir()
    env.update(FREECAD_USER_HOME=str(home))
    mod = _user_mod_dir(env)
    assert mod.resolve().is_relative_to(tmp_path.resolve()), f"FreeCAD used {mod}, not the scratch home"
    old = mod / "FreeCADMCP" / "freecad_listener.py"
    old.parent.mkdir(parents=True)
    old.write_text(OLD_COPY.format(marker=marker), encoding="utf-8")
    env.update(FREECAD_MCP_HEADLESS="1", FREECAD_MCP_PORT=str(port), FREECAD_MCP_TOKEN_FILE=str(token_file))
    proc = subprocess.Popen(
        [FREECADCMD, "-c", LAUNCH], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        _wait_for_port(proc, port)
        reply = protocol.request("127.0.0.1", port, {"type": "ping"}, protocol.read_token(token_file), 10)
    finally:
        proc.kill()
        proc.wait(30)
    assert reply["listener_version"] == cadkit.__version__
    assert reply["protocol"] == cadkit.PROTOCOL_VERSION
    assert not marker.exists()
