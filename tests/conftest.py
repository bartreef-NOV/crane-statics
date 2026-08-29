"""Session-scoped QGuiApplication fixture for Qt/QML tests."""

import sys
import pytest
from PyQt6.QtGui import QGuiApplication


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    yield app
