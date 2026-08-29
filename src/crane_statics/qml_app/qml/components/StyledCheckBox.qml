import QtQuick
import QtQuick.Controls.Fusion
import "../../design"

CheckBox {
    id: root

    implicitHeight: DesignTokens.sizing.inputHeight
    implicitWidth: indicator.implicitWidth + spacing + label.implicitWidth
    spacing: DesignTokens.spacing.sm
    leftPadding: DesignTokens.sizing.iconNormal + DesignTokens.spacing.sm
    rightPadding: 0

    background: Item {}

    Accessible.role: Accessible.CheckBox
    Accessible.name: text

    indicator: Rectangle {
        id: indicator
        implicitWidth: DesignTokens.sizing.iconNormal
        implicitHeight: DesignTokens.sizing.iconNormal
        x: 0
        y: (root.height - height) / 2
        radius: DesignTokens.sizing.radiusSmall
        color: root.checked ? DesignTokens.colors.primary : DesignTokens.colors.surface
        border.width: root.activeFocus ? DesignTokens.sizing.borderNormal : DesignTokens.sizing.borderThin
        border.color: root.activeFocus
            ? DesignTokens.colors.focusRing
            : (root.enabled ? DesignTokens.colors.border : DesignTokens.colors.borderLight)

        Text {
            anchors.centerIn: parent
            text: "\u2713"
            font.pixelSize: DesignTokens.typography.bodyLarge
            font.weight: DesignTokens.typography.weightBold
            color: DesignTokens.colors.textInverse
            visible: root.checked
        }

        Behavior on color {
            ColorAnimation { duration: DesignTokens.transitions.fast }
        }
    }

    contentItem: Text {
        id: label
        text: root.text
        font: root.font
        color: root.enabled ? DesignTokens.colors.textPrimary : DesignTokens.colors.textDisabled
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
}
