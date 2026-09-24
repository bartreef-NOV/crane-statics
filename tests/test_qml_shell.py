"""QML front end: every view loads warning-free and the model tables populate."""

from pathlib import Path

import pytest
from PyQt6.QtCore import QObject, QCoreApplication, QUrl
from PyQt6.QtTest import QTest
from PyQt6.QtQml import (
    QJSValue,
    QQmlApplicationEngine,
    QQmlComponent,
    QQmlEngine,
    QQmlExpression,
)
from PyQt6.QtGui import QGuiApplication

from crane_statics.qml_app.session import SessionState
from crane_statics.qml_app.app import QML_DIR
from crane_statics.qml_app.viewmodels.app_vm import AppViewModel
from crane_statics.qml_app.viewmodels.chart_vm import ChartViewModel
from crane_statics.qml_app.viewmodels.model_vm import ModelViewModel
from crane_statics.qml_app.viewmodels.scene_vm import SceneViewModel

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"


@pytest.fixture
def qml_engine():
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(QML_DIR))

    # Parent the view models to the engine so QML objects are torn down first.
    session = SessionState()
    app_vm = AppViewModel(session, engine)
    model_vm = ModelViewModel(session, engine)
    scene_vm = SceneViewModel(session, engine)
    chart_vm = ChartViewModel(session, engine)

    engine.rootContext().setContextProperty("appVm", app_vm)
    engine.rootContext().setContextProperty("modelVm", model_vm)
    engine.rootContext().setContextProperty("sceneVm", scene_vm)
    engine.rootContext().setContextProperty("chartVm", chart_vm)

    warnings: list[str] = []
    engine.warnings.connect(lambda errors: warnings.extend(str(e.toString()) for e in errors))

    yield engine, app_vm, model_vm, warnings
    for root in engine.rootObjects():
        root.deleteLater()
    # Drain the deferred deletions before the next engine is built. Objects left
    # pending are destroyed inside a later test's event loop, and a QML item torn
    # down mid-frame takes the whole process down with it.
    QTest.qWait(20)


def test_main_qml_loads_without_warnings(qml_engine):
    engine, _app_vm, _model_vm, warnings = qml_engine
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))

    assert engine.rootObjects(), "Main.qml failed to instantiate"
    assert warnings == []


def test_theme_menu_tracks_color_scheme_preference(qml_engine):
    engine, app_vm, _model_vm, warnings = qml_engine
    app_vm.setColorScheme("system")
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))

    root = engine.rootObjects()[-1]
    actions = {
        item.property("text").replace("&", ""): item
        for item in root.findChildren(QObject)
        if isinstance(item.property("text"), str) and item.property("text")
    }
    assert {"Follow System", "Light", "Dark"} <= set(actions)

    app_vm.setColorScheme("dark")
    QTest.qWait(50)
    assert app_vm.colorScheme == "dark"
    source = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
    assert 'checked: appVm.colorScheme === "dark"' in source
    assert 'checked: appVm.colorScheme === "light"' in source
    assert warnings == []


def test_theme_override_changes_rendered_design_tokens(qml_engine):
    engine, _app_vm, _model_vm, warnings = qml_engine
    component = QQmlComponent(engine)
    component.setData(
        b"""import QtQuick
import "../design" as Design
Item {
    id: root
    property string scheme: "light"
    property color surface: Design.DesignTokens.colors.surface
    property color background: Design.DesignTokens.colors.background
    property color text: Design.DesignTokens.colors.textPrimary
    property color chartCanvas: Design.DesignTokens.colors.chartCanvasBackground
    property color chartPlot: Design.DesignTokens.colors.chartPlotBackground
    property color chartTooltip: Design.DesignTokens.colors.chartTooltipBackground
    property color chartText: Design.DesignTokens.colors.chartAxisText
    Binding { target: Design.DesignTokens; property: "colorScheme"; value: root.scheme }
}""",
        QUrl.fromLocalFile(str(QML_DIR / "theme_probe.qml")),
    )
    probe = component.create()

    assert probe is not None
    light = tuple(
        probe.property(name).name()
        for name in (
            "surface",
            "background",
            "text",
            "chartCanvas",
            "chartPlot",
            "chartTooltip",
            "chartText",
        )
    )
    probe.setProperty("scheme", "dark")
    QCoreApplication.processEvents()
    dark = tuple(
        probe.property(name).name()
        for name in (
            "surface",
            "background",
            "text",
            "chartCanvas",
            "chartPlot",
            "chartTooltip",
            "chartText",
        )
    )

    assert light == ("#ffffff", "#f7f8fa", "#202428", "#f7f8fa", "#ffffff", "#ffffff", "#4b5563")
    assert dark == ("#24282d", "#1b1e22", "#f1f3f5", "#1b1e22", "#15181c", "#24282d", "#c4cdd6")
    assert light != dark
    assert warnings == []


