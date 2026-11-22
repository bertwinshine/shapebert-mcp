# Changelog

## 1.1.0 - 2026-11-22

**Updating from 1.0.0: run `install_autostart.FCMacro` in FreeCAD once more and
restart FreeCAD** (or update ShapeBert in the Addon Manager). The bridge now speaks
protocol 5, so an old listener and a new server refuse each other; `doctor` says
which one is out of date.

- **Signed bridge.** The token no longer travels over the socket. Every request and
  every reply is signed with HMAC-SHA256 over the protocol version, a timestamp, a
  one-time nonce and a hash of the message. The listener refuses unsigned, changed,
  replayed and stale requests (more than 30 s off), and the server ignores replies
  that fail the check.
- **Approval dialog for free-form code.** With `FREECAD_MCP_ALLOW_CODE=1`, every
  script from `run_freecad_code` (and the test run in `save_example`) waits for your
  OK in a dialog in FreeCAD: Run once, Allow for this FreeCAD session, or Cancel (the
  default). No answer in 120 s refuses it. Each answer goes to the code log. Headless
  FreeCAD refuses these scripts unless `FREECAD_MCP_HEADLESS_CODE=1` (for CI only).
- **Install from FreeCAD's Addon Manager.** The repository is now a FreeCAD add-on
  (`package.xml`, namespaced `freecad/shapebert`). After installing, FreeCAD asks
  once whether to start the bridge, with a warning that connected AI agents can run
  code with your account's permissions. The `ShapeBert_Bridge` macro changes the
  answer. The listener prints the same warning whenever it starts.
- **Single-threaded CalculiX.** Every analysis runs CalculiX on one thread, because
  multithreaded builds gave unstable results on CI. `FREECAD_MCP_CCX_THREADS=<n>`
  opts in to more threads.
