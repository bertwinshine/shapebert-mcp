"""Starts freecad_listener.py when the FreeCAD GUI opens.

install_autostart.FCMacro writes the listener's path to listener_path.txt next to
this file. Delete this folder from FreeCAD's Mod directory to turn auto-start off.
"""


def _freecad_mcp_autostart():
    import os
    import sys

    import FreeCAD as App
    from PySide import QtCore

    # FreeCAD execs InitGui.py without __file__, but it does put the Mod folder on sys.path.
    config = next(
        (
            os.path.join(p, "listener_path.txt")
            for p in sys.path
            if p.rstrip("/\\").endswith("FreeCADMCP") and os.path.isfile(os.path.join(p, "listener_path.txt"))
        ),
        None,
    )
    if config is None:
        App.Console.PrintWarning(
            "[FreeCAD MCP] listener_path.txt not found - run install_autostart.FCMacro again.\n"
        )
        return
    with open(config, encoding="utf-8") as f:
        path = f.read().strip()
    if not os.path.isfile(path):
        App.Console.PrintWarning(f"[FreeCAD MCP] listener not found at {path}\n")
        return

    def start():
        try:
            with open(path, encoding="utf-8") as f:
                exec(compile(f.read(), path, "exec"), {"__name__": "__main__", "__file__": path})
        except Exception as e:  # noqa: BLE001 - a broken listener must never stop FreeCAD from starting
            App.Console.PrintError(f"[FreeCAD MCP] auto-start failed: {e}\n")

    # Give the main window a moment to exist before the listener parents its timer to it.
    QtCore.QTimer.singleShot(1500, start)


_freecad_mcp_autostart()
