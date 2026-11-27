"""Checks written from the user's request, validated before they are stored on a part."""

import math
import re

import shapebert_selectors as selectors

MAX_CHECKS = 50
MAX_QUOTE = 300
CHECK_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,39}")
LENGTH_TOLERANCE_MM = 0.01
RELATIVE_TOLERANCE = 0.01  # volume and mass: 1 % of the required value

# kind -> (unit, what target is: "object", "faces" or "faces or edges")
KINDS = {
    "size": ("mm", "object"),
    "hole_count": ("count", "faces"),
    "hole_diameter": ("mm", "faces"),
    "pitch_circle_diameter": ("mm", "faces"),
    "hole_spacing": ("mm", "faces"),
    "edge_distance": ("mm", "faces"),
    "thickness": ("mm", "faces"),
    "position": ("mm", "faces"),
    "offset": ("mm", "faces"),
    "volume": ("mm3", "object"),
    "mass": ("kg", "object"),
    "feature": (None, "faces or edges"),
}
COMMON_KEYS = {"id", "kind", "target", "value", "unit", "op", "tolerance", "source_quote", "source"}
# A limit from a design rule rather than from the request names that rule.
RULE_SOURCES = ("knowledge", "calc")
EXTRA_KEYS = {"size": {"axis"}, "position": {"axis"}, "offset": {"face"}, "mass": {"density_kg_m3"}}
AXES = ("X", "Y", "Z")
MAX_REFERENCE_FACES = 6
# eq: the value within the tolerance; min / max: a limit the measured value may reach.
OPS = ("eq", "min", "max")


class RequirementError(ValueError):
    pass


def _value(kind, value, what):
    """A position may be zero or negative and an offset zero; every other value is positive."""
    if kind not in ("position", "offset"):
        return _positive(value, what)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise RequirementError(f"{what} must be a finite number")
    if kind == "offset" and value < 0:
        raise RequirementError(f"{what} is a distance and must be 0 or more")
    return float(value)


def _positive(value, what):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise RequirementError(f"{what} must be a finite number greater than 0")
    return float(value)


def quote(value, where):
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_QUOTE:
        raise RequirementError(
            f"{where}: source_quote must be the request's own words, 1 to {MAX_QUOTE} characters"
        )
    if any(ord(c) < 32 for c in value):
        raise RequirementError(f"{where}: source_quote contains control characters")
    return value.strip()


def _origin(check, where):
    if ("source_quote" in check) == ("source" in check):
        raise RequirementError(
            f"{where}: give source_quote (the request's own words) or source (the knowledge rule "
            "or calculator a limit comes from), exactly one of them"
        )
    if "source_quote" in check:
        return {"source_quote": quote(check["source_quote"], where)}
    source = check["source"]
    if not isinstance(source, dict) or source.get("type") not in RULE_SOURCES:
        raise RequirementError(
            f"{where}: source must be a {' or '.join(RULE_SOURCES)} source; "
            "a value from the request uses source_quote"
        )
    # provenance imports this module, so it can only be imported once this one is loaded.
    from cadkit import provenance

    try:
        return {"source": provenance.check_source(source, f"{where}: source")}
    except provenance.SourceError as e:
        raise RequirementError(str(e)) from None


def _target(kind, target, where):
    expects = KINDS[kind][1]
    if expects == "object":
        if target not in (None, "object"):
            raise RequirementError(f"{where}: a {kind} check measures the whole object; leave target out")
        return "object", "object"
    try:
        if expects == "faces":
            return selectors.parse_face(target), "faces"
        try:
            return selectors.parse_face(target), "faces"
        except selectors.SelectorError:
            return selectors.parse_edges(target), "edges"
    except selectors.SelectorError as e:
        raise RequirementError(f"{where}: target: {e}") from None


