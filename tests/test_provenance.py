"""Validation of where each Params value came from, and the table explain_params shows."""

import pytest
from replies import load

from cadkit import provenance as prov

server = pytest.importorskip("server")

PROMPT = {"type": "prompt", "source_quote": "12 mm thick"}
KNOWLEDGE = {"type": "knowledge", "file": "conventions.md", "rule": "Fillets and chamfers"}
CALC = {"type": "calc", "tool": "calc_fasteners", "calc": "bolt_hole", "inputs": {"size": "M10"}}
DEFAULT = {"type": "default", "where": "conventions.md: 1 mm fillet when no size is given"}
EDIT = {"type": "user edit", "source_quote": "make it 15 mm thick"}


def _with(base, **changes):
    out = {**base, **changes}
    return {k: v for k, v in out.items() if v is not ...}


def test_each_source_type_comes_back_canonical():
    assert prov.check_source(_with(PROMPT, source_quote="  12 mm thick "), "s") == PROMPT
    assert prov.check_source(_with(KNOWLEDGE, rule="fillets  AND chamfers"), "s") == KNOWLEDGE
    assert prov.check_source(CALC, "s") == CALC
    assert prov.check_source(DEFAULT, "s") == DEFAULT
    assert prov.check_source(EDIT, "s") == EDIT


def test_a_numbered_domain_heading_is_a_rule():
    rule = "3. Core calculations (run before assigning values) -> `calc_fasteners`"
    source = {"type": "knowledge", "file": "domains/fasteners-fits.md", "rule": rule}
    assert prov.check_source(source, "s")["rule"] == rule


def test_code_comments_are_not_headings():
    text = "# Title\n## Rule one\n```python\n# not a rule\n```\n### Rule two ###\n"
    assert prov.headings(text) == ["Title", "Rule one", "Rule two"]


@pytest.mark.parametrize(
    "source, message",
    [
        ("prompt", "give the source as an object"),
        ({"source_quote": "x"}, "type must be one of"),
        (_with(PROMPT, type="guess"), "type must be one of"),
        (_with(PROMPT, rule="x"), "unknown keys"),
        (_with(PROMPT, source_quote=""), "source_quote"),
        (_with(PROMPT, source_quote=...), "source_quote"),
        (_with(PROMPT, source_quote="12 mm\nthick"), "control characters"),
        (_with(PROMPT, source_quote="x" * 301), "source_quote"),
        (_with(EDIT, source_quote=...), "source_quote"),
        (_with(KNOWLEDGE, file="domains/flanges.md"), "not a file in the knowledge base"),
        (_with(KNOWLEDGE, file="../server.md"), "not a file in the knowledge base"),
        (_with(KNOWLEDGE, file="conventions.txt"), "knowledge .md file"),
        (_with(KNOWLEDGE, rule="Bolt sizes for flanges"), "has no heading"),
        (_with(KNOWLEDGE, rule=...), "rule must be text"),
        (_with(CALC, tool="calc_magic"), "tool must be one of"),
        (_with(CALC, calc="_private"), "has no calc"),
        (_with(CALC, calc="en1092"), "has no calc"),
        (_with(CALC, inputs={"diameter": 10}), "inputs do not fit"),
        (_with(CALC, inputs={}), "inputs do not fit"),
        (_with(CALC, inputs="size=M10"), "inputs must be"),
        (_with(CALC, inputs={"size": {"nested": 1}}), "calc inputs must be"),
        (_with(CALC, inputs={"size": float("nan")}), "finite numbers"),
        (_with(CALC, inputs={"size": "M10\nx"}), "one line"),
        (_with(DEFAULT, where=""), "where must be text"),
        (_with(DEFAULT, where="a\tb"), "one line"),
    ],
)
def test_bad_sources_are_refused(source, message):
    with pytest.raises(prov.SourceError, match=message):
        prov.check_source(source, "s")


def test_every_parameter_needs_exactly_one_source():
    params = {"Thk": "12 mm", "HoleD": "11 mm"}
    checked = prov.check_sources(params, {"Thk": PROMPT, "HoleD": CALC})
    assert checked == {"Thk": PROMPT, "HoleD": CALC}
    with pytest.raises(prov.SourceError, match=r"missing for \['HoleD'\]"):
        prov.check_sources(params, {"Thk": PROMPT})
    with pytest.raises(prov.SourceError, match=r"not being set: \['Bore'\]"):
        prov.check_sources(params, {"Thk": PROMPT, "HoleD": CALC, "Bore": PROMPT})
    with pytest.raises(prov.SourceError, match="sources must be an object"):
        prov.check_sources(params, [PROMPT, CALC])
    with pytest.raises(prov.SourceError, match="params must be"):
        prov.check_sources({}, {})


def test_set_parameters_refuses_before_freecad(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "_fc", lambda func, **k: calls.append((func, k)) or {"sheet": "Params"})
    assert load(server.set_parameters({"Thk": "12 mm"}, {}))["ok"] is False
    assert load(server.set_parameters({"Thk": "12 mm"}, {"Thk": _with(PROMPT, type="guess")}))["ok"] is False
    assert calls == []
    load(server.set_parameters({"Thk": "12 mm"}, {"Thk": _with(PROMPT, source_quote=" 12 mm thick")}))
    assert calls == [
        ("set_parameters", {"params": {"Thk": "12 mm"}, "sources": {"Thk": PROMPT}, "sheet": "Params"})
    ]


def _row(name, content, stored_content=None, source=None, value=12.0, unit="mm"):
    stored = None if source is None else {"source": source, "content": stored_content or content}
    return {"parameter": name, "value": value, "unit": unit, "content": content, "stored": stored}


def test_the_table_shows_sources_edits_and_assumptions():
    rows = [
        _row("Thk", "=12 mm", source=PROMPT),
        _row("HoleD", "=11 mm", source=CALC, value=11.0),
        _row("FilletR", "=1 mm", source=DEFAULT, value=1.0),
        _row("PlateL", "=140 mm", stored_content="=120 mm", source=PROMPT, value=140.0),
        _row("NHoles", "6", value=6, unit=""),
        _row("Gap", "=2 mm", source="not a source"),
    ]
    out = prov.explain(rows)
    table = {r["parameter"]: r for r in out["parameters"]}
    assert table["Thk"] == {
        "parameter": "Thk",
        "value": 12.0,
        "unit": "mm",
        "source": "prompt",
        "detail": '"12 mm thick"',
    }
    assert table["HoleD"]["detail"] == "calc_fasteners bolt_hole(size='M10')"
    assert table["PlateL"]["source"] == "user edit"
    assert "from =120 mm to =140 mm" in table["PlateL"]["detail"]
    assert '(was prompt: "12 mm thick")' in table["PlateL"]["detail"]
    assert table["NHoles"]["source"] == table["Gap"]["source"] == "unrecorded"
    assert [a["parameter"] for a in out["assumptions"]] == ["FilletR", "NHoles", "Gap"]
    assert out["counts"] == {
        "prompt": 1,
        "knowledge": 0,
        "calc": 1,
        "default": 1,
        "user edit": 1,
        "unrecorded": 2,
    }


def test_knowledge_detail_names_file_and_rule():
    assert prov.describe(KNOWLEDGE) == 'conventions.md, rule "Fillets and chamfers"'


def test_explain_params_is_read_only_and_refuses_bad_names(monkeypatch):
    assert "explain_params" in server.READ_ONLY_TOOLS
    calls = []
    monkeypatch.setattr(server, "_fc", lambda func, **k: calls.append((func, k)))
    assert load(server.explain_params("bad\nname"))["ok"] is False
    assert calls == []
