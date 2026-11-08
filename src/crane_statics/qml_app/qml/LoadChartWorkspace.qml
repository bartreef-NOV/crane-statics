import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Dialogs
import QtQuick.Layouts
import "dialogs"

Item {
    id: root
    objectName: "loadChartWorkspace"

    readonly property bool compact: width > 0 && width < 1240
    readonly property int layoutSpacing: Math.round(
        8
    )

    // The curve point the calculation details describe: the pinned one, else the hovered
    // one. A contractual marker has no clause trail.
    readonly property var inspectedPoint: plot.pinnedPoint || plot.hoveredPoint
    onInspectedPointChanged: chartVm.setDetailOutreach(
        inspectedPoint && typeof inspectedPoint.seriesId === "string" ? inspectedPoint.outreach : -1)

    // The menu acts on the chart point under the cursor (null when there is none).
    function openChartMenu(position) {
        chartMenu.targetPoint = plot.nearestPoint(position.x, position.y)
        chartMenu.targetMarker = plot.nearestMarker(position.x, position.y)
        chartMenu.cursorData = plot.dataAt(position.x, position.y)
        chartMenu.popup(chartMenu.parent.mapFromItem(plot, position))
    }

    GridLayout {
        anchors.fill: parent
        anchors.margins: root.layoutSpacing
        columns: root.compact ? 1 : 2
        columnSpacing: root.layoutSpacing
        rowSpacing: root.layoutSpacing

        ColumnLayout {
            Layout.preferredWidth: root.compact ? -1 : 420
            Layout.fillWidth: root.compact
            Layout.fillHeight: !root.compact
            Layout.preferredHeight: root.compact ? 460 : -1
            spacing: root.layoutSpacing

            DataTable {
                id: designLimits
                Layout.fillWidth: true
                Layout.fillHeight: true
                title: qsTr("Design Limits")
                model: chartVm.limitsModel
                editable: true
                rowsEditable: false
                stretchColumn: 0
                emptyText: qsTr("No design limits")
                onGroupToggleRequested: row => chartVm.toggleLimitGroup(row)

                toolbarExtras: RowLayout {
                    spacing: root.layoutSpacing

                    TextField {
                        Layout.preferredWidth: 120
                        placeholderText: qsTr("Filter")
                        selectByMouse: true
                        onTextChanged: chartVm.setLimitFilter(text)
                    }

                    Button {
                        text: qsTr("Auto")
                        ToolTip.visible: hovered
                        ToolTip.text: qsTr("Set the selected limit, or every limit in the selected group, from the contractual points")
                        enabled: designLimits.hasSelection
                        onClicked: chartVm.autoSetLimitRow(designLimits.currentRow)
                    }
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 360
            spacing: root.layoutSpacing

            RowLayout {
                Layout.fillWidth: true
                spacing: root.layoutSpacing

                Label {
                    text: qsTr("Hoist")
                }

                ComboBox {
                    Layout.preferredWidth: 140
                    model: chartVm.hoistIds
                    currentIndex: Math.max(0, chartVm.hoistIds.indexOf(chartVm.selectedHoistId))
                    onActivated: index => {
                        if (index >= 0 && index < model.length)
                            chartVm.selectHoist(model[index])
                    }
                }

                Button {
                    text: qsTr("Normal")
                    checkable: true
                    visible: chartVm.splitable
                    checked: chartVm.chartMode === "normal"
                    onClicked: chartVm.setChartMode("normal")
                }

                Button {
                    text: qsTr("Split")
                    checkable: true
                    visible: chartVm.splitable
                    checked: chartVm.chartMode === "split"
                    onClicked: chartVm.setChartMode("split")
                }

                // Rules documents only: the load condition the chart is drawn for.
                Label {
                    text: qsTr("Condition")
                    visible: conditionSelector.visible
                }

                ComboBox {
                    id: conditionSelector
                    objectName: "conditionSelector"
                    Layout.preferredWidth: 140
                    visible: chartVm.conditionNames.length > 0
                    model: chartVm.conditionNames
                    currentIndex: Math.max(0, chartVm.conditionNames.indexOf(chartVm.currentCondition))
                    onActivated: index => {
                        if (index >= 0 && index < model.length)
                            chartVm.setCurrentCondition(model[index])
                    }
                }

                Item { Layout.fillWidth: true }

                Label {
                    text: qsTr("Outreach step (m)")
                }

                NumberField {
                    Layout.preferredWidth: 80
                    decimals: 2
                    Component.onCompleted: setValue(chartVm.outreachStep)
                    onEditingFinished: chartVm.setOutreachStep(value)
                }

            }

            GridLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 240
                columns: root.compact ? 1 : 2
                columnSpacing: root.layoutSpacing
                rowSpacing: root.layoutSpacing

                QuickChartPlot {
                    id: plot
                    objectName: "quickChartPlot"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 240

                    TapHandler {
                        acceptedButtons: Qt.RightButton
                        onTapped: eventPoint => root.openChartMenu(eventPoint.position)
                    }
                }

                ChartLegend {
                    Layout.fillWidth: root.compact
                    Layout.fillHeight: true
                    Layout.preferredWidth: root.compact ? -1 : 250
                    Layout.minimumHeight: root.compact ? 140 : 240
                    items: plot.legendItems
                    visibilityByKey: plot.visibilityByKey
                    onToggleRequested: key => plot.setSeriesVisible(key, !plot.seriesKeyVisible(key))
                }
            }

            // Rules documents only: the clause trail of the pinned or hovered curve point.
            GroupBox {
                id: calculationDetails
                objectName: "calculationDetails"
                Layout.fillWidth: true
                Layout.preferredHeight: 250
                visible: chartVm.conditionNames.length > 0
                title: chartVm.provenanceHeading === ""
                       ? qsTr("Calculation details")
                       : qsTr("Calculation details: %1").arg(chartVm.provenanceHeading)

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 4

                    ScrollView {
                        id: detailsScroll
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        // Fixed implicit size: the layout gives the panel its width, and the
                        // content width follows it, so the GroupBox must not size from it.
                        implicitWidth: 200
                        implicitHeight: 120
                        clip: true
                        contentWidth: availableWidth

                        ColumnLayout {
                            width: detailsScroll.availableWidth
                            spacing: 4

                            Label {
                                Layout.fillWidth: true
                                visible: chartVm.provenanceRows.length === 0
                                text: qsTr("Hover or click a point on the capacity curve to see how its factors were obtained.")
                                color: detailsPalette.placeholderText
                                wrapMode: Text.WordWrap
                            }

                            Repeater {
                                id: provenanceRepeater
                                objectName: "provenanceRepeater"
                                model: chartVm.provenanceRows

                                delegate: Label {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    wrapMode: Text.WordWrap
                                    textFormat: Text.PlainText
                                    font.bold: modelData.isOverride
                                    text: qsTr("%1 = %2%3  [%4]  %5%6")
                                          .arg(modelData.quantity)
                                          .arg(modelData.value)
                                          .arg(modelData.unit === "" ? "" : " " + modelData.unit)
                                          .arg(modelData.clause)
                                          .arg(modelData.formula)
                                          .arg(modelData.isOverride ? qsTr("  (manual override)") : "")
                                    ToolTip.visible: detailHover.hovered && modelData.inputs !== ""
                                    ToolTip.text: modelData.inputs

                                    HoverHandler { id: detailHover }
                                }
                            }
                        }
                    }

                    // Warnings and standing statements stay in view below the scrolled trail.
                    Repeater {
                        model: chartVm.provenanceWarnings

                        delegate: Label {
                            required property string modelData
                            Layout.fillWidth: true
                            // Wraps to the panel width instead of sizing the panel from the text.
                            Layout.preferredWidth: 100
                            wrapMode: Text.WordWrap
                            color: "#c62828"
                            text: qsTr("⚠ %1").arg(modelData)
                        }
                    }

                    Label {
                        objectName: "calculationNotesLabel"
                        Layout.fillWidth: true
                        Layout.preferredWidth: 100
                        wrapMode: Text.WordWrap
                        color: detailsPalette.placeholderText
                        text: chartVm.calculationNotes.join("\n")
                    }
                }

                SystemPalette { id: detailsPalette }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: root.layoutSpacing

                Label {
                    text: chartVm.stale ? qsTr("⚠ Chart stale — press Draw") : chartVm.statusText
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }
        }
    }

    ContractualPointDialog {
        id: contractualDialog
        onCommitted: (index, fields) => index < 0 ? chartVm.addContractualPoint(fields)
                                                  : chartVm.updateContractualPoint(index, fields)
    }

    Menu {
        id: chartMenu
        objectName: "chartMenu"

        property var targetPoint: null
        // The contractual marker and the chart coordinates under the cursor (null when none).
        property var targetMarker: null
        property var cursorData: null
        // Asked once per opening: availability has no change signal to bind to.
        property bool governingCaseAvailable: false

        onAboutToShow: governingCaseAvailable = targetPoint !== null
                                                && typeof targetPoint.seriesId === "string"
                                                && chartVm.governingCaseAvailable(targetPoint.seriesId)

        MenuItem {
            text: qsTr("Reset view")
            onTriggered: chartVm.resetView()
        }

        MenuItem {
            text: qsTr("Refresh chart")
            enabled: !chartVm.busy
            onTriggered: chartVm.draw()
        }

        MenuItem {
            objectName: "governingCaseMenuItem"
            text: qsTr("Show governing case in Scene")
            enabled: chartMenu.governingCaseAvailable
            onTriggered: chartVm.showGoverningCase(chartMenu.targetPoint.seriesId,
                                                   chartMenu.targetPoint.outreach)
        }

        MenuSeparator {}

        MenuItem {
            objectName: "addContractualMenuItem"
            text: qsTr("Add contractual point here…")
            enabled: chartMenu.cursorData !== null
            onTriggered: contractualDialog.openFor(-1, {
                "outreach_m": Math.max(0, Math.round(chartMenu.cursorData.outreach * 10) / 10),
                "load_t": Math.max(0, Math.round(chartMenu.cursorData.load * 10) / 10)
            })
        }

        MenuItem {
            objectName: "editContractualMenuItem"
            text: qsTr("Edit contractual point…")
            enabled: chartMenu.targetMarker !== null
            onTriggered: contractualDialog.openFor(chartMenu.targetMarker.index, {
                "outreach_m": chartMenu.targetMarker.outreach,
                "load_t": chartMenu.targetMarker.load
            })
        }

        MenuItem {
            objectName: "deleteContractualMenuItem"
            text: qsTr("Delete contractual point")
            enabled: chartMenu.targetMarker !== null
            onTriggered: chartVm.deleteContractualPoint(chartMenu.targetMarker.index)
        }

        MenuSeparator {}

        MenuItem {
            text: qsTr("Export chart data…")
            enabled: chartVm.chartComplete
            onTriggered: csvDialog.open()
        }

        MenuItem {
            text: qsTr("Export PNG…")
            enabled: chartVm.chartComplete
            onTriggered: pngDialog.open()
        }
    }

    FileDialog {
        id: csvDialog
        title: qsTr("Export chart data")
        fileMode: FileDialog.SaveFile
        defaultSuffix: "csv"
        nameFilters: [qsTr("CSV files (*.csv)")]
        onAccepted: chartVm.exportCsv(selectedFile)
    }

    FileDialog {
        id: pngDialog
        title: qsTr("Export chart image")
        fileMode: FileDialog.SaveFile
        defaultSuffix: "png"
        nameFilters: [qsTr("PNG images (*.png)")]
        onAccepted: plot.grabToImage(result => result.saveToFile(chartVm.toLocalPath(selectedFile)))
    }
}


