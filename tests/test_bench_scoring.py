import sys

import pytest
from conftest import ROOT

sys.path.insert(0, str(ROOT / "bench"))
score = pytest.importorskip("score")


@pytest.mark.parametrize(
    "reply",
    [
        "Which motor is it?",
        "I need to know which motor this is before I build anything. Please send me the frame size.",
        "I need one number before I can build this: the outside diameter of your water pipe.",
        "Let me know the gear ratio and centre distance.",
    ],
)
def test_requests_count_as_asking(reply):
    assert score.asks_for_input(reply)


def test_a_finished_part_is_not_asking():
    assert not score.asks_for_input("Built the bracket: 80 x 40 x 5 mm, volume 15,200 mm3, valid solid.")


def test_ask_case_needs_both_a_request_and_no_geometry():
    case = score.CASES["ASK-motor-plate"]
    assert score.score_ask(case, "I need the motor model first.", 0)["score"] == 1.0
    assert score.score_ask(case, "I need the motor model first.", 2)["score"] == 0.0
