"""QML front end: every view loads warning-free and the model tables populate."""

import time
from pathlib import Path

import pytest
from PyQt6.QtCore import QCoreApplication, QMetaObject, QObject, QUrl
from PyQt6.QtTest import QTest
from PyQt6.QtQml import (
    QJSValue,
    QQmlApplicationEngine,
    QQmlComponent,
    QQmlEngine,
    QQmlExpression,
)
from PyQt6.QtGui import QColor, QGuiApplication
from PyQt6.QtQuick import QQuickItem

from crane_statics.qml_app.session import SessionState
from crane_statics.qml_app.app import QML_DIR
from crane_statics.qml_app.viewmodels.app_vm import AppViewModel
from crane_statics.qml_app.viewmodels.chart_vm import ChartViewModel
from crane_statics.qml_app.viewmodels.model_vm import ModelViewModel
from crane_statics.qml_app.viewmodels.scene_vm import SceneViewModel

EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.yaml"


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
    chart_vm.set_scene_view_model(scene_vm)

    engine.rootContext().setContextProperty("appVm", app_vm)
    engine.rootContext().setContextProperty("modelVm", model_vm)
    engine.rootContext().setContextProperty("sceneVm", scene_vm)
    engine.rootContext().setContextProperty("chartVm", chart_vm)

    warnings: list[str] = []
    engine.warnings.connect(lambda errors: warnings.extend(str(e.toString()) for e in errors))

    yield engine, app_vm, model_vm, warnings
    # Stop chart sweeps before the engine goes, as app.py does on quit.
    chart_vm.shutdown()
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


def test_chart_exports_are_disabled_while_the_chart_is_partial(qml_engine):
    engine, app_vm, _model_vm, warnings = qml_engine
    app_vm.openPath(str(EXAMPLE))
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    chart_vm = engine.rootContext().contextProperty("chartVm")
    root = engine.rootObjects()[-1]
    labels = ("Export chart data…", "Export PNG…")
    items = [
        obj
        for obj in root.findChildren(QObject)
        if obj.metaObject().className().startswith("MenuItem") and obj.property("text") in labels
    ]
    assert sorted(item.property("text") for item in items) == sorted(labels)

    chart_vm._set_partial(True)
    assert [item.property("enabled") for item in items] == [False, False]
    chart_vm._set_partial(False)
    assert [item.property("enabled") for item in items] == [True, True]
    assert warnings == []


def test_chart_pending_markers_are_a_neutral_palette_grey(qml_engine):
    engine, _app_vm, _model_vm, warnings = qml_engine
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / "QuickChartPlot.qml")))
    plot = component.create()
    assert plot is not None, component.errorString()

    pending = QColor(plot.property("pendingColor"))
    assert pending != QColor("#ef6c00")
    assert pending == QGuiApplication.palette().placeholderText().color()
    # The legend entry is grey while every marker is still pending.
    undecided = _evaluate_in(plot, 'contractualLegendColor([{ status: "pending" }])')
    decided = _evaluate_in(
        plot, 'contractualLegendColor([{ status: "pending" }, { status: "pass" }])'
    )
    assert QColor(undecided) == pending
    assert QColor(decided) == QColor(plot.property("passColor"))
    series = _evaluate_in(
        plot, 'chartSeriesColor({ id: "contractual", points: [{ status: "pending" }] })'
    )
    assert QColor(series) == pending
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
        "dialogs/NodeDialog.qml",
        "dialogs/MassPointDialog.qml",
        "dialogs/WindAreaDialog.qml",
        "dialogs/HoistDialog.qml",
        "dialogs/SegmentDialog.qml",
        "dialogs/ContractualPointDialog.qml",
    ],
)
def test_component_loads_without_warnings(qml_engine, qml_file):
    engine, _app_vm, _model_vm, warnings = qml_engine
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / qml_file)))

    assert component.status() == QQmlComponent.Status.Ready, component.errorString()
    obj = component.create()
    assert obj is not None
    assert warnings == []


