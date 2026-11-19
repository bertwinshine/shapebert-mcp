"""Framing: messages must arrive whole, however TCP splits them."""

import json
import socket
import threading

import freecad_listener as L
from cadkit import protocol


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
