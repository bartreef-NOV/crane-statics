import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Dialogs
import QtQuick.Layouts
import "dialogs"

Item {
    id: root

    readonly property bool compact: width > 0 && width < 1240
    readonly property int layoutSpacing: Math.round(
        8
    )

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

            DesignLimitsTable {
                Layout.fillWidth: true
                Layout.fillHeight: true
                title: qsTr("Rope Limits")
                model: chartVm.ropeLimitsModel
            }

            DesignLimitsTable {
                Layout.fillWidth: true
                Layout.fillHeight: true
                title: qsTr("Connection Limits")
                model: chartVm.connectionLimitsModel
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
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 240

                    TapHandler {
                        acceptedButtons: Qt.RightButton
                        onTapped: eventPoint => chartMenu.popup(
                            chartMenu.parent.mapFromItem(plot, eventPoint.position)
                        )
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

            ContractualTable {
                Layout.fillWidth: true
                Layout.preferredHeight: 180
                model: chartVm.contractualModel
                onAddRequested: contractualDialog.openFor(-1, null)
                onEditRequested: row => contractualDialog.openFor(row, chartVm.contractualFields(row))
                onDeleteRequested: row => chartVm.deleteContractualPoint(row)
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

        MenuItem {
            text: qsTr("Reset view")
            onTriggered: chartVm.resetView()
        }

        MenuItem {
            text: qsTr("Refresh chart")
            enabled: !chartVm.busy
            onTriggered: chartVm.draw()
        }

        MenuSeparator {}

        MenuItem {
            text: qsTr("Export chart data…")
            enabled: chartVm.chartComplete
            onTriggered: csvDialog.open()
        }

        MenuItem {
            text: qsTr("Export PNG…")
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


