"""Score a benchmark case against what is currently open in FreeCAD.

Usage: python bench/score.py L1-plate-4xM6 [--object Result]
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import server  # noqa: E402

CASES = {c["id"]: c for c in json.loads((HERE / "cases.json").read_text(encoding="utf-8"))}


def _check(label, ok, detail):
    return {"check": label, "pass": bool(ok), "detail": detail}


# Some models build in a document of their own instead of the one the benchmark opened,
# so look for the result in every open document, not only the active one.
FIND_DOCUMENT = """
hits = [d for d in App.listDocuments().values() if d.getObject({name!r}) or d.getObjectsByLabel({name!r})]
if hits:
    App.setActiveDocument(hits[-1].Name)
result = App.ActiveDocument.Name if App.ActiveDocument else None
"""


def _activate_document_with(name):
    if name:
        server._run(FIND_DOCUMENT.format(name=name))


# Finds the spreadsheet value that equals the prompt's size, changes it and
# recomputes: a part built from hard numbers or from a static copy cannot follow.
EDIT_PARAMETER = """
import json as _json
_spec = _json.loads({spec!r})
_doc = App.ActiveDocument
_hits = []
for _sheet in [o for o in _doc.Objects if o.TypeId == "Spreadsheet::Sheet"]:
    for _cell in _sheet.getNonEmptyCells():
        _alias = _sheet.getAlias(_cell)
        if not _alias:
            continue
        _value = _sheet.get(_alias)
        _number = getattr(_value, "Value", _value)
        if isinstance(_number, (int, float)) and abs(_number - _spec["from"]) < 1e-6:
            _hits.append((_sheet, _cell, _alias, hasattr(_value, "Unit")))
# Several aliases can hold the same value (PlateL and a leftover L); change the ones
# the geometry reads, and fall back to the first only if none is used.
import re as _re
_used = set()
for _o in _doc.Objects:
    for _prop, _expr in _o.ExpressionEngine:
        _used.update(_re.findall(r"[A-Za-z_][A-Za-z0-9_]*", _expr))
_targets = [h for h in _hits if h[2] in _used] or _hits[:1]
result = {{"aliases": [h[2] for h in _hits]}}
if _targets:
    for _sheet, _cell, _alias, _has_unit in _targets:
        _sheet.set(_cell, f"={{_spec['to']}} mm" if _has_unit else f"={{_spec['to']}}")
        _sheet.recompute()
    _doc.recompute()
    result["changed"] = [h[2] for h in _targets]
    result["errors"] = [o.Label for o in _doc.Objects if {{"Invalid", "Error"}} & set(o.State or [])]
