import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import BF.DesignSystem

/**
 * Badge Component
 *
 * Small status indicator with semantic colors (success, warning, error, info).
 * Useful for status labels, tags, and indicators.
 *
 * Usage:
 *   import Crane.Components 1.0
 *   Badge {
 *       text: "Active"
 *       semantic: "success"
 *   }
 *
 * Design tokens used:
 * - sizing.buttonHeightSmall (24px)
 * - sizing.radiusRound (20px, for pill shape)
 * - colors.success/warning/error/info (background colors)
 * - colors.textInverse (white text)
 * - typography.caption
 * - spacing.sm (padding)
 */

Rectangle {
    id: root

    // Badge semantic type: "success" | "warning" | "error" | "info" | "primary"
    property string semantic: "primary"
    property alias text: label.text

    implicitWidth: label.implicitWidth + 2 * Metrics.spacing8
    implicitHeight: Metrics.spacing24

    color: Theme.getSemanticColor(semantic)
    radius: height / 2

    Accessible.role: Accessible.StaticText
    Accessible.name: label.text
    Accessible.description: "Status badge: " + semantic

    Text {
        id: label

        anchors.centerIn: parent
        font.pixelSize: Typography.caption
        font.weight: Typography.weightMedium
        color: Theme.textOnDark
    }
}
