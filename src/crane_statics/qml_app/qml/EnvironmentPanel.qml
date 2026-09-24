import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import "../design" as Design
import "components"

ColumnLayout {
    id: root

    readonly property int layoutSpacing: Math.round(
        Design.DesignTokens.spacing.sm * Design.DesignTokens.layout.spacingMultiplier
    )

    spacing: root.layoutSpacing

    component EnvRow: RowLayout {
        id: envRow

        property string label: ""
        property string fieldKey: ""
        property int decimals: 3

        Layout.fillWidth: true
        spacing: root.layoutSpacing

        Label {
            Layout.fillWidth: true
            text: envRow.label
            elide: Text.ElideRight
        }

        NumberField {
            id: envField
            Layout.preferredWidth: 96
            decimals: envRow.decimals
            Component.onCompleted: setValue(modelVm.environment[envRow.fieldKey])
            onEditingFinished: modelVm.setEnvironmentValue(envRow.fieldKey, value)

            Connections {
                target: modelVm
                function onEnvironmentChanged() {
                    if (!envField.activeFocus)
                        envField.setValue(modelVm.environment[envRow.fieldKey])
                }
            }
        }
    }

    StyledGroupBox {
        Layout.fillWidth: true
        title: qsTr("Primary Structure")

        ColumnLayout {
            anchors.fill: parent
            spacing: root.layoutSpacing

            RowLayout {
                Layout.fillWidth: true
                spacing: root.layoutSpacing

                Label { Layout.fillWidth: true; text: qsTr("Point"); font.bold: true }
                Label { Layout.preferredWidth: 96; text: qsTr("X (m)"); font.bold: true }
                Label { Layout.preferredWidth: 96; text: qsTr("Z (m)"); font.bold: true }
            }

            Repeater {
                model: modelVm.primaryStructureModel

                RowLayout {
                    id: pointRow

                    required property string nodeId
                    required property string label
                    required property real posX
                    required property real posZ

                    Layout.fillWidth: true
                    spacing: root.layoutSpacing

                    Label {
                        Layout.fillWidth: true
                        text: pointRow.label
                        elide: Text.ElideRight
                    }

                    NumberField {
                        id: xField
                        Layout.preferredWidth: 96
                        Component.onCompleted: setValue(pointRow.posX)
                        onEditingFinished: modelVm.setPrimaryStructurePoint(pointRow.nodeId, value, zField.value)
                    }

                    NumberField {
                        id: zField
                        Layout.preferredWidth: 96
                        Component.onCompleted: setValue(pointRow.posZ)
                        onEditingFinished: modelVm.setPrimaryStructurePoint(pointRow.nodeId, xField.value, value)
                    }
                }
            }
        }
    }

    StyledGroupBox {
        Layout.fillWidth: true
        title: qsTr("Support Widths")

        ColumnLayout {
            anchors.fill: parent
            spacing: root.layoutSpacing

            EnvRow { label: qsTr("Boom Heel Width (m)"); fieldKey: "boom_width_m" }
            EnvRow { label: qsTr("Slewing Bearing Diameter (m)"); fieldKey: "slewing_bearing_diameter_m" }
        }
    }

    StyledGroupBox {
        Layout.fillWidth: true
        title: qsTr("Environment")

        ColumnLayout {
            anchors.fill: parent
            spacing: root.layoutSpacing

            EnvRow { label: qsTr("Gravity (m/s²)"); fieldKey: "gravity_m_s2" }
            EnvRow { label: qsTr("Max Wind Speed (m/s)"); fieldKey: "max_wind_speed_m_s" }
            EnvRow { label: qsTr("Wind Reference Height (m ASL)"); fieldKey: "wind_reference_height_m_asl" }
            EnvRow { label: qsTr("Air Density (kg/m³)"); fieldKey: "air_density_kg_m3" }
            EnvRow { label: qsTr("Wind Profile Exponent"); fieldKey: "wind_profile_exponent" }
            EnvRow { label: qsTr("Mean Sea Level Z (m)"); fieldKey: "mean_sealevel_z_m" }
        }
    }

    StyledGroupBox {
        Layout.fillWidth: true
        title: qsTr("Design Duty")

        ColumnLayout {
            anchors.fill: parent
            spacing: root.layoutSpacing

            EnvRow { label: qsTr("Hook Height at Min Outreach (m)"); fieldKey: "hook_height_at_min_outreach_m" }
        }
    }

    StyledGroupBox {
        Layout.fillWidth: true
        title: qsTr("Accelerations")

        ColumnLayout {
            anchors.fill: parent
            spacing: root.layoutSpacing

            EnvRow { label: qsTr("Surge (m/s²)"); fieldKey: "accel_x_m_s2" }
            EnvRow { label: qsTr("Sway (m/s²)"); fieldKey: "accel_y_m_s2" }
            EnvRow { label: qsTr("Heave (m/s²)"); fieldKey: "accel_z_m_s2" }
            EnvRow { label: qsTr("Roll (rad/s²)"); fieldKey: "roll_angular_accel_rad_s2" }
            EnvRow { label: qsTr("Pitch (rad/s²)"); fieldKey: "pitch_angular_accel_rad_s2" }
            EnvRow { label: qsTr("Reference X (m)"); fieldKey: "reference_x_m" }
            EnvRow { label: qsTr("Reference Z (m)"); fieldKey: "reference_z_m" }
        }
    }
}


