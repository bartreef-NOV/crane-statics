import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts

// The load conditions of a rules document: a list to pick, add, duplicate and delete
// them, and a form for the selected one. Every edit goes through modelVm, which reports
// a rejected value through editFailed (shown by ModelWorkspace's edit error dialog).
RowLayout {
    id: root
    objectName: "conditionsPanel"

    readonly property int layoutSpacing: 8
    readonly property var liftChoices: ["onboard", "offboard"]

    spacing: root.layoutSpacing

    component ConditionRow: RowLayout {
        id: conditionRow

        property string label: ""
        property string fieldKey: ""
        property int decimals: 3
        // When true, an empty field means "unset": the value is cleared on the
        // condition instead of being written as 0.
        property bool nullable: false

        Layout.fillWidth: true
        spacing: root.layoutSpacing

        function applyDisplayValue() {
            const v = modelVm.condition[conditionRow.fieldKey]
            if (v === null || v === undefined)
                conditionField.clear()
            else
                conditionField.setValue(v)
        }

        Label {
            Layout.fillWidth: true
            text: conditionRow.label
            elide: Text.ElideRight
        }

        NumberField {
            id: conditionField
            objectName: "conditionField_" + conditionRow.fieldKey
            Layout.preferredWidth: 96
            decimals: conditionRow.decimals
            Component.onCompleted: conditionRow.applyDisplayValue()
            onEditingFinished: {
                // Leaving a field unchanged is not an edit (no undo step, no dirty flag).
                const current = modelVm.condition[conditionRow.fieldKey]
                const unset = current === null || current === undefined
                if (conditionRow.nullable && conditionField.text.trim() === "") {
                    if (!unset)
                        modelVm.clearConditionValue(conditionRow.fieldKey)
                } else if (unset || conditionField.text !== Number(current).toFixed(conditionRow.decimals)) {
                    modelVm.setConditionValue(conditionRow.fieldKey, value)
                }
                // A rejected value changes nothing: show the condition's value again.
                conditionRow.applyDisplayValue()
            }

            Connections {
                target: modelVm
                function onConditionsChanged() {
                    if (conditionField.activeFocus)
                        return
                    conditionRow.applyDisplayValue()
                }
            }
        }
    }

    ColumnLayout {
        Layout.preferredWidth: 220
        Layout.fillHeight: true
        spacing: root.layoutSpacing

        ListView {
            id: conditionList
            objectName: "conditionList"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: modelVm.conditionNames
            currentIndex: modelVm.conditionNames.indexOf(modelVm.selectedCondition)
            boundsBehavior: Flickable.StopAtBounds

            delegate: ItemDelegate {
                required property string modelData

                width: ListView.view.width
                text: modelData
                highlighted: modelData === modelVm.selectedCondition
                onClicked: modelVm.selectCondition(modelData)
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: root.layoutSpacing

            Button {
                objectName: "addConditionButton"
                Layout.fillWidth: true
                text: qsTr("Add")
                onClicked: modelVm.addCondition()
            }

            Button {
                objectName: "duplicateConditionButton"
                Layout.fillWidth: true
                text: qsTr("Duplicate")
                enabled: modelVm.selectedCondition !== ""
                onClicked: modelVm.duplicateCondition()
            }

            Button {
                objectName: "deleteConditionButton"
                Layout.fillWidth: true
                text: qsTr("Delete")
                // A rules document needs at least one condition.
                enabled: modelVm.conditionNames.length > 1
                onClicked: modelVm.deleteCondition()
            }
        }
    }

    ScrollView {
        id: formScroll
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            // Capped so a label stays near its field on a wide window.
            width: Math.min(formScroll.availableWidth, 560)
            spacing: root.layoutSpacing

            GroupBox {
                Layout.fillWidth: true
                title: qsTr("General")

                ColumnLayout {
                    anchors.fill: parent
                    spacing: root.layoutSpacing

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: root.layoutSpacing

                        Label {
                            Layout.fillWidth: true
                            text: qsTr("Name")
                        }

                        TextField {
                            id: nameField
                            objectName: "conditionNameField"
                            Layout.preferredWidth: 200
                            selectByMouse: true

                            function applyName() {
                                text = modelVm.condition.name ?? ""
                            }

                            Component.onCompleted: applyName()
                            onEditingFinished: {
                                const name = text.trim()
                                if (name !== "" && name !== modelVm.selectedCondition)
                                    modelVm.renameCondition(name)
                                // A rejected name changes nothing: show the condition's again.
                                applyName()
                            }

                            Connections {
                                target: modelVm
                                function onConditionsChanged() {
                                    if (nameField.activeFocus)
                                        return
                                    nameField.applyName()
                                }
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: root.layoutSpacing

                        Label {
                            Layout.fillWidth: true
                            text: qsTr("Lift")
                        }

                        ComboBox {
                            id: liftBox
                            objectName: "conditionLiftBox"
                            Layout.preferredWidth: 200
                            model: root.liftChoices

                            function applyLift() {
                                currentIndex = Math.max(
                                    0, root.liftChoices.indexOf(modelVm.condition.lift ?? "onboard"))
                            }

                            Component.onCompleted: applyLift()
                            onActivated: index => {
                                if (root.liftChoices[index] !== modelVm.condition.lift)
                                    modelVm.setConditionLift(root.liftChoices[index])
                                applyLift()
                            }

                            Connections {
                                target: modelVm
                                function onConditionsChanged() {
                                    liftBox.applyLift()
                                }
                            }
                        }
                    }
                }
            }

            GroupBox {
                Layout.fillWidth: true
                title: qsTr("Wind and Load")

                ColumnLayout {
                    anchors.fill: parent
                    spacing: root.layoutSpacing

                    ConditionRow { label: qsTr("Wind Speed (m/s)"); fieldKey: "wind_speed_m_s" }
                    ConditionRow { label: qsTr("Load Wind Area (m²)"); fieldKey: "load_wind_area_m2" }
                    ConditionRow { label: qsTr("Load Drag Coefficient"); fieldKey: "load_drag_coefficient" }
                    ConditionRow {
                        label: qsTr("Hook Height Override (m)")
                        fieldKey: "hook_height_override_m"
                        nullable: true
                    }
                }
            }

            GroupBox {
                objectName: "conditionOffboardGroup"
                Layout.fillWidth: true
                visible: modelVm.condition.lift === "offboard"
                title: qsTr("Offboard")

                ColumnLayout {
                    anchors.fill: parent
                    spacing: root.layoutSpacing

                    ConditionRow {
                        label: qsTr("Significant Wave Height (m)")
                        fieldKey: "significant_wave_height_m"
                        nullable: true
                    }
                    ConditionRow {
                        label: qsTr("Supply Deck Velocity v_in (m/s)")
                        fieldKey: "v_in_m_s"
                        nullable: true
                    }
                    ConditionRow {
                        label: qsTr("Crane Tip Velocity v_t (m/s)")
                        fieldKey: "v_t_m_s"
                        nullable: true
                    }
                }
            }

            GroupBox {
                Layout.fillWidth: true
                title: qsTr("Vessel Motion (± limits)")

                ColumnLayout {
                    anchors.fill: parent
                    spacing: root.layoutSpacing

                    ConditionRow { label: qsTr("Surge (m/s²)"); fieldKey: "accel_x_m_s2" }
                    ConditionRow { label: qsTr("Sway (m/s²)"); fieldKey: "accel_y_m_s2" }
                    ConditionRow { label: qsTr("Heave (m/s²)"); fieldKey: "accel_z_m_s2" }
                    ConditionRow { label: qsTr("Roll (rad/s²)"); fieldKey: "roll_angular_accel_rad_s2" }
                    ConditionRow { label: qsTr("Pitch (rad/s²)"); fieldKey: "pitch_angular_accel_rad_s2" }
                    ConditionRow { label: qsTr("Roll angle (°)"); fieldKey: "roll_deg" }
                    ConditionRow { label: qsTr("Pitch angle (°)"); fieldKey: "pitch_deg" }
                    ConditionRow { label: qsTr("Motion Reference X (m)"); fieldKey: "reference_x_m" }
                    ConditionRow { label: qsTr("Motion Reference Z (m)"); fieldKey: "reference_z_m" }
                }
            }

            Item { Layout.fillHeight: true }
        }
    }
}
