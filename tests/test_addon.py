"""The Addon Manager package: package.xml, versions, and the bridge's ask-once start."""

import importlib
import json
import re
import sys
import types
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import tomllib

import cadkit
import freecad_listener as L

ROOT = Path(__file__).resolve().parent.parent
NS = {"p": "https://wiki.freecad.org/Package_Metadata"}
PLUGIN = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def package():
    root = ET.parse(ROOT / "package.xml").getroot()
    assert root.tag == f"{{{NS['p']}}}package" and root.get("format") == "1"
    return root


def _text(package, tag):
    return package.find(f"p:{tag}", NS).text.strip()


def test_package_has_every_required_element(package):
    for tag in ("name", "version", "date", "description", "maintainer", "license", "icon", "content"):
        assert package.find(f"p:{tag}", NS) is not None, tag
    assert _text(package, "name") == "ShapeBert"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", _text(package, "date"))
    assert _text(package, "freecadmin") == "1.1.0"


def test_maintainer_uses_only_the_noreply_address(package):
    (maintainer,) = package.findall("p:maintainer", NS)
    email = maintainer.get("email")
    assert email.endswith("@users.noreply.github.com") and maintainer.text == PLUGIN["author"]["name"]
    assert "@" not in (ROOT / "package.xml").read_text(encoding="utf-8").replace(email, "")


def test_license_icon_and_repository_point_at_real_things(package):
    license_tag = package.find("p:license", NS)
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert license_tag.text == pyproject["project"]["license"] == "Apache-2.0"
    assert (ROOT / license_tag.get("file")).is_file()
    assert (ROOT / _text(package, "icon")).is_file()
    repo = [u for u in package.findall("p:url", NS) if u.get("type") == "repository"]
    assert len(repo) == 1 and repo[0].get("branch") == "main"
    assert repo[0].text == PLUGIN["repository"]


def test_content_is_one_other_item_with_a_namespaced_init_gui(package):
    content = list(package.find("p:content", NS))
    assert [c.tag.split("}")[1] for c in content] == ["other"]
    assert (ROOT / "freecad" / "shapebert" / "init_gui.py").is_file()
    # A freecad/__init__.py would hide FreeCAD's own freecad namespace package.
    assert not (ROOT / "freecad" / "__init__.py").exists()


def test_every_version_number_agrees(package):
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    versions = {
        "cadkit": cadkit.__version__,
        "listener": L.LISTENER_VERSION,
        "pyproject": pyproject["project"]["version"],
        "plugin.json": PLUGIN["version"],
        "package.xml": _text(package, "version"),
    }
    assert set(versions.values()) == {"1.1.0"}, versions
    assert f"## {cadkit.__version__}" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


class FakeParams:
    def __init__(self):
        self.values = {}

    def GetString(self, key, default):
        return self.values.get(key, default)

    def SetString(self, key, value):
        self.values[key] = value


@pytest.fixture
def bridge(monkeypatch):
    """freecad/shapebert/bridge.py with a stand-in FreeCAD and no Qt."""
    params, messages = FakeParams(), []
    app = types.ModuleType("FreeCAD")
    app.ParamGet = lambda path: params
    app.Console = types.SimpleNamespace(PrintMessage=messages.append)
    monkeypatch.setitem(sys.modules, "FreeCAD", app)
    module = importlib.reload(importlib.import_module("freecad.shapebert.bridge"))
    calls = types.SimpleNamespace(started=0, dialogs=[], params=params.values, messages=messages, app=app)

    def started():
        calls.started += 1

    monkeypatch.setattr(module, "start_listener", started)
    monkeypatch.setattr(module, "_show_dialog", calls.dialogs.append)
    module.calls = calls
    return module


def test_first_start_asks_and_starts_nothing(bridge):
    bridge.on_startup()
    assert bridge.calls.started == 0 and len(bridge.calls.dialogs) == 1


def test_agreeing_starts_the_listener_now_and_on_later_starts(bridge):
    bridge.on_startup()
    bridge.calls.dialogs[0](True)
    assert bridge.calls.params == {"Bridge": "start"} and bridge.calls.started == 1
    bridge.on_startup()
    assert bridge.calls.started == 2 and len(bridge.calls.dialogs) == 1


def test_declining_is_remembered_and_never_asked_again_at_startup(bridge):
    bridge.on_startup()
    bridge.calls.dialogs[0](False)
    bridge.on_startup()
    assert bridge.calls.params == {"Bridge": "off"} and bridge.calls.started == 0
    assert len(bridge.calls.dialogs) == 1 and "ShapeBert_Bridge" in bridge.calls.messages[0]


def test_declining_from_the_macro_stops_a_running_listener(bridge):
    stopped = []
    bridge.calls.app._mcp_listener = types.SimpleNamespace(stop=lambda: stopped.append(True))
    bridge.ask()
    bridge.calls.dialogs[0](False)
    assert stopped == [True] and bridge.calls.app._mcp_listener is None


def test_dialog_text_warns_about_agent_permissions(bridge, monkeypatch):
    monkeypatch.delenv("FREECAD_MCP_PORT", raising=False)
    text = bridge.message()
    assert "full permissions" in text and "127.0.0.1:9876" in text and "ShapeBert_Bridge" in text


def test_bridge_starts_the_listener_shipped_next_to_it(bridge):
    assert Path(bridge.LISTENER) == ROOT / "freecad_listener.py"


def test_macro_asks_through_the_bridge():
    macro = (ROOT / "ShapeBert_Bridge.FCMacro").read_text(encoding="utf-8")
    assert "from freecad.shapebert import bridge" in macro and "bridge.ask()" in macro
