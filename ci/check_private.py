"""Fail if a tracked file contains personal data: real user paths, e-mail addresses,
or anything listed in the local, untracked .private-patterns file (your name, your
username, ...). The patterns file stays on your computer, so this script never
publishes what it looks for.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = ("knowledge-private/",)
SKIP_SUFFIXES = {".fcstd", ".stl", ".png", ".jpg", ".jpeg", ".step", ".stp", ".3mf", ".pdf"}
MAX_FILE_BYTES = 256 * 1024  # plugin file limit from docs/SECURITY_RULES.md

# These files name the author on purpose: the copyright holder, the plugin's publisher and
# the FreeCAD add-on's maintainer.
NAMES_AUTHOR = {
    "LICENSE",
    "NOTICE",
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    "package.xml",
}
# Install and uninstall commands, the official-source line, the release check and the
# Addon Manager repository URL have to name the GitHub account the plugin is published from.
PLUGIN_COMMANDS = (
    "/plugin marketplace add ",
    "/plugin install ",
    "/plugin uninstall ",
    "Official source: github.com/",
    "`gh release verify ",
    "Repository URL: `https://github.com/",
)
# The README's badge and issues link point at the official repository, which names the account.
OFFICIAL_REPO_URL = "https://github.com/bertwinshine/shapebert-mcp"
OFFICIAL_REPO = re.compile(re.escape(OFFICIAL_REPO_URL) + r"(?![\w.-])")
# CODEOWNERS has to name the owner's GitHub handle; other content there is still checked.
CODEOWNERS = ".github/CODEOWNERS"
OWNER_LINE = re.compile(r"^\S+(?:\s+@[A-Za-z0-9-]+(?:/[A-Za-z0-9_.-]+)?)+\s*$")

BUILT_IN = [
    # Real home folders; placeholders like <you>, YOU or path/to are fine.
    re.compile(r"[A-Za-z]:\\\\?Users\\\\?(?!<|you\b|YOU\b|Public\b)[A-Za-z0-9._-]+", re.IGNORECASE),
    re.compile(r"/(?:home|Users)/(?!<|you\b|runner\b|user\b)[a-z][a-z0-9._-]+"),
    re.compile(
        r"[A-Za-z0-9._%+-]+@(?!users\.noreply\.github\.com|example\.(?:com|org))[A-Za-z0-9.-]+\.[a-z]{2,}"
    ),
]


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [f for f in out.stdout.splitlines() if not f.startswith(SKIP_DIRS)]


def local_patterns() -> list[re.Pattern]:
    path = ROOT / ".private-patterns"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [
        re.compile(re.escape(x.strip()), re.IGNORECASE) for x in lines if x.strip() and not x.startswith("#")
    ]


def has_personal_data(line: str, patterns: list[re.Pattern]) -> bool:
    """True if a pattern matches outside the official repository URL."""
    return any(p.search(OFFICIAL_REPO.sub("", line)) for p in patterns)


def main() -> int:
    patterns = BUILT_IN + local_patterns()
    hits = []
    for name in tracked_files():
        if Path(name).suffix.lower() == ".fcstd":
            hits.append(f"{name}: .FCStd files must not be tracked")
            continue
        path = ROOT / name
        if path.is_file() and path.stat().st_size > MAX_FILE_BYTES:
            hits.append(f"{name}: {path.stat().st_size} bytes, over the 256 KiB plugin limit")
        if Path(name).suffix.lower() in SKIP_SUFFIXES or name in {"ci/check_private.py", *NAMES_AUTHOR}:
            continue
        try:
            text = (ROOT / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith(PLUGIN_COMMANDS):
                continue
            if name == CODEOWNERS and OWNER_LINE.match(line):
                continue
            if has_personal_data(line, patterns):
                hits.append(f"{name}:{number}: {line.strip()[:100]}")
    for hit in hits:
        print(hit)
    print(f"{len(hits)} problem(s) found" if hits else "no personal data, no .FCStd, no oversized files")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
