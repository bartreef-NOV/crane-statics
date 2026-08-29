import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import ".."
import "../../design" as Design
import "../components" as Components

Components.Dialog {
    id: root

    property int editIndex: -1
    property var nodeIds: []
    property bool isBoomHoist: false

    signal committed(int index, var fields)

    function openFor(index, values) {
        editIndex = index
        isBoomHoist = !!(values && values.is_boom_hoist)
        idField.text = values && values.id !== undefined ? values.id : ""
        idField.readOnly = index >= 0
        nodeCombo.currentIndex = values ? nodeIds.indexOf(values.support_node_id) : -1
        fallsSpin.value = values && values.falls ? values.falls : 1
        hookMassField.setValue(values && values.hook_mass_t !== undefined ? values.hook_mass_t : 0)
        linearMassField.setValue(values && values.linear_mass_kg_m !== undefined ? values.linear_mass_kg_m : 0)
        if (values && values.rope_length_m !== undefined && values.rope_length_m !== null)
            ropeLengthField.setValue(values.rope_length_m)
        else
            ropeLengthField.text = ""
        splitableCheck.checked = values ? !!values.splitable_block : false
        splitFallsSpin.value = values && values.split_falls ? values.split_falls : fallsSpin.value
        splitHookMassField.setValue(values && values.split_hook_mass_t !== undefined && values.split_hook_mass_t !== null
                                    ? values.split_hook_mass_t : hookMassField.value)
        dafField.setValue(values && values.hook_daf !== undefined ? values.hook_daf : 1)
        offleadField.setValue(values && values.offlead_deg !== undefined ? values.offlead_deg : 0)
        sideLeadField.setValue(values && values.side_lead_deg !== undefined ? values.side_lead_deg : 0)
        minTravelField.setValue(values && values.min_hook_travel_m !== undefined && values.min_hook_travel_m !== null
                                ? values.min_hook_travel_m : 0)
        maxTravelField.setValue(values && values.max_hook_travel_m !== undefined && values.max_hook_travel_m !== null
                                ? values.max_hook_travel_m : 0)
        open()
    }

    title: editIndex < 0 ? qsTr("Add Hoist") : (isBoomHoist ? qsTr("Edit Boom Hoist") : qsTr("Edit Hoist"))
    modal: true
    anchors.centerIn: Overlay.overlay
    standardButtons: Dialog.Ok | Dialog.Cancel

    onAccepted: committed(editIndex, {
        "id": idField.text,
        "support_node_id": nodeCombo.currentText,
        "falls": fallsSpin.value,
        "hook_mass_t": hookMassField.value,
        "linear_mass_kg_m": linearMassField.value,
        "rope_length_m": ropeLengthField.text.trim() === "" ? null : ropeLengthField.value,
        "splitable_block": splitableCheck.checked,
        "split_falls": splitFallsSpin.value,
        "split_hook_mass_t": splitHookMassField.value,
        "hook_daf": dafField.value,
        "offlead_deg": offleadField.value,
        "side_lead_deg": sideLeadField.value,
        "min_hook_travel_m": minTravelField.value,
        "max_hook_travel_m": maxTravelField.value
    })

    GridLayout {
        columns: 2
        columnSpacing: Math.round(Design.DesignTokens.spacing.controlGap * Design.DesignTokens.layout.spacingMultiplier)
        rowSpacing: Math.round(Design.DesignTokens.spacing.sm * Design.DesignTokens.layout.spacingMultiplier)

        Label { text: qsTr("ID:") }
        TextField {
            id: idField
            Layout.preferredWidth: Design.DesignTokens.sizing.maxInputWidth
            selectByMouse: true
            ToolTip.visible: hovered && readOnly
            ToolTip.text: qsTr("Hoist ID is immutable after creation")
        }

        Label { text: qsTr("Support Node:"); visible: !root.isBoomHoist }
        ComboBox { id: nodeCombo; Layout.preferredWidth: Design.DesignTokens.sizing.maxInputWidth; editable: true; model: root.nodeIds; visible: !root.isBoomHoist }

        Label { text: qsTr("Falls:"); visible: !root.isBoomHoist }
        SpinBox { id: fallsSpin; Layout.preferredWidth: Design.DesignTokens.sizing.maxInputWidth; from: 1; to: 99; value: 1; visible: !root.isBoomHoist }

        Label { text: qsTr("Hook Mass (t):"); visible: !root.isBoomHoist }
        NumberField { id: hookMassField; Layout.preferredWidth: Design.DesignTokens.sizing.maxInputWidth; visible: !root.isBoomHoist }

        Label { text: qsTr("Linear Mass (kg/m):") }
        NumberField {
            id: linearMassField
            Layout.preferredWidth: Design.DesignTokens.sizing.maxInputWidth
            validator: DoubleValidator { bottom: 0; notation: DoubleValidator.StandardNotation }
        }

        Label { text: qsTr("Rope Length (m):") }
        NumberField {
            id: ropeLengthField
            Layout.preferredWidth: Design.DesignTokens.sizing.maxInputWidth
            placeholderText: qsTr("auto (reeved length)")
            validator: DoubleValidator { bottom: 0; notation: DoubleValidator.StandardNotation }
        }

        Components.StyledCheckBox {
            id: splitableCheck
            Layout.columnSpan: 2
            text: qsTr("Splittable block")
            visible: !root.isBoomHoist
        }

        Label { text: qsTr("Split Falls:"); visible: !root.isBoomHoist && splitableCheck.checked }
        SpinBox {
            id: splitFallsSpin
            Layout.preferredWidth: Design.DesignTokens.sizing.maxInputWidth
            visible: !root.isBoomHoist && splitableCheck.checked
            from: 1
            to: fallsSpin.value
            value: 1
        }

        Label { text: qsTr("Split Hook Mass (t):"); visible: !root.isBoomHoist && splitableCheck.checked }
        NumberField { id: splitHookMassField; Layout.preferredWidth: Design.DesignTokens.sizing.maxInputWidth; visible: !root.isBoomHoist && splitableCheck.checked }

        Label { text: qsTr("DAF:"); visible: !root.isBoomHoist }
        NumberField { id: dafField; Layout.preferredWidth: Design.DesignTokens.sizing.maxInputWidth; visible: !root.isBoomHoist }

        Label { text: qsTr("Off Lead (deg):"); visible: !root.isBoomHoist }
        NumberField { id: offleadField; Layout.preferredWidth: Design.DesignTokens.sizing.maxInputWidth; visible: !root.isBoomHoist }

        Label { text: qsTr("Side Lead (deg):"); visible: !root.isBoomHoist }
        NumberField { id: sideLeadField; Layout.preferredWidth: Design.DesignTokens.sizing.maxInputWidth; visible: !root.isBoomHoist }

        Label { text: qsTr("Min Hook Travel (m):"); visible: !root.isBoomHoist }
        NumberField { id: minTravelField; Layout.preferredWidth: Design.DesignTokens.sizing.maxInputWidth; visible: !root.isBoomHoist }

        Label { text: qsTr("Max Hook Travel (m):"); visible: !root.isBoomHoist }
        NumberField { id: maxTravelField; Layout.preferredWidth: Design.DesignTokens.sizing.maxInputWidth; visible: !root.isBoomHoist }
    }
}


