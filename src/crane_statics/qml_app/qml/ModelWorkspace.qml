import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Dialogs
import QtQuick.Layouts
import "dialogs"
import BF.DesignSystem

Item {
    id: root

    readonly property bool compact: width > 0 && width < Metrics.breakpointCompact
    readonly property int layoutSpacing: Math.round(
        Metrics.spacing8 * Metrics.spacingMultiplier
    )
    readonly property string bodyLabel: bodyTabs.currentIndex >= 0
        && bodyTabs.currentIndex < modelVm.bodyLabels.length
        ? modelVm.bodyLabels[bodyTabs.currentIndex] : ""

    GridLayout {
        anchors.fill: parent
        anchors.margins: root.layoutSpacing
        columns: root.compact ? 1 : 2
        columnSpacing: root.layoutSpacing
        rowSpacing: root.layoutSpacing

        ScrollView {
            id: envScroll
            Layout.preferredWidth: root.compact ? -1 : 400
            Layout.fillWidth: root.compact
            Layout.fillHeight: !root.compact
            Layout.preferredHeight: root.compact ? 420 : -1
            clip: true
            contentWidth: availableWidth

            EnvironmentPanel {
                width: envScroll.availableWidth
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 320
            spacing: root.layoutSpacing

            RowLayout {
                Layout.fillWidth: true
                spacing: root.layoutSpacing

                TabBar {
                    id: sectionTabs
                    Layout.fillWidth: true

                    TabButton { text: qsTr("Components"); Layout.fillWidth: true }
                    TabButton { text: qsTr("Hoists"); Layout.fillWidth: true }
                    TabButton { text: qsTr("Ropes"); Layout.fillWidth: true }
                    TabButton { text: qsTr("Load Charts"); Layout.fillWidth: true }
                }

                Label {
                    text: modelVm.healthVerdict
                    font.bold: true
                }

                Label {
                    text: modelVm.healthChecks
                    elide: Text.ElideRight
                    Layout.maximumWidth: 360
                }
            }

            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: sectionTabs.currentIndex

                ColumnLayout {
                    spacing: root.layoutSpacing

                    TabBar {
                        id: bodyTabs
                        Layout.fillWidth: true
                        onCurrentIndexChanged: {
                            if (currentIndex >= 0 && currentIndex < modelVm.bodyIds.length)
                                modelVm.selectBody(modelVm.bodyIds[currentIndex])
                        }

                        Repeater {
                            model: modelVm.bodyLabels
                            TabButton {
                                required property string modelData
                                text: modelData
                                Layout.fillWidth: true
                            }
                        }
                    }

                    DataTable {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        title: qsTr("Nodes")
                        emptyText: qsTr("No nodes in this component.")
                        editable: true
                        model: modelVm.nodesModel
                        editorChoices: modelVm.editableNodeIds
                        onAddRequested: nodeDialog.openFor(-1, null)
                        onDeleteRequested: row => modelVm.deleteNode(row)
                    }

                    DataTable {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        title: qsTr("Mass Points")
                        emptyText: qsTr("No mass points in this component.")
                        editable: true
                        model: modelVm.massPointsModel
                        onAddRequested: massPointDialog.openFor(-1, null)
                        onDeleteRequested: row => modelVm.deleteMassPoint(row)
                    }

                    DataTable {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        title: qsTr("Wind Areas")
                        emptyText: qsTr("No wind areas in this component.")
                        editable: true
                        model: modelVm.windAreasModel
                        onAddRequested: windAreaDialog.openFor(-1, null)
                        onDeleteRequested: row => modelVm.deleteWindArea(row)
                    }
                }

                DataTable {
                    title: qsTr("Hoists")
                    emptyText: qsTr("No hoists defined.")
                    editable: true
                    model: modelVm.hoistsModel
                    editorChoices: modelVm.editableNodeIds
                    onAddRequested: hoistDialog.openFor(-1, null)
                    onDeleteRequested: row => modelVm.deleteHoist(row)
                }

                ColumnLayout {
                    spacing: root.layoutSpacing

                    HoistSelector { payloadOnly: false }

                    DataTable {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        title: qsTr("Rope Segments")
                        emptyText: qsTr("No rope segments for this hoist.")
                        editable: true
                        model: modelVm.ropeSegmentsModel
                        editorChoices: modelVm.editableNodeIds
                        onAddRequested: segmentDialog.openFor(-1, null)
                        onDeleteRequested: row => modelVm.deleteRopeSegment(row)
                    }
                }

                ColumnLayout {
                    spacing: root.layoutSpacing

                    HoistSelector { payloadOnly: true }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: root.layoutSpacing
                        visible: modelVm.hoistSplitable

                        Label {
                            text: qsTr("Hook Configuration")
                        }

                        Button {
                            text: qsTr("Normal")
                            checkable: true
                            checked: modelVm.contractualMode === "normal"
                            onClicked: modelVm.setContractualMode("normal")
                        }

                        Button {
                            text: qsTr("Split")
                            checkable: true
                            checked: modelVm.contractualMode === "split"
                            onClicked: modelVm.setContractualMode("split")
                        }

                        Item { Layout.fillWidth: true }
                    }

                    DataTable {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        title: qsTr("Contractual Points")
                        emptyText: qsTr("No contractual points for this hoist.")
                        editable: true
                        model: modelVm.contractualModel
                        onAddRequested: contractualDialog.openFor(-1, null)
                        onDeleteRequested: row => modelVm.deleteContractualPoint(row)
                    }
                }
            }
        }
    }

    component HoistSelector: RowLayout {
        property bool payloadOnly: false
        Layout.fillWidth: true
        spacing: root.layoutSpacing

        Label {
            text: qsTr("Hoist")
        }

        ComboBox {
            Layout.preferredWidth: 200
            model: payloadOnly ? modelVm.payloadHoistIds : modelVm.hoistIds
            currentIndex: Math.max(0, model.indexOf(modelVm.selectedHoistId))
            onActivated: index => {
                if (index >= 0 && index < model.length)
                    modelVm.selectHoist(model[index])
            }
        }
    }

    /*  The dialogs only add here: an existing row is edited in its own cell, which
        submits the same fields through the same validation. The dialogs still carry
        the row index in their signal because the load chart workspace edits its
        contractual points through one. */

    NodeDialog {
        id: nodeDialog
        bodyId: modelVm.selectedBodyId
        componentLabel: root.bodyLabel
        nodeIds: modelVm.editableNodeIds
        onCommitted: (index, fields) => modelVm.addNode(fields)
    }

    MassPointDialog {
        id: massPointDialog
        bodyId: modelVm.selectedBodyId
        componentLabel: root.bodyLabel
        onCommitted: (index, fields) => modelVm.addMassPoint(fields)
    }

    WindAreaDialog {
        id: windAreaDialog
        bodyId: modelVm.selectedBodyId
        componentLabel: root.bodyLabel
        onCommitted: (index, fields) => modelVm.addWindArea(fields)
    }

    HoistDialog {
        id: hoistDialog
        nodeIds: modelVm.editableNodeIds
        onCommitted: (index, fields) => modelVm.addHoist(fields)
    }

    SegmentDialog {
        id: segmentDialog
        nodeIds: modelVm.editableNodeIds
        onCommitted: (index, fields) => modelVm.addRopeSegment(fields)
    }

    ContractualPointDialog {
        id: contractualDialog
        onCommitted: (index, fields) => modelVm.addContractualPoint(fields)
    }

    MessageDialog {
        id: editErrorDialog
        title: qsTr("Model Edit")
        buttons: MessageDialog.Ok
    }

    Connections {
        target: modelVm
        function onEditFailed(message) {
            editErrorDialog.text = message
            editErrorDialog.open()
        }
    }
}