def test_main_tab_switching_loads_chart_without_crashing(qml_engine):
    engine, app_vm, _model_vm, warnings = qml_engine
    app_vm.openPath(str(EXAMPLE))
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))

    root = engine.rootObjects()[-1]
    tabs = root.findChild(QObject, "workspaceTabs")
    assert tabs is not None

    for index in (0, 1, 0, 1, 0, 1):
        tabs.setProperty("currentIndex", index)
        QTest.qWait(100)

    assert root.findChild(QObject, "quickChartCanvas") is not None
    assert warnings == []


def test_chart_legend_handles_long_labels_and_toggles_visibility(qml_engine):
    engine, _app_vm, _model_vm, warnings = qml_engine
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / "ChartLegend.qml")))
    legend = component.create()
    assert legend is not None

    items = [
        {
            "id": "long-limit",
            "label": "Very long engineering limit series name " * 3,
            "color": "#D55E00",
        },
        {"id": "capacity", "label": "Capacity", "color": "#0A60D2"},
    ]
    legend.setProperty("items", items)
    toggled: list[str] = []
    legend.toggleRequested.connect(toggled.append)

    assert legend.property("implicitWidth") >= 200
    assert legend.property("implicitHeight") >= 150
    assert legend.property("items") == items
    assert warnings == []


@pytest.mark.parametrize(
    "qml_file",
    [
        "NumberField.qml",
        "NumericRow.qml",
        "DataTable.qml",
        "CellEditor.qml",
        "NoDocumentPage.qml",
        "EnvironmentPanel.qml",
        "ModelWorkspace.qml",
        "SceneControlRail.qml",
        "SceneWorkspace.qml",
        "scene/QuickSceneCanvas.qml",
        "ResultsTable.qml",
        "ReportDialog.qml",
        "LoadOverviewDialog.qml",
        "ChartLegend.qml",
        "QuickChartPlot.qml",
        "DesignLimitsTable.qml",
        "ContractualTable.qml",
        "dialogs/NodeDialog.qml",
        "dialogs/MassPointDialog.qml",
        "dialogs/WindAreaDialog.qml",
        "dialogs/HoistDialog.qml",
        "dialogs/SegmentDialog.qml",
        "dialogs/ContractualPointDialog.qml",
        "DesignSystemTokensDemo.qml",
        "ComponentLibraryShowcase.qml",
        "components/StyledCheckBox.qml",
        "components/StyledRadioButton.qml",
        "components/IconButton.qml",
    ],
)
def test_component_loads_without_warnings(qml_engine, qml_file):
    engine, _app_vm, _model_vm, warnings = qml_engine
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / qml_file)))

    assert component.status() == QQmlComponent.Status.Ready, component.errorString()
    obj = component.create()
    assert obj is not None
    assert warnings == []


@pytest.mark.parametrize(
    "qml_file",
    [
        "ResultRowDelegate.qml",
        "scene/SceneCgMarker.qml",
        "scene/SceneAxisArrow.qml",
        "scene/SceneNodeMarker.qml",
    ],
)
def test_delegate_component_compiles(qml_engine, qml_file):
    engine, _app_vm, _model_vm, _warnings = qml_engine
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / qml_file)))

    # Delegates declare required model roles, so they compile but cannot be built standalone.
    assert component.status() == QQmlComponent.Status.Ready, component.errorString()


def _cell_editor(engine, **properties):
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / "CellEditor.qml")))
    assert component.status() == QQmlComponent.Status.Ready, component.errorString()
    editor = component.createWithInitialProperties(properties)
    assert editor is not None
    return editor


@pytest.mark.parametrize(
    "kind, initial, expected",
    [
        ("text", "mh_winch", "mh_winch"),
        ("number", "1.500", "1.500"),
        ("int", 3, "3"),
        ("bool", True, True),
        ("node", "bh_winch", "bh_winch"),
    ],
)
def test_cell_editor_reads_back_what_the_operator_left_in_it(qml_engine, kind, initial, expected):
    engine, _app_vm, _model_vm, warnings = qml_engine

    editor = _cell_editor(engine, kind=kind, initialValue=initial, choices=["bh_winch", "mh_winch"])

    assert editor.property("value") == expected
    assert warnings == []


