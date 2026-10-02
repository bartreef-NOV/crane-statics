import QtQuick
import QtQuick.Controls.Fusion
import BF.DesignSystem

TextField {
    id: field

    property int decimals: 3
    property bool flippable: false
    readonly property real value: parseFloat(text) || 0
    signal flipDirectionRequested()

    implicitHeight: Metrics.controlHeight
    implicitWidth: Metrics.maxInputWidth
    leftPadding: Metrics.spacing8
    rightPadding: Metrics.spacing8
    font.pixelSize: Typography.body
    palette.text: enabled ? Theme.text : Theme.disabledText
    palette.base: Theme.surface
    palette.mid: activeFocus ? Theme.focusRing : Theme.border
    palette.highlight: Theme.selection
    palette.highlightedText: Theme.selectionText

    function setValue(newValue) {
        text = Number(newValue).toFixed(decimals)
    }

    function clear() {
        text = ""
    }

    text: "0.000"
    horizontalAlignment: TextInput.AlignRight
    selectByMouse: true
    validator: DoubleValidator { notation: DoubleValidator.StandardNotation }

    Action {
        id: flipDirectionAction
        text: qsTr("&Flip Direction")
        shortcut: "F"
        enabled: field.flippable
        onTriggered: field.flipDirectionRequested()
    }

    ContextMenu.menu: Menu {
        MenuItem {
            text: qsTr("Undo")
            enabled: field.canUndo
            onTriggered: field.undo()
        }
        MenuItem {
            text: qsTr("Redo")
            enabled: field.canRedo
            onTriggered: field.redo()
        }
        MenuSeparator {}
        MenuItem {
            text: qsTr("Cut")
            enabled: field.selectedText.length > 0
            onTriggered: field.cut()
        }
        MenuItem {
            text: qsTr("Copy")
            enabled: field.selectedText.length > 0
            onTriggered: field.copy()
        }
        MenuItem {
            text: qsTr("Paste")
            onTriggered: field.paste()
        }
        MenuItem {
            text: qsTr("Select All")
            enabled: field.length > 0
            onTriggered: field.selectAll()
        }
        MenuItem {
            visible: field.flippable
            height: field.flippable ? implicitHeight : 0
            text: qsTr("&Flip Direction")
            onTriggered: field.flipDirectionRequested()
        }
    }
}