def _reference_faces(value, where):
    """One flat-face selector, or several when a pattern sits the same distance from
    opposite sides (holes 20 mm from both ends). Always a list."""
    faces = value if isinstance(value, list) else [value]
    if not 1 <= len(faces) <= MAX_REFERENCE_FACES:
        raise RequirementError(f"{where}: face must be one selector or a list of 1 to {MAX_REFERENCE_FACES}")
    try:
        return [selectors.parse_face(f) for f in faces]
    except selectors.SelectorError as e:
        raise RequirementError(f"{where}: face: {e}") from None


def _op(check, where):
    op = check.get("op", "eq")
    if op not in OPS:
        raise RequirementError(f"{where}: op must be one of {list(OPS)}, not {op!r}")
    if op != "eq" and "tolerance" in check:
        raise RequirementError(f"{where}: a {op} check is a limit; leave tolerance out")
    return op


def _tolerance(kind, check, value, where):
    if kind == "hole_count":
        if check.get("tolerance") not in (None, 0):
            raise RequirementError(f"{where}: a count is exact; leave tolerance out")
        return 0.0
    if "tolerance" not in check:
        return value * RELATIVE_TOLERANCE if kind in ("volume", "mass") else LENGTH_TOLERANCE_MM
    tol = check["tolerance"]
    if isinstance(tol, bool) or not isinstance(tol, (int, float)) or not math.isfinite(tol) or tol < 0:
        raise RequirementError(f"{where}: tolerance must be a finite number of 0 or more")
    return float(tol)


def check_one(check, index):
    """One validated check in canonical form."""
    where = f"check {index}"
    if not isinstance(check, dict):
        raise RequirementError(f"{where}: give an object with id, kind, target, value, unit, source_quote")
    kind = check.get("kind")
    if kind not in KINDS:
        raise RequirementError(f"{where}: kind must be one of {sorted(KINDS)}, not {kind!r}")
    unknown = set(check) - COMMON_KEYS - EXTRA_KEYS.get(kind, set())
    if unknown:
        raise RequirementError(f"{where}: unknown keys {sorted(unknown)} for a {kind} check")
    check_id = check.get("id")
    if not isinstance(check_id, str) or not CHECK_ID.fullmatch(check_id):
        raise RequirementError(
            f"{where}: id must be letters, digits, _ or - (up to 40), starting with a letter"
        )
    where = f"check {check_id!r}"
    target, element = _target(kind, check.get("target"), where)
    out = {"id": check_id, "kind": kind, "target": target, "element": element}
    unit = KINDS[kind][0]
    if kind == "feature":
        if any(k in check for k in ("value", "unit", "op", "tolerance")):
            raise RequirementError(f"{where}: a feature check has no value, unit, op or tolerance")
    else:
        if check.get("unit") != unit:
            raise RequirementError(f"{where}: unit must be {unit!r} for a {kind} check")
        value = _value(kind, check.get("value"), f"{where}: value")
        if kind == "hole_count" and not value.is_integer():
            raise RequirementError(f"{where}: a hole count must be a whole number")
        op = _op(check, where)
        out.update(value=value, unit=unit, op=op)
        if op == "eq":
            out["tolerance"] = _tolerance(kind, check, value, where)
    if kind in ("size", "position"):
        axis = str(check.get("axis", "")).upper()
        if axis not in AXES:
            raise RequirementError(f"{where}: axis must be X, Y or Z")
        out["axis"] = axis
    if kind == "offset":
        out["face"] = _reference_faces(check.get("face"), where)
    if kind == "mass":
        out["density_kg_m3"] = _positive(check.get("density_kg_m3"), f"{where}: density_kg_m3")
    out.update(_origin(check, where))
    return out


def check_all(checks) -> list[dict]:
    """Validated checks; refuses the whole list if any check is wrong or ids repeat."""
    if not isinstance(checks, list) or not 1 <= len(checks) <= MAX_CHECKS:
        raise RequirementError(f"requirements must be a list of 1 to {MAX_CHECKS} checks")
    out = [check_one(c, i) for i, c in enumerate(checks, 1)]
    ids = [c["id"] for c in out]
    repeated = sorted({i for i in ids if ids.count(i) > 1})
    if repeated:
        raise RequirementError(f"check ids must be unique; repeated: {repeated}")
    return out
