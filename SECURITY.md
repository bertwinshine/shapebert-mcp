# Security

## Reporting a problem

Please don't open a public issue for a security problem. Use **Report a
vulnerability** on the repository's Security tab instead; only I can see those
reports. I'll answer within a week.

## How the bridge is protected

- The listener inside FreeCAD only accepts connections from `127.0.0.1`.
- Every request must be signed with the token from `~/.freecad_mcp/token`, which
  the listener creates on first start, readable by your account only. Other
  programs and web pages can't send code without it.
- The token itself never goes over the socket. Each request carries
  HMAC-SHA256(token, label | protocol version | timestamp | nonce | SHA-256 of the
  body). The listener checks it with a constant-time comparison and refuses requests
  that are unsigned (including the old plain-token format), wrongly signed, changed,
  more than 30 s off its clock, or a replay of a nonce it has already seen. It keeps
  seen nonces until their timestamp is out of the window, with a fixed upper limit.
- The listener signs every reply the same way, tied to the request's nonce. The server
  checks that signature before it uses a reply. A reply that fails the check is ignored
  and none of its text is shown, so a program squatting on the listener's port can't
  return fake results or instructions. Requests and replies are signed under different
  labels, so a captured request can't be echoed back as a reply.
- Free-form code (`run_freecad_code`, and verifying examples in `save_example`) is
  off unless `FREECAD_MCP_ALLOW_CODE=1` is set. When it is on, every script is
  logged to `logs/code_log.jsonl` in the work folder. It is still not a sandbox:
  the code can do anything your user account can, so keep your AI client's
  permission prompts on and leave it off for files or prompts from people you
  don't know.
- With code on, scripts may only import FreeCAD's CAD modules and plain maths and
  data modules (`math`, `collections`, ...). Other imports, `getattr`,
  `vars`, `open`, `eval`, `exec`, double-underscore names and FreeCAD's
  `doCommand`/`runCommand` are refused unless `FREECAD_MCP_ALLOW_SYSTEM=1` is also set. Saved examples must always be plain CAD
  code, because later sessions reuse them.
- Each tool tells the AI client whether it only reads, changes the model, or can
  overwrite things (`run_freecad_code`, exports, saves), so clients can ask before
  the risky ones.
- The server only talks to a listener on this computer; it refuses to start if
  `FREECAD_MCP_HOST` points anywhere else. Messages are signed, not encrypted, so
  code and model data stay on this computer.
- The listener drops clients that send nothing for 30 s and caps open connections
  and waiting jobs, so a misbehaving local program can't freeze FreeCAD.
- Patterns are capped at 200 copies and FEA meshes at about 2 million elements (and
  0.05 mm), so one request can't tie FreeCAD up for hours or run out of memory.
- Dependencies are pinned with checksums in `requirements.lock`.
- File tools only read and write inside the work folder (`~/FreeCAD_MCP_work`, or
  `FREECAD_MCP_WORKDIR`), and only model and FreeCAD file types.
- The server never sees your Claude login or any API key. The token is a random
  local secret, separate on every computer.

## What isn't covered

Calculator results and generated parts are engineering aids. Check anything that
carries load or people (boats, lifting parts, pressure parts) against the
standards and with a qualified engineer before you build it.
