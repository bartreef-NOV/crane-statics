import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Effects
import QtQuick.Layouts
import QtQuick.Dialogs
import "../../design"
import "."

/**
 * Dialog Component
 *
 * Reusable base dialog/modal wrapper enforcing consistent title, footer, button,
 * and padding sizing. Extends Control.Dialog with token-aware styling.
 *
 * Usage:
 *   import Crane.Components 1.0
 *   Dialog {
 *       title: "Confirm Action"
 *       message: "Are you sure?"
 *       standardButtons: Dialog.Ok | Dialog.Cancel
 *       onAccepted: vm.confirm()
 *   }
 *
 * Design tokens used:
 * - colors.background, surfaceAlt, border
 * - sizing.radiusNormal, borderNormal
 * - spacing.dialogPadding, md
 * - typography.heading
 * - shadows.elevation3
 */

Dialog {
    id: root

    property string message: ""
    default property alias dialogContentData: contentColumn.data

    readonly property int viewportMargin: DesignTokens.spacing.lg
    readonly property real availableDialogWidth: Overlay.overlay
        ? Math.max(0, Overlay.overlay.width - 2 * viewportMargin)
        : DesignTokens.sizing.dialogWidth
    readonly property real availableDialogHeight: Overlay.overlay
        ? Math.max(0, Overlay.overlay.height - 2 * viewportMargin)
        : 1000000

    // Keep compact dialogs comfortable while preventing long forms from leaving the window.
    width: Math.min(
        availableDialogWidth,
        Math.max(
            DesignTokens.sizing.dialogWidth,
            contentColumn.implicitWidth + 2 * DesignTokens.spacing.dialogPadding
        )
    )
    height: Math.min(
        availableDialogHeight,
        Math.max(
            DesignTokens.sizing.buttonHeight * 3,
            header.implicitHeight + contentScroll.implicitHeight + footer.implicitHeight
        )
    )

    // Styling
    background: Rectangle {
        color: DesignTokens.colors.background
        border.color: DesignTokens.colors.border
        border.width: DesignTokens.sizing.borderNormal
        radius: DesignTokens.sizing.radiusNormal

        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: DesignTokens.shadows.getShadowColor()
            shadowBlur: 0.5
            shadowVerticalOffset: 4
        }
    }

    // Dialog overlay (semi-transparent background)
    Overlay.modal: Rectangle {
        color: DesignTokens.colors.overlay
    }

    // Header with title
    header: Rectangle {
        color: DesignTokens.colors.surfaceAlt
        implicitHeight: DesignTokens.sizing.buttonHeight + 2 * DesignTokens.spacing.md
        border.width: 0

        Text {
            anchors.fill: parent
            anchors.leftMargin: DesignTokens.spacing.dialogPadding
            anchors.rightMargin: DesignTokens.spacing.dialogPadding
            text: root.title
            font.pixelSize: DesignTokens.typography.heading
            font.weight: DesignTokens.typography.weightSemiBold
            color: DesignTokens.colors.textPrimary
            verticalAlignment: Text.AlignVCenter
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: DesignTokens.sizing.borderThin
            color: DesignTokens.colors.divider
        }
    }

    // Content area accepts either a message or arbitrary dialog content.
    contentItem: ScrollView {
        id: contentScroll
        clip: true
        implicitHeight: contentColumn.implicitHeight
            + topPadding + bottomPadding + 12
        contentWidth: availableWidth
        leftPadding: DesignTokens.spacing.dialogPadding
        rightPadding: DesignTokens.spacing.dialogPadding
        topPadding: DesignTokens.spacing.dialogPadding
        bottomPadding: DesignTokens.spacing.dialogPadding

        ColumnLayout {
            id: contentColumn
            width: contentScroll.width - contentScroll.leftPadding - contentScroll.rightPadding
            height: implicitHeight
            spacing: DesignTokens.spacing.sm

            Text {
                Layout.fillWidth: true
                text: root.message
                visible: root.message.length > 0
                font.pixelSize: DesignTokens.typography.body
                color: DesignTokens.colors.textPrimary
                wrapMode: Text.Wrap
            }
        }

        ScrollBar.vertical: ScrollBar {
            policy: contentScroll.contentHeight > contentScroll.availableHeight + 1
                ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
        }

        ScrollBar.horizontal: ScrollBar {
            policy: ScrollBar.AlwaysOff
        }
    }

    // Footer with buttons
    footer: DialogButtonBox {
        background: Rectangle {
            color: DesignTokens.colors.surfaceAlt
            border.width: 0

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: DesignTokens.sizing.borderThin
                color: DesignTokens.colors.divider
            }
        }

        // Style all buttons in footer
        delegate: Button {
            implicitHeight: DesignTokens.sizing.buttonHeight
            semantic: DialogButtonBox.buttonRole === DialogButtonBox.AcceptRole
                ? "primary" : "secondary"
        }

        padding: DesignTokens.spacing.md
        spacing: DesignTokens.spacing.controlGap
    }
}
