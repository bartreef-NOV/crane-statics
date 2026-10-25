"""Session-scoped QGuiApplication fixture for Qt/QML tests."""

import copy
import sys
import pytest
from PyQt6.QtGui import QGuiApplication


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    yield app


_SWEEP_MEMO: dict = {}


@pytest.fixture(autouse=True)
def memoized_blocking_sweeps(monkeypatch):
    """Share identical blocking sweeps between tests.

    ``ChartViewModel.drawBlocking`` re-sweeps the same example once per test, which
    dominates the suite's runtime. A sweep is a pure function of the document content,
    limits, hoist, mode and step, so the first result is reused (as a copy). Calls with
    progress/cancel/streaming callbacks run for real.
    """
    from crane_statics.core.chart_cache import chart_fingerprint
    from crane_statics.qml_app.viewmodels import chart_vm as chart_vm_module

    real = chart_vm_module.run_mode_sweep

    def memoized(doc, hoist_id, mode_name, enabled_limits, outreach_step, names, *args, **kw):
        if args or any(v is not None for v in kw.values()):
            return real(doc, hoist_id, mode_name, enabled_limits, outreach_step, names, *args, **kw)
        key = (
            hoist_id,
            mode_name,
            outreach_step,
            chart_fingerprint(doc, enabled_limits, names),
        )
        if key not in _SWEEP_MEMO:
            _SWEEP_MEMO[key] = real(doc, hoist_id, mode_name, enabled_limits, outreach_step, names)
        return copy.deepcopy(_SWEEP_MEMO[key])

    monkeypatch.setattr(chart_vm_module, "run_mode_sweep", memoized)
