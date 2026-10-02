import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Effects
import QtQuick.Layouts
import QtQuick.Dialogs
import BF.DesignSystem
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

    readonly property int viewportMargin: Metrics.spacing24
    readonly property real availableDialogWidth: Overlay.overlay
        ? Math.max(0, Overlay.overlay.width - 2 * viewportMargin)
        : Metrics.dialogWidth
    readonly property real availableDialogHeight: Overlay.overlay
        ? Math.max(0, Overlay.overlay.height - 2 * viewportMargin)
        : 1000000

    // Keep compact dialogs comfortable while preventing long forms from leaving the window.
    width: Math.min(
        availableDialogWidth,
        Math.max(
            Metrics.dialogWidth,
            contentColumn.implicitWidth + 2 * Metrics.spacing16
        )
    )
    height: Math.min(
        availableDialogHeight,
        Math.max(
            Metrics.controlHeight * 3,
            header.implicitHeight + contentScroll.implicitHeight + footer.implicitHeight
        )
    )

    // Styling
    background: Rectangle {
        color: Theme.pageBackground
        border.color: Theme.border
        border.width: Metrics.borderWidthNormal
        radius: Metrics.radiusMedium

        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: Theme.shadowColor
            shadowBlur: 0.5
            shadowVerticalOffset: 4
        }
    }

    // Dialog overlay (semi-transparent background)
    Overlay.modal: Rectangle {
        color: Theme.overlay
    }

    // Header with title
    header: Rectangle {
        color: Theme.surfaceSubtle
        implicitHeight: Metrics.controlHeight + 2 * Metrics.spacing16
        border.width: 0

        Text {
            anchors.fill: parent
            anchors.leftMargin: Metrics.spacing16
            anchors.rightMargin: Metrics.spacing16
            text: root.title
            font.pixelSize: Typography.heading
            font.weight: Typography.weightSemiBold
            color: Theme.text
            verticalAlignment: Text.AlignVCenter
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: Metrics.borderWidth
            color: Theme.borderSubtle
        }
    }

    // Content area accepts either a message or arbitrary dialog content.
    contentItem: ScrollView {
        id: contentScroll
        clip: true
        implicitHeight: contentColumn.implicitHeight
            + topPadding + bottomPadding + 12
        contentWidth: availableWidth
        leftPadding: Metrics.spacing16
        rightPadding: Metrics.spacing16
        topPadding: Metrics.spacing16
        bottomPadding: Metrics.spacing16

        ColumnLayout {
            id: contentColumn
            width: contentScroll.width - contentScroll.leftPadding - contentScroll.rightPadding
            height: implicitHeight
            spacing: Metrics.spacing8

            Text {
                Layout.fillWidth: true
                text: root.message
                visible: root.message.length > 0
                font.pixelSize: Typography.body
                color: Theme.text
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
            color: Theme.surfaceSubtle
            border.width: 0

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: Metrics.borderWidth
                color: Theme.borderSubtle
            }
        }

        // Style all buttons in footer
        delegate: Button {
            implicitHeight: Metrics.controlHeight
            semantic: DialogButtonBox.buttonRole === DialogButtonBox.AcceptRole
                ? "primary" : "secondary"
        }

        padding: Metrics.spacing16
        spacing: Metrics.spacing8
    }
}