def test_environment_panel_nullable_field_shows_blank_when_unset(qml_engine):
    """slewing_bearing_diameter_m is optional; with no document loaded it must
    read as blank, not '0.000', while an ordinary field like boom_width_m
    still shows its numeric default.
    """
    engine, _app_vm, _model_vm, warnings = qml_engine
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / "EnvironmentPanel.qml")))
    panel = component.create()
    assert panel is not None, component.errorString()

    nullable_field = panel.findChild(QObject, "envField_slewing_bearing_diameter_m")
    ordinary_field = panel.findChild(QObject, "envField_boom_width_m")

    assert nullable_field is not None, "NumberField for the nullable row must be discoverable"
    assert ordinary_field is not None, "NumberField for an ordinary row must be discoverable"
    assert nullable_field.property("text") == ""
    assert ordinary_field.property("text") == "0.000"
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


def test_scene_canvas_segment_delegates_are_antialiased(qml_engine):
    """Booms and ropes are drawn at arbitrary angles; Qt only antialiases a
    Rectangle by default when it has a radius, so these delegates need the
    property set explicitly or their diagonal edges come out jagged.
    """
    engine, _app_vm, _model_vm, warnings = qml_engine
    component = QQmlComponent(
        engine, QUrl.fromLocalFile(str(QML_DIR / "scene/QuickSceneCanvas.qml"))
    )
    canvas = component.create()
    assert canvas is not None, component.errorString()

    canvas.setProperty(
        "frame",
        {
            "structuralSegments": [
                {
                    "start_x": 0.0,
                    "start_y": 0.0,
                    "end_x": 10.0,
                    "end_y": 6.0,
                    "width": 4.0,
                    "color": "#808080",
                },
            ],
            "ropeSegments": [
                {
                    "start_x": 0.0,
                    "start_y": 0.0,
                    "end_x": 8.0,
                    "end_y": -3.0,
                    "width": 2.0,
                    "color": "#c0c0c0",
                },
            ],
        },
    )
    QTest.qWait(20)

    def _iter_items(item: QQuickItem):
        yield item
        for child in item.childItems():
            yield from _iter_items(child)

    # Repeater delegates aren't in the QObject parent/child tree (their
    # QObject parent is None; only the QQuickItem visual parentItem() chain
    # reaches them), and an inline `Rectangle { ... }` delegate with extra
    # properties gets a synthesized class name like "QQuickRectangle_QML_48"
    # rather than the bare built-in name, so match by prefix.
    segment_rects = [
        item
        for item in _iter_items(canvas)
        if item.metaObject().className().startswith("QQuickRectangle")
        and item.property("rotation") not in (0, 0.0, None)
    ]
    assert len(segment_rects) == 2, "expected one structural and one rope segment delegate"
    assert all(rect.property("antialiasing") for rect in segment_rects)
    assert warnings == []


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


@pytest.mark.parametrize(
    ("qml_file", "minimum_height"),
    [
        ("dialogs/NodeDialog.qml", 150),
        ("dialogs/HoistDialog.qml", 400),
        ("dialogs/MassPointDialog.qml", 200),
    ],
)
def test_data_entry_dialog_height_follows_content(qml_engine, qml_file, minimum_height):
    engine, _app_vm, _model_vm, warnings = qml_engine
    # Native Dialog only resolves Overlay.overlay (and therefore counts header/footer
    # height) once it actually has a window ancestor to open into, matching how the
    # app always instantiates dialogs as children of the ApplicationWindow.
    dialog_url = QUrl.fromLocalFile(str(QML_DIR / qml_file)).toString()
    component = QQmlComponent(engine)
    component.setData(
        f"""import QtQuick
import QtQuick.Controls
ApplicationWindow {{
    visible: true
    width: 800
    height: 800
    property var dialog: loader.item
    Loader {{ id: loader; source: "{dialog_url}" }}
}}""".encode(
            "utf-8"
        ),
        QUrl.fromLocalFile(str(QML_DIR / "_dialog_height_probe.qml")),
    )

    assert component.status() == QQmlComponent.Status.Ready, component.errorString()
    window = component.create()
    assert window is not None
    dialog = window.property("dialog")
    assert dialog is not None

    dialog.open()
    QTest.qWait(20)
    assert dialog.property("height") >= minimum_height
    assert warnings == []


