import QtQuick
import QtQuick.Controls.Fusion
import BF.DesignSystem

CheckBox {
    id: root

    implicitHeight: Metrics.controlHeight
    implicitWidth: indicator.implicitWidth + spacing + label.implicitWidth
    spacing: Metrics.spacing8
    leftPadding: Metrics.iconNormal + Metrics.spacing8
    rightPadding: 0

    background: Item {}

    Accessible.role: Accessible.CheckBox
    Accessible.name: text

    indicator: Rectangle {
        id: indicator
        implicitWidth: Metrics.iconNormal
        implicitHeight: Metrics.iconNormal
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        radius: Metrics.radiusSmall
        color: root.checked ? Theme.primary : Theme.surface
        border.width: root.activeFocus ? Metrics.borderWidthNormal : Metrics.borderWidth
        border.color: root.activeFocus
            ? Theme.focusRing
            : (root.enabled ? Theme.border : Theme.borderSubtle)

        Text {
            anchors.centerIn: parent
            text: "\u2713"
            font.pixelSize: Typography.bodyLarge
            font.weight: Typography.weightBold
            color: Theme.textOnDark
            visible: root.checked
        }

        Behavior on color {
            ColorAnimation { duration: Metrics.transitionFast }
        }
    }

    contentItem: Text {
        id: label
        text: root.text
        font: root.font
        color: root.enabled ? Theme.text : Theme.disabledText
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
}
