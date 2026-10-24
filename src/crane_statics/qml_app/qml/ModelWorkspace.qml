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
    readonly property int bodyIndex: modelVm.bodyIds.indexOf(modelVm.selectedBodyId)
    readonly property string bodyLabel: bodyIndex >= 0 && bodyIndex < modelVm.bodyLabels.length
        ? modelVm.bodyLabels[bodyIndex] : ""

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
                    objectName: "sectionTabs"
                    Layout.fillWidth: true

                    TabButton { text: qsTr("Components"); Layout.fillWidth: true }
                    TabButton { text: qsTr("Hoists"); Layout.fillWidth: true }
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

                RowLayout {
                    spacing: root.layoutSpacing

                    ListView {
                        id: bodyList
                        objectName: "bodyList"
                        Layout.preferredWidth: 220
                        Layout.fillHeight: true
                        clip: true
                        model: modelVm.bodyLabels
                        currentIndex: root.bodyIndex
                        boundsBehavior: Flickable.StopAtBounds

                        delegate: ItemDelegate {
                            required property int index
                            required property string modelData

                            width: ListView.view.width
                            text: modelData
                            highlighted: ListView.isCurrentItem
                            onClicked: modelVm.selectBody(modelVm.bodyIds[index])
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: root.layoutSpacing

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
                }

                HoistsPanel {
                    onAddRequested: hoistDialog.openFor(-1, null)
                    onAddSegmentRequested: segmentDialog.openFor(-1, null)
                    onAddContractualPointRequested: contractualDialog.openFor(-1, null)
                }
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


