import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import ".."
import BF.DesignSystem
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
        sideleadField.setValue(values && values.sidelead_deg !== undefined ? values.sidelead_deg : 0)
        deadTurnsSpin.value = values && values.drum_dead_turns ? values.drum_dead_turns : 0
        if (values && values.drum_diameter_m !== undefined && values.drum_diameter_m !== null)
            drumDiameterField.setValue(values.drum_diameter_m)
        else
            drumDiameterField.text = ""
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
        "sidelead_deg": sideleadField.value,
        "drum_dead_turns": deadTurnsSpin.value,
        "drum_diameter_m": drumDiameterField.text.trim() === "" ? null : drumDiameterField.value
    })

    GridLayout {
        columns: 2
        columnSpacing: Math.round(Metrics.spacing8 * Metrics.spacingMultiplier)
        rowSpacing: Math.round(Metrics.spacing8 * Metrics.spacingMultiplier)

        Label { text: qsTr("ID:") }
        TextField {
            id: idField
            Layout.preferredWidth: Metrics.maxInputWidth
            selectByMouse: true
            ToolTip.visible: hovered && readOnly
            ToolTip.text: qsTr("Hoist ID is immutable after creation")
        }

        Label { text: qsTr("Support Node:"); visible: !root.isBoomHoist }
        ComboBox { id: nodeCombo; Layout.preferredWidth: Metrics.maxInputWidth; editable: true; model: root.nodeIds; visible: !root.isBoomHoist }

        Label { text: qsTr("Falls:"); visible: !root.isBoomHoist }
        SpinBox { id: fallsSpin; Layout.preferredWidth: Metrics.maxInputWidth; from: 1; to: 99; value: 1; visible: !root.isBoomHoist }

        Label { text: qsTr("Hook Mass (t):"); visible: !root.isBoomHoist }
        NumberField { id: hookMassField; Layout.preferredWidth: Metrics.maxInputWidth; visible: !root.isBoomHoist }

        Label { text: qsTr("Linear Mass (kg/m):") }
        NumberField {
            id: linearMassField
            Layout.preferredWidth: Metrics.maxInputWidth
            validator: DoubleValidator { bottom: 0; notation: DoubleValidator.StandardNotation }
        }

        // Only the boom hoist owns an authored rope length; a payload hoist's is
        // derived from the document's hook height at minimum outreach.
        Label { text: qsTr("Rope Length (m):"); visible: root.isBoomHoist }
        NumberField {
            id: ropeLengthField
            Layout.preferredWidth: Metrics.maxInputWidth
            visible: root.isBoomHoist
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
            Layout.preferredWidth: Metrics.maxInputWidth
            visible: !root.isBoomHoist && splitableCheck.checked
            from: 1
            to: fallsSpin.value
            value: 1
        }

        Label { text: qsTr("Split Hook Mass (t):"); visible: !root.isBoomHoist && splitableCheck.checked }
        NumberField { id: splitHookMassField; Layout.preferredWidth: Metrics.maxInputWidth; visible: !root.isBoomHoist && splitableCheck.checked }

        Label { text: qsTr("DAF:"); visible: !root.isBoomHoist }
        NumberField { id: dafField; Layout.preferredWidth: Metrics.maxInputWidth; visible: !root.isBoomHoist }

        Label { text: qsTr("Offlead (deg):"); visible: !root.isBoomHoist }
        NumberField { id: offleadField; Layout.preferredWidth: Metrics.maxInputWidth; visible: !root.isBoomHoist }

        Label { text: qsTr("Sidelead (deg):"); visible: !root.isBoomHoist }
        NumberField { id: sideleadField; Layout.preferredWidth: Metrics.maxInputWidth; visible: !root.isBoomHoist }

        Label { text: qsTr("Drum Dead Turns:"); visible: !root.isBoomHoist }
        SpinBox { id: deadTurnsSpin; Layout.preferredWidth: Metrics.maxInputWidth; from: 0; to: 999; value: 0; visible: !root.isBoomHoist }

        Label { text: qsTr("Drum Diameter (m):"); visible: !root.isBoomHoist }
        NumberField {
            id: drumDiameterField
            Layout.preferredWidth: Metrics.maxInputWidth
            visible: !root.isBoomHoist
            placeholderText: qsTr("required for dead turns")
            validator: DoubleValidator { bottom: 0; notation: DoubleValidator.StandardNotation }
        }
    }
}


