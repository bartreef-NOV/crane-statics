import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import BF.DesignSystem

ColumnLayout {
    id: root

    readonly property int layoutSpacing: Math.round(
        Metrics.spacing8 * Metrics.spacingMultiplier
    )

    spacing: root.layoutSpacing

    component EnvRow: RowLayout {
        id: envRow

        property string label: ""
        property string fieldKey: ""
        property int decimals: 3
        // When true, an empty field means "unset" rather than 0 - the field is
        // cleared on the document instead of being written as a numeric value.
        property bool nullable: false

        Layout.fillWidth: true
        spacing: root.layoutSpacing

        function displayValue() {
            const v = modelVm.environment[envRow.fieldKey]
            return (envRow.nullable && (v === null || v === undefined)) ? "" : v
        }

        function applyDisplayValue() {
            const v = envRow.displayValue()
            if (v === "")
                envField.clear()
            else
                envField.setValue(v)
        }

        Label {
            Layout.fillWidth: true
            text: envRow.label
            elide: Text.ElideRight
        }

        NumberField {
            id: envField
            objectName: "envField_" + envRow.fieldKey
            Layout.preferredWidth: 96
            decimals: envRow.decimals
            Component.onCompleted: envRow.applyDisplayValue()
            onEditingFinished: {
                if (envRow.nullable && envField.text.trim() === "")
                    modelVm.clearEnvironmentValue(envRow.fieldKey)
                else
                    modelVm.setEnvironmentValue(envRow.fieldKey, value)
            }

            Connections {
                target: modelVm
                function onEnvironmentChanged() {
                    if (envField.activeFocus)
                        return
                    envRow.applyDisplayValue()
                }
            }
        }
    }

    GroupBox {
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

    GroupBox {
        Layout.fillWidth: true
        title: qsTr("Support Widths")

        ColumnLayout {
            anchors.fill: parent
            spacing: root.layoutSpacing

            EnvRow { label: qsTr("Boom Heel Width (m)"); fieldKey: "boom_width_m" }
            EnvRow {
                label: qsTr("Slewing Bearing Diameter (m)")
                fieldKey: "slewing_bearing_diameter_m"
                nullable: true
            }
        }
    }

    GroupBox {
        Layout.fillWidth: true
        title: qsTr("Environment")

        ColumnLayout {
            anchors.fill: parent
            spacing: root.layoutSpacing

            EnvRow { label: qsTr("Gravity (m/s²)"); fieldKey: "gravity_m_s2" }
            EnvRow { label: qsTr("Max Wind Speed (m/s)"); fieldKey: "max_wind_speed_m_s" }
            EnvRow { label: qsTr("Air Density (kg/m³)"); fieldKey: "air_density_kg_m3" }
        }
    }

    GroupBox {
        Layout.fillWidth: true
        title: qsTr("Design Duty")

        ColumnLayout {
            anchors.fill: parent
            spacing: root.layoutSpacing

            EnvRow { label: qsTr("Hook Height at Min Outreach (m)"); fieldKey: "hook_height_at_min_outreach_m" }
        }
    }

    GroupBox {
        Layout.fillWidth: true
        title: qsTr("Accelerations")

        ColumnLayout {
            anchors.fill: parent
            spacing: root.layoutSpacing

            EnvRow { label: qsTr("Vessel Roll (°)"); fieldKey: "roll_deg" }
            EnvRow { label: qsTr("Vessel Pitch (°)"); fieldKey: "pitch_deg" }
            EnvRow { label: qsTr("Crane Slewing Angle (°)"); fieldKey: "crane_slewing_angle_deg" }
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


