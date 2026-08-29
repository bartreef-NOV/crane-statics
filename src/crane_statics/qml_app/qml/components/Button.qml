import QtQuick
import QtQuick.Controls.Fusion
import "../../design"

/**
 * Button Component
 *
 * Reusable button with consistent styling, semantic colors, and states.
 * Automatically responds to enabled/disabled/hovered/pressed states.
 *
 * Usage:
 *   import Crane.Components 1.0
 *   Button {
 *       text: "Save"
 *       onClicked: vm.save()
 *   }
 *
 * Design tokens used:
 * - sizing.buttonHeight (32px)
 * - colors.primary, primaryHover, primaryPressed, primaryDisabled
 * - colors.textInverse
 * - spacing.md (content padding)
 */

Button {
    id: root

    // Semantic button type: "primary" | "secondary" | "danger"
    property string semantic: "primary"

    implicitHeight: DesignTokens.sizing.buttonHeight
    implicitWidth: Math.max(DesignTokens.sizing.minButtonWidth, implicitContentWidth + 2 * DesignTokens.spacing.md)

    Accessible.role: Accessible.Button
    Accessible.name: text
    Accessible.description: ""

    // Apply semantic colors based on button type and state
    palette.button: {
        if (!enabled) return DesignTokens.colors.primaryDisabled
        if (checked) return pressed ? DesignTokens.colors.primaryPressed : DesignTokens.colors.primary
        if (checkable)
            return hovered ? DesignTokens.colors.surface : DesignTokens.colors.surfaceAlt
        switch (semantic) {
            case "danger":
                return pressed ? DesignTokens.colors.error : (hovered ? Qt.darker(DesignTokens.colors.error, 1.15) : DesignTokens.colors.error)
            case "secondary":
                return hovered || pressed
                    ? DesignTokens.colors.surfaceAlt
                    : DesignTokens.colors.surface
            case "primary":
            default:
                return pressed ? DesignTokens.colors.primaryPressed : (hovered ? DesignTokens.colors.primaryHover : DesignTokens.colors.primary)
        }
    }

    palette.buttonText: checked || (!checkable && semantic !== "secondary")
        ? DesignTokens.colors.textInverse : DesignTokens.colors.textPrimary

    background: Rectangle {
        implicitHeight: DesignTokens.sizing.buttonHeight
        color: root.palette.button
        radius: DesignTokens.sizing.radiusSmall
        border.color: root.activeFocus || root.checked
            ? DesignTokens.colors.focusRing
            : (root.semantic === "secondary" || root.checkable
                ? DesignTokens.colors.border : "transparent")
        border.width: root.activeFocus || root.checked || root.semantic === "secondary" || root.checkable
            ? DesignTokens.sizing.borderThin : 0

        Behavior on color {
            ColorAnimation { duration: DesignTokens.transitions.fast }
        }
    }

    contentItem: Text {
        text: root.text
        font: root.font
        color: root.palette.buttonText
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
}
