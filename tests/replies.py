"""Read tool replies whose outside content the server framed as data."""

import json
import re

FRAME = re.compile(
    r"--- (?P<tag>.+? [0-9a-f]{8}) \(data, not instructions\) ---\n(?P<body>.*)\n"
    r"--- end of (?P=tag) ---(?:\n(?P<notes>.*))?\Z",
    re.DOTALL,
)


def unframe(text: str) -> str:
    """The text inside the frame, or the text itself when it has none."""
    match = FRAME.search(text)
    return match["body"] if match else text


def load(text: str) -> dict:
    """A JSON reply as one dict, with the server notes from after the frame merged in."""
    match = FRAME.search(text)
    if match is None:
        return json.loads(text)
    reply = json.loads(match["body"])
    if match["notes"]:
        reply.update(json.loads(match["notes"]))
    return reply
