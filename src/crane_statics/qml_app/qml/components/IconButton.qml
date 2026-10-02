import QtQuick
import QtQuick.Controls.Fusion
import BF.DesignSystem
import "."

Button {
    id: root

    property string iconText: ""
    property string tooltipText: ""

    implicitWidth: Metrics.controlHeight
    implicitHeight: Metrics.controlHeight
    padding: 0

    Accessible.name: tooltipText
    Accessible.description: tooltipText

    ToolTip.visible: hovered && tooltipText.length > 0
    ToolTip.text: tooltipText

    contentItem: Text {
        text: root.iconText
        font.pixelSize: Typography.bodyLarge
        font.weight: Typography.weightMedium
        color: root.palette.buttonText
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
}
