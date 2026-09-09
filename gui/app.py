"""Application entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .main_window import APP_STYLESHEET, MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Proton Drive GUI")
    app.setStyleSheet(APP_STYLESHEET)
    icon_path = Path(__file__).resolve().parent.parent / "assets" / "icon.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
