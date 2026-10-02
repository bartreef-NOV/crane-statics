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

    signal committed(int index, var fields)

    function openFor(index, values) {
        editIndex = index
        fromCombo.currentIndex = values ? nodeIds.indexOf(values.from_node_id) : -1
        toCombo.currentIndex = values ? nodeIds.indexOf(values.to_node_id) : -1
        multSpin.value = values && values.mult !== undefined ? values.mult : 1
        open()
    }

    title: editIndex < 0 ? qsTr("Add Segment") : qsTr("Edit Segment")
    modal: true
    anchors.centerIn: Overlay.overlay
    standardButtons: Dialog.Ok | Dialog.Cancel

    onAccepted: committed(editIndex, {
        "from_node_id": fromCombo.currentText,
        "to_node_id": toCombo.currentText,
        "mult": multSpin.value
    })

    GridLayout {
        columns: 2
        columnSpacing: Math.round(Metrics.spacing8 * Metrics.spacingMultiplier)
        rowSpacing: Math.round(Metrics.spacing8 * Metrics.spacingMultiplier)

        Label { text: qsTr("From Node:") }
        ComboBox { id: fromCombo; Layout.preferredWidth: Metrics.maxInputWidth; editable: true; model: root.nodeIds }

        Label { text: qsTr("To Node:") }
        ComboBox { id: toCombo; Layout.preferredWidth: Metrics.maxInputWidth; editable: true; model: root.nodeIds }

        Label { text: qsTr("Mult:") }
        SpinBox { id: multSpin; Layout.preferredWidth: Metrics.maxInputWidth; from: 1; to: 99; value: 1 }
    }
}


