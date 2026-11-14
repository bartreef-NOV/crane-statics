import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import ".."

/*  Adds or edits one point of a hoist's load chart: its outreach, its load and the load
    conditions it applies to. A new point applies to every condition the hoist is
    usable in until some are unticked. */
Dialog {
    id: root

    property int editIndex: -1
    // The conditions a point of this hoist can name (the hoist is usable in them).
    property var conditionNames: []
    property var checkedNames: []

    signal committed(int index, var fields)

    function openFor(index, values) {
        editIndex = index
        outreachField.setValue(values && values.outreach_m !== undefined ? values.outreach_m : 0)
        loadField.setValue(values && values.load_t !== undefined ? values.load_t : 0)
        checkedNames = values && values.conditions ? values.conditions.slice() : conditionNames.slice()
        open()
    }

    function setChecked(name, on) {
        const kept = checkedNames.filter(n => n !== name)
        if (on)
            kept.push(name)
        // Document order, whatever order the boxes were ticked in.
        checkedNames = conditionNames.filter(n => kept.indexOf(n) >= 0)
    }

    function syncOk() {
        const ok = standardButton(Dialog.Ok)
        if (ok)
            ok.enabled = checkedNames.length > 0
    }

    title: editIndex < 0 ? qsTr("Add Load-Chart Point") : qsTr("Edit Load-Chart Point")
    modal: true
    anchors.centerIn: Overlay.overlay
    standardButtons: Dialog.Ok | Dialog.Cancel

    onCheckedNamesChanged: syncOk()
    onOpened: syncOk()
    onAccepted: committed(editIndex, {
        "outreach_m": outreachField.value,
        "load_t": loadField.value,
        "conditions": checkedNames
    })

    ColumnLayout {
        spacing: 8

        GridLayout {
            columns: 2
            columnSpacing: 8
            rowSpacing: 8

            Label { text: qsTr("Outreach (m):") }
            NumberField { id: outreachField; Layout.preferredWidth: 200 }

            Label { text: qsTr("Load (t):") }
            NumberField { id: loadField; Layout.preferredWidth: 200 }
        }

        Label {
            text: qsTr("Applies to conditions:")
        }

        Repeater {
            model: root.conditionNames

            CheckBox {
                required property string modelData

                objectName: "chartPointCondition_" + modelData
                text: modelData
                checked: root.checkedNames.indexOf(modelData) >= 0
                onToggled: {
                    root.setChecked(modelData, checked)
                    // Keep following the dialog's list, which the next openFor resets.
                    checked = Qt.binding(() => root.checkedNames.indexOf(modelData) >= 0)
                }
            }
        }
    }
}
