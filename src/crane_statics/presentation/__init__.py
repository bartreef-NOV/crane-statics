"""Presentation layer: view-independent formatters and adapters.

This layer is responsible for transforming domain/analysis data into
QML-consumable formats. It should NOT import PyQt6 or qml_app.
"""

from .formatters import (
    RopeFormatter,
    ConnectionFormatter,
    HoistFormatter,
    EnvironmentFormatter,
    ResultRowFormatter,
)

__all__ = [
    "RopeFormatter",
    "ConnectionFormatter",
    "HoistFormatter",
    "EnvironmentFormatter",
    "ResultRowFormatter",
]
