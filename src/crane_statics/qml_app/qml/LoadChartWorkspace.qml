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


