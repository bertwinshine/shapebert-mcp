"""The guard against identical calls repeated in a row."""

import json

import pytest

server = pytest.importorskip("server")


@pytest.fixture(autouse=True)
def fresh_history():
    server._last_call.update(key=None, count=0)


def test_third_identical_call_gets_a_warning():
    replies = [json.loads(server.calc_gears("module_from", {"x": 1})) for _ in range(3)]
    assert "repeat_warning" not in replies[1]
    assert "call number 3" in replies[2]["repeat_warning"]


def test_a_different_call_resets_the_count():
    server.calc_gears("module_from", {"x": 1})
    server.calc_gears("module_from", {"x": 1})
    server.calc_gears("module_from", {"x": 2})
    reply = json.loads(server.calc_gears("module_from", {"x": 2}))
    assert "repeat_warning" not in reply


def test_tool_schemas_keep_their_parameters():
    import asyncio

    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    assert set(tools["run_freecad_code"].inputSchema["properties"]) >= {
        "code",
        "rollback_on_error",
        "timeout_s",
    }
