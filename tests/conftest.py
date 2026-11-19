import os
import socket
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LIVE_PORT = int(os.environ.get("FREECAD_MCP_PORT", "9876"))

# The live tests drive FreeCAD with free-form code, which is off by default.
# Tests of the off switch remove this with monkeypatch.
os.environ.setdefault("FREECAD_MCP_ALLOW_CODE", "1")
# Keep test exports out of the real work folder in the home directory.
os.environ.setdefault("FREECAD_MCP_WORKDIR", str(Path(tempfile.gettempdir()) / "freecad_mcp_test_work"))


def listener_up(port=LIVE_PORT):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture
def kb_copy(tmp_path, monkeypatch):
    """A throw-away copy of knowledge/ so tests never touch the real files."""
    import shutil

    from cadkit import knowledge

    dst = tmp_path / "knowledge"
    shutil.copytree(
        ROOT / "knowledge", dst, ignore=shutil.ignore_patterns("assets", "*.FCStd", "*.FCBak", "*.stl")
    )
    monkeypatch.setattr(knowledge, "ROOT", dst)
    monkeypatch.setattr(knowledge, "EXTRA_ROOTS", [])
    return dst
