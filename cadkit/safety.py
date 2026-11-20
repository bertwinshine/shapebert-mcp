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


# CAD code never needs these. Blocking them doesn't make free-form code a sandbox
# (FreeCAD's own modules can still read and write files), but it stops the usual
# moves of an injected prompt: run a program, reach the network, delete files.
BLOCKED_MODULES = {
    "os",
    "subprocess",
    "socket",
    "shutil",
    "pathlib",
    "urllib",
    "http",
    "requests",
    "ftplib",
    "smtplib",
    "telnetlib",
    "ssl",
    "ctypes",
    "winreg",
    "_winapi",
    "msvcrt",
    "multiprocessing",
    "pickle",
    "marshal",
    "importlib",
    "webbrowser",
    "pty",
    "signal",
    "sys",
    "builtins",
    "gc",
    "inspect",
    "runpy",
}
BLOCKED_CALLS = {"eval", "exec", "compile", "open", "__import__", "globals", "breakpoint"}

SYSTEM_ACCESS_MESSAGE = (
    "The code uses {found}, which CAD code doesn't need, so it was not run. Use the file "
    "tools (import_model, export_model, save_document) for files. If you really need this, "
    "the user can set FREECAD_MCP_ALLOW_SYSTEM=1 the same way as FREECAD_MCP_ALLOW_CODE "
    '(ShapeBert README, "Switching free-form code on").'
)


class SafetyError(Exception):
    pass


def system_access_allowed() -> bool:
    return os.environ.get("FREECAD_MCP_ALLOW_SYSTEM", "").strip().lower() in {"1", "true", "yes"}


def system_access(code: str) -> list[str]:
    """Names of blocked modules, calls and dunder tricks used in `code`."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []  # FreeCAD reports the syntax error itself
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names if a.name.split(".")[0] in BLOCKED_MODULES)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in BLOCKED_MODULES:
                found.add(node.module)
        elif isinstance(node, ast.Name) and node.id in BLOCKED_CALLS:
            found.add(f"{node.id}()")
        elif isinstance(node, ast.Name) and _dunder(node.id) and node.id != "__name__":
            found.add(node.id)
        elif _getattr_dunder(node):
            # getattr(__builtins__, "__import__") hides the name in a string.
            found.add(node.args[1].value)
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr != "__init__":
            # __subclasses__, __globals__, __builtins__ are the classic ways around a block list
            found.add(node.attr)
    return sorted(found)


def _dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _getattr_dunder(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"getattr", "setattr", "delattr", "hasattr"}
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
        and node.args[1].value.startswith("__")
    )


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


def log_code(source: str, code: str, blocked: bool = False) -> None:
    record = {
        "time": dt.datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "blocked": bool(blocked),
        "sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
        "code": code,
    }
    log = work_dir() / "logs" / "code_log.jsonl"
    log.parent.mkdir(exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
