import QtQuick
import QtQuick.Controls.Fusion
import BF.DesignSystem

RadioButton {
    id: root

    implicitHeight: Metrics.controlHeight
    implicitWidth: indicator.implicitWidth + spacing + label.implicitWidth
    spacing: Metrics.spacing8
    leftPadding: Metrics.iconNormal + Metrics.spacing8
    rightPadding: 0

    background: Item {}

    Accessible.role: Accessible.RadioButton
    Accessible.name: text

    indicator: Rectangle {
        id: indicator
        implicitWidth: Metrics.iconNormal
        implicitHeight: Metrics.iconNormal
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        radius: width / 2
        color: Theme.surface
        border.width: root.activeFocus ? Metrics.borderWidthNormal : Metrics.borderWidth
        border.color: root.activeFocus
            ? Theme.focusRing
            : (root.enabled ? Theme.border : Theme.borderSubtle)

        Rectangle {
            anchors.centerIn: parent
            width: 10
            height: 10
            radius: width / 2
            color: Theme.primary
            visible: root.checked
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
