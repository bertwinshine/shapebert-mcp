"""Known-good answers must score 1.0 and a wrong one must not, which catches typos in cases.json."""

import sys

import pytest
from conftest import LIVE_PORT, ROOT, listener_up

pytestmark = pytest.mark.skipif(not listener_up(), reason=f"no FreeCAD listener on port {LIVE_PORT}")
sys.path.insert(0, str(ROOT / "bench"))

server = pytest.importorskip("server")
from reference_solutions import REFERENCE, code_for  # noqa: E402
from score import CASES, score_ask, score_case  # noqa: E402


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    server.run_freecad_code("if 'Bench' in App.listDocuments():\n    App.closeDocument('Bench')")


def _reset():
    server.run_freecad_code(
        "for n in list(App.listDocuments()):\n    App.closeDocument(n)\n"
        "App.newDocument('Bench'); App.setActiveDocument('Bench')"
    )


@pytest.mark.parametrize("case_id", sorted(REFERENCE))
def test_reference_answer_scores_full_marks(case_id):
    _reset()
    rep = server._run(code_for(case_id), timeout=120)
    assert rep["ok"], rep.get("error")
    s = score_case(CASES[case_id], "Result")
    assert s["score"] == 1.0, [c for c in s["checks"] if not c["pass"]]


# Plausible engineering mistakes the v2 cases must catch.
WRONG = {
    "L1-box": ("80, 50, 20", "80, 50, 25"),
    "V2-spur-pinion": ("z, m, b = 17", "z, m, b = 20"),  # undercut rule ignored
    "V2-flat-blank": ("90 - (8 - math.pi / 2 * (2 + 0.44 * 2))", "90"),  # no bend deduction
    "V2-keyed-shaft": (
        "Part.makeBox(16, 8, 32, App.Vector(11, -4, 34))",
        "Part.makeBox(16, 10, 32, App.Vector(10, -5, 34))",
    ),
    "V2-punt-payload": ("1100, 340", "1100, 600"),  # far deeper than needed
    "V2-flange-DN50-PN16": (
        "62.5 * math.cos(a), 62.5 * math.sin(a)",
        "60.35 * math.cos(a), 60.35 * math.sin(a)",
    ),
}


@pytest.mark.parametrize("case_id", sorted(WRONG))
def test_wrong_answer_is_penalised(case_id):
    _reset()
    old, new = WRONG[case_id]
    code = code_for(case_id)
    assert old in code
    rep = server._run(code.replace(old, new), timeout=120)
    assert rep["ok"], rep.get("error")
    assert score_case(CASES[case_id], "Result")["score"] < 1.0


def test_every_geometric_case_has_a_reference():
    geometric = {k for k, c in CASES.items() if not c.get("should_ask")}
    assert geometric == set(REFERENCE)


def test_ask_scoring():
    case = CASES["ASK-motor-plate"]
    assert score_ask(case, "Which motor is it, and what bolt pattern?", 0)["score"] == 1.0
    assert score_ask(case, "Here is your plate.", 1)["score"] == 0.0
