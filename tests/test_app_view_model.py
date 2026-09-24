"""Application shell view model: titles, status text and file-action guards."""

from pathlib import Path

import pytest
from PyQt6.QtCore import QSettings, QUrl, Qt
from PyQt6.QtGui import QGuiApplication

from crane_statics.qml_app.session import SessionState
from crane_statics.core.accessibility import contrast_ratio
from crane_statics.qml_app.viewmodels.app_vm import AppViewModel

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"


@pytest.fixture
def app_vm():
    return AppViewModel(SessionState())


class TestTitleAndStatus:
    def test_initial_state_has_no_document(self, app_vm):
        assert app_vm.title == "Crane Statics"
        assert app_vm.statusText == "No document loaded"
        assert app_vm.hasDocument is False

    def test_title_shows_file_name_and_dirty_marker(self, app_vm):
        if not EXAMPLE.exists():
            pytest.skip("Example file not found")
        app_vm.openPath(str(EXAMPLE))

        assert app_vm.title == f"Crane Statics - {EXAMPLE.name}"

        app_vm.session.model.set_dirty(True)
        assert app_vm.title == f"Crane Statics - {EXAMPLE.name} ●"

    def test_new_document_is_titled_untitled(self, app_vm):
        app_vm.newDocument()

        assert app_vm.title == "Crane Statics - Untitled"
        assert app_vm.hasDocument is True

    def test_closing_restores_the_no_document_state(self, app_vm):
        app_vm.newDocument()
        messages: list[tuple[str, str]] = []
        app_vm.notification.connect(lambda msg, level: messages.append((msg, level)))

        app_vm.closeDocument()

        assert app_vm.hasDocument is False
        assert app_vm.title == "Crane Statics"
        assert app_vm.statusText == "No document loaded"
        assert ("Document closed", "info") in messages


class TestSaveGuards:
    def test_save_without_document_warns(self, app_vm):
        messages: list[tuple[str, str]] = []
        app_vm.notification.connect(lambda msg, level: messages.append((msg, level)))

        assert app_vm.save() is False
        assert messages and messages[-1][1] == "warning"

    def test_save_without_path_does_not_write(self, app_vm):
        app_vm.newDocument()

        assert app_vm.save() is False
        assert app_vm.currentPath == ""

    def test_save_as_appends_the_json_suffix(self, app_vm, tmp_path):
        app_vm.newDocument()
        target = tmp_path / "model_without_suffix"

        assert app_vm.saveAs(QUrl.fromLocalFile(str(target))) is True

        assert target.with_suffix(".json").exists()
        assert app_vm.currentPath.endswith(".json")
        assert app_vm.dirty is False

    def test_save_after_save_as_reuses_the_path(self, app_vm, tmp_path):
        app_vm.newDocument()
        target = tmp_path / "model.json"
        app_vm.saveAs(QUrl.fromLocalFile(str(target)))
        app_vm.session.model.set_dirty(True)

        assert app_vm.save() is True
        assert app_vm.dirty is False


class TestLayoutReset:
    def test_reset_is_ignored_without_a_document(self, app_vm):
        requested: list[int] = []
        app_vm.layoutResetRequested.connect(lambda: requested.append(1))

        app_vm.resetLayout()

        assert requested == []

    def test_reset_emits_with_a_document(self, app_vm):
        app_vm.newDocument()
        requested: list[int] = []
        app_vm.layoutResetRequested.connect(lambda: requested.append(1))

        app_vm.resetLayout()

        assert requested == [1]


class TestColorScheme:
    @pytest.fixture(autouse=True)
    def _isolate_settings(self):
        settings = QSettings("CraneStatics", "CraneStatics")
        had_value = settings.contains("ui/colorScheme")
        previous = settings.value("ui/colorScheme") if had_value else None
        settings.remove("ui/colorScheme")
        settings.sync()
        yield
        if had_value:
            settings.setValue("ui/colorScheme", previous)
        else:
            settings.remove("ui/colorScheme")
        settings.sync()

    def test_defaults_to_following_the_system(self):
        assert AppViewModel(SessionState()).colorScheme == "system"

    @pytest.mark.parametrize("scheme", ["light", "dark", "system"])
    def test_choice_persists_across_instances(self, scheme):
        first = AppViewModel(SessionState())
        first.setColorScheme("dark" if scheme != "dark" else "light")
        first.setColorScheme(scheme)

        assert first.colorScheme == scheme
        assert AppViewModel(SessionState()).colorScheme == scheme

    def test_unknown_scheme_is_ignored(self):
        vm = AppViewModel(SessionState())
        vm.setColorScheme("light")
        changes: list[int] = []
        vm.colorSchemeChanged.connect(lambda: changes.append(1))

        vm.setColorScheme("solarized")

        assert vm.colorScheme == "light"
        assert changes == []

        @pytest.mark.parametrize("scheme", ["light", "dark", "system"])
        def test_restored_scheme_can_be_applied_to_qt(self, scheme):
            first = AppViewModel(SessionState())
            first.setColorScheme(scheme)

            restored = AppViewModel(SessionState())
            restored.applyColorScheme()

            expected = {
                "light": Qt.ColorScheme.Light,
                "dark": Qt.ColorScheme.Dark,
                "system": Qt.ColorScheme.Unknown,
            }[scheme]
            assert restored.colorScheme == scheme
            assert QGuiApplication.styleHints().colorScheme() == expected


class TestAccessibilityTokens:
    @pytest.mark.parametrize(
        "background",
        [(46, 125, 50), (163, 95, 0), (198, 40, 40), (21, 101, 192)],
    )
    def test_inverse_text_meets_wcag_aa_on_semantic_backgrounds(self, background):
        assert contrast_ratio((255, 255, 255), background) >= 4.5

    def test_contrast_ratio_rejects_malformed_rgb_values(self):
        with pytest.raises(ValueError):
            contrast_ratio((0, 0), (255, 255, 255))
