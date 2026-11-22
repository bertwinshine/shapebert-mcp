"""Limits on what the AI can do on this computer through the MCP server.

Free-form code is off unless the user switches it on, file reads and writes stay
inside one work folder, and every piece of free-form code is logged there.
"""

import ast
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

MODEL_FILES = {".step", ".stp", ".iges", ".igs", ".brep", ".brp", ".stl", ".3mf", ".obj"}
DOCUMENT_FILES = {".fcstd"}

CODE_OFF_MESSAGE = (
    "Free-form code is switched off (the default). Build with the structured tools instead: "
    "create_box, create_cylinder, set_placement, bind_parameters, pattern_polar, pattern_linear, "
    "boolean, fillet_edges, chamfer_edges. If the part really needs free-form code, tell the user "
    "what for; they can switch it on themselves as the ShapeBert README describes under "
    '"Switching free-form code on". Do not edit the plugin\'s own files: updates replace them.'
)


# Free-form code may import only these. The list doesn't make it a sandbox (FreeCAD's
# own modules can still read and write files), but it stops the usual moves of an
# injected prompt: run a program, reach the network, delete files.
ALLOWED_IMPORTS = {
    "FreeCAD",
    "App",
    "Part",
    "Sketcher",
    "Draft",
    "PartDesign",
    "Spreadsheet",
    "Fem",
    "ObjectsFem",
    "Mesh",
    "MeshPart",
    "BOPTools",
    "math",
    "cmath",
    "itertools",
    "functools",
    "collections",
    "json",
    "re",
    "dataclasses",
    "typing",
    "copy",
    "random",
    "statistics",
    "decimal",
    "fractions",
}
# Add-on packages under FreeCAD's lowercase namespace, allowed one by one.
ALLOWED_PACKAGES = {"freecad.gears"}
BLOCKED_NAMES = {
    "getattr",
    "setattr",
    "delattr",
    "vars",
    "dir",
    "locals",
    "globals",
    "eval",
    "exec",
    "compile",
    "open",
    "__import__",
    "breakpoint",
}
# FreeCADGui runs these as Python, so they would carry any code past the checks.
BLOCKED_ATTRIBUTES = {"doCommand", "doCommandGui", "runCommand", "addCommand", "runMacro"}
# Allowed modules keep system modules as attributes (collections._sys, random._os,
# dataclasses.sys), and typing evaluates strings, so the import list alone leaks.
SYSTEM_ATTRIBUTES = {
    "os",
    "nt",
    "posix",
    "sys",
    "subprocess",
    "builtins",
    "importlib",
    "inspect",
    "codecs",
    "operator",
    "io",
    "linecache",
    "get_type_hints",
    "ForwardRef",
    "eval_type",
}
ALLOWED_DUNDERS = {"__name__", "__init__"}

SYSTEM_ACCESS_MESSAGE = (
    "The code uses {found}, which CAD code doesn't need, so it was not run. Imports are "
    "limited to FreeCAD's CAD modules and plain maths/data modules (math, collections, "
    "json, re and similar). Use the file tools (import_model, export_model, save_document) "
    "for files. If you really need this, the user can set FREECAD_MCP_ALLOW_SYSTEM=1 the same "
    'way as FREECAD_MCP_ALLOW_CODE (ShapeBert README, "Switching free-form code on").'
)


class SafetyError(Exception):
    pass


def system_access_allowed() -> bool:
    return os.environ.get("FREECAD_MCP_ALLOW_SYSTEM", "").strip().lower() in {"1", "true", "yes"}


def system_access(code: str) -> list[str]:
    """Imports, names and attributes in `code` that CAD code is not allowed to use."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []  # FreeCAD reports the syntax error itself
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(f"import {a.name}" for a in node.names if not _import_allowed(a.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level or not _import_allowed(node.module or ""):
                found.add(f"import {'.' * node.level}{node.module or ''}")
            found.update(a.name for a in node.names if _blocked_name(a.name))
        elif isinstance(node, ast.Name) and _blocked_name(node.id):
            found.add(node.id)
        elif isinstance(node, ast.Attribute) and _blocked_attribute(node.attr):
            found.add(f".{node.attr}")
    return sorted(found)


def _import_allowed(module: str) -> bool:
    if module.split(".")[0] in ALLOWED_IMPORTS:
        return True
    return any(module == p or module.startswith(f"{p}.") for p in ALLOWED_PACKAGES)


def _blocked_name(name: str) -> bool:
    return name in BLOCKED_NAMES or name in BLOCKED_ATTRIBUTES or _bad_dunder(name)


def _blocked_attribute(attr: str) -> bool:
    return attr in BLOCKED_ATTRIBUTES or attr.lstrip("_") in SYSTEM_ATTRIBUTES or _bad_dunder(attr)


def _bad_dunder(name: str) -> bool:
    # __subclasses__, __globals__, __self__, __builtins__ are the classic ways around a block list.
    return name.startswith("__") and name not in ALLOWED_DUNDERS


def code_allowed() -> bool:
    return os.environ.get("FREECAD_MCP_ALLOW_CODE", "").strip().lower() in {"1", "true", "yes"}


def work_dir() -> Path:
    path = Path(os.environ.get("FREECAD_MCP_WORKDIR") or Path.home() / "FreeCAD_MCP_work")
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def safe_path(path: str, allowed_types: set[str]) -> Path:
    """Resolve `path` inside the work folder. Relative paths are taken from there."""
    base = work_dir()
    given = Path(path)
    # resolve() follows symlinks and "..", so neither can be used to step outside.
    target = (given if given.is_absolute() else base / given).resolve()
    if base not in target.parents:
        raise SafetyError(f"{path} is outside the work folder {base}")
    if target.suffix.lower() not in allowed_types:
        raise SafetyError(f"file type '{target.suffix}' not allowed here, use one of {sorted(allowed_types)}")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


# Seconds the listener waits for the user's answer in FreeCAD's approval dialog;
# keep in sync with freecad_listener.py (tests check it).
APPROVAL_TIMEOUT_S = 120


def log_code(source: str, code: str, blocked: bool = False) -> None:
    _log_record(
        {
            "source": source,
            "blocked": bool(blocked),
            "sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
            "code": code,
        }
    )


def log_decision(source: str, code: str, decision: str) -> None:
    """Record the user's answer in FreeCAD's approval dialog; sha256 links it to the code."""
    _log_record(
        {"source": source, "decision": decision, "sha256": hashlib.sha256(code.encode("utf-8")).hexdigest()}
    )


def _log_record(fields: dict) -> None:
    record = {"time": dt.datetime.now().isoformat(timespec="seconds"), **fields}
    log = work_dir() / "logs" / "code_log.jsonl"
    log.parent.mkdir(exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
