"""Listener behaviour outside FreeCAD: job isolation, output capture, concurrency, timeouts."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

import freecad_listener as L
from cadkit import protocol


def test_listener_does_not_autostart_outside_freecad():
    assert L.App is None
    assert not hasattr(L, "_mcp_listener")


def test_result_and_stdout_captured():
    rep = L.execute_job("print('hello')\nresult = {'a': 1}")
    assert rep["ok"] is True
    assert rep["result"] == {"a": 1}
    assert rep["stdout"] == "hello\n"


def test_error_returns_traceback_and_ok_false():
    rep = L.execute_job("x = 1\nraise ValueError('boom')")
    assert rep["ok"] is False
    assert "ValueError: boom" in rep["error"]


def test_fresh_namespace_each_job():
    L.execute_job("leak = 42")
    rep = L.execute_job("result = 'leak' in dir()")
    assert rep["result"] is False


def test_non_json_result_is_stringified():
    rep = L.execute_job("result = object()")
    assert rep["ok"] and isinstance(rep["result"], str)


def test_default_result_when_not_set():
    assert L.execute_job("x = 1")["result"] == "executed"


TOKEN = "test-token"


@pytest.fixture
def live(unused_port):
    """A real Listener on a socket, with a 'main thread' loop draining jobs."""
    lst = L.Listener(port=unused_port, token=TOKEN)
    threading.Thread(target=lst.serve, daemon=True).start()
    stop = threading.Event()

    def main_loop():
        while not stop.is_set():
            lst.drain()
            time.sleep(0.005)

    threading.Thread(target=main_loop, daemon=True).start()
    for _ in range(100):
        if lst.running:
            break
        time.sleep(0.01)
    yield lst
    stop.set()
    lst.stop()


@pytest.fixture
def unused_port():
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _req(port, payload, timeout=10):
    return protocol.request("127.0.0.1", port, {"token": TOKEN, **payload}, timeout)


def test_token_file_is_created_once_and_reused(tmp_path):
    path = tmp_path / "sub" / "token"
    first = L.load_or_create_token(path)
    assert len(first) == 32 and L.load_or_create_token(path) == first
    assert protocol.read_token(path) == first


def test_read_token_without_file(tmp_path):
    assert protocol.read_token(tmp_path / "missing") is None


@pytest.mark.parametrize("token", [None, "", "wrong"])
def test_requests_without_the_right_token_are_refused(live, token):
    payload = {"type": "run_script", "code": "import builtins; builtins._sneaky = True"}
    if token is not None:
        payload["token"] = token
    rep = protocol.request("127.0.0.1", live.port, payload, 5)
    assert rep["ok"] is False and rep["auth"] is False
    import builtins

    assert not hasattr(builtins, "_sneaky")


def test_slow_job_keeps_running_and_its_report_can_be_fetched(live):
    rep = _req(
        live.port, {"type": "run_script", "code": "import time; time.sleep(0.8); result = 7", "timeout": 0.2}
    )
    assert rep["ok"] is False and rep["still_running"] is True
    pending = _req(live.port, {"type": "result", "job_id": rep["job_id"]})
    assert pending["pending"] is True
    done = _req(live.port, {"type": "result", "job_id": rep["job_id"], "wait": 5})
    assert done["ok"] is True and done["result"] == 7


def test_unknown_job_id(live):
    rep = _req(live.port, {"type": "result", "job_id": "999"})
    assert rep["ok"] is False and "unknown" in rep["error"]


def test_long_stdout_is_paged(live):
    rep = _req(live.port, {"type": "run_script", "code": "print('a' * 30000 + 'b' * 15000, end='')"})
    assert rep["stdout_chars"] == 45000 and rep["stdout"] == "a" * 5000 + "b" * 15000
    first = _req(live.port, {"type": "result", "job_id": rep["job_id"], "stdout_offset": 0})
    second = _req(live.port, {"type": "result", "job_id": rep["job_id"], "stdout_offset": 40000})
    assert first["stdout"] == "a" * 20000 and first["more"] is True
    assert second["stdout"] == "b" * 5000 and second["more"] is False


def test_status_lists_recent_jobs(live):
    rep = _req(live.port, {"type": "run_script", "code": "result = 1"})
    jobs = _req(live.port, {"type": "status"})["recent_jobs"]
    assert jobs[-1] == {"job_id": rep["job_id"], "ok": True, "duration_s": rep["duration_s"]}


def test_only_recent_finished_jobs_are_kept(live, monkeypatch):
    monkeypatch.setattr(L, "KEEP_FINISHED", 3)
    ids = [_req(live.port, {"type": "run_script", "code": "result = 1"})["job_id"] for _ in range(6)]
    assert _req(live.port, {"type": "result", "job_id": ids[-1]})["ok"] is True
    assert "unknown" in _req(live.port, {"type": "result", "job_id": ids[0]})["error"]


def test_ping_and_status(live):
    assert _req(live.port, {"type": "ping"})["result"] == "pong"
    st = _req(live.port, {"type": "status"})
    assert st["ok"] and st["queued"] == 0 and st["protocol"] == L.PROTOCOL_VERSION


def test_unknown_message_type(live):
    rep = _req(live.port, {"type": "explode"})
    assert rep["ok"] is False and "unknown" in rep["error"]


def test_parallel_calls_each_get_their_own_correct_answer(live):
    """20 clients at once: every reply must belong to its own request."""

    def job(i):
        return _req(live.port, {"type": "run_script", "code": f"result = {i} * 2"})

    with ThreadPoolExecutor(20) as ex:
        reps = list(ex.map(job, range(20)))
    assert [r["result"] for r in reps] == [i * 2 for i in range(20)]
    assert all(r["ok"] for r in reps)
    assert len({r["job_id"] for r in reps}) == 20


def test_timed_out_job_that_never_started_is_cancelled(live):
    # occupy the main thread for 1.5 s
    slow = threading.Thread(
        target=_req,
        args=(live.port, {"type": "run_script", "code": "import time; time.sleep(1.5)", "timeout": 5}),
    )
    slow.start()
    time.sleep(0.2)
    rep = _req(
        live.port,
        {"type": "run_script", "code": "import builtins; builtins._ran_late = True", "timeout": 0.3},
    )
    assert rep["ok"] is False and "never started" in rep["error"]
    slow.join()
    time.sleep(0.2)
    import builtins

    assert not getattr(builtins, "_ran_late", False), "cancelled job must not run later"


def test_listener_survives_an_exception_and_keeps_working(live):
    bad = _req(live.port, {"type": "run_script", "code": "1/0"})
    assert bad["ok"] is False
    good = _req(live.port, {"type": "run_script", "code": "result = 'still alive'"})
    assert good["result"] == "still alive"


def test_large_code_and_result(live):
    code = "data = '" + "x" * 2_000_000 + "'\nresult = len(data)"
    assert _req(live.port, {"type": "run_script", "code": code}, 30)["result"] == 2_000_000


def test_silent_client_is_dropped_after_the_read_timeout(unused_port, monkeypatch):
    import socket

    monkeypatch.setattr(L, "READ_TIMEOUT_S", 0.2)
    lst = L.Listener(port=unused_port, token=TOKEN)
    threading.Thread(target=lst.serve, daemon=True).start()
    time.sleep(0.1)
    with socket.create_connection(("127.0.0.1", unused_port), timeout=5) as s:
        s.settimeout(5)
        reply = protocol.recv_msg(s)  # sends nothing; the listener gives up and answers
    lst.stop()
    assert reply["ok"] is False and "bad message" in reply["error"]


def test_too_many_open_connections_are_refused(live, monkeypatch):
    import socket

    for _ in range(L.MAX_CONNECTIONS):
        assert live.slots.acquire(blocking=False)
    try:
        with socket.create_connection(("127.0.0.1", live.port), timeout=5) as s:
            s.settimeout(5)
            reply = protocol.recv_msg(s)
    finally:
        for _ in range(L.MAX_CONNECTIONS):
            live.slots.release()
    assert reply["ok"] is False and "busy" in reply["error"]


def test_full_job_queue_refuses_new_jobs(monkeypatch):
    lst = L.Listener(port=0, token=TOKEN)
    monkeypatch.setattr(L, "MAX_QUEUED_JOBS", 1)
    lst.jobs.put(object())
    reply = lst._run({"code": "result = 1"})
    assert reply["ok"] is False and "waiting" in reply["error"]
