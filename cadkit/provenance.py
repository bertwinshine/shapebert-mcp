"""Where each Params value came from, validated before it is stored with the spreadsheet."""

import inspect
import math
import re

from cadkit import knowledge as kb
from cadkit.calculators import boat, fasteners, flanges, gears, shafts, sheet_metal, weldments
from cadkit.requirements import MAX_QUOTE, RequirementError, quote

TYPES = ("prompt", "knowledge", "calc", "default", "user edit")
KEYS = {
    "prompt": {"source_quote"},
    "knowledge": {"file", "rule"},
    "calc": {"tool", "calc", "inputs"},
    "default": {"where"},
    "user edit": {"source_quote"},
}
CALC_TOOLS = {
    "calc_gears": gears,
    "calc_sheet_metal": sheet_metal,
    "calc_boat": boat,
    "calc_weld": weldments,
    "calc_fasteners": fasteners,
    "calc_shafts": shafts,
    "calc_flanges": flanges,
}
MAX_INPUTS = 20
MAX_INPUT_TEXT = 100
HEADING = re.compile(r"#{1,6}\s+(.+?)\s*#*\s*")


class SourceError(ValueError):
    pass


def _line(value, where, what):
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_QUOTE:
        raise SourceError(f"{where}: {what} must be text of 1 to {MAX_QUOTE} characters")
    if any(ord(c) < 32 for c in value):
        raise SourceError(f"{where}: {what} must be one line without control characters")
    return value.strip()


def _words(text):
    return " ".join(text.split()).casefold()


def headings(text: str) -> list[str]:
    """Markdown headings outside code blocks, whose `# comments` are not rules."""
    out, fenced = [], False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and (m := HEADING.fullmatch(line)):
            out.append(m[1])
    return out


def _knowledge(source, where):
    path = _line(source.get("file"), where, "file")
    if not path.endswith(".md"):
        raise SourceError(f"{where}: file must be a knowledge .md file, e.g. 'domains/fasteners-fits.md'")
    try:
        text = kb.read_doc(path)
    except (FileNotFoundError, ValueError):
        raise SourceError(f"{where}: {path!r} is not a file in the knowledge base") from None
    rule = _line(source.get("rule"), where, "rule")
    found = [h for h in headings(text) if _words(h) == _words(rule)]
    if not found:
        raise SourceError(f"{where}: {path} has no heading {rule!r}; its headings are {headings(text)}")
    return {"type": "knowledge", "file": path, "rule": found[0]}


def _public_calcs(module):
    return sorted(
        name
        for name, fn in inspect.getmembers(module, inspect.isfunction)
        if not name.startswith("_") and fn.__module__ == module.__name__
    )


def _input_value(value, where):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise SourceError(f"{where}: calc inputs must be finite numbers")
        return value
    if isinstance(value, str):
        if len(value) > MAX_INPUT_TEXT or any(ord(c) < 32 for c in value):
            raise SourceError(
                f"{where}: a calc input text must be one line of up to {MAX_INPUT_TEXT} characters"
            )
        return value
    if isinstance(value, list) and len(value) <= MAX_INPUTS:
        return [_input_value(v, where) for v in value]
    raise SourceError(f"{where}: calc inputs must be numbers, text, true/false or short lists of them")


def _calc(source, where):
    tool = source.get("tool")
    if tool not in CALC_TOOLS:
        raise SourceError(f"{where}: tool must be one of {sorted(CALC_TOOLS)}, not {tool!r}")
    module = CALC_TOOLS[tool]
    calc = source.get("calc")
    if calc not in _public_calcs(module):
        raise SourceError(f"{where}: {tool} has no calc {calc!r}; it has {_public_calcs(module)}")
    inputs = source.get("inputs")
    if not isinstance(inputs, dict) or len(inputs) > MAX_INPUTS:
        raise SourceError(f"{where}: inputs must be the calc's arguments as an object")
    try:
        inspect.signature(getattr(module, calc)).bind(**inputs)
    except TypeError as e:
        raise SourceError(f"{where}: inputs do not fit {tool} {calc}: {e}") from None
    inputs = {k: _input_value(v, where) for k, v in inputs.items()}
    return {"type": "calc", "tool": tool, "calc": calc, "inputs": inputs}


def check_source(source, where) -> dict:
    """One validated source in canonical form."""
    if not isinstance(source, dict):
        raise SourceError(f"{where}: give the source as an object with a type")
    kind = source.get("type")
    if kind not in TYPES:
        raise SourceError(f"{where}: type must be one of {list(TYPES)}, not {kind!r}")
    unknown = set(source) - {"type"} - KEYS[kind]
    if unknown:
        raise SourceError(f"{where}: unknown keys {sorted(unknown)} for a {kind!r} source")
    if kind in ("prompt", "user edit"):
        try:
            return {"type": kind, "source_quote": quote(source.get("source_quote"), where)}
        except RequirementError as e:
            raise SourceError(str(e)) from None
    if kind == "knowledge":
        return _knowledge(source, where)
    if kind == "calc":
        return _calc(source, where)
    return {"type": "default", "where": _line(source.get("where"), where, "where")}


def check_sources(params, sources) -> dict:
    """Validated sources, exactly one for each parameter being set."""
    if not isinstance(params, dict) or not params:
        raise SourceError("params must be an object of one or more name: value pairs")
    if not isinstance(sources, dict):
        raise SourceError("sources must be an object mapping each parameter to its source")
    missing = sorted(set(params) - set(sources))
    if missing:
        raise SourceError(f"every parameter needs a source; missing for {missing}")
    extra = sorted(set(sources) - set(params))
    if extra:
        raise SourceError(f"sources given for parameters that are not being set: {extra}")
    return {name: check_source(sources[name], f"source of {name!r}") for name in params}


def describe(source: dict) -> str:
    """One line saying where a stored source points."""
    kind = source.get("type")
    if kind in ("prompt", "user edit"):
        return f'"{source.get("source_quote")}"'
    if kind == "knowledge":
        return f'{source.get("file")}, rule "{source.get("rule")}"'
    if kind == "calc":
        args = ", ".join(f"{k}={v!r}" for k, v in (source.get("inputs") or {}).items())
        return f"{source.get('tool')} {source.get('calc')}({args})"
    return str(source.get("where"))


def _row_source(row):
    entry = row.get("stored")
    source = entry.get("source") if isinstance(entry, dict) else None
    if not isinstance(source, dict) or source.get("type") not in TYPES:
        return "unrecorded", "no source stored: the value was set outside set_parameters"
    if entry.get("content") != row.get("content"):
        was = f"{source['type']}: {describe(source)}"
        return (
            "user edit",
            f"changed in the spreadsheet from {entry.get('content')} to {row.get('content')} (was {was})",
        )
    return source["type"], describe(source)


def explain(rows: list[dict]) -> dict:
    """The parameter table, with every default or unrecorded value listed as an assumption."""
    table = []
    for row in rows:
        kind, detail = _row_source(row)
        table.append(
            {
                "parameter": row.get("parameter"),
                "value": row.get("value"),
                "unit": row.get("unit"),
                "source": kind,
                "detail": detail,
            }
        )
    return {
        "parameters": table,
        "assumptions": [r for r in table if r["source"] in ("default", "unrecorded")],
        "counts": {k: sum(r["source"] == k for r in table) for k in (*TYPES, "unrecorded")},
    }
