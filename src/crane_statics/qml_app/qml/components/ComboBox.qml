import QtQuick
import QtQuick.Controls.Fusion
import BF.DesignSystem

/**
 * ComboBox Component
 *
 * Reusable dropdown selector with consistent styling and token-based appearance.
 * Responds to enabled/disabled/hovered states.
 *
 * Usage:
 *   import Crane.Components 1.0
 *   ComboBox {
 *       model: ["Option A", "Option B", "Option C"]
 *       onCurrentIndexChanged: vm.selected = currentIndex
 *   }
 *
 * Design tokens used:
 * - sizing.inputHeight (32px)
 * - sizing.radiusSmall (2px border radius)
 * - colors.surface, border, primary, textPrimary
 * - spacing.sm (padding)
 * - typography.body
 */

ComboBox {
    id: root

    implicitHeight: Metrics.controlHeight
    implicitWidth: Metrics.minInputWidth

    palette.text: enabled ? Theme.text : Theme.disabledText
    palette.base: Theme.surface
    palette.mid: Theme.border
    palette.button: Theme.surfaceSubtle
    palette.highlight: Theme.primary
    palette.highlightedText: Theme.textOnDark

    font.pixelSize: Typography.body
    font.family: Typography.fontFamily

    Accessible.role: Accessible.ComboBox
    Accessible.name: currentText
    Accessible.description: "Dropdown selector"

    background: Rectangle {
        color: Theme.surface
        border.color: root.activeFocus ? Theme.focusRing : Theme.border
        border.width: root.activeFocus
            ? Metrics.borderWidthNormal
            : Metrics.borderWidth
        radius: Metrics.radiusSmall

        Behavior on border.color {
            ColorAnimation { duration: Metrics.transitionFast }
        }
    }

    contentItem: Text {
        text: root.displayText
        font: root.font
        color: root.palette.text
        horizontalAlignment: Text.AlignLeft
        verticalAlignment: Text.AlignVCenter
        leftPadding: Metrics.spacing8
        elide: Text.ElideRight
    }

    popup: Popup {
        y: root.height - Metrics.borderWidthNormal
        width: root.width
        implicitHeight: Math.min(
            Math.max(1, root.count) * Metrics.tableRowHeight,
            Metrics.tableRowHeight * 8
        )

        contentItem: ListView {
            objectName: "comboPopupList"
            implicitHeight: popup.implicitHeight
            clip: true
            // ComboBox.delegateModel is built from the top-level ComboBox.delegate,
            // which this component never sets (only the ListView's own delegate below),
            // so delegateModel always instantiates zero items. Bind directly to the data.
            model: root.model

            delegate: ItemDelegate {
                width: parent.width
                implicitHeight: Metrics.tableRowHeight
                padding: Metrics.spacing8
                hoverEnabled: true
                highlighted: hovered

                background: Rectangle {
                    color: highlighted ? Theme.primary : "transparent"
                }

                contentItem: Text {
                    text: modelData
                    font: root.font
                    color: highlighted ? Theme.textOnDark : Theme.text
                    verticalAlignment: Text.AlignVCenter
                }

                onClicked: {
                    if (index < 0 || index >= root.count)
                        return
                    root.currentIndex = index
                    root.activated(index)
                    root.popup.close()
                }
            }
        }

        background: Rectangle {
            color: Theme.surface
            border.color: Theme.border
            border.width: Metrics.borderWidth
            radius: Metrics.radiusSmall
        }
    }
}