def test_cell_editor_offers_a_node_it_was_not_given(qml_engine):
    """Ropes are reeved through primary-structure nodes the editable list leaves out.

    The combo box has to keep such an id rather than snap to the first choice,
    or opening the cell would silently re-route the rope.
    """
    engine, _app_vm, _model_vm, warnings = qml_engine

    editor = _cell_editor(engine, kind="node", initialValue="boom_heel", choices=["mh_winch"])

    assert editor.property("value") == "boom_heel"
    assert warnings == []


def test_cell_editor_commits_once_and_not_at_all_after_escape(qml_engine):
    """Qt closes an editor for Return, for Escape and for losing focus alike.

    Return commits and then drops focus, and Escape drops focus too, so the
    editor has to remember which of the two happened.
    """
    engine, _app_vm, _model_vm, warnings = qml_engine
    accepted = _cell_editor(engine, kind="number", initialValue="1.500")
    commits: list[object] = []
    accepted.commitRequested.connect(lambda: commits.append(accepted.property("value")))

    _evaluate_in(accepted, "commit()")
    _evaluate_in(accepted, "commit()")

    assert commits == ["1.500"]

    cancelled = _cell_editor(engine, kind="number", initialValue="2.500")
    refused: list[int] = []
    cancelled.commitRequested.connect(lambda: refused.append(1))

    _evaluate_in(cancelled, "cancel()")
    _evaluate_in(cancelled, "commit()")

    assert refused == []
    assert cancelled.property("cancelled") is True
    assert warnings == []


def test_model_workspace_tables_populate_from_document(qml_engine):
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    _engine, app_vm, model_vm, _warnings = qml_engine
    app_vm.openPath(str(EXAMPLE))

    assert model_vm.bodyIds
    assert model_vm.hoistIds
    assert model_vm.hoistsModel.count == len(app_vm.session.model.document.hoists)

    model_vm.selectBody("boom")
    assert model_vm.nodesModel.count > 0
    assert model_vm.massPointsModel.count > 0

    model_vm.selectHoist(model_vm.hoistIds[0])
    assert model_vm.ropeSegmentsModel.count > 0


def test_model_load_chart_hoist_selector_excludes_solve_hoist(qml_engine):
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    _engine, app_vm, model_vm, _warnings = qml_engine
    app_vm.openPath(str(EXAMPLE))

    assert model_vm.payloadHoistIds
    assert "BH" not in model_vm.payloadHoistIds
    assert set(model_vm.payloadHoistIds) <= set(model_vm.hoistIds)


def test_open_reports_error_for_missing_file(qml_engine):
    _engine, app_vm, _model_vm, _warnings = qml_engine
    messages: list[tuple[str, str]] = []
    app_vm.notification.connect(lambda msg, level: messages.append((msg, level)))

    app_vm.openPath(str(EXAMPLE.parent / "does_not_exist.json"))

    assert app_vm.hasDocument is False
    assert messages and messages[-1][1] == "error"


def test_qml_visible_text_has_no_encoding_corruption():
    qml_files = QML_DIR.rglob("*.qml")
    corrupted_markers = ("Â²", "Â³", "â€”", "âš ", "â€¦")

    for qml_file in qml_files:
        text = qml_file.read_text(encoding="utf-8")
        assert not any(marker in text for marker in corrupted_markers), qml_file


def test_scene_canvas_background_follows_system_palette(qml_engine):
    engine, _app_vm, _model_vm, warnings = qml_engine
    component = QQmlComponent(
        engine, QUrl.fromLocalFile(str(QML_DIR / "scene/QuickSceneCanvas.qml"))
    )
    scene_canvas = component.create()
    assert scene_canvas is not None

    expected = QGuiApplication.palette().base().color()
    assert scene_canvas.property("backgroundColor") == expected
    assert warnings == []


def test_scene_canvas_exposes_accessible_metadata(qml_engine):
    _engine, _app_vm, _model_vm, warnings = qml_engine
    source = (QML_DIR / "SceneWorkspace.qml").read_text(encoding="utf-8")

    assert 'Accessible.name: qsTr("Crane scene canvas")' in source
    assert 'Accessible.description: qsTr("Interactive crane scene.' in source
    assert warnings == []


def test_quick_canvas_exposes_production_scene_menu_actions(qml_engine):
    engine, app_vm, _model_vm, warnings = qml_engine
    app_vm.openPath(str(EXAMPLE))
    component = QQmlComponent(
        engine, QUrl.fromLocalFile(str(QML_DIR / "scene/QuickSceneCanvas.qml"))
    )
    canvas = component.create()

    assert canvas is not None
    menu_items = canvas.findChildren(QObject)
    texts = {
        item.property("text")
        for item in menu_items
        if isinstance(item.property("text"), str) and item.property("text")
    }
    assert {"Equilibrium Check", "Load Summary", "Fit View"} <= texts
    assert warnings == []


