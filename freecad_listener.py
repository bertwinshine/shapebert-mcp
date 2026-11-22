"""Socket listener that runs inside FreeCAD and executes code sent by server.py.

Run it as a macro in the FreeCAD GUI, or headless with
``FREECAD_MCP_HEADLESS=1 freecadcmd freecad_listener.py``. ``FREECAD_MCP_PORT``
overrides the default port 9876.

Every request must be signed with the token stored in ~/.freecad_mcp/token (or the
file named by ``FREECAD_MCP_TOKEN_FILE``), and every reply is signed the same way.
The listener creates the file on first start and server.py reads it, so only
programs running as your user can send code. The token never goes over the socket.

Requests marked for approval (free-form code written by the AI) wait for the user
to allow them in a dialog in FreeCAD. Headless FreeCAD can't ask, so it refuses
them unless ``FREECAD_MCP_HEADLESS_CODE=1`` is set (meant for CI only).
"""

import contextlib
import hashlib
import hmac
import io
import json
import os
import queue
import secrets
import socket
import struct
import threading
import time
import traceback
from collections import OrderedDict
from pathlib import Path

try:
    import FreeCAD as App
except ImportError:
    App = None  # imported by the unit tests outside FreeCAD

LISTENER_VERSION = "1.0.0"
PROTOCOL_VERSION = 5
HOST = "127.0.0.1"
PORT = int(os.environ.get("FREECAD_MCP_PORT", "9876"))
TOKEN_FILE = Path(os.environ.get("FREECAD_MCP_TOKEN_FILE") or Path.home() / ".freecad_mcp" / "token")

KEEP_FINISHED = 50  # finished jobs whose reports can still be fetched
# Limits against a local program flooding FreeCAD. The MCP server sends one request
# at a time and parallel benchmark runs stay far below them.
MAX_CONNECTIONS = 32
MAX_QUEUED_JOBS = 50
READ_TIMEOUT_S = 30
OUTPUT_PAGE = 20000  # characters of stdout per reply
MAX_OUTPUT = 2 * 1024 * 1024
APPROVAL_TIMEOUT_S = 120
ALLOWED = {"once", "session", "session_allowed", "headless_allowed"}
REFUSALS = {
    "cancelled": "Cancelled in FreeCAD's approval dialog; the code was not run.",
    "timeout": f"No answer in FreeCAD's approval dialog within {APPROVAL_TIMEOUT_S} s; the code was not run.",
    "headless_refused": "Headless FreeCAD can't show the approval dialog, so the code was not run. "
    "For CI only, start the listener with FREECAD_MCP_HEADLESS_CODE=1.",
}

# This file is pasted into FreeCAD as a stand-alone macro, so it can't import
# cadkit. Keep the framing and signing in sync with cadkit/protocol.py (tests check it).
_HEADER = struct.Struct(">I")
_MAX_MESSAGE = 64 * 1024 * 1024
_REQUEST, _REPLY = "shapebert-request", "shapebert-reply"
CLOCK_WINDOW_S = 30
# Nonces are kept until their timestamp falls out of the clock window. Only token
# holders can add one, so the cap is a backstop, not a limit real use reaches.
MAX_NONCES = 10000


def _recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(min(n - len(buf), 1 << 20))
        if not chunk:
            raise ConnectionError("connection closed mid-message")
        buf.extend(chunk)
    return bytes(buf)


def _send_msg(sock, payload):
    body = json.dumps(payload).encode("utf-8")
    sock.sendall(_HEADER.pack(len(body)) + body)


def _recv_msg(sock):
    (length,) = _HEADER.unpack(_recv_exact(sock, _HEADER.size))
    if length > _MAX_MESSAGE:
        raise ValueError("message too large")
    return json.loads(_recv_exact(sock, length).decode("utf-8"))


def _signature(token, label, version, ts, nonce, body):
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    text = f"{label}|{version}|{ts}|{nonce}|{digest}"
    return hmac.new(token.encode("utf-8"), text.encode("utf-8"), hashlib.sha256).hexdigest()


def _sign_reply(token, payload, nonce):
    body = json.dumps(payload)
    ts = int(time.time())
    sig = _signature(token, _REPLY, PROTOCOL_VERSION, ts, nonce, body)
    return {"v": PROTOCOL_VERSION, "ts": ts, "nonce": nonce, "sig": sig, "body": body}


