import QtQuick
import QtQuick.Controls.Fusion
import "../design" as Design

TextField {
    id: field

    property int decimals: 3
    property bool flippable: false
    readonly property real value: parseFloat(text) || 0
    signal flipDirectionRequested()

    implicitHeight: Design.DesignTokens.sizing.inputHeight
    implicitWidth: Design.DesignTokens.sizing.maxInputWidth
    leftPadding: Design.DesignTokens.spacing.sm
    rightPadding: Design.DesignTokens.spacing.sm
    font.pixelSize: Design.DesignTokens.typography.body
    palette.text: enabled ? Design.DesignTokens.colors.textPrimary : Design.DesignTokens.colors.textDisabled
    palette.base: Design.DesignTokens.colors.surface
    palette.mid: activeFocus ? Design.DesignTokens.colors.focusRing : Design.DesignTokens.colors.border
    palette.highlight: Design.DesignTokens.colors.selection
    palette.highlightedText: Design.DesignTokens.colors.selectionText

    function setValue(newValue) {
        text = Number(newValue).toFixed(decimals)
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


