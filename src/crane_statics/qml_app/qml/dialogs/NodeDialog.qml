import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import ".."
import BF.DesignSystem
import "../components" as Components

Components.Dialog {
    id: root

    property string bodyId: ""
    property string componentLabel: ""
    property int editIndex: -1
    property var nodeIds: []

    readonly property bool boomBody: bodyId === "boom"

    signal committed(int index, var fields)

    function openFor(index, values) {
        editIndex = index
        idField.text = values && values.id !== undefined ? values.id : ""
        hangingCheck.checked = values ? !!values.hanging : false
        hangFromCombo.currentIndex = values && values.below_node_id
            ? nodeIds.indexOf(values.below_node_id) : -1
        xField.setValue(values && values.x_m !== undefined ? values.x_m : 0)
        zField.setValue(values && values.z_m !== undefined ? values.z_m : 0)
        uField.setValue(values && values.local_x_m !== undefined ? values.local_x_m : 0)
        wField.setValue(values && values.local_z_m !== undefined ? values.local_z_m : 0)
        open()
    }

    title: (editIndex < 0 ? qsTr("Add Node") : qsTr("Edit Node"))
           + (componentLabel.length > 0 ? " (" + componentLabel + ")" : "")
    modal: true
    anchors.centerIn: Overlay.overlay
    standardButtons: Dialog.Ok | Dialog.Cancel

    onAccepted: committed(editIndex, {
        "id": idField.text,
        "hanging": hangingCheck.checked,
        "below_node_id": hangFromCombo.currentText,
        "x_m": xField.value,
        "z_m": zField.value,
        "local_x_m": uField.value,
        "local_z_m": wField.value
    })

    GridLayout {
        columns: 2
        columnSpacing: Math.round(Metrics.spacing8 * Metrics.spacingMultiplier)
        rowSpacing: Math.round(Metrics.spacing8 * Metrics.spacingMultiplier)

        Label { text: qsTr("ID:") }
        TextField {
            id: idField
            Layout.preferredWidth: Metrics.maxInputWidth
            placeholderText: qsTr("e.g. boom_tip")
            selectByMouse: true
        }

        Components.StyledCheckBox {
            id: hangingCheck
            Layout.columnSpan: 2
            text: qsTr("Hanging node")
        }

        Label { text: qsTr("Hang From Node ID:"); visible: hangingCheck.checked }
        ComboBox {
            id: hangFromCombo
            Layout.preferredWidth: Metrics.maxInputWidth
            visible: hangingCheck.checked
            editable: true
            model: root.nodeIds
        }

        Label { text: qsTr("X (m):"); visible: !hangingCheck.checked && !root.boomBody }
        NumberField { id: xField; Layout.preferredWidth: Metrics.maxInputWidth; visible: !hangingCheck.checked && !root.boomBody }

        Label { text: qsTr("Z (m):"); visible: !hangingCheck.checked && !root.boomBody }
        NumberField { id: zField; Layout.preferredWidth: Metrics.maxInputWidth; visible: !hangingCheck.checked && !root.boomBody }

        Label { text: qsTr("Local U (m):"); visible: !hangingCheck.checked && root.boomBody }
        NumberField { id: uField; Layout.preferredWidth: Metrics.maxInputWidth; visible: !hangingCheck.checked && root.boomBody }

        Label { text: qsTr("Local W (m):"); visible: !hangingCheck.checked && root.boomBody }
        NumberField { id: wField; Layout.preferredWidth: Metrics.maxInputWidth; visible: !hangingCheck.checked && root.boomBody }
    }
}


