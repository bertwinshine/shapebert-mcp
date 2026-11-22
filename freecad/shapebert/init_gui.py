"""Offers to start the ShapeBert bridge when FreeCAD's GUI opens (Addon Manager install)."""

from PySide import QtCore

from freecad.shapebert import bridge

# The main window must exist before the dialog or the listener's timer can use it.
QtCore.QTimer.singleShot(1500, bridge.on_startup)
