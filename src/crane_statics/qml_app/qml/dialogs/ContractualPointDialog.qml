import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import ".."

Dialog {
    id: root

    property int editIndex: -1

    signal committed(int index, var fields)

    function openFor(index, values) {
        editIndex = index
        outreachField.setValue(values && values.outreach_m !== undefined ? values.outreach_m : 0)
        loadField.setValue(values && values.load_t !== undefined ? values.load_t : 0)
        open()
    }

    title: editIndex < 0 ? qsTr("Add Contractual Point") : qsTr("Edit Contractual Point")
    modal: true
    anchors.centerIn: Overlay.overlay
    standardButtons: Dialog.Ok | Dialog.Cancel

    onAccepted: committed(editIndex, {
        "outreach_m": outreachField.value,
        "load_t": loadField.value
    })

    GridLayout {
        columns: 2
        columnSpacing: Math.round(8)
        rowSpacing: Math.round(8)

        Label { text: qsTr("Outreach (m):") }
        NumberField { id: outreachField; Layout.preferredWidth: 200 }

        Label { text: qsTr("Load (t):") }
        NumberField { id: loadField; Layout.preferredWidth: 200 }
    }
}