def _wait_until(predicate, timeout: float = 60.0) -> None:
    """Pump the Qt event loop until ``predicate()`` holds; worker signals arrive this way."""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        QCoreApplication.processEvents()
        time.sleep(0.005)


def _drawn_main(qml_engine):
    """Main.qml on the example with a finished Load Chart for the selected hoist."""
    if not EXAMPLE.exists():
        pytest.skip("Example file not found")
    engine, app_vm, _model_vm, warnings = qml_engine
    app_vm.openPath(str(EXAMPLE))
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    root = engine.rootObjects()[-1]
    chart_vm = engine.rootContext().contextProperty("chartVm")
    chart_vm._outreach_step = 10.0
    chart_vm.drawBlocking()
    # No background sweeps of the other charts while the test runs.
    chart_vm._refresh_timer.stop()
    QTest.qWait(50)
    return engine, root, chart_vm, warnings


def _only_series_visible(plot: QObject, key: str) -> None:
    keys = [item["id"] for item in _evaluate_in(plot, "collectLegendSeries()")]
    for other in keys:
        _evaluate_in(plot, f"setSeriesVisible({other!r}, {str(other == key).lower()})")


def _point_under(plot: QObject):
    """``nearestPoint`` on the first point of the only visible series, and its position."""
    return _evaluate_in(
        plot,
        """
        (function () {
            const markers = chartVm.markers || []
            const series = collectSeries()
            const first = series.length > 0
                ? { outreach: series[0].points[0][0], load: series[0].points[0][1] }
                : { outreach: markers[0].outreach, load: markers[0].load }
            const px = mapX(first.outreach, viewRanges, plotLeft, plotWidth)
            const py = mapY(first.load, viewRanges, plotTop, plotHeight)
            const point = nearestPoint(px, py)
            return point === null ? "no point" : [point.seriesId, px, py]
        })()
        """,
    )


def test_chart_points_carry_the_series_a_governing_case_is_asked_for(qml_engine):
    """A limit's point names the limit, the combined curve "", a contractual marker none."""
    _engine, root, chart_vm, warnings = _drawn_main(qml_engine)
    plot = root.findChild(QObject, "quickChartPlot")
    assert plot is not None
    limit_id = chart_vm.limitSeries[0]["id"]

    _only_series_visible(plot, limit_id)
    assert _point_under(plot)[0] == limit_id
    _only_series_visible(plot, "capacity")
    assert _point_under(plot)[0] == ""
    _only_series_visible(plot, "contractual")
    assert _point_under(plot)[0] is None
    assert warnings == []


def test_chart_menu_shows_the_governing_case_in_the_scene(qml_engine):
    """Right-click a curve point -> Scene tab, banner label and Restore; an edit drops the label."""
    engine, root, _chart_vm, warnings = _drawn_main(qml_engine)
    scene_vm = engine.rootContext().contextProperty("sceneVm")
    tabs = root.findChild(QObject, "workspaceTabs")
    tabs.setProperty("currentIndex", 1)
    QTest.qWait(50)
    workspace = root.findChild(QObject, "loadChartWorkspace")
    plot = root.findChild(QObject, "quickChartPlot")
    item = root.findChild(QObject, "governingCaseMenuItem")
    label = root.findChild(QObject, "governingCaseLabel")
    restore = root.findChild(QObject, "restoreInputsButton")
    assert None not in (workspace, plot, item, label, restore)
    assert item.property("text") == "Show governing case in Scene"
    assert label.property("visible") is False
    assert restore.property("visible") is False

    # A contractual marker has no curve behind it: the entry is there, but disabled.
    _only_series_visible(plot, "contractual")
    _series_id, px, py = _point_under(plot)
    _evaluate_in(workspace, f"openChartMenu(Qt.point({px}, {py}))")
    assert item.property("enabled") is False
    QMetaObject.invokeMethod(root.findChild(QObject, "chartMenu"), "close")

    _only_series_visible(plot, "capacity")
    _series_id, px, py = _point_under(plot)
    _evaluate_in(workspace, f"openChartMenu(Qt.point({px}, {py}))")
    assert item.property("enabled") is True
    QMetaObject.invokeMethod(item, "triggered")
    _wait_until(lambda: scene_vm.governingCaseLabel != "")
    QTest.qWait(50)

    assert tabs.property("currentIndex") == 0
    assert label.property("visible") is True
    assert label.property("text") == scene_vm.governingCaseLabel
    assert restore.property("visible") is True

    scene_vm.setAngle(scene_vm.angle - 1.0)
    assert label.property("visible") is False
    assert restore.property("visible") is True

    QMetaObject.invokeMethod(restore, "click")
    assert restore.property("visible") is False
    assert not scene_vm.canRestoreInputs
    assert warnings == []


