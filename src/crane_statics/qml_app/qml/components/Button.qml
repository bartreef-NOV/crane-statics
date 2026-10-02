import QtQuick
import QtQuick.Controls.Fusion
import BF.DesignSystem

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

    implicitHeight: Metrics.controlHeight
    implicitWidth: Math.max(Metrics.buttonMinWidth, implicitContentWidth + 2 * Metrics.spacing16)

    Accessible.role: Accessible.Button
    Accessible.name: text
    Accessible.description: ""

    // Apply semantic colors based on button type and state
    palette.button: {
        if (!enabled) return Theme.primaryDisabled
        if (checked) return pressed ? Theme.primaryPressed : Theme.primary
        if (checkable)
            return hovered ? Theme.surface : Theme.surfaceSubtle
        switch (semantic) {
            case "danger":
                return pressed ? Theme.error : (hovered ? Qt.darker(Theme.error, 1.15) : Theme.error)
            case "secondary":
                return hovered || pressed
                    ? Theme.surfaceSubtle
                    : Theme.surface
            case "primary":
            default:
                return pressed ? Theme.primaryPressed : (hovered ? Theme.primaryHover : Theme.primary)
        }
    }

    palette.buttonText: checked || (!checkable && semantic !== "secondary")
        ? Theme.textOnDark : Theme.text

    background: Rectangle {
        implicitHeight: Metrics.controlHeight
        color: root.palette.button
        radius: Metrics.radiusSmall
        border.color: root.activeFocus || root.checked
            ? Theme.focusRing
            : (root.semantic === "secondary" || root.checkable
                ? Theme.border : "transparent")
        border.width: root.activeFocus || root.checked || root.semantic === "secondary" || root.checkable
            ? Metrics.borderWidth : 0

        Behavior on color {
            ColorAnimation { duration: Metrics.transitionFast }
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
