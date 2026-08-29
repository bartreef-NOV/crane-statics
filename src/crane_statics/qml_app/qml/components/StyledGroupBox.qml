import QtQuick
import QtQuick.Controls.Fusion
import "../../design"

GroupBox {
    id: root

    background: Rectangle {
        color: DesignTokens.colors.surface
        border.color: DesignTokens.colors.border
        border.width: DesignTokens.sizing.borderThin
        radius: DesignTokens.sizing.radiusSmall
    }

    label: Label {
        text: root.title
        color: DesignTokens.colors.textPrimary
        font.pixelSize: DesignTokens.typography.body
        font.weight: DesignTokens.typography.weightSemiBold
        leftPadding: DesignTokens.spacing.sm
        rightPadding: DesignTokens.spacing.sm
    }
}