import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts

ColumnLayout {
    id: root

    readonly property int layoutSpacing: Math.round(
        8
    )

    spacing: root.layoutSpacing

    GroupBox {
        Layout.fillWidth: true
        title: qsTr("Active Hoist")
        topPadding: 24
        bottomPadding: 6
        leftPadding: 6
        rightPadding: 6

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

    GroupBox {
        Layout.fillWidth: true
        title: qsTr("Hook Configuration")
        visible: sceneVm.splitable
        topPadding: 24
        bottomPadding: 6
        leftPadding: 6
        rightPadding: 6

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

    GroupBox {
        Layout.fillWidth: true
        title: qsTr("Geometry")
        topPadding: 24
        bottomPadding: 6
        leftPadding: 6
        rightPadding: 6

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

            NumericRow {
                Layout.fillWidth: true
                label: qsTr("Slewing Angle (deg):")
                from: -180
                to: 180
                flippable: true
                value: sceneVm.craneSlewingAngle
                onCommitted: newValue => sceneVm.setCraneSlewingAngle(newValue)
            }
        }
    }

    GroupBox {
        Layout.fillWidth: true
        title: qsTr("Load")
        topPadding: 24
        bottomPadding: 6
        leftPadding: 6
        rightPadding: 6

        ColumnLayout {
            anchors.fill: parent
            spacing: root.layoutSpacing

            NumericRow {
                Layout.fillWidth: true
                label: qsTr("Applied Hook Load (t):")
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

                CheckBox {
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

    GroupBox {
        Layout.fillWidth: true
        title: qsTr("Wind")
        topPadding: 24
        bottomPadding: 6
        leftPadding: 6
        rightPadding: 6

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

                    RadioButton {
                        text: qsTr("X")
                        checked: sceneVm.windAxis === "X"
                        onClicked: sceneVm.setWindAxis("X")
                    }

                    RadioButton {
                        text: qsTr("Y")
                        checked: sceneVm.windAxis === "Y"
                        onClicked: sceneVm.setWindAxis("Y")
                    }
                }
            }
        }
    }

    GroupBox {
        Layout.fillWidth: true
        title: qsTr("Vessel Motion")
        topPadding: 24
        bottomPadding: 6
        leftPadding: 6
        rightPadding: 6

        ColumnLayout {
            anchors.fill: parent
            spacing: root.layoutSpacing

            NumericRow {
                Layout.fillWidth: true
                label: qsTr("Surge (m/s²):")
                flippable: true
                value: sceneVm.accelX
                onCommitted: newValue => sceneVm.setAccelX(newValue)
            }

            NumericRow {
                Layout.fillWidth: true
                label: qsTr("Sway (m/s²):")
                flippable: true
                value: sceneVm.accelY
                onCommitted: newValue => sceneVm.setAccelY(newValue)
            }

            NumericRow {
                Layout.fillWidth: true
                label: qsTr("Heave (m/s²):")
                flippable: true
                value: sceneVm.accelZ
                onCommitted: newValue => sceneVm.setAccelZ(newValue)
            }

            NumericRow {
                Layout.fillWidth: true
                label: qsTr("Roll (rad/s²):")
                flippable: true
                value: sceneVm.rollAccel
                onCommitted: newValue => sceneVm.setRollAccel(newValue)
            }

            NumericRow {
                Layout.fillWidth: true
                label: qsTr("Pitch (rad/s²):")
                flippable: true
                value: sceneVm.pitchAccel
                onCommitted: newValue => sceneVm.setPitchAccel(newValue)
            }

            NumericRow {
                Layout.fillWidth: true
                label: qsTr("Roll angle (°):")
                flippable: true
                value: sceneVm.vesselRoll
                onCommitted: newValue => sceneVm.setVesselRoll(newValue)
            }

            NumericRow {
                Layout.fillWidth: true
                label: qsTr("Pitch angle (°):")
                flippable: true
                value: sceneVm.vesselPitch
                onCommitted: newValue => sceneVm.setVesselPitch(newValue)
            }
        }
    }
}


