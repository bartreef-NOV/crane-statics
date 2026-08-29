# ADR-0001 — `SessionState` is the signal seam, not a mirror of `SessionModel`

- **Status**: accepted
- **Date**: 2026-08-27
- **Supersedes**: the facade rule formerly enforced by
  `tests/test_architecture.py::test_session_state_exposes_explicit_facade_api`

## Context

`core.session_model.SessionModel` holds the session: the loaded document, the
per-hoist scene states, the selected hoist, the derived design limits, the dirty
flag. It is pure Python and publishes changes through a small `subscribe(event,
callback)` registry.

`qml_app.session.SessionState` is the Qt side of that. It wraps a `SessionModel`,
declares six `pyqtSignal`s, and connects each to the matching model event so QML
view models can `connect(...)` to them.

It also used to mirror the model: roughly forty members, every one of the form
`return self._model.x` or `return self._model.f(...)`. The six signals and the six
`subscribe` hookups in `__init__` were the only implementation. A previous
architecture test pinned that mirror in place — it forbade a `__getattr__`
passthrough and required five named delegates to exist — on the reasoning that the
session's surface should be explicit rather than magic.

The friction was that the mirror is a **large shallow interface**: as complex to
learn as the implementation behind it, and it charged a second edit for every
`SessionModel` member added. It also bought no encapsulation. `SessionModel`'s
attributes are public and mutable, and the view models already mutated them
straight through — `session.get_active_hoist_state().scene_state.wind_speed_m_s = …`
reaches the model's interior regardless of how many delegates sit in front of it.

## Decision

`SessionState` is the six signals plus the `model` it wraps:

```python
class SessionState(QObject):
    dirty_changed = pyqtSignal(bool)
    document_changed = pyqtSignal(object)
    content_changed = pyqtSignal()
    hoist_selected = pyqtSignal(str)
    design_limits_changed = pyqtSignal(list)
    notification = pyqtSignal(str, str)

    def __init__(self, model=None, parent=None):
        super().__init__(parent)
        self.model = model if model is not None else SessionModel()
        for event, signal in (...):
            self.model.subscribe(event, signal.emit)
```

The forty delegates are gone. Each view model binds `self._model = session.model` in
its `__init__` and reads session state as `self._model.x`; `self._session` is kept
for signal connections and for the object's lifetime, nothing else.

The old test is replaced by `test_session_state_stays_a_signal_seam`, which asserts
the public class surface is exactly those six signals and that an instance carries a
`SessionModel`. The intent of the original rule — an explicit surface, no magic — is
better served by having nothing to be explicit about than by forty hand-written
delegates.

## Consequences

- Adding a `SessionModel` member costs one edit, not two.
- A new delegating member on `SessionState` now fails a test, in the opposite
  direction from before. So does a `__getattr__`.
- `SessionState()` still constructs with no arguments, so test setup is unchanged;
  only member access moved to `.model`.
- Tests that need session state but no Qt signals construct a `SessionModel`
  directly. That is the intended reading of the seam: the signals are the only
  thing `SessionState` adds, so a test that does not exercise signals should not
  need Qt at all.
- The seam sits where something actually varies — a pure model on one side, Qt
  signal delivery on the other. `SessionState` is the only adapter across it, and
  the whole reason it exists is that `pyqtSignal` cannot live in `core/`.
