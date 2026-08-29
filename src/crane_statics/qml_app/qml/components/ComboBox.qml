import QtQuick
import QtQuick.Controls.Fusion
import "../../design"

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

    implicitHeight: DesignTokens.sizing.inputHeight
    implicitWidth: DesignTokens.sizing.minInputWidth

    palette.text: enabled ? DesignTokens.colors.textPrimary : DesignTokens.colors.textDisabled
    palette.base: DesignTokens.colors.surface
    palette.mid: DesignTokens.colors.border
    palette.button: DesignTokens.colors.surfaceAlt
    palette.highlight: DesignTokens.colors.primary
    palette.highlightedText: DesignTokens.colors.textInverse

    font.pixelSize: DesignTokens.typography.body
    font.family: DesignTokens.typography.fontFamily

    Accessible.role: Accessible.ComboBox
    Accessible.name: currentText
    Accessible.description: "Dropdown selector"

    background: Rectangle {
        color: DesignTokens.colors.surface
        border.color: root.activeFocus ? DesignTokens.colors.focusRing : DesignTokens.colors.border
        border.width: root.activeFocus
            ? DesignTokens.sizing.borderNormal
            : DesignTokens.sizing.borderThin
        radius: DesignTokens.sizing.radiusSmall

        Behavior on border.color {
            ColorAnimation { duration: DesignTokens.transitions.fast }
        }
    }

    contentItem: Text {
        text: root.displayText
        font: root.font
        color: root.palette.text
        horizontalAlignment: Text.AlignLeft
        verticalAlignment: Text.AlignVCenter
        leftPadding: DesignTokens.spacing.sm
        elide: Text.ElideRight
    }

    popup: Popup {
        y: root.height - DesignTokens.sizing.borderNormal
        width: root.width
        implicitHeight: Math.min(
            Math.max(1, root.count) * DesignTokens.sizing.rowHeight,
            DesignTokens.sizing.rowHeight * 8
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
                implicitHeight: DesignTokens.sizing.rowHeight
                padding: DesignTokens.spacing.sm
                hoverEnabled: true
                highlighted: hovered

                background: Rectangle {
                    color: highlighted ? DesignTokens.colors.primary : "transparent"
                }

                contentItem: Text {
                    text: modelData
                    font: root.font
                    color: highlighted ? DesignTokens.colors.textInverse : DesignTokens.colors.textPrimary
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
            color: DesignTokens.colors.surface
            border.color: DesignTokens.colors.border
            border.width: DesignTokens.sizing.borderThin
            radius: DesignTokens.sizing.radiusSmall
        }
    }
}
