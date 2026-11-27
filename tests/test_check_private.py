"""ci/check_private.py lets the official repository URL through, and nothing broader."""

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("check_private", ROOT / "ci" / "check_private.py")
check_private = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_private)

URL = check_private.OFFICIAL_REPO_URL
ACCOUNT = URL.split("/")[3]
PATTERNS = check_private.BUILT_IN + [re.compile(re.escape(ACCOUNT), re.IGNORECASE)]


@pytest.mark.parametrize(
    "line",
    [
        URL,
        f'<a href="{URL}/actions/workflows/tests.yml"><img src="{URL}/actions/workflows/tests.yml/badge.svg"></a>',
        f"[open an issue]({URL}/issues) with the part you'd like to see built next.",
    ],
)
def test_official_repo_url_is_allowed(line):
    assert not check_private.has_personal_data(line, PATTERNS)


@pytest.mark.parametrize(
    "line",
    [
        f"https://github.com/{ACCOUNT}",
        f"https://github.com/{ACCOUNT}/other-repo",
        f"{URL}-fork",
        f"{URL}.evil",
        f"http://github.com/{ACCOUNT}/shapebert-mcp",
        f"github.com/{ACCOUNT}/shapebert-mcp",
        f"{URL}/issues, written by {ACCOUNT}",
    ],
)
def test_anything_else_naming_the_account_is_caught(line):
    assert check_private.has_personal_data(line, PATTERNS)
