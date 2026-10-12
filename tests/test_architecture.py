"""Import-boundary tests for the package refactor."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from crane_statics.core.session_model import SessionModel
from crane_statics.qml_app.session import SessionState

SOURCE_ROOT = Path(__file__).parent.parent / "src" / "crane_statics"
PURE_PACKAGES = ("core", "data", "calculation")
FORBIDDEN_DOMAIN_IMPORTS = (
    "PyQt6",
    "crane_statics.qml_app",
    "crane_statics.app",
    "crane_statics.ui",
    "crane_statics.render",
)
FORBIDDEN_SOURCE_IMPORTS = (
    "crane_statics.app",
    "crane_statics.ui",
    "crane_statics.render",
)


def _imports_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def _forbidden_imports(path: Path, forbidden: tuple[str, ...]) -> set[str]:
    return {
        imported
        for imported in _imports_in(path)
        if any(imported == prefix or imported.startswith(f"{prefix}.") for prefix in forbidden)
    }


@pytest.mark.parametrize("package", PURE_PACKAGES)
def test_domain_packages_do_not_import_ui_dependencies(package: str):
    violations = {
        path.relative_to(SOURCE_ROOT): _forbidden_imports(path, FORBIDDEN_DOMAIN_IMPORTS)
        for path in (SOURCE_ROOT / package).rglob("*.py")
        if _forbidden_imports(path, FORBIDDEN_DOMAIN_IMPORTS)
    }

    assert not violations, f"Domain import-boundary violations: {violations}"


def test_source_does_not_import_removed_packages():
    violations = {
        path.relative_to(SOURCE_ROOT): _forbidden_imports(path, FORBIDDEN_SOURCE_IMPORTS)
        for path in SOURCE_ROOT.rglob("*.py")
        if _forbidden_imports(path, FORBIDDEN_SOURCE_IMPORTS)
    }

    assert not violations, f"Removed package imports remain: {violations}"


def test_session_state_stays_a_signal_seam():
    """``SessionState`` is signals plus the model -- not a mirror of it.

    It used to delegate ~40 members to :class:`SessionModel`, so every session
    member cost a second edit here. See
    ``docs/adr/0001-session-state-is-the-signal-seam.md``. A new delegate
    reappearing is the regression this test exists to catch; a magic
    ``__getattr__`` passthrough is the other way to lose the explicit surface.
    """
    assert "__getattr__" not in SessionState.__dict__
    assert sorted(name for name in vars(SessionState) if not name.startswith("_")) == [
        "content_changed",
        "design_limits_changed",
        "dirty_changed",
        "document_changed",
        "hoist_selected",
        "notification",
    ]
    assert isinstance(SessionState().model, SessionModel)


@pytest.mark.parametrize("name", ["select_hoist", "active_hoist", "hoist_by_id"])
def test_session_model_exposes_only_explicit_hoist_apis(name: str):
    assert not hasattr(SessionModel, name)


def test_scene_renderer_implements_canvas_contract():
    """Verify CraneSceneRenderer exposes the public SceneCanvasContract interface.

    This guards against accidental regressions where private renderer members
    like _scene_to_world, _map_scale, or _heel_world get accessed directly
    instead of through the public contract properties.
    """
    from crane_statics.qml_app.scene.scene_renderer import CraneSceneRenderer
    from crane_statics.qml_app.scene.scene_drag import SceneCanvasContract

    # Verify the renderer has all three required properties
    for prop_name in ("scene_to_world", "map_scale", "heel_world"):
        assert hasattr(
            CraneSceneRenderer, prop_name
        ), f"CraneSceneRenderer missing required SceneCanvasContract property: {prop_name}"
        # Verify it's a property descriptor, not a method
        attr = getattr(CraneSceneRenderer, prop_name)
        assert isinstance(
            attr, property
        ), f"CraneSceneRenderer.{prop_name} must be a @property, not a method"

    # Verify the Protocol interface itself exists and has correct signatures
    assert hasattr(
        SceneCanvasContract, "__protocol_attrs__"
    ), "SceneCanvasContract must be a typing.Protocol"


def test_scene_renderer_only_shows_the_frame_it_is_handed():
    """The renderer holds no scene state of its own beyond the published frame.

    What the scene shows is decided by ``core.scene_build.build_scene_frame`` and the
    load model by ``core.drawn_loads``. The renderer used to duplicate both behind an
    eight-setter push protocol plus a hand-synced shadow copy of the scene state; its
    whole interface is now ``show(frame)`` plus the three SceneCanvasContract members.
    Anything else appearing here means scene state is drifting back into the view.
    """
    from crane_statics.qml_app.scene.scene_renderer import CraneSceneRenderer

    surface = {
        name for name in vars(CraneSceneRenderer) if not name.startswith("_") or name == "__init__"
    }

    assert surface == {
        "__init__",
        "show",
        "scene_frame",
        "scene_to_world",
        "map_scale",
        "heel_world",
    }, f"renderer surface drifted: {sorted(surface)}"


def test_drawn_load_model_is_qt_free_and_in_plane():
    """The load model is pure and documents its X/Z scope on LoadConditions."""
    from crane_statics.core import drawn_loads

    source = Path(drawn_loads.__file__).read_text(encoding="utf-8")
    assert "PyQt6" not in source and "QColor" not in source

    # Out-of-plane inputs must not be silently accepted: they belong to the
    # left/right support split, not to X/Z equilibrium.
    fields = set(drawn_loads.LoadConditions.__dataclass_fields__)
    for out_of_plane in ("accel_y_m_s2", "roll_accel_rad_s2", "sidelead_deg"):
        assert out_of_plane not in fields, f"{out_of_plane} is out-of-plane; not drawable in X/Z"