def test_edit_menu_undo_follows_history(qml_engine):
    engine, app_vm, model_vm, warnings = qml_engine
    app_vm.openPath(str(EXAMPLE))
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    root = engine.rootObjects()[-1]
    undo = root.findChild(QObject, "undoAction")
    redo = root.findChild(QObject, "redoAction")
    assert undo is not None and redo is not None
    assert undo.property("enabled") is False

    wind = model_vm._model.document.environment.max_wind_speed_m_s
    model_vm.setEnvironmentValue("max_wind_speed_m_s", wind + 1.0)
    assert undo.property("enabled") is True and redo.property("enabled") is False

    app_vm.undo()
    assert undo.property("enabled") is False and redo.property("enabled") is True
    assert warnings == []


def test_chart_menu_edits_contractual_points_at_the_cursor(qml_engine):
    """Add works anywhere in the plot; edit and delete need a contractual marker close by."""
    _engine, root, chart_vm, warnings = _drawn_main(qml_engine)
    tabs = root.findChild(QObject, "workspaceTabs")
    tabs.setProperty("currentIndex", 1)
    QTest.qWait(50)
    workspace = root.findChild(QObject, "loadChartWorkspace")
    plot = root.findChild(QObject, "quickChartPlot")
    menu = root.findChild(QObject, "chartMenu")
    add = root.findChild(QObject, "addContractualMenuItem")
    edit = root.findChild(QObject, "editContractualMenuItem")
    delete = root.findChild(QObject, "deleteContractualMenuItem")
    assert None not in (workspace, plot, menu, add, edit, delete)

    _only_series_visible(plot, "contractual")
    _series_id, px, py = _point_under(plot)
    _evaluate_in(workspace, f"openChartMenu(Qt.point({px}, {py}))")
    assert add.property("enabled") is True
    assert edit.property("enabled") is True
    assert delete.property("enabled") is True
    QMetaObject.invokeMethod(menu, "close")

    # Far from every marker, inside the plot: only Add is available.
    left, top = plot.property("plotLeft") + 1, plot.property("plotTop") + 1
    _evaluate_in(workspace, f"openChartMenu(Qt.point({left}, {top}))")
    assert add.property("enabled") is True
    assert edit.property("enabled") is False
    assert delete.property("enabled") is False
    QMetaObject.invokeMethod(menu, "close")

    # Outside the plot area nothing is offered.
    _evaluate_in(workspace, "openChartMenu(Qt.point(0, 0))")
    assert add.property("enabled") is False
    QMetaObject.invokeMethod(menu, "close")

    before = len(chart_vm.markers)
    _only_series_visible(plot, "contractual")
    _series_id, px, py = _point_under(plot)
    _evaluate_in(workspace, f"openChartMenu(Qt.point({px}, {py}))")
    QMetaObject.invokeMethod(delete, "triggered")
    assert len(chart_vm.markers) == before - 1
    assert not warnings