class _Refused(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def load_or_create_token(path=TOKEN_FILE):
    """Return the shared secret, creating the file on first use."""
    path = Path(path)
    if path.exists():
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(16)
    # Created owner-only in one step, so the secret is never readable by others in between.
    # On Windows the mode does little, but the file sits in the user's private profile.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(token)
    return token


def _jsonable(value):
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return str(value)
    return value


def _snapshot():
    if App is None:
        return {}
    return {d.Name: [o.Name for o in d.Objects] for d in App.listDocuments().values()}


def _shape_summary(obj):
    info = {"name": obj.Name, "label": obj.Label, "type": obj.TypeId}
    shape = getattr(obj, "Shape", None)
    # FEM mesh objects have a Shape property that links to the part instead.
    if not hasattr(shape, "isNull") or shape.isNull():
        return info
    bb = shape.BoundBox
    info["valid"] = bool(shape.isValid())
    info["solids"] = len(shape.Solids)
    info["volume_mm3"] = round(shape.Volume, 3)
    info["bbox_mm"] = [round(bb.XLength, 3), round(bb.YLength, 3), round(bb.ZLength, 3)]
    return info


def _rollback(before):
    """Remove objects created since ``before`` and close documents that are new."""
    removed = []
    for name, doc in list(App.listDocuments().items()):
        if name not in before:
            App.closeDocument(name)
            removed.append(f"document {name}")
            continue
        old = set(before[name])
        for obj in reversed(list(doc.Objects)):
            obj_name = obj.Name
            if obj_name in old:
                continue
            # Best effort: FreeCAD sometimes raises after the object is already gone,
            # so check the document instead of trusting the exception.
            with contextlib.suppress(Exception):
                doc.removeObject(obj_name)
            if doc.getObject(obj_name) is None:
                removed.append(f"{name}.{obj_name}")
        with contextlib.suppress(Exception):
            doc.recompute()
    return removed


def _inspect_new_objects(before):
    new_objects, warnings = [], []
    for name, doc in App.listDocuments().items():
        old = set(before.get(name, []))
        for obj in doc.Objects:
            state = list(getattr(obj, "State", []) or [])
            if "Invalid" in state or "Error" in state:
                warnings.append(f"{name}.{obj.Name} state={state}")
            if obj.Name in old or len(new_objects) >= 25:
                continue
            summary = _shape_summary(obj)
            new_objects.append(summary)
            if summary.get("valid") is False:
                warnings.append(f"{obj.Name} is NOT a valid shape")
    return new_objects, warnings


def execute_job(code, rollback=True, job_id="local"):
    """Run ``code`` in a fresh namespace and return a report dict."""
    return _execute(code, rollback, job_id)[0]


def _execute(code, rollback, job_id):
    """Like execute_job, but also return the whole stdout for paging."""
    started = time.time()
    before = _snapshot()
    out, err = io.StringIO(), io.StringIO()
    env = {"__name__": "__mcp_job__", "__builtins__": __builtins__}
    if App is not None:
        env.update({"FreeCAD": App, "App": App})

    report = {"job_id": job_id, "ok": False, "result": None, "error": None}
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            exec(compile(code, f"<mcp-job-{job_id}>", "exec"), env)
    except Exception:  # noqa: BLE001 - arbitrary user code; the traceback is the report
        report["error"] = traceback.format_exc(limit=8)
        if rollback and App is not None:
            report["rolled_back"] = _rollback(before)
    else:
        report["ok"] = True
        report["result"] = _jsonable(env.get("result", "executed"))

    stdout = out.getvalue()[:MAX_OUTPUT]
    report["stdout"] = stdout[-OUTPUT_PAGE:]
    if len(stdout) > OUTPUT_PAGE:
        report["stdout_chars"] = len(stdout)
        report["stdout_note"] = "Only the end is shown; page through it with get_job_result."
    report["stderr"] = err.getvalue()[-OUTPUT_PAGE:]
    if App is not None and report["ok"]:
        report["new_objects"], report["warnings"] = _inspect_new_objects(before)
    report["duration_s"] = round(time.time() - started, 3)
    return report, stdout


def _qt_ask(source, code, on_decision):
    """Show the approval dialog without blocking; return a function that closes it.

    The dialog is not modal and runs no event loop of its own, so FreeCAD keeps
    working while it is open. Cancel is the default button, and Esc or closing the
    window also cancels.
    """
    import FreeCADGui as Gui
    from PySide import QtCore, QtGui, QtWidgets

    dialog = QtWidgets.QDialog(Gui.getMainWindow())
    dialog.setWindowTitle("ShapeBert: allow AI-written code?")
    dialog.setWindowFlags(dialog.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
    layout = QtWidgets.QVBoxLayout(dialog)
    layout.addWidget(
        QtWidgets.QLabel(
            f"An AI assistant wants to run this Python code in FreeCAD ({source}).\n"
            "It can do anything your user account can. Read it before you allow it.\n"
            f"Without an answer it is cancelled after {APPROVAL_TIMEOUT_S} s."
        )
    )
    text = QtWidgets.QPlainTextEdit(code)
    text.setReadOnly(True)
    text.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
    text.setMinimumSize(640, 360)
    layout.addWidget(text)
    buttons = QtWidgets.QDialogButtonBox()
    once = buttons.addButton("Run once", QtWidgets.QDialogButtonBox.AcceptRole)
    session = buttons.addButton("Allow for this FreeCAD session", QtWidgets.QDialogButtonBox.AcceptRole)
    cancel = buttons.addButton("Cancel", QtWidgets.QDialogButtonBox.RejectRole)
    for button in (once, session):
        button.setAutoDefault(False)
    cancel.setDefault(True)
    layout.addWidget(buttons)
    decided = []

    def decide(decision):
        if decided:
            return
        decided.append(decision)
        dialog.hide()
        dialog.deleteLater()
        on_decision(decision)

    once.clicked.connect(lambda: decide("once"))
    session.clicked.connect(lambda: decide("session"))
    cancel.clicked.connect(lambda: decide("cancelled"))
    dialog.rejected.connect(lambda: decide("cancelled"))
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    cancel.setFocus()

    def close():
        if not decided:
            decided.append("closed")
            dialog.hide()
            dialog.deleteLater()

    return close


class _Job:
    def __init__(self, job_id, code, rollback, approval=None):
        self.id = job_id
        self.code = code
        self.rollback = rollback
        # Approval jobs: {"source", "code"} to show; decision, when asked, the closer.
        self.approval = approval
        self.decision = None
        self.decided = threading.Event()
        self.asked_at = None
        self.close = None
        self.done = threading.Event()
        self.abandoned = False
        self.started_at = None
        self.report = None
        self.stdout = ""


def _approval(msg):
    approval = msg.get("approval")
    if approval is None:
        return None
    if not isinstance(approval, dict):
        approval = {}
    return {
        "source": str(approval.get("source", "code")),
        "code": str(approval.get("code", msg.get("code", ""))),
    }


class Listener:
    def __init__(self, host=HOST, port=PORT, token=None):
        self.host = host
        self.port = port
        self.token = token or load_or_create_token()
        self.jobs = queue.Queue()
        self.known = OrderedDict()  # job id -> _Job, queued, running or recently finished
        self.current = None
        self.counter = 0
        self.lock = threading.Lock()
        self.running = False
        self.srv = None
        self.timer = None
        self.slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        self.nonces = {}  # nonce -> its request timestamp
        # ask(source, code, on_decision) -> close; set by start_gui. None means headless.
        self.ask = None
        self.pending = None  # the approval job waiting for an answer
        self.session_allowed = False
        self.nonce_lock = threading.Lock()

    def drain(self):
        """Run queued jobs. Must be called on FreeCAD's main thread.

        While an approval is open, later jobs wait so they run in order.
        """
        while True:
            if self.pending is not None and not self._settle(self.pending):
                return
            try:
                job = self.jobs.get_nowait()
            except queue.Empty:
                return
            if job.abandoned:
                job.done.set()
            elif job.approval is not None:
                self._ask(job)
            else:
                self._start(job)

    def _start(self, job):
        self.current = job
        job.started_at = time.time()
        try:
            job.report, job.stdout = _execute(job.code, job.rollback, job.id)
            if job.approval is not None:
                job.report["approval"] = job.decision
        finally:
            self.current = None
            job.code = ""  # can be megabytes; the report is all we keep
            job.done.set()

    def _standing_decision(self):
        if self.session_allowed:
            return "session_allowed"
        if self.ask is None:
            allowed = os.environ.get("FREECAD_MCP_HEADLESS_CODE") == "1"
            return "headless_allowed" if allowed else "headless_refused"
        return None

    def _ask(self, job):
        job.decision = self._standing_decision()
        if job.decision is None:
            job.asked_at = time.time()
            self.pending = job
            job.close = self.ask(job.approval["source"], job.approval["code"], lambda d: self._answer(job, d))
        else:
            self._finish_approval(job)

    def _answer(self, job, decision):
        if job.decision is None:
            job.decision = decision

    def _settle(self, job):
        """Finish the open approval if it has an answer or ran out of time."""
        if job.decision is None:
            if not job.abandoned and time.time() - job.asked_at <= APPROVAL_TIMEOUT_S:
                return False
            job.decision = "timeout"
        self.pending = None
        job.close()
        self._finish_approval(job)
        return True

    def _finish_approval(self, job):
        job.decided.set()
        if job.decision == "session":
            self.session_allowed = True
        if job.decision in ALLOWED and not job.abandoned:
            self._start(job)
            return
        error = REFUSALS.get(job.decision, REFUSALS["timeout"])
        job.report = {"ok": False, "job_id": job.id, "approval": job.decision, "error": error}
        job.code = ""
        job.done.set()

    def status(self):
        cur = self.current
        with self.lock:
            recent = [j for j in self.known.values() if j.report][-5:]
        return {
            "ok": True,
            "listener_version": LISTENER_VERSION,
            "protocol": PROTOCOL_VERSION,
            "queued": self.jobs.qsize(),
            "busy_job": cur.id if cur else None,
            "busy_for_s": round(time.time() - cur.started_at, 1) if cur and cur.started_at else 0,
            "recent_jobs": [
                {"job_id": j.id, "ok": j.report.get("ok"), "duration_s": j.report.get("duration_s")}
                for j in recent
            ],
            "freecad_version": ".".join(App.Version()[:3]) if App else None,
            "documents": list(App.listDocuments()) if App else [],
            "gui": bool(App and App.GuiUp),
        }

    def handle(self, conn):
        if not self.slots.acquire(blocking=False):
            with conn, contextlib.suppress(OSError):
                _send_msg(
                    conn, {"ok": False, "busy": True, "error": "listener busy: too many open connections"}
                )
            return
        try:
            self._handle(conn)
        finally:
            self.slots.release()

    def _handle(self, conn):
        with conn:
            # A client that connects and then sends nothing would hold a thread forever.
            # Replies can take minutes, so the timeout only covers reading the request.
            conn.settimeout(READ_TIMEOUT_S)
            try:
                msg = _recv_msg(conn)
            except (OSError, ValueError) as e:
                with contextlib.suppress(OSError):
                    _send_msg(conn, {"ok": False, "error": f"bad message: {e}"})
                return
            conn.settimeout(None)

            try:
                nonce, request = self._open_request(msg)
            except _Refused as e:
                refusal = {"ok": False, "auth": False, "auth_error": e.code, "protocol": PROTOCOL_VERSION}
                _send_msg(conn, {**refusal, "error": str(e)})
                return
            _send_msg(conn, _sign_reply(self.token, self._dispatch(request), nonce))

    def _open_request(self, msg):
        """Verify a signed request; return its nonce and payload or raise _Refused."""
        if (
            not isinstance(msg, dict)
            or not isinstance(msg.get("sig"), str)
            or not isinstance(msg.get("body"), str)
        ):
            raise _Refused(
                "unsigned",
                f"unsigned request refused: this listener needs signed requests (protocol {PROTOCOL_VERSION}). "
                "Update the ShapeBert MCP server.",
            )
        if msg.get("v") != PROTOCOL_VERSION:
            raise _Refused(
                "protocol", f"request uses protocol {msg.get('v')!r}, this listener {PROTOCOL_VERSION}"
            )
        ts, nonce = msg.get("ts"), msg.get("nonce")
        if not isinstance(ts, int) or not isinstance(nonce, str) or not 16 <= len(nonce) <= 64:
            raise _Refused("signature", "malformed signature fields")
        expected = _signature(self.token, _REQUEST, PROTOCOL_VERSION, ts, nonce, msg["body"])
        if not hmac.compare_digest(msg["sig"], expected):
            raise _Refused("signature", f"wrong signature; server.py must read the token in {TOKEN_FILE}")
        now = time.time()
        if abs(now - ts) > CLOCK_WINDOW_S:
            raise _Refused("stale", f"request timestamp is more than {CLOCK_WINDOW_S} s off this clock")
        self._remember_nonce(nonce, ts, now)
        request = json.loads(msg["body"])
        if not isinstance(request, dict):
            raise _Refused("signature", "signed body is not a JSON object")
        return nonce, request

    def _remember_nonce(self, nonce, ts, now):
        with self.nonce_lock:
            # A nonce whose timestamp left the window can go: a replay of it is stale.
            self.nonces = {n: t for n, t in self.nonces.items() if t >= now - CLOCK_WINDOW_S}
            if nonce in self.nonces:
                raise _Refused("replayed", "request nonce already used")
            if len(self.nonces) >= MAX_NONCES:
                raise _Refused("busy", "too many signed requests in the last 30 s")
            self.nonces[nonce] = ts

    def _dispatch(self, msg):
        kind = msg.get("type")
        if kind == "ping":
            return {
                "ok": True,
                "result": "pong",
                "listener_version": LISTENER_VERSION,
                "protocol": PROTOCOL_VERSION,
            }
        if kind == "status":
            return self.status()
        if kind == "run_script":
            return self._run(msg)
        if kind == "result":
            return self._result(msg)
        return {"ok": False, "error": f"unknown message type {kind!r}"}

    def _remember(self, job):
        with self.lock:
            self.known[job.id] = job
            finished = [j for j in self.known.values() if j.done.is_set()]
            for old in finished[: max(0, len(finished) - KEEP_FINISHED)]:
                del self.known[old.id]

    def _run(self, msg):
        if self.jobs.qsize() >= MAX_QUEUED_JOBS:
            return {"ok": False, "error": f"{MAX_QUEUED_JOBS} jobs already waiting; try again later"}
        with self.lock:
            self.counter += 1
            job = _Job(
                str(self.counter), msg.get("code", ""), bool(msg.get("rollback", True)), _approval(msg)
            )
        self._remember(job)
        timeout = float(msg.get("timeout", 60))
        self.jobs.put(job)
        if job.approval is not None:
            # The run timeout starts once the user has answered.
            job.decided.wait(APPROVAL_TIMEOUT_S + 5)
        if job.done.wait(timeout):
            return job.report or {"ok": False, "job_id": job.id, "error": "job skipped"}

        # A queued job is cancelled so drain() skips it. A running job can't be
        # interrupted, so it finishes and its report is kept for get_job_result.
        job.abandoned = True
        if job.started_at is None:
            error = f"timed out after {timeout:g} s. The job never started (FreeCAD busy) and was cancelled."
            return {"ok": False, "job_id": job.id, "error": error}
        return {
            "ok": False,
            "job_id": job.id,
            "still_running": True,
            "approval": job.decision,
            "error": f"still running after {timeout:g} s. Fetch the report with get_job_result "
            f"(job_id {job.id!r}) instead of sending the code again.",
        }

    def _result(self, msg):
        job_id = str(msg.get("job_id", ""))
        job = self.known.get(job_id)
        if job is None:
            return {"ok": False, "job_id": job_id, "error": "unknown job id (or too old to keep)"}
        job.done.wait(max(0.0, float(msg.get("wait", 0))))
        if not job.done.is_set():
            running = round(time.time() - job.started_at, 1) if job.started_at else None
            return {"ok": False, "job_id": job_id, "pending": True, "running_for_s": running}
        if job.report is None:
            return {"ok": False, "job_id": job_id, "error": "job was cancelled before it started"}

        reply = dict(job.report)
        offset = msg.get("stdout_offset")
        if offset is not None:
            offset = max(0, int(offset))
            reply["stdout"] = job.stdout[offset : offset + OUTPUT_PAGE]
            reply["stdout_offset"] = offset
            reply["stdout_chars"] = len(job.stdout)
            reply["more"] = offset + OUTPUT_PAGE < len(job.stdout)
        return reply

    def serve(self):
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind((self.host, self.port))
        self.srv.listen(16)
        self.running = True
        while self.running:
            try:
                conn, _ = self.srv.accept()
            except OSError:  # stop() closed the socket
                break
            threading.Thread(target=self.handle, args=(conn,), daemon=True).start()

    def stop(self):
        self.running = False
        if self.timer is not None:
            self.timer.stop()
        if self.srv is not None:
            self.srv.close()

    def start_gui(self):
        import FreeCADGui as Gui
        from PySide import QtCore

        self.timer = QtCore.QTimer()
        # Without a parent the timer is garbage-collected when the macro returns.
        self.timer.setParent(Gui.getMainWindow())
        self.timer.timeout.connect(self.drain)
        self.timer.start(30)
        self.ask = _qt_ask
        threading.Thread(target=self.serve, daemon=True).start()

    def run_headless(self):
        threading.Thread(target=self.serve, daemon=True).start()
        while True:
            self.drain()
            time.sleep(0.02)


def start():
    # Re-running the macro would otherwise fail with "address already in use".
    old = getattr(App, "_mcp_listener", None)
    if old is not None:
        old.stop()
        time.sleep(0.2)

    listener = Listener()
    App._mcp_listener = listener
    banner = f"[FreeCAD MCP listener {LISTENER_VERSION}]"
    if App.GuiUp:
        listener.start_gui()
        App.Console.PrintMessage(f"{banner} listening on {HOST}:{PORT}\n")
    else:
        print(f"{banner} headless on {HOST}:{PORT}")
        listener.run_headless()
    return listener


if App is not None and (App.GuiUp or os.environ.get("FREECAD_MCP_HEADLESS") == "1"):
    start()
