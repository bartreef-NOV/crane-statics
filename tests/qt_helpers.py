"""Event-loop helpers for tests that wait on Qt signals from worker threads."""

from __future__ import annotations

import time
from typing import Callable

from PyQt6.QtCore import QCoreApplication


def wait_until(predicate: Callable[[], object], timeout: float = 60.0) -> None:
    """Pump the Qt event loop until ``predicate()`` holds; worker signals arrive this way."""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        QCoreApplication.processEvents()
        time.sleep(0.005)


def pump_events(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.005)
