"""The agent runner's glue code; the API and FreeCAD are not needed."""

import sys
from types import SimpleNamespace

from conftest import ROOT

sys.path.insert(0, str(ROOT / "bench"))
import run_agent  # noqa: E402


def _tool(name):
    return SimpleNamespace(name=name, description="d", inputSchema={"type": "object", "properties": {}})


def test_bare_variant_only_gets_the_bridge_tools():
    tools = run_agent.to_openai_tools([_tool("run_freecad_code"), _tool("measure")], run_agent.BARE_TOOLS)
    assert [t["function"]["name"] for t in tools] == ["run_freecad_code"]


def test_bad_tool_arguments_are_caught():
    assert run_agent.parse_arguments("{not json") is None
    assert run_agent.parse_arguments("[1, 2]") is None
    assert run_agent.parse_arguments("") == {}


def _result(*parts):
    return SimpleNamespace(content=list(parts))


def test_screenshots_reach_vision_models_as_images():
    image = SimpleNamespace(type="image", data="QUJD", mimeType="image/png")
    messages = run_agent.tool_messages("c1", _result(image), vision=True)
    assert messages[0]["role"] == "tool"
    assert messages[1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_text_only_models_are_told_the_screenshot_was_dropped():
    image = SimpleNamespace(type="image", data="QUJD", mimeType="image/png")
    messages = run_agent.tool_messages("c1", _result(image), vision=False)
    assert len(messages) == 1 and "omitted" in messages[0]["content"]


def test_missing_key_gives_a_clear_error(monkeypatch):
    monkeypatch.delenv(run_agent.KEY_VAR, raising=False)
    try:
        run_agent.chat("m", [], [])
    except run_agent.ApiError as e:
        assert run_agent.KEY_VAR in str(e)
    else:
        raise AssertionError("expected ApiError")


def test_transcripts_drop_screenshots_and_shorten_the_system_prompt(tmp_path):
    row = {
        "transcript": [
            {"role": "system", "content": "x" * 5000},
            {
                "role": "user",
                "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "ok"},
        ]
    }
    path = tmp_path / "t.json"
    run_agent.save_transcript(row, path)
    text = path.read_text(encoding="utf-8")
    assert "base64" not in text and "[screenshot]" in text and len(text) < 1000
