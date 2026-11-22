"""The approval dialog for free-form code, with a fake dialog in place of Qt."""

import functools
import json
import socket
import threading
import time

import pytest
from replies import load

import freecad_listener as L
from cadkit import protocol, safety

server = pytest.importorskip("server")

TOKEN = "test-token"
FLAG = "import builtins\nbuiltins._approval_runs = getattr(builtins, '_approval_runs', 0) + 1\nresult = 'ran'"


class FakeDialog:
    """Stands in for _qt_ask: answers each question with the next queued answer.

    None leaves the question open, as a user who walks away would.
    """

    def __init__(self, *answers):
        self.answers = list(answers)
        self.asked = []
        self.closed = 0

    def __call__(self, source, code, on_decision):
        self.asked.append((source, code))
        answer = self.answers.pop(0) if self.answers else None
        if answer is not None:
            on_decision(answer)
        return self.close

    def close(self):
        self.closed += 1


@pytest.fixture
def listener(monkeypatch, tmp_path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    lst = L.Listener(port=port, token=TOKEN)
    threading.Thread(target=lst.serve, daemon=True).start()
    stop = threading.Event()

    def main_loop():
        while not stop.is_set():
            lst.drain()
            time.sleep(0.005)

    threading.Thread(target=main_loop, daemon=True).start()
    for _ in range(200):
        if lst.running:
            break
        time.sleep(0.01)
    token_file = tmp_path / "token"
    token_file.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setattr(protocol, "read_token", functools.partial(protocol.read_token, token_file))
    monkeypatch.setattr(server, "FREECAD_PORT", port)
    monkeypatch.setenv("FREECAD_MCP_WORKDIR", str(tmp_path / "work"))
    monkeypatch.setenv("FREECAD_MCP_ALLOW_CODE", "1")
    monkeypatch.delenv("FREECAD_MCP_HEADLESS_CODE", raising=False)
    yield lst
    stop.set()
    lst.stop()


@pytest.fixture(autouse=True)
def runs():
    import builtins

    builtins._approval_runs = 0
    yield lambda: builtins._approval_runs
    del builtins._approval_runs


def _ask(lst, code=FLAG, timeout=5):
    payload = {
        "type": "run_script",
        "code": code,
        "timeout": timeout,
        "approval": {"source": "test", "code": code},
    }
    return protocol.request("127.0.0.1", lst.port, payload, TOKEN, timeout + 10)


def _decisions(tmp_path):
    log = tmp_path / "work" / "logs" / "code_log.jsonl"
    return [
        r["decision"]
        for r in map(json.loads, log.read_text(encoding="utf-8").splitlines())
        if "decision" in r
    ]


def test_run_once_runs_the_code_and_asks_again_next_time(listener, runs):
    listener.ask = FakeDialog("once", "once")
    first, second = _ask(listener), _ask(listener)
    assert first["ok"] and first["result"] == "ran" and first["approval"] == "once"
    assert second["approval"] == "once" and runs() == 2 and len(listener.ask.asked) == 2
    assert listener.ask.asked[0] == ("test", FLAG)


def test_cancel_refuses_and_nothing_runs(listener, runs):
    listener.ask = FakeDialog("cancelled")
    reply = _ask(listener)
    assert reply["ok"] is False and reply["approval"] == "cancelled" and "not run" in reply["error"]
    assert runs() == 0 and listener.ask.closed == 1


def test_no_answer_in_time_refuses_and_closes_the_dialog(listener, runs, monkeypatch):
    monkeypatch.setattr(L, "APPROVAL_TIMEOUT_S", 0.3)
    listener.ask = FakeDialog(None)
    started = time.time()
    reply = _ask(listener)
    assert reply["ok"] is False and reply["approval"] == "timeout"
    assert runs() == 0 and listener.ask.closed == 1 and time.time() - started < 5


def test_an_answer_after_the_timeout_is_ignored(listener, runs, monkeypatch):
    monkeypatch.setattr(L, "APPROVAL_TIMEOUT_S", 0.3)
    late = []
    listener.ask = lambda source, code, on_decision: late.append(on_decision) or (lambda: None)
    assert _ask(listener)["approval"] == "timeout"
    late[0]("once")
    time.sleep(0.1)
    assert runs() == 0


def test_session_allow_stops_asking_until_freecad_restarts(listener, runs):
    listener.ask = FakeDialog("session")
    first, second = _ask(listener), _ask(listener)
    assert first["approval"] == "session" and second["approval"] == "session_allowed"
    assert runs() == 2 and len(listener.ask.asked) == 1
    assert not L.Listener(port=0, token=TOKEN).session_allowed


def test_headless_freecad_refuses_without_the_ci_switch(listener, runs, monkeypatch):
    assert listener.ask is None
    reply = _ask(listener)
    assert reply["ok"] is False and reply["approval"] == "headless_refused"
    assert "FREECAD_MCP_HEADLESS_CODE" in reply["error"] and runs() == 0
    monkeypatch.setenv("FREECAD_MCP_HEADLESS_CODE", "1")
    assert _ask(listener)["approval"] == "headless_allowed" and runs() == 1


def test_fixed_tool_code_is_not_asked_about(listener, runs):
    listener.ask = FakeDialog()
    reply = protocol.request("127.0.0.1", listener.port, {"type": "run_script", "code": FLAG}, TOKEN, 5)
    assert reply["ok"] and "approval" not in reply and listener.ask.asked == [] and runs() == 1


def test_later_jobs_wait_while_the_dialog_is_open(listener, runs):
    answers = []
    listener.ask = lambda source, code, on_decision: answers.append(on_decision) or (lambda: None)
    asking = threading.Thread(target=_ask, args=(listener,))
    asking.start()
    while not answers:
        time.sleep(0.01)
    queued = threading.Thread(
        target=protocol.request,
        args=("127.0.0.1", listener.port, {"type": "run_script", "code": "result = 1"}, TOKEN, 10),
    )
    queued.start()
    time.sleep(0.3)
    assert listener.jobs.qsize() == 1 and runs() == 0
    status = protocol.request("127.0.0.1", listener.port, {"type": "status"}, TOKEN, 5)
    assert status["ok"] and status["queued"] == 1
    answers[0]("once")
    asking.join(5)
    queued.join(5)
    assert listener.jobs.qsize() == 0 and runs() == 1


def test_run_freecad_code_logs_each_decision(listener, tmp_path, runs):
    listener.ask = FakeDialog("cancelled", "once")
    refused = load(server.run_freecad_code("result = 6 * 7"))
    allowed = load(server.run_freecad_code("result = 6 * 7"))
    assert refused["ok"] is False and refused["approval"] == "cancelled"
    assert allowed["ok"] and allowed["result"] == 42
    assert _decisions(tmp_path) == ["cancelled", "once"]


def test_save_example_shows_the_example_code_not_the_wrapper(listener, tmp_path, kb_copy):
    listener.ask = FakeDialog("cancelled")
    reply = json.loads(server.save_example("t", "p", "x = 1"))
    assert reply["saved"] is False and listener.ask.asked == [("save_example", "x = 1")]
    assert _decisions(tmp_path) == ["cancelled"]


def test_an_unreachable_listener_is_logged_as_no_answer(listener, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "FREECAD_PORT", 1)
    assert load(server.run_freecad_code("result = 1"))["ok"] is False
    assert _decisions(tmp_path) == ["no_answer"]


def test_server_and_listener_agree_on_the_timeout():
    assert safety.APPROVAL_TIMEOUT_S == L.APPROVAL_TIMEOUT_S
