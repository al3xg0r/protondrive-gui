"""Light/dark theme palettes for the app.

Applied via QApplication.setPalette() together with the Fusion style —
native Qt styles don't reliably honor every palette role, Fusion does,
which matters since both the app's own stylesheets (APP_STYLESHEET,
sidebar/table/grid styles) and the hand-drawn icons key off palette()
colors.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

LIGHT = "light"
DARK = "dark"


def light_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.Window, QColor(240, 240, 242))
    p.setColor(QPalette.WindowText, QColor(20, 20, 22))
    p.setColor(QPalette.Base, QColor(255, 255, 255))
    p.setColor(QPalette.AlternateBase, QColor(246, 246, 248))
    p.setColor(QPalette.Text, QColor(20, 20, 22))
    p.setColor(QPalette.Button, QColor(230, 230, 233))
    p.setColor(QPalette.ButtonText, QColor(20, 20, 22))
    p.setColor(QPalette.Highlight, QColor(61, 132, 228))
    p.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.Mid, QColor(200, 200, 203))
    p.setColor(QPalette.Midlight, QColor(222, 222, 225))
    p.setColor(QPalette.Dark, QColor(120, 120, 124))
    p.setColor(QPalette.Disabled, QPalette.WindowText, QColor(165, 165, 168))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor(165, 165, 168))
    return p


def dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.Window, QColor(43, 43, 46))
    p.setColor(QPalette.WindowText, QColor(225, 225, 225))
    p.setColor(QPalette.Base, QColor(30, 30, 33))
    p.setColor(QPalette.AlternateBase, QColor(38, 38, 42))
    p.setColor(QPalette.Text, QColor(225, 225, 225))
    p.setColor(QPalette.Button, QColor(53, 53, 57))
    p.setColor(QPalette.ButtonText, QColor(225, 225, 225))
    p.setColor(QPalette.Highlight, QColor(61, 132, 228))
    p.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.Mid, QColor(70, 70, 74))
    p.setColor(QPalette.Midlight, QColor(60, 60, 64))
    p.setColor(QPalette.Dark, QColor(150, 150, 154))
    p.setColor(QPalette.Disabled, QPalette.WindowText, QColor(120, 120, 124))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor(120, 120, 124))
    return p


def palette_for(mode: str) -> QPalette:
    return dark_palette() if mode == DARK else light_palette()
