import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import BF.DesignSystem

/**
 * Section Component
 *
 * Titled container for grouping related form fields or content sections.
 * Provides consistent spacing and typography for section titles.
 *
 * Usage:
 *   import Crane.Components 1.0
 *   Section {
 *       title: "Model Parameters"
 *       contentItem: ColumnLayout {
 *           // form fields here
 *       }
 *   }
 *
 * Design tokens used:
 * - typography.heading (16px)
 * - typography.weightSemiBold (600)
 * - colors.textPrimary
 * - colors.border (separator line)
 * - spacing.md (spacing around content)
 */

ColumnLayout {
    id: root

    // Section title text
    property string title: ""

    // Content to embed in the section
    property Component contentItem: null

    spacing: Metrics.spacing16

    Accessible.role: Accessible.Section
    Accessible.name: title

    // Title
    Text {
        visible: root.title.length > 0
        text: root.title
        font.pixelSize: Typography.heading
        font.weight: Typography.weightSemiBold
        color: Theme.text

        Layout.fillWidth: true
    }

    // Separator line
    Rectangle {
        visible: root.title.length > 0
        Layout.fillWidth: true
        implicitHeight: Metrics.borderWidth
        color: Theme.border
    }

    // Content
    Loader {
        Layout.fillWidth: true
        Layout.fillHeight: true
        visible: root.contentItem !== null
        sourceComponent: root.contentItem
    }
}
