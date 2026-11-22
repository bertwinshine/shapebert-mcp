"""Framing: messages must arrive whole, however TCP splits them."""

import json
import socket
import threading
import time

import pytest

import freecad_listener as L
from cadkit import protocol

TOKEN = "test-token"


def test_roundtrip_small():
    a, b = socket.socketpair()
    protocol.send_msg(a, {"type": "ping"})
    assert protocol.recv_msg(b) == {"type": "ping"}


def test_roundtrip_large_5mb():
    a, b = socket.socketpair()
    payload = {"code": "x = 1\n" * 900_000}  # ~5.4 MB, far above the old 1 MB recv
    t = threading.Thread(target=protocol.send_msg, args=(a, payload))
    t.start()
    got = protocol.recv_msg(b)
    t.join()
    assert got == payload


def test_message_split_into_tiny_chunks():
    a, b = socket.socketpair()
    raw = protocol.encode({"msg": "äöü – unicode ok", "n": list(range(1000))})

    def dribble():
        for i in range(0, len(raw), 7):
            a.sendall(raw[i : i + 7])

    t = threading.Thread(target=dribble)
    t.start()
    assert protocol.recv_msg(b)["msg"] == "äöü – unicode ok"
    t.join()


def test_listener_and_server_framing_are_identical():
    a, b = socket.socketpair()
    L._send_msg(a, {"from": "listener"})
    assert protocol.recv_msg(b) == {"from": "listener"}
    protocol.send_msg(b, {"from": "server"})
    assert L._recv_msg(a) == {"from": "server"}


def test_old_unframed_reply_is_detected():
    """An old v0.2 listener replies raw JSON; the header then decodes to a huge length."""
    a, b = socket.socketpair()
    a.sendall(json.dumps({"ok": True, "result": "pong"}).encode())
    a.close()
    try:
        protocol.recv_msg(b)
    except protocol.ProtocolError:
        return
    raise AssertionError("expected ProtocolError")


def test_listener_and_server_sign_identically():
    args = (TOKEN, protocol.REPLY, protocol.PROTOCOL_VERSION, 1700000000, "ab" * 16, '{"ok": true}')
    assert protocol.signature(*args) == L._signature(*args)
    assert (L._REQUEST, L._REPLY, L.CLOCK_WINDOW_S) == (
        protocol.REQUEST,
        protocol.REPLY,
        protocol.CLOCK_WINDOW_S,
    )
    assert L.PROTOCOL_VERSION == protocol.PROTOCOL_VERSION


def test_envelope_carries_no_token():
    envelope = protocol.sign(TOKEN, protocol.REQUEST, {"type": "ping"})
    assert set(envelope) == {"v", "ts", "nonce", "sig", "body"}
    assert TOKEN not in json.dumps(envelope)


def test_signed_reply_opens():
    reply = L._sign_reply(TOKEN, {"ok": True, "result": 42}, "cd" * 16)
    assert protocol.open_reply(TOKEN, reply, "cd" * 16) == {"ok": True, "result": 42}


def _reply(**changes):
    return {**L._sign_reply(TOKEN, {"ok": True, "result": "pong"}, "cd" * 16), **changes}


@pytest.mark.parametrize(
    "envelope, reason",
    [
        ({"ok": True, "result": "pong"}, "unsigned"),
        (_reply(body='{"ok": true, "result": "evil"}'), "signature"),
        (_reply(sig="0" * 64), "signature"),
        (_reply(nonce="ef" * 16), "signature"),
        (_reply(v=protocol.PROTOCOL_VERSION - 1), "protocol"),
        (L._sign_reply("another-token", {"ok": True}, "cd" * 16), "signature"),
        (protocol.sign(TOKEN, protocol.REQUEST, {"ok": True}, nonce="cd" * 16), "signature"),
    ],
    ids=[
        "unsigned",
        "tampered-body",
        "wrong-sig",
        "other-request",
        "old-protocol",
        "other-token",
        "reflected",
    ],
)
def test_bad_replies_are_refused(envelope, reason):
    with pytest.raises(protocol.ReplyRefused) as refused:
        protocol.open_reply(TOKEN, envelope, "cd" * 16)
    assert refused.value.reason == reason


def test_old_reply_is_refused(monkeypatch):
    envelope = L._sign_reply(TOKEN, {"ok": True}, "cd" * 16)
    monkeypatch.setattr(time, "time", lambda: envelope["ts"] + protocol.CLOCK_WINDOW_S + 1)
    with pytest.raises(protocol.ReplyRefused, match="stale"):
        protocol.open_reply(TOKEN, envelope, "cd" * 16)
