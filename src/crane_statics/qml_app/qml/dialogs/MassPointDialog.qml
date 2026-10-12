import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import ".."
import BF.DesignSystem

Dialog {
    id: root

    property string bodyId: ""
    property string componentLabel: ""
    property int editIndex: -1

    readonly property bool boomBody: bodyId === "boom"

    signal committed(int index, var fields)

    function openFor(index, values) {
        editIndex = index
        idField.text = values && values.id !== undefined ? values.id : ""
        massField.setValue(values && values.mass_t !== undefined ? values.mass_t : 0)
        xField.setValue(values && values.x_m !== undefined ? values.x_m : 0)
        yField.setValue(values && values.y_m !== undefined ? values.y_m : 0)
        zField.setValue(values && values.z_m !== undefined ? values.z_m : 0)
        uField.setValue(values && values.local_x_m !== undefined ? values.local_x_m : 0)
        vField.setValue(values && values.local_y_m !== undefined ? values.local_y_m : 0)
        wField.setValue(values && values.local_z_m !== undefined ? values.local_z_m : 0)
        open()
    }

    title: (editIndex < 0 ? qsTr("Add Mass Point") : qsTr("Edit Mass Point"))
           + (componentLabel.length > 0 ? " (" + componentLabel + ")" : "")
    modal: true
    anchors.centerIn: Overlay.overlay
    standardButtons: Dialog.Ok | Dialog.Cancel

    onAccepted: committed(editIndex, {
        "id": idField.text,
        "mass_t": massField.value,
        "x_m": xField.value,
        "y_m": yField.value,
        "z_m": zField.value,
        "local_x_m": uField.value,
        "local_y_m": vField.value,
        "local_z_m": wField.value
    })

    GridLayout {
        columns: 2
        columnSpacing: Math.round(Metrics.spacing8 * Metrics.spacingMultiplier)
        rowSpacing: Math.round(Metrics.spacing8 * Metrics.spacingMultiplier)

        Label { text: qsTr("ID:") }
        TextField { id: idField; Layout.preferredWidth: Metrics.maxInputWidth; selectByMouse: true }

        Label { text: qsTr("Mass (t):") }
        NumberField { id: massField; Layout.preferredWidth: Metrics.maxInputWidth }

        Label { text: qsTr("X (m):"); visible: !root.boomBody }
        NumberField { id: xField; Layout.preferredWidth: Metrics.maxInputWidth; visible: !root.boomBody }

        Label { text: qsTr("Y (m):"); visible: !root.boomBody }
        NumberField { id: yField; Layout.preferredWidth: Metrics.maxInputWidth; visible: !root.boomBody }

        Label { text: qsTr("Z (m):"); visible: !root.boomBody }
        NumberField { id: zField; Layout.preferredWidth: Metrics.maxInputWidth; visible: !root.boomBody }

        Label { text: qsTr("Local U (m):"); visible: root.boomBody }
        NumberField { id: uField; Layout.preferredWidth: Metrics.maxInputWidth; visible: root.boomBody }

        Label { text: qsTr("Local V (m):"); visible: root.boomBody }
        NumberField { id: vField; Layout.preferredWidth: Metrics.maxInputWidth; visible: root.boomBody }

        Label { text: qsTr("Local W (m):"); visible: root.boomBody }
        NumberField { id: wField; Layout.preferredWidth: Metrics.maxInputWidth; visible: root.boomBody }
    }
}


