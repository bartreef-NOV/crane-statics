import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import ".."

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
        areaWField.setValue(values && values.area_w_m2 !== undefined ? values.area_w_m2 : 0)
        areaVField.setValue(values && values.area_v_m2 !== undefined ? values.area_v_m2 : 0)
        xField.setValue(values && values.x_m !== undefined ? values.x_m : 0)
        zField.setValue(values && values.z_m !== undefined ? values.z_m : 0)
        uField.setValue(values && values.local_x_m !== undefined ? values.local_x_m : 0)
        wField.setValue(values && values.local_z_m !== undefined ? values.local_z_m : 0)
        cdField.setValue(values && values.cd !== undefined ? values.cd : 1)
        open()
    }

    title: (editIndex < 0 ? qsTr("Add Wind Area") : qsTr("Edit Wind Area"))
           + (componentLabel.length > 0 ? " (" + componentLabel + ")" : "")
    modal: true
    anchors.centerIn: Overlay.overlay
    standardButtons: Dialog.Ok | Dialog.Cancel

    onAccepted: committed(editIndex, {
        "id": idField.text,
        "area_w_m2": areaWField.value,
        "area_v_m2": areaVField.value,
        "x_m": xField.value,
        "z_m": zField.value,
        "local_x_m": uField.value,
        "local_z_m": wField.value,
        "cd": cdField.value
    })

    GridLayout {
        columns: 2
        columnSpacing: Math.round(8)
        rowSpacing: Math.round(8)

        Label { text: qsTr("ID:") }
        TextField { id: idField; Layout.preferredWidth: 200; selectByMouse: true }

        Label { text: qsTr("Area X (m²):") }
        NumberField { id: areaWField; Layout.preferredWidth: 200 }

        Label { text: qsTr("Area Y (m²):") }
        NumberField { id: areaVField; Layout.preferredWidth: 200 }

        Label { text: qsTr("X (m):"); visible: !root.boomBody }
        NumberField { id: xField; Layout.preferredWidth: 200; visible: !root.boomBody }

        Label { text: qsTr("Z (m):"); visible: !root.boomBody }
        NumberField { id: zField; Layout.preferredWidth: 200; visible: !root.boomBody }

        Label { text: qsTr("Local U (m):"); visible: root.boomBody }
        NumberField { id: uField; Layout.preferredWidth: 200; visible: root.boomBody }

        Label { text: qsTr("Local W (m):"); visible: root.boomBody }
        NumberField { id: wField; Layout.preferredWidth: 200; visible: root.boomBody }

        Label { text: qsTr("Cd:") }
        NumberField { id: cdField; Layout.preferredWidth: 200 }
    }
}


