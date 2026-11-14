import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import ".."

/*  Adds a payload hoist. An existing hoist is edited in the Hoists panel's form; its
    lead limits and DAF belong to each condition (the Conditions tab). */
Dialog {
    id: root

    property var nodeIds: []

    signal committed(int index, var fields)

    function openFor(index, values) {
        idField.text = values && values.id !== undefined ? values.id : ""
        nodeCombo.currentIndex = values ? nodeIds.indexOf(values.support_node_id) : -1
        fallsSpin.value = values && values.falls ? values.falls : 1
        lowerBlockMassField.setValue(values && values.lower_block_mass_t !== undefined ? values.lower_block_mass_t : 0)
        linearMassField.setValue(values && values.linear_mass_kg_m !== undefined ? values.linear_mass_kg_m : 0)
        splitableCheck.checked = values ? !!values.splitable_block : false
        splitFallsSpin.value = values && values.split_falls ? values.split_falls : fallsSpin.value
        splitLowerBlockMassField.setValue(values && values.split_lower_block_mass_t !== undefined && values.split_lower_block_mass_t !== null
                                    ? values.split_lower_block_mass_t : lowerBlockMassField.value)
        lowestHookHeightField.setValue(values && values.lowest_hook_height_m !== undefined ? values.lowest_hook_height_m : 0)
        open()
    }

    title: qsTr("Add Hoist")
    modal: true
    anchors.centerIn: Overlay.overlay
    standardButtons: Dialog.Ok | Dialog.Cancel

    onAccepted: committed(-1, {
        "id": idField.text,
        "support_node_id": nodeCombo.currentText,
        "falls": fallsSpin.value,
        "lower_block_mass_t": lowerBlockMassField.value,
        "linear_mass_kg_m": linearMassField.value,
        "splitable_block": splitableCheck.checked,
        "split_falls": splitFallsSpin.value,
        "split_lower_block_mass_t": splitLowerBlockMassField.value,
        "lowest_hook_height_m": lowestHookHeightField.value
    })

    GridLayout {
        columns: 2
        columnSpacing: Math.round(8)
        rowSpacing: Math.round(8)

        Label { text: qsTr("ID:") }
        TextField {
            id: idField
            Layout.preferredWidth: 200
            selectByMouse: true
        }

        Label { text: qsTr("Support Node:") }
        ComboBox { id: nodeCombo; Layout.preferredWidth: 200; editable: true; model: root.nodeIds }

        Label { text: qsTr("Falls:") }
        SpinBox { id: fallsSpin; Layout.preferredWidth: 200; from: 1; to: 99; value: 1 }

        Label { text: qsTr("Lower Block Mass (t):") }
        NumberField { id: lowerBlockMassField; Layout.preferredWidth: 200 }

        Label { text: qsTr("Linear Mass (kg/m):") }
        NumberField {
            id: linearMassField
            Layout.preferredWidth: 200
            validator: DoubleValidator { bottom: 0; notation: DoubleValidator.StandardNotation }
        }

        CheckBox {
            id: splitableCheck
            Layout.columnSpan: 2
            text: qsTr("Splittable block")
        }

        Label { text: qsTr("Split Falls:"); visible: splitableCheck.checked }
        SpinBox {
            id: splitFallsSpin
            Layout.preferredWidth: 200
            visible: splitableCheck.checked
            from: 1
            to: fallsSpin.value
            value: 1
        }

        Label { text: qsTr("Split Lower Block Mass (t):"); visible: splitableCheck.checked }
        NumberField { id: splitLowerBlockMassField; Layout.preferredWidth: 200; visible: splitableCheck.checked }

        Label { text: qsTr("Lowest Hook Height (m):") }
        NumberField { id: lowestHookHeightField; Layout.preferredWidth: 200 }

        Label {
            objectName: "hoistDialogConditionsNote"
            Layout.columnSpan: 2
            Layout.maximumWidth: 360
            wrapMode: Text.WordWrap
            text: qsTr("The new hoist is usable in every condition. Set its off-lead, side-lead and DAF per condition in the Conditions tab, and its load chart in the Hoists tab.")
        }
    }
}
