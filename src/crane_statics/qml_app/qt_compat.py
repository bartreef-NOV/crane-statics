"""Names PyQt6 provides at runtime but its bundled type stubs omit."""

from __future__ import annotations

from typing import Any

from PyQt6 import QtCore

pyqtProperty: Any = getattr(QtCore, "pyqtProperty")
