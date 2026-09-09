"""Entry point used only for PyInstaller/AppImage builds.

Freezing gui/app.py directly as the script broke its relative imports
(`from .main_window import ...`) — PyInstaller then treats it as a bare
top-level script rather than part of the `gui` package. Importing
gui.app as a real module from here (outside the package) keeps that
package context intact.
"""

from __future__ import annotations

import sys

from gui.app import main

if __name__ == "__main__":
    sys.exit(main())