"""


def _pick_object(name):
    objects = server._fc("doc_info").get("objects", [])
    if name and any(name in (o["name"], o["label"]) for o in objects):
        return name
    solids = [o for o in objects if o.get("top_level") and o.get("volume_mm3")]
    return max(solids, key=lambda o: o["volume_mm3"])["name"] if solids else None


def _size_checks(expect, measured):
    if "solids" not in measured:
        return [_check("measure", False, measured.get("error"))]
    checks = []
    if "solids" in expect:
        checks.append(
            _check(
                f"solids == {expect['solids']}", measured["solids"] == expect["solids"], measured["solids"]
            )
        )
    if "volume_mm3" in expect:
        target, tol = expect["volume_mm3"]
        got = measured["volume_mm3"]
        error = 100 * (got - target) / target
        checks.append(
            _check(
                f"volume within {tol:.1f}%", abs(error) <= tol, f"{got:.1f} vs {target:.1f} ({error:.2f}%)"
            )
        )
    if "bbox_sorted_mm" in expect:
        # Targets are listed smallest first; None marks a size the prompt leaves open.
        # A list of targets means more than one answer is right (e.g. 17 or 18 teeth).
        target, tol = expect["bbox_sorted_mm"]
        options = target if isinstance(target[0], list) else [target]
        got = sorted(measured["bbox"]["size_mm"])
        ok = any(
            all(b is None or abs(a - b) <= tol for a, b in zip(got, option, strict=True))
            for option in options
        )
        checks.append(_check(f"bbox within {tol:.1f} mm", ok, f"{got} vs {target}"))
    if "bolt_circle" in expect:
        spec = expect["bolt_circle"]
        radius, tol = spec["pcd_mm"] / 2, spec.get("tol_mm", 0.5)
        holes = [
            c
            for c in measured.get("cylinders", [])
            if abs(c["diameter_mm"] - spec["diameter_mm"]) < 0.05
            and abs(c["axis_from_center_mm"] - radius) <= tol
        ]
        label = f"{spec['count']} holes of {spec['diameter_mm']} mm on PCD {spec['pcd_mm']} mm"
        checks.append(_check(label, len(holes) >= spec["count"], f"{len(holes)} found"))
    if "min_faces" in expect:
        faces = measured["faces"]
        checks.append(_check(f"at least {expect['min_faces']} faces", faces >= expect["min_faces"], faces))
    if "holes" in expect:
        found = measured.get("cylindrical_faces_by_diameter_mm", {})
        # Counterbores and tubes show more than one cylindrical face per hole, hence >=.
        for dia, count in expect["holes"].items():
            checks.append(_check(f"holes {dia} mm x{count}", found.get(dia, 0) >= count, found))
    return checks


def _hydrostatics_check(name, spec):
    report = server._fc("hydrostatics", timeout=240, name=name, mass_kg=spec["mass_kg"], rho_kg_m3=1000.0)
    freeboard = report.get("freeboard_mm", -1) if report.get("floats") else -1
    low, high = spec["min_freeboard_mm"], spec.get("max_freeboard_mm", float("inf"))
    label = f"freeboard {low}-{high} mm" if high != float("inf") else f"floats with freeboard >= {low} mm"
    return _check(
        label, low <= freeboard <= high, f"freeboard {freeboard} mm, draft {report.get('draft_mm')} mm"
    )


def _printability_checks(name, spec):
    report = server._fc(
        "printability",
        timeout=240,
        name=name,
        max_overhang_deg=45.0,
        build_volume_mm=spec.get("fits"),
        min_wall_mm=spec.get("min_wall_mm"),
    )
    checks = []
    if "needs_support" in spec:
        checks.append(
            _check(
                f"needs_support == {spec['needs_support']}",
                report.get("needs_support") == spec["needs_support"],
                f"overhang {report.get('overhang_area_pct', 0):.1f}%",
            )
        )
    if "fits" in spec:
        checks.append(
            _check("fits build volume", report.get("fits_build_volume"), report.get("part_size_mm"))
        )
    if "min_wall_mm" in spec:
        checks.append(
            _check(
                f"no wall < {spec['min_wall_mm']:.1f} mm",
                report.get("thin_wall_samples_pct", 100) == 0,
                f"min {report.get('wall_min_mm')} mm",
            )
        )
    return checks


def score_case(case, obj=None):
    expect = case.get("expect", {})
    _activate_document_with(obj)
    name = _pick_object(obj)
    if name is None:
        return {
            "case": case["id"],
            "object": None,
            "score": 0.0,
            "checks": [_check("object exists", False, "no solid found")],
        }

    geometry = server._fc("check_geometry", name=name)
    checks = [_check("valid geometry", geometry.get("valid"), geometry.get("issues"))]
    checks += _size_checks(expect, server._fc("measure", name=name))
    if "hydrostatics" in expect:
        checks.append(_hydrostatics_check(name, expect["hydrostatics"]))
    if "printability" in expect:
        checks += _printability_checks(name, expect["printability"])
    if case.get("reference_step"):
        cmp = server._fc("compare_shapes", candidate=name, reference=str(HERE / case["reference_step"]))
        checks.append(_check("IoU >= 0.95", cmp.get("iou", 0) >= 0.95, cmp.get("iou")))

    passed = sum(c["pass"] for c in checks)
    return {
        "case": case["id"],
        "object": name,
        "score": round(passed / len(checks), 3),
        "passed": passed,
        "total": len(checks),
        "checks": checks,
    }


# Replies often ask without a question mark ("I need the pipe diameter", "Please send me ...").
REQUEST = re.compile(
    r"\?|\b(i need|i'd need|please (send|tell|give|share|provide|confirm)|let me know|tell me|"
    r"before i (build|start|model)|could you|can you)\b",
    re.IGNORECASE,
)


def asks_for_input(text):
    return bool(REQUEST.search(text or ""))


def score_ask(case, final_text, objects_created):
    asked = asks_for_input(final_text)
    built_nothing = objects_created == 0
    return {
        "case": case["id"],
        "score": 1.0 if asked and built_nothing else 0.0,
        "checks": [
            _check("asked a question", asked, ""),
            _check("built nothing before asking", built_nothing, f"{objects_created} objects"),
        ],
    }


def rescore_ask_rows(csv_path):
    """Re-score the ask cases of a saved run from their stored reply text."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        case = CASES.get(row["case"], {})
        if case.get("should_ask"):
            built = json.loads(row["checks"])[1]["detail"].split()[0]
            row.update(
                {k: v for k, v in score_ask(case, row["final_text"], int(built)).items() if k != "case"}
            )
            row["checks"] = json.dumps(row["checks"]) if not isinstance(row["checks"], str) else row["checks"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("case", nargs="?")
    parser.add_argument("--object", default=None)
    parser.add_argument("--rescore", metavar="CSV", help="re-score the ask cases of a saved run")
    args = parser.parse_args()
    if args.rescore:
        for row in rescore_ask_rows(args.rescore):
            print(f"{row['case']:<24} {float(row['score']):.2f}")
    else:
        print(json.dumps(score_case(CASES[args.case], args.object), indent=1))


def score_structure():
    """check_model_structure's 0-100 score and its reasons for the open document."""
    report = server._fc("model_structure")
    return report.get("score"), report.get("issues") or report.get("error")


def score_edit(case, obj="Result"):
    """Change the case's driving size in Params and check the part follows."""
    spec = case["edit"]
    _activate_document_with(obj)
    reply = server._run(EDIT_PARAMETER.format(spec=json.dumps(spec)))
    info = reply.get("result") or {}
    label = f"a Params value of {spec['from']} drives the part"
    detail = {"found": info.get("aliases"), "changed": info.get("changed")} if info else reply.get("error")
    checks = [_check(label, bool(info.get("changed")), detail)]
    if info.get("changed"):
        checks.append(_check("recompute without errors", not info.get("errors"), info.get("errors")))
        name = _pick_object(obj)
        if name is None:
            checks.append(_check("part still exists after the edit", False, None))
        else:
            geometry = server._fc("check_geometry", name=name)
            checks.append(_check("valid after the edit", geometry.get("valid"), geometry.get("issues")))
            new_size = {"solids": 1, "bbox_sorted_mm": spec["bbox_sorted_mm"]}
            checks += _size_checks(new_size, server._fc("measure", name=name))
    passed = sum(c["pass"] for c in checks)
    return {"edit_score": round(passed / len(checks), 3), "edit_checks": checks}


def score_build_quality(case, obj="Result"):
    """Structure score for every built part, plus the edit test where the case has one.
    Runs after score_case because the edit changes the model."""
    structure, issues = score_structure()
    out = {"structure_score": structure, "structure_issues": issues}
    if case.get("edit"):
        out.update(score_edit(case, obj))
    return out