def test_quick_canvas_allocates_report_dialog_content(qml_engine):
    engine, app_vm, _model_vm, warnings = qml_engine
    app_vm.openPath(str(EXAMPLE))
    component = QQmlComponent(
        engine, QUrl.fromLocalFile(str(QML_DIR / "scene/QuickSceneCanvas.qml"))
    )
    canvas = component.create()

    assert canvas is not None
    report_list = canvas.findChild(QObject, "reportList")
    assert report_list is not None
    assert report_list.property("height") > 0
    assert warnings == []


def _evaluate_in(canvas: QObject, script: str):
    """Run a JS expression in the canvas's own QML scope and return its value."""
    expression = QQmlExpression(QQmlEngine.contextForObject(canvas), canvas, script)
    # PyQt returns (value, isUndefined); only the value is interesting here.
    value, _undefined = expression.evaluate()
    assert not expression.hasError(), expression.error().toString()
    return value.toVariant() if isinstance(value, QJSValue) else value


def test_quick_canvas_click_pins_one_tooltip_and_a_second_click_closes_it(qml_engine):
    """Tooltips are pinned by a click, not raised by hovering.

    The canvas holds a single ``pinnedTip``, so "one tooltip at a time" is a
    property of the state rather than of the click handling: clicking the element
    that already owns the tooltip closes it, and any new frame drops it.
    """
    engine, app_vm, _model_vm, warnings = qml_engine
    app_vm.openPath(str(EXAMPLE))
    component = QQmlComponent(
        engine, QUrl.fromLocalFile(str(QML_DIR / "scene/QuickSceneCanvas.qml"))
    )
    canvas = component.create()

    assert canvas is not None
    canvas.setProperty("width", 900.0)
    canvas.setProperty("height", 700.0)

    outcome = _evaluate_in(
        canvas,
        """
        (function () {
            const nodes = sceneVm.sceneFrame.nodes
            for (let i = 0; i < nodes.length; ++i) {
                const x = mapSceneX(nodes[i].scene_x)
                const y = mapSceneY(nodes[i].scene_y)
                if (dragTargetAt(x, y).length > 0 || pickAt(x, y) === null)
                    continue
                toggleTipAt(x, y)
                const opened = pinnedTip === null ? "" : pinnedTip.text
                toggleTipAt(x, y)
                return [opened, pinnedTip === null ? "closed" : "still open"]
            }
            return ["", "no pickable node"]
        })()
        """,
    )

    assert outcome[0]
    assert outcome[1] == "closed"

    reopened = _evaluate_in(
        canvas,
        """
        (function () {
            const nodes = sceneVm.sceneFrame.nodes
            for (let i = 0; i < nodes.length; ++i) {
                const x = mapSceneX(nodes[i].scene_x)
                const y = mapSceneY(nodes[i].scene_y)
                if (dragTargetAt(x, y).length > 0 || pickAt(x, y) === null)
                    continue
                toggleTipAt(x, y)
                return pinnedTip !== null
            }
            return false
        })()
        """,
    )
    assert reopened is True

    # A new frame renumbers the keys the pinned tooltip was named by.
    engine.rootContext().contextProperty("sceneVm").setAngle(40.0)
    assert canvas.property("pinnedTip") is None
    assert warnings == []


def test_quick_canvas_lays_out_the_winch_spool_readout(qml_engine):
    """The readout only instantiates its rows once a document is loaded.

    ``test_component_loads_without_warnings`` builds this canvas against an empty
    session, so the card is hidden and its delegates never run. Loading the example
    is what exercises the row bindings -- including the right-aligned value column,
    whose width must come from ``TextMetrics`` rather than from its parent (which
    would be a binding loop, reported here as a warning).
    """
    engine, app_vm, _model_vm, warnings = qml_engine
    app_vm.openPath(str(EXAMPLE))
    component = QQmlComponent(
        engine, QUrl.fromLocalFile(str(QML_DIR / "scene/QuickSceneCanvas.qml"))
    )
    canvas = component.create()

    assert canvas is not None
    card = canvas.findChild(QObject, "winchSpoolCard")
    assert card is not None
    assert card.property("visible") is True
    assert len(card.property("rows")) == 4

    values = canvas.findChild(QObject, "winchSpoolValueColumn")
    assert values is not None
    # Four stacked rows, so the column has real height and a right-aligned width.
    assert values.property("height") > 0
    assert values.property("width") > 0
    assert warnings == []


