"""Length-prefixed JSON messages between server.py and freecad_listener.py.

TCP doesn't preserve message boundaries, so every message carries a 4-byte
big-endian length header.
"""

from __future__ import annotations

import json
import os
import socket
import struct
from pathlib import Path

HEADER = struct.Struct(">I")
MAX_MESSAGE = 64 * 1024 * 1024
# Written by freecad_listener.py on its first start; keep the path in sync with it.
TOKEN_FILE = Path(os.environ.get("FREECAD_MCP_TOKEN_FILE") or Path.home() / ".freecad_mcp" / "token")


class ProtocolError(Exception):
    pass


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


def request(host: str, port: int, payload: dict, timeout: float) -> dict:
    """Open a connection, send one message, wait for one reply."""
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.settimeout(timeout)
        send_msg(s, payload)
        return recv_msg(s)
