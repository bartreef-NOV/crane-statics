import QtQuick
import QtQuick.Controls.Fusion
import BF.DesignSystem

/**
 * TextField Component
 *
 * Reusable text input with consistent styling, error states, and validation.
 * Responds to enabled/disabled/focused/error states via design tokens.
 *
 * Usage:
 *   import Crane.Components 1.0
 *   TextField {
 *       placeholderText: "Enter name..."
 *       onAccepted: vm.name = text
 *   }
 *
 *   TextField {
 *       isError: !validator.isValid(text)
 *       errorText: "Invalid format"
 *   }
 *
 * Design tokens used:
 * - sizing.inputHeight (32px)
 * - sizing.radiusSmall (2px border radius)
 * - colors.surface, border, error, textPrimary, textDisabled
 * - spacing.sm (padding)
 */

TextField {
    id: root

    // Error state properties
    property bool isError: false
    property string errorText: ""

    implicitHeight: Metrics.controlHeight
    implicitWidth: Metrics.maxInputWidth

    palette.text: enabled ? Theme.text : Theme.disabledText
    palette.base: Theme.surface
    palette.mid: isError ? Theme.error : Theme.border
    palette.highlight: Theme.selection
    palette.highlightedText: Theme.selectionText

    font.pixelSize: Typography.body
    font.family: Typography.fontFamily

    selectByMouse: true
    padding: Metrics.spacing8

    Accessible.role: Accessible.EditableText
    Accessible.name: placeholderText
    Accessible.description: errorText

    background: Rectangle {
        color: Theme.surface
        border.color: root.isError
            ? Theme.error
            : (root.activeFocus ? Theme.focusRing : Theme.border)
        border.width: root.isError || root.activeFocus
            ? Metrics.borderWidthNormal
            : Metrics.borderWidth
        radius: Metrics.radiusSmall

        Behavior on border.color {
            ColorAnimation { duration: Metrics.transitionFast }
        }
    }
}
