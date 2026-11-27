"""Argument checks of the structured build tools; nothing here needs FreeCAD."""

import asyncio

import pytest
from replies import load

from cadkit import build_checks

server = pytest.importorskip("server")

STRUCTURED = {
    "set_placement",
    "bind_parameters",
    "boolean",
    "pattern_polar",
    "pattern_linear",
    "fillet_edges",
    "chamfer_edges",
}


@pytest.fixture
def fc_calls(monkeypatch):
    calls = []

    def fake_fc(func, **kwargs):
        calls.append((func, kwargs))
        return {"name": "X"}

    monkeypatch.setattr(server, "_fc", fake_fc)
    return calls


@pytest.mark.parametrize(
    "expr",
    [
        "Params.PlateL",
        "Params.BoreD / 2",
        "Params.Thk + 2 mm",
        "(Params.PCD - 2.5mm) * 0.5",
        "Box.Length",
        12,
        1.5e2,
        "sqrt(Params.L)",
        "atan2(Params.RibH, Params.RibL)",
        "Params.PCD / 2 * cos(45 deg)",
        "sqrt(Params.RibL * Params.RibL + Params.RibH * Params.RibH)",
        "max(Params.Thk, 2 mm) + abs(Params.Off)",
        "2 * pi * Params.R",
        "asin(0.5) + acos(0.5) + atan(1) + sin(30 deg) + tan(1 deg) + min(1, 2)",
    ],
)
def test_expression_accepts_references_numbers_units_and_maths(expr):
    assert build_checks.expression(expr)


@pytest.mark.parametrize(
    "expr",
    [
        "",
        "PlateL",  # bare names are ambiguous; write Params.PlateL
        "Params.L; 1",
        "Params.fn (1)",
        "open(Params.L)",  # only the maths functions
        "eval(1)",
        "str(Params.L)",
        "create(<<Part::Box>>)",
        "Params.L.sqrt(2)",  # no method calls
        "sqrt(Params.L).real",  # no attribute access on a result
        "sqrt Params.L",  # a function must be called
        "pi(1)",
        "pi mm",
        "(Params.A, Params.B)",  # a comma only between arguments
        "Params.A, Params.B",
        "atan2(Params.A, Params.B",
        "sqrt(Params.A))",
        "sqrt(Params.__class__)",
        "<<text>>",
        "'text'",
        "Params.L # comment",
        "mm + 2",
        "Params.L ? 1 : 2",
        "x" * 201,
        "Params.__class__",
        "__builtins__.open",
        "Params.L * 1e400",
        True,
        None,
    ],
)
def test_expression_refuses_everything_else(expr):
    with pytest.raises(ValueError):
        build_checks.expression(expr)


@pytest.mark.parametrize("path", ["Radius", "Placement.Base.x", "IntervalX.y", "NumberPolar"])
def test_property_paths(path):
    assert build_checks.expressions({path: "Params.A1"}) == {path: "Params.A1"}


@pytest.mark.parametrize("path", ["", "Placement..x", "Base[0]", "a.b.c.d.e", "1Radius"])
def test_bad_property_paths(path):
    with pytest.raises(ValueError):
        build_checks.expressions({path: "Params.A1"})


@pytest.mark.parametrize(
    "check, value",
    [
        (lambda v: build_checks.vector(v, "v", [0, 0, 0]), [1, 2]),
        (lambda v: build_checks.vector(v, "v", [0, 0, 0]), [1, 2, float("nan")]),
        (lambda v: build_checks.vector(v, "v", [0, 0, 1], nonzero=True), [0, 0, 0]),
        (lambda v: build_checks.count(v), 0),
        (lambda v: build_checks.count(v), 2.5),
        (lambda v: build_checks.count(v), build_checks.MAX_COUNT + 1),
        (lambda v: build_checks.number(v, "r", positive=True), 0),
        (lambda v: build_checks.number(v, "r"), float("inf")),
        (lambda v: build_checks.new_name(v, "Cut"), "Bad Name"),
        (lambda v: build_checks.object_ref(v), "line\nbreak"),
        (lambda v: build_checks.edges(v), "outer"),
        (lambda v: build_checks.edges(v), ["Edge0"]),
        (lambda v: build_checks.edges(v), ["Face1"]),
        (lambda v: build_checks.edges(v), ["Edge1", "vertical"]),
        (lambda v: build_checks.edges(v), []),
        (lambda v: build_checks.edges(v), "edges of Face3"),
    ],
)
def test_bad_values_are_refused(check, value):
    with pytest.raises(ValueError):
        check(value)


def test_tools_are_registered_and_change_the_model_without_overwriting():
    assert {t.name for t in asyncio.run(server.mcp.list_tools())} >= STRUCTURED
    assert not STRUCTURED & (server.READ_ONLY_TOOLS | server.DESTRUCTIVE_TOOLS)


def test_bad_arguments_never_reach_freecad(fc_calls):
    replies = [
        server.boolean("subtract", "Disk", ["Bore"]),
        server.boolean("cut", "Disk", ["Disk"]),
        server.boolean("cut", "Disk", []),
        server.bind_parameters("Disk", {"Radius": "__import__('os')"}),
        server.pattern_polar("Hole", count=0),
        server.pattern_linear("Hole", count=3, spacing=-5),
        server.set_placement("Hole", rotation_axis=[0, 0, 0]),
        server.fillet_edges("Plate", radius=2, edges="outer"),
        server.chamfer_edges("Plate", size=0),
    ]
    assert fc_calls == []
    assert all(load(r)["ok"] is False for r in replies)


def test_cut_with_several_tools_passes_names_and_defaults(fc_calls):
    server.boolean("cut", "Disk", ["Bore", "Array"], label="Result")
    assert fc_calls == [
        (
            "boolean",
            {
                "operation": "cut",
                "base": "Disk",
                "tools": ["Bore", "Array"],
                "name": "Cut",
                "label": "Result",
            },
        )
    ]


def test_patterns_and_placement_fill_in_default_vectors(fc_calls):
    server.pattern_polar("Hole", count=4)
    server.pattern_linear("Hole", count=3, spacing=30)
    server.set_placement("Hole", position=[37.5, 0, 0])
    assert fc_calls[0][1]["axis"] == [0, 0, 1] and fc_calls[0][1]["center"] == [0, 0, 0]
    assert fc_calls[1][1]["direction"] == [1, 0, 0]
    assert fc_calls[2][1]["rotation_axis"] == [0, 0, 1]


def test_fillet_and_chamfer_use_one_freecad_function(fc_calls):
    server.fillet_edges("Plate", radius=2, edges=["Edge1", "Edge3"])
    server.chamfer_edges("Plate", size=1, edges="top")
    server.fillet_edges("Plate", radius=2, edges=["Edges of the TOP face", "vertical", "top"])
    assert [(f, k["kind"], k["edges"], k["selectors"]) for f, k in fc_calls] == [
        ("round_edges", "Fillet", ["Edge1", "Edge3"], None),
        ("round_edges", "Chamfer", None, ["edges of top"]),
        ("round_edges", "Fillet", None, ["edges of top", "vertical"]),
    ]


def test_code_off_message_points_to_the_structured_tools_and_not_to_plugin_files():
    message = server.safety.CODE_OFF_MESSAGE
    assert "boolean" in message and "pattern_polar" in message
    assert ".mcp.json" not in message and "plugin.json" not in message
    assert "README" in message
