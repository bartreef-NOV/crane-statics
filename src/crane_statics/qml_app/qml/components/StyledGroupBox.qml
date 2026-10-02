import QtQuick
import QtQuick.Controls.Fusion
import BF.DesignSystem

GroupBox {
    id: root

    background: Rectangle {
        color: Theme.surface
        border.color: Theme.border
        border.width: Metrics.borderWidth
        radius: Metrics.radiusSmall
    }

    label: Label {
        text: root.title
        color: Theme.text
        font.pixelSize: Typography.body
        font.weight: Typography.weightSemiBold
        leftPadding: Metrics.spacing8
        rightPadding: Metrics.spacing8
    }
}
