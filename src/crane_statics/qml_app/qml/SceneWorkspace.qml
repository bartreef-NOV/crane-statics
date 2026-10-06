import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import "scene"
import BF.DesignSystem

Item {
    id: root

    readonly property bool compact: width > 0 && width < Metrics.breakpointCompact
    readonly property int layoutSpacing: Math.round(
        Metrics.spacing8 * Metrics.spacingMultiplier
    )

    GridLayout {
        anchors.fill: parent
        anchors.margins: root.layoutSpacing
        columns: root.compact ? 1 : 3
        columnSpacing: root.layoutSpacing
        rowSpacing: root.layoutSpacing

        ScrollView {
            id: railScroll
            Layout.minimumWidth: root.compact ? -1 : 280
            Layout.preferredWidth: root.compact ? -1 : 300
            Layout.maximumWidth: root.compact ? -1 : 320
            Layout.fillWidth: root.compact
            Layout.fillHeight: !root.compact
            Layout.preferredHeight: root.compact ? 360 : -1
            clip: true
            contentWidth: availableWidth

            SceneControlRail {
                width: railScroll.availableWidth
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 320
            spacing: root.layoutSpacing

            QuickSceneCanvas {
                id: canvas
                objectName: "sceneCanvas"
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 200
                focus: true
                Accessible.name: qsTr("Crane scene canvas")
                Accessible.description: qsTr("Interactive crane scene. Use the mouse to pan and zoom, or press R to fit the view.")

                Rectangle {
                    anchors.fill: parent
                    color: "transparent"
                    border.width: Metrics.borderWidth
                    border.color: Theme.border
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: root.layoutSpacing

                Label {
                    text: qsTr("Contractual:")
                }

                Flow {
                    Layout.fillWidth: true
                    spacing: root.layoutSpacing

                    Label {
                        text: qsTr("No contractual points")
                        visible: sceneVm.contractualLabels.length === 0
                    }

                    Repeater {
                        model: sceneVm.contractualLabels

                        Button {
                            required property string modelData
                            required property int index
                            text: modelData
                            checkable: true
                            checked: index === sceneVm.selectedContractualIdx
                            onClicked: sceneVm.selectContractual(checked ? index : -1)
                        }
                    }
                }
            }
        }

        ColumnLayout {
            Layout.preferredWidth: root.compact ? -1 : 420
            Layout.fillWidth: root.compact
            Layout.fillHeight: !root.compact
            Layout.preferredHeight: root.compact ? 420 : -1
            spacing: root.layoutSpacing

            ResultsTable {
                Layout.fillWidth: true
                Layout.fillHeight: true
                title: qsTr("Hoists")
                model: sceneVm.ropeRowsModel
                onBarClicked: row => sceneVm.openLoadOverview("rope", row)
            }

            ResultsTable {
                Layout.fillWidth: true
                Layout.fillHeight: true
                title: qsTr("Connections")
                model: sceneVm.connectionRowsModel
                onBarClicked: row => sceneVm.openLoadOverview("connection", row)
            }
        }
    }
}


