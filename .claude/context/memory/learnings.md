# PyQt6 Learnings

- For QTableWidget-based "value + detail" UX, keep the numeric value in the cell text and move verbose analysis details into `QTableWidgetItem.setToolTip(...)` for readability.
- When Auto-Set writes a value programmatically, set the tooltip on that same item in the same write path; when users manually edit the value, clear the tooltip in the `itemChanged` handler to avoid stale provenance.
- Preserve MVC boundaries by deriving tooltip content from controller-produced result metadata and existing document/session state rather than hardcoding UI-only strings.
- For this PyQt6/QML app, set `QT_QUICK_CONTROLS_STYLE=Fusion` before creating `QApplication` and retain `QT_QUICK_CONTROLS_FALLBACK_STYLE=Basic` for incomplete wheels. A small `ApplicationWindow.palette` can then provide a runtime light/dark toggle without recreating a custom control style.
- Parent QML context view models and `QQmlApplicationEngine` to `QApplication`/engine in the production bootstrap, matching the test fixture. Stop `QTimer` instances and wait for active `QThread` workers from `QApplication.aboutToQuit` before teardown; otherwise QML bindings can observe null context properties and Qt may emit cross-thread `QBasicTimer::stop` warnings.
- For clean PyQt6/QML shutdown, call `engine.deleteLater()` and flush `QEvent.Type.DeferredDelete` from the `aboutToQuit` cleanup while the GUI event dispatcher is still alive; leaving the engine to `QApplication` destruction can produce `QObject::disconnect` and `QBasicTimer::start` diagnostics.
