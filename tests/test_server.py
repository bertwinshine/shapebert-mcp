"""MCP server: tool registration and behaviour when FreeCAD is not reachable."""

import asyncio

import pytest
from replies import load

server = pytest.importorskip("server")

EXPECTED_TOOLS = {
    "ping_freecad",
    "get_status",
    "run_freecad_code",
    "get_job_result",
    "create_box",
    "create_cylinder",
    "set_placement",
    "bind_parameters",
    "boolean",
    "pattern_polar",
    "pattern_linear",
    "fillet_edges",
    "chamfer_edges",
    "get_document_info",
    "inspect_object",
    "measure",
    "check_geometry",
    "get_view",
    "compare_shapes",
    "export_model",
    "import_model",
    "save_document",
    "set_parameters",
    "hydrostatics",
    "check_printability",
    "calc_gears",
    "calc_sheet_metal",
    "calc_boat",
    "calc_weld",
    "calc_fasteners",
    "calc_flanges",
    "check_model_structure",
    "build_spur_gear",
    "build_ring_gear",
    "build_sheet_profile",
    "doctor",
    "calc_shafts",
    "match_domain",
    "list_knowledge",
    "read_knowledge",
    "search_examples",
    "save_example",
    "log_correction",
}


def test_all_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names >= EXPECTED_TOOLS, EXPECTED_TOOLS - names
    for t in tools:
        assert t.description and len(t.description) > 20, f"{t.name} needs a docstring"


def test_prompts_and_resources_registered():
    prompts = {p.name for p in asyncio.run(server.mcp.list_prompts())}
    assert {"design_part", "design_boat", "review_part", "learn_from_correction"} <= prompts
    templates = {str(t.uriTemplate) for t in asyncio.run(server.mcp.list_resource_templates())}
    assert "knowledge://domains/{name}" in templates


def test_clear_message_when_freecad_is_down(monkeypatch):
    monkeypatch.setattr(server.protocol, "read_token", lambda: "any")
    monkeypatch.setattr(server, "FREECAD_PORT", 1)  # nothing listens on port 1
    rep = load(server.ping_freecad())
    assert rep["ok"] is False and "freecad_listener.py" in rep["error"]


def test_clear_message_when_token_file_is_missing(monkeypatch):
    monkeypatch.setattr(server.protocol, "read_token", lambda: None)
    rep = load(server.ping_freecad())
    assert rep["ok"] is False and "token file" in rep["error"]


def test_calc_tool_unknown_name_lists_options():
    rep = load(server.calc_gears("nope", {}))
    assert rep["ok"] is False and "spur_pair" in rep["available"]


def test_calc_tool_bad_args_shows_signature():
    rep = load(server.calc_fasteners("bolt_hole", {"diameter": 6}))
    assert rep["ok"] is False and "signature" in rep


def test_calc_tool_happy_path():
    rep = load(server.calc_fasteners("fit", {"d_mm": 25, "fit_code": "H7/g6"}))
    assert rep["type"] == "clearance"


def test_read_knowledge_tool_rejects_escape():
    rep = load(server.read_knowledge("../../etc/passwd"))
    assert rep["ok"] is False


def test_match_domain_hands_over_the_closest_examples():
    reply = load(server.match_domain("shaft 30 mm with a DIN 6885 keyway"))
    assert reply["examples"][0]["file"] == "keyed_shaft.md"
    assert "keyed_shaft.md" in reply["example_advice"]


def test_doctor_explains_how_to_fix_an_unreachable_freecad(monkeypatch):
    monkeypatch.setattr(server.protocol, "read_token", lambda: "any")
    monkeypatch.setattr(server, "FREECAD_PORT", 1)
    report = load(server.doctor())
    assert report["freecad"]["reachable"] is False
    assert "install_autostart.FCMacro" in report["freecad"]["fix"]
    assert report["free_form_code"] in ("on", "off (default, safer)")


def test_sheet_profile_with_impossible_flanges_is_refused_before_freecad(monkeypatch):
    def no_freecad(*args, **kwargs):
        raise AssertionError("FreeCAD must not be called")

    monkeypatch.setattr(server, "_fc", no_freecad)
    reply = server.build_sheet_profile(thickness=2, inner_radius=3, flanges=[3, 50], angles=[90], length=100)
    assert "shorter than its bends need" in reply
