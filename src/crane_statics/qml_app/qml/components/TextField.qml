import QtQuick
import QtQuick.Controls.Fusion
import "../../design"

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

    implicitHeight: DesignTokens.sizing.inputHeight
    implicitWidth: DesignTokens.sizing.maxInputWidth

    palette.text: enabled ? DesignTokens.colors.textPrimary : DesignTokens.colors.textDisabled
    palette.base: DesignTokens.colors.surface
    palette.mid: isError ? DesignTokens.colors.error : DesignTokens.colors.border
    palette.highlight: DesignTokens.colors.selection
    palette.highlightedText: DesignTokens.colors.selectionText

    font.pixelSize: DesignTokens.typography.body
    font.family: DesignTokens.typography.fontFamily

    selectByMouse: true
    padding: DesignTokens.spacing.sm

    Accessible.role: Accessible.EditableText
    Accessible.name: placeholderText
    Accessible.description: errorText

    background: Rectangle {
        color: DesignTokens.colors.surface
        border.color: root.isError
            ? DesignTokens.colors.error
            : (root.activeFocus ? DesignTokens.colors.focusRing : DesignTokens.colors.border)
        border.width: root.isError || root.activeFocus
            ? DesignTokens.sizing.borderNormal
            : DesignTokens.sizing.borderThin
        radius: DesignTokens.sizing.radiusSmall

        Behavior on border.color {
            ColorAnimation { duration: DesignTokens.transitions.fast }
        }
    }
}