WORKSPACES = ["ModelWorkspace.qml", "SceneWorkspace.qml", "LoadChartWorkspace.qml"]


@pytest.mark.parametrize("width,height,compact", [(1920, 1080, False), (1000, 800, True)])
@pytest.mark.parametrize("qml_file", WORKSPACES)
def test_workspace_layout_fits_without_clipping(qml_engine, qml_file, width, height, compact):
    """Every workspace lays out inside the window at both sides of the compact breakpoint."""
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    engine, app_vm, _model_vm, warnings = qml_engine
    app_vm.openPath(str(EXAMPLE))

    component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / qml_file)))
    assert component.status() == QQmlComponent.Status.Ready, component.errorString()
    root = component.create()
    assert root is not None

    root.setProperty("width", width)
    root.setProperty("height", height)

    assert root.property("compact") is compact
    # The root responsive layout must accept the viewport dimensions without growing past it.
    assert root.property("implicitHeight") > 0 or root.property("height") == height
    assert root.property("width") == width
    assert warnings == []


def test_live_tables_use_the_shared_row_height_token(qml_engine):
    engine, app_vm, _model_vm, warnings = qml_engine
    app_vm.openPath(str(EXAMPLE))

    component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / "ModelWorkspace.qml")))
    assert component.status() == QQmlComponent.Status.Ready, component.errorString()
    root = component.create()
    assert root is not None
    root.setProperty("width", 1400)
    root.setProperty("height", 900)
    QTest.qWait(50)

    tables = [
        child
        for child in root.findChildren(QObject)
        if child.property("title") == "Nodes" and child.property("tableRowHeight") is not None
    ]
    assert len(tables) == 1

    assert tables[0].property("tableRowHeight") == 28
    assert warnings == []


def test_combo_popup_has_visible_row_height(qml_engine):
    _engine, _app_vm, _model_vm, warnings = qml_engine
    source = (QML_DIR / "components/ComboBox.qml").read_text(encoding="utf-8")

    assert "root.count" in source
    assert "DesignTokens.sizing.rowHeight" in source
    assert "Math.min(" in source
    assert warnings == []


def _find_combo_list_view(item):
    if item.property("objectName") == "comboPopupList":
        return item
    for child in item.children():
        found = _find_combo_list_view(child)
        if found is not None:
            return found
    return None


def test_combo_popup_keeps_items_after_close_without_selecting(qml_engine):
    engine, _app_vm, _model_vm, warnings = qml_engine
    component = QQmlComponent(engine)
    component.setData(
        b"""
        import QtQuick
        import "components" as Components

        Item {
            id: probe
            property alias combo: box
            property int listViewCount: -1

            Components.ComboBox {
                id: box
                model: ["Alpha", "Beta", "Gamma"]
            }

            function findListView(item) {
                if (item.objectName === "comboPopupList")
                    return item
                for (var i = 0; i < item.children.length; i++) {
                    var found = findListView(item.children[i])
                    if (found)
                        return found
                }
                return null
            }

            function refreshCount() {
                var lv = box.popup.contentItem ? findListView(box.popup.contentItem) : null
                listViewCount = lv ? lv.count : -1
            }

            function openPopup() { box.popup.open() }
            function closePopup() { box.popup.close() }
        }
        """,
        QUrl.fromLocalFile(str(QML_DIR / "_combo_probe.qml")),
    )
    probe = component.create()
    assert probe is not None, component.errorString()

    probe.openPopup()
    QTest.qWait(50)
    probe.refreshCount()
    assert probe.property("listViewCount") == 3

    probe.closePopup()
    QTest.qWait(50)
    probe.openPopup()
    QTest.qWait(50)
    probe.refreshCount()

    assert probe.property("listViewCount") == 3
    assert warnings == []


@pytest.mark.parametrize(
    ("qml_file", "minimum_height"),
    [
        ("dialogs/NodeDialog.qml", 200),
        ("dialogs/HoistDialog.qml", 400),
        ("dialogs/MassPointDialog.qml", 250),
    ],
)
def test_data_entry_dialog_height_follows_content(qml_engine, qml_file, minimum_height):
    engine, _app_vm, _model_vm, warnings = qml_engine
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / qml_file)))

    assert component.status() == QQmlComponent.Status.Ready, component.errorString()
    dialog = component.create()
    assert dialog is not None
    assert dialog.property("height") >= minimum_height
    assert warnings == []
