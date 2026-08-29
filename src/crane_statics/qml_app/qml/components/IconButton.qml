import QtQuick
import QtQuick.Controls.Fusion
import "../../design"
import "."

Button {
    id: root

    property string iconText: ""
    property string tooltipText: ""

    implicitWidth: DesignTokens.sizing.buttonHeight
    implicitHeight: DesignTokens.sizing.buttonHeight
    padding: 0

    Accessible.name: tooltipText
    Accessible.description: tooltipText

    ToolTip.visible: hovered && tooltipText.length > 0
    ToolTip.text: tooltipText

    contentItem: Text {
        text: root.iconText
        font.pixelSize: DesignTokens.typography.bodyLarge
        font.weight: DesignTokens.typography.weightMedium
        color: root.palette.buttonText
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
}
