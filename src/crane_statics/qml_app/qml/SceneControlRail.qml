import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import BF.DesignSystem
import "components"

ColumnLayout {
    id: root

    readonly property int layoutSpacing: Math.round(
        Metrics.spacing8 * Metrics.spacingMultiplier
    )

    spacing: root.layoutSpacing

    StyledGroupBox {
        Layout.fillWidth: true
        title: qsTr("Active Hoist")
        topPadding: Metrics.spacing24
        bottomPadding: Metrics.spacing6
        leftPadding: Metrics.spacing6
        rightPadding: Metrics.spacing6

        Flow {
            anchors.fill: parent
            spacing: root.layoutSpacing

            Repeater {
                model: sceneVm.hoistIds

                Button {
                    required property string modelData
                    text: modelData
                    checkable: true
                    checked: modelData === sceneVm.selectedHoistId
                    onClicked: sceneVm.selectHoist(modelData)
                }
            }
        }
    }

    StyledGroupBox {
        Layout.fillWidth: true
        title: qsTr("Hook Configuration")
        visible: sceneVm.splitable
        topPadding: Metrics.spacing24
        bottomPadding: Metrics.spacing6
        leftPadding: Metrics.spacing6
        rightPadding: Metrics.spacing6

        RowLayout {
            anchors.fill: parent
            spacing: root.layoutSpacing

            Button {
                Layout.fillWidth: true
                text: qsTr("Normal")
                checkable: true
                checked: sceneVm.hookMode === "normal"
                onClicked: sceneVm.setHookMode("normal")
            }

            Button {
                Layout.fillWidth: true
                text: qsTr("Split")
                checkable: true
                checked: sceneVm.hookMode === "split"
                onClicked: sceneVm.setHookMode("split")
            }
        }
    }

    StyledGroupBox {
        Layout.fillWidth: true
        title: qsTr("Geometry")
        topPadding: Metrics.spacing24
        bottomPadding: Metrics.spacing6
        leftPadding: Metrics.spacing6
        rightPadding: Metrics.spacing6

        ColumnLayout {
            anchors.fill: parent
            spacing: root.layoutSpacing

            NumericRow {
                Layout.fillWidth: true
                label: qsTr("Boom Angle (deg):")
                from: sceneVm.angleMin
                to: sceneVm.angleMax
                value: sceneVm.angle
                onCommitted: newValue => sceneVm.setAngle(newValue)
            }

            NumericRow {
                Layout.fillWidth: true
                label: qsTr("Outreach (m):")
                from: sceneVm.outreachMin
                to: sceneVm.outreachMax
                value: sceneVm.outreach
                onCommitted: newValue => sceneVm.setOutreach(newValue)
            }

            NumericRow {
                Layout.fillWidth: true
                label: qsTr("Tackle (m):")
                from: sceneVm.tackleMin
                to: sceneVm.tackleMax
                value: sceneVm.tackle
                onCommitted: newValue => sceneVm.setTackle(newValue)
            }
        }
    }

    StyledGroupBox {
        Layout.fillWidth: true
        title: qsTr("Load")
        topPadding: Metrics.spacing24
        bottomPadding: Metrics.spacing6
        leftPadding: Metrics.spacing6
        rightPadding: Metrics.spacing6

        ColumnLayout {
            anchors.fill: parent
            spacing: root.layoutSpacing

            NumericRow {
                Layout.fillWidth: true
                label: qsTr("Static Hook Load (t):")
                from: 0
                to: 10000
                decimals: 1
                value: sceneVm.hookLoadTonnes
                inputEnabled: !sceneVm.hookLoadAuto
                onCommitted: newValue => sceneVm.setHookLoadTonnes(newValue)
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: root.layoutSpacing

                Item { Layout.fillWidth: true }

                StyledCheckBox {
                    Layout.preferredWidth: 96
                    text: qsTr("Auto")
                    checked: sceneVm.hookLoadAuto
                    onToggled: sceneVm.setHookLoadAuto(checked)
                }
            }

            NumericRow {
                Layout.fillWidth: true
                label: qsTr("Offlead (deg):")
                from: -90
                to: 90
                flippable: true
                value: sceneVm.offlead
                onCommitted: newValue => sceneVm.setOfflead(newValue)
            }

            NumericRow {
                Layout.fillWidth: true
                label: qsTr("Sidelead (deg):")
                from: -90
                to: 90
                flippable: true
                value: sceneVm.sidelead
                onCommitted: newValue => sceneVm.setSidelead(newValue)
            }
        }
    }

    StyledGroupBox {
        Layout.fillWidth: true
        title: qsTr("Wind")
        topPadding: Metrics.spacing24
        bottomPadding: Metrics.spacing6
        leftPadding: Metrics.spacing6
        rightPadding: Metrics.spacing6

        ColumnLayout {
            anchors.fill: parent
            spacing: root.layoutSpacing

            NumericRow {
                Layout.fillWidth: true
                label: qsTr("Wind speed (m/s):")
                from: -50
                to: 50
                flippable: true
                value: sceneVm.windSpeed
                onCommitted: newValue => sceneVm.setWindSpeed(newValue)
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: root.layoutSpacing

                Label {
                    Layout.fillWidth: true
                    text: qsTr("Direction:")
                }

                RowLayout {
                    Layout.preferredWidth: 96
                    spacing: Math.max(2, root.layoutSpacing - 4)

                    StyledRadioButton {
                        text: qsTr("X")
                        checked: sceneVm.windAxis === "X"
                        onClicked: sceneVm.setWindAxis("X")
                    }

                    StyledRadioButton {
                        text: qsTr("Y")
                        checked: sceneVm.windAxis === "Y"
                        onClicked: sceneVm.setWindAxis("Y")
                    }
                }
            }
        }
    }

    StyledGroupBox {
        Layout.fillWidth: true
        title: qsTr("Accelerations")
        topPadding: Metrics.spacing24
        bottomPadding: Metrics.spacing6
        leftPadding: Metrics.spacing6
        rightPadding: Metrics.spacing6

        ColumnLayout {
            anchors.fill: parent
            spacing: root.layoutSpacing

            NumericRow {
                Layout.fillWidth: true
                label: qsTr("Surge (m/s²):")
                from: -10
                to: 10
                flippable: true
                value: sceneVm.accelX
                onCommitted: newValue => sceneVm.setAccelX(newValue)
            }

            NumericRow {
                Layout.fillWidth: true
                label: qsTr("Sway (m/s²):")
                from: -10
                to: 10
                flippable: true
                value: sceneVm.accelY
                onCommitted: newValue => sceneVm.setAccelY(newValue)
            }

            NumericRow {
                Layout.fillWidth: true
                label: qsTr("Heave (m/s²):")
                from: -10
                to: 10
                flippable: true
                value: sceneVm.accelZ
                onCommitted: newValue => sceneVm.setAccelZ(newValue)
            }

            NumericRow {
                Layout.fillWidth: true
                label: qsTr("Roll (rad/s²):")
                from: -5
                to: 5
                flippable: true
                value: sceneVm.rollAccel
                onCommitted: newValue => sceneVm.setRollAccel(newValue)
            }

            NumericRow {
                Layout.fillWidth: true
                label: qsTr("Pitch (rad/s²):")
                from: -5
                to: 5
                flippable: true
                value: sceneVm.pitchAccel
                onCommitted: newValue => sceneVm.setPitchAccel(newValue)
            }
        }
    }
}


