"""Starts the ShapeBert listener in FreeCAD's GUI only after the user has agreed to it.

The answer is kept in FreeCAD's preferences, so the user is asked once; the
ShapeBert_Bridge macro asks again.
"""

import os

import FreeCAD as App

PARAMS = "User parameter:BaseApp/Preferences/Mod/ShapeBert"
START, OFF = "start", "off"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LISTENER = os.path.join(ROOT, "freecad_listener.py")
TITLE = "ShapeBert bridge"


def choice() -> str:
    """'start', 'off', or '' when the user has not been asked yet."""
    return App.ParamGet(PARAMS).GetString("Bridge", "")


def on_startup() -> None:
    current = choice()
    if current == START:
        start_listener()
    elif current == "":
        ask()


def ask() -> None:
    """Show the consent dialog; the answer is applied when the user clicks."""
    _show_dialog(apply)


def apply(start: bool) -> None:
    App.ParamGet(PARAMS).SetString("Bridge", START if start else OFF)
    if start:
        start_listener()
        return
    running = getattr(App, "_mcp_listener", None)
    if running is not None:
        running.stop()
        App._mcp_listener = None
    App.Console.PrintMessage(
        "[ShapeBert] The bridge is off. To start it later, run Macro > Macros... > ShapeBert_Bridge.\n"
    )


def start_listener() -> None:
    with open(LISTENER, encoding="utf-8") as f:
        exec(compile(f.read(), LISTENER, "exec"), {"__name__": "__main__", "__file__": LISTENER})


def message() -> str:
    port = os.environ.get("FREECAD_MCP_PORT", "9876")
    return (
        "ShapeBert lets AI assistants (Claude Code and other MCP clients) build and check parts "
        f"in this FreeCAD through a bridge on this computer only (127.0.0.1:{port}). Every request "
        "must be signed with a secret token that only your user account can read.\n\n"
        "Warning: a connected AI agent can run code in FreeCAD with the full permissions of your "
        "user account. Free-form code stays off unless you switch it on in the MCP server, and "
        "then each script needs your OK in a dialog here.\n\n"
        "Start the bridge now and every time FreeCAD starts? You can change this later with "
        "Macro > Macros... > ShapeBert_Bridge."
    )


def _show_dialog(on_answer) -> None:
    """Opened with open(), not exec(): no nested event loop, so FreeCAD finishes starting."""
    import FreeCADGui as Gui
    from PySide import QtWidgets

    box = QtWidgets.QMessageBox(Gui.getMainWindow())
    box.setWindowTitle(TITLE)
    box.setIcon(QtWidgets.QMessageBox.Warning)
    box.setText(message())
    start = box.addButton("Start with FreeCAD", QtWidgets.QMessageBox.AcceptRole)
    off = box.addButton("Don't start", QtWidgets.QMessageBox.RejectRole)
    box.setDefaultButton(off)
    box.setEscapeButton(off)
    box.finished.connect(lambda _result: on_answer(box.clickedButton() is start))
    box.open()
