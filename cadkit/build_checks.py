"""Argument checks for the structured build tools, run before anything reaches FreeCAD."""

import math
import re

NEW_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
PROPERTY_PATH = re.compile(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*){0,3}")
EDGE_NAME = re.compile(r"Edge[1-9]\d{0,4}")
EDGE_SELECTORS = {"all", "top", "bottom", "vertical"}
BOOLEAN_OPERATIONS = {"cut", "fuse", "common"}
UNITS = {"um", "mm", "cm", "m", "in", "ft", "deg", "rad"}
MAX_COUNT = 500

# Numbers (with an optional unit after them), dotted references and arithmetic only.
# FreeCAD expressions also know functions and string literals; neither is needed to
# tie a size to Params, so neither gets through.
TOKEN = re.compile(
    r"\s*(?:(?P<num>(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)"
    r"|(?P<ref>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)"
    r"|(?P<op>[-+*/()]))"
)


def object_ref(value, what: str = "object") -> str:
    """An existing object's Name or Label."""
    if not isinstance(value, str) or not value.strip() or len(value) > 100:
        raise ValueError(f"{what} must be an object name or label of 1 to 100 characters")
    if any(ord(c) < 32 for c in value):
        raise ValueError(f"{what} contains control characters")
    return value


def new_name(value: str | None, default: str) -> str:
    if value is None or value == "":
        return default
    if not isinstance(value, str) or not NEW_NAME.fullmatch(value):
        raise ValueError(f"name {value!r} must be letters, digits and _ (up to 64), starting with a letter")
    return value


def label(value: str | None) -> str | None:
    return None if value in (None, "") else object_ref(value, "label")


def number(value, what: str, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{what} must be a finite number")
    if positive and value <= 0:
        raise ValueError(f"{what} must be greater than 0")
    return float(value)


def count(value, what: str = "count") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_COUNT:
        raise ValueError(f"{what} must be a whole number from 1 to {MAX_COUNT}")
    return value


def vector(value, what: str, default: list[float], nonzero: bool = False) -> list[float]:
    if value is None:
        return default
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{what} must be [x, y, z]")
    out = [number(v, what) for v in value]
    if nonzero and not any(out):
        raise ValueError(f"{what} must not be [0, 0, 0]")
    return out


def expression(value) -> str:
    """A FreeCAD expression limited to references, numbers, units and + - * / ( )."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(number(value, "expression"))
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError("expression must be text of 1 to 200 characters, e.g. 'Params.PlateL / 2'")
    text = value.strip()
    pos, previous = 0, None
    while pos < len(text):
        match = TOKEN.match(text, pos)
        if not match or match.end() == pos:
            raise ValueError(f"expression {value!r}: {text[pos:].strip()[:20]!r} is not allowed")
        kind, token = match.lastgroup, match.group(match.lastgroup)
        pos = match.end()
        if kind == "ref":
            if token in UNITS:
                if previous != "num":
                    raise ValueError(f"expression {value!r}: unit {token!r} must follow a number")
            elif "." not in token:
                raise ValueError(f"expression {value!r}: write {token!r} as Sheet.Alias or Object.Property")
            if text[pos:].lstrip().startswith("("):
                raise ValueError(f"expression {value!r}: function calls are not allowed")
        previous = kind
    return text


def expressions(value) -> dict[str, str]:
    if not isinstance(value, dict) or not value or len(value) > 30:
        raise ValueError(
            'expressions must map 1 to 30 property paths to expressions, e.g. {"Height": "Params.Thk"}'
        )
    out = {}
    for path, expr in value.items():
        if not isinstance(path, str) or not PROPERTY_PATH.fullmatch(path):
            raise ValueError(f"property path {path!r} must look like Radius or Placement.Base.x")
        out[path] = expression(expr)
    return out


def edges(value) -> str | list[str]:
    if isinstance(value, str):
        if value not in EDGE_SELECTORS:
            raise ValueError(
                f"edges must be one of {sorted(EDGE_SELECTORS)} or a list like ['Edge1', 'Edge4']"
            )
        return value
    if not isinstance(value, list) or not value or len(value) > MAX_COUNT:
        raise ValueError("edges must be a selector word or a list of edge names")
    for name in value:
        if not isinstance(name, str) or not EDGE_NAME.fullmatch(name):
            raise ValueError(f"edge {name!r} must look like Edge3")
    return value
