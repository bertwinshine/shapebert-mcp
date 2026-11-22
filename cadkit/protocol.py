"""Signed, length-prefixed JSON messages between server.py and freecad_listener.py.

TCP doesn't preserve message boundaries, so every message carries a 4-byte
big-endian length header. Requests and replies are signed with HMAC-SHA256 keyed
by the shared token; the token itself never goes over the socket.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import socket
import struct
import time
from pathlib import Path

from cadkit import PROTOCOL_VERSION

HEADER = struct.Struct(">I")
MAX_MESSAGE = 64 * 1024 * 1024
# Written by freecad_listener.py on its first start; keep the path in sync with it.
TOKEN_FILE = Path(os.environ.get("FREECAD_MCP_TOKEN_FILE") or Path.home() / ".freecad_mcp" / "token")


# Requests and replies are signed under different labels, so a captured request
# can never pass as a reply.
REQUEST, REPLY = "shapebert-request", "shapebert-reply"
CLOCK_WINDOW_S = 30


class ProtocolError(Exception):
    pass


class ReplyRefused(ProtocolError):
    """The reply was unsigned or failed verification; `reply` is untrusted."""

    def __init__(self, reason: str, reply: dict):
        super().__init__(reason)
        self.reason = reason
        self.reply = reply


def read_token(path: Path = TOKEN_FILE) -> str | None:
    """The listener's shared secret, or None if the listener has never run."""
    try:
        return Path(path).read_text(encoding="utf-8").strip() or None
    except FileNotFoundError:
        return None


def encode(payload: dict) -> bytes:
    body = json.dumps(payload).encode("utf-8")
    if len(body) > MAX_MESSAGE:
        raise ProtocolError(f"message too large ({len(body)} bytes)")
    return HEADER.pack(len(body)) + body


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    chunks = []
    remaining = n
    while remaining:
        chunk = sock.recv(min(remaining, 1 << 20))
        if not chunk:
            raise ProtocolError("connection closed before the full message arrived")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def send_msg(sock: socket.socket, payload: dict) -> None:
    sock.sendall(encode(payload))


def recv_msg(sock: socket.socket) -> dict:
    (length,) = HEADER.unpack(_recv_exact(sock, HEADER.size))
    if length > MAX_MESSAGE:
        raise ProtocolError(f"announced message too large ({length} bytes)")
    return json.loads(_recv_exact(sock, length).decode("utf-8"))


def signature(token: str, label: str, version, ts, nonce, body: str) -> str:
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    text = f"{label}|{version}|{ts}|{nonce}|{digest}"
    return hmac.new(token.encode("utf-8"), text.encode("utf-8"), hashlib.sha256).hexdigest()


def sign(token: str, label: str, payload: dict, nonce: str | None = None) -> dict:
    """Envelope for `payload`; the body travels as the exact JSON text that was signed."""
    body = json.dumps(payload)
    ts = int(time.time())
    nonce = nonce or secrets.token_hex(16)
    sig = signature(token, label, PROTOCOL_VERSION, ts, nonce, body)
    return {"v": PROTOCOL_VERSION, "ts": ts, "nonce": nonce, "sig": sig, "body": body}


def open_reply(token: str, envelope: dict, nonce: str) -> dict:
    """The verified payload of a reply to the request signed with `nonce`."""
    if not isinstance(envelope.get("sig"), str) or not isinstance(envelope.get("body"), str):
        raise ReplyRefused("unsigned", envelope)
    if envelope.get("v") != PROTOCOL_VERSION:
        raise ReplyRefused("protocol", envelope)
    ts = envelope.get("ts")
    expected = signature(token, REPLY, PROTOCOL_VERSION, ts, nonce, envelope["body"])
    if not hmac.compare_digest(envelope["sig"], expected) or envelope.get("nonce") != nonce:
        raise ReplyRefused("signature", envelope)
    if not isinstance(ts, int) or abs(time.time() - ts) > CLOCK_WINDOW_S:
        raise ReplyRefused("stale", envelope)
    payload = json.loads(envelope["body"])
    if not isinstance(payload, dict):
        raise ReplyRefused("signature", envelope)
    return payload


def request(host: str, port: int, payload: dict, token: str, timeout: float) -> dict:
    """Send one signed request and return the verified reply.

    Raises ReplyRefused when the reply is unsigned or its signature is wrong.
    """
    envelope = sign(token, REQUEST, payload)
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.settimeout(timeout)
        send_msg(s, envelope)
        return open_reply(token, recv_msg(s), envelope["nonce"])
