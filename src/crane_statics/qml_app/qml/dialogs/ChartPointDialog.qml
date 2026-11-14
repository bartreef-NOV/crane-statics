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
    // The point as opened (null for a new one): untouched fields submit these values.
    property var original: null

    signal committed(int index, var fields)

    function openFor(index, values) {
        editIndex = index
        original = values ? {
            "outreach_m": values.outreach_m !== undefined ? values.outreach_m : 0,
            "load_t": values.load_t !== undefined ? values.load_t : 0,
            "conditions": values.conditions ? values.conditions.slice() : conditionNames.slice()
        } : null
        outreachField.setValue(original ? original.outreach_m : 0)
        loadField.setValue(original ? original.load_t : 0)
        checkedNames = original ? original.conditions.slice() : conditionNames.slice()
        open()
    }

    // A field's value: the opened one while its text still shows it (so a value with
    // more decimals than the field shows is not rounded), else what was typed.
    function fieldValue(field, value) {
        if (original === null)
            return field.value
        const text = field.text.trim()
        if (text === Number(value).toFixed(field.decimals) || Number(text) === Number(value))
            return value
        return field.value
    }

    function submit() {
        const fields = {
            "outreach_m": fieldValue(outreachField, original ? original.outreach_m : 0),
            "load_t": fieldValue(loadField, original ? original.load_t : 0),
            "conditions": checkedNames
        }
        // Nothing changed: no edit (and no undo step).
        if (editIndex >= 0 && original !== null && fields.outreach_m === original.outreach_m
                && fields.load_t === original.load_t
                && JSON.stringify(fields.conditions) === JSON.stringify(original.conditions))
            return
        committed(editIndex, fields)
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
    onAccepted: submit()

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
