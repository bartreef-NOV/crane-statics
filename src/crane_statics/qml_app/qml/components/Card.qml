import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Effects
import QtQuick.Layouts
import "../../design"

/**
 * Card Component
 *
 * Elevated container for grouping related content. Provides consistent padding,
 * border styling, and optional shadow elevation.
 *
 * Usage:
 *   import Crane.Components 1.0
 *   Card {
 *       contentItem: ColumnLayout {
 *           Label { text: "Card content here" }
 *       }
 *   }
 *
 * Design tokens used:
 * - colors.surface (background)
 * - colors.border (border)
 * - sizing.radiusNormal (8px border radius)
 * - sizing.borderThin (1px border)
 * - spacing.panelPadding (12px padding)
 * - shadows.elevation2 (card shadow)
 */

Rectangle {
    id: root

    // Optional content to embed in the card
    property Component contentItem: null

    color: DesignTokens.colors.surface
    radius: DesignTokens.sizing.radiusNormal
    border.color: DesignTokens.colors.border
    border.width: DesignTokens.sizing.borderThin

    // Elevation shadow (optional, can be disabled)
    layer.enabled: true
    layer.effect: MultiEffect {
        shadowEnabled: true
        shadowColor: DesignTokens.shadows.getShadowColor()
        shadowBlur: 0.35
        shadowVerticalOffset: 2
    }

    Accessible.role: Accessible.Section
    Accessible.name: "Card container"

    // Default: fill with padding
    anchors.margins: 0

    Loader {
        visible: root.contentItem !== null
        anchors.fill: parent
        anchors.margins: DesignTokens.spacing.panelPadding
        sourceComponent: root.contentItem
    }
}
