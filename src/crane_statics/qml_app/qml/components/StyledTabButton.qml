import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import BF.DesignSystem

TabButton {
    id: root

    property bool fillWidth: false

    implicitHeight: Math.round(Metrics.controlHeight * 1.125)
    implicitWidth: Math.max(
        Metrics.buttonMinWidth,
        implicitContentWidth + 2 * Metrics.spacing16
    )
    width: fillWidth && parent ? parent.width / Math.max(1, parent.count) : implicitWidth
    Layout.fillWidth: fillWidth
    padding: Metrics.spacing8

    Accessible.role: Accessible.PageTab
    Accessible.name: text

    contentItem: Text {
        text: root.text
        font: root.font
        color: root.checked
            ? Theme.primary
            : (root.enabled ? Theme.text : Theme.disabledText)
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        color: root.checked
            ? Theme.surface
            : (root.hovered || root.activeFocus ? Theme.surfaceSubtle : "transparent")
        border.color: root.checked ? Theme.primary : "transparent"
        border.width: root.checked ? Metrics.borderWidthNormal : 0
        radius: Metrics.radiusSmall

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: Metrics.borderWidthNormal
            color: Theme.primary
            visible: root.checked
        }

        Behavior on color {
            ColorAnimation { duration: Metrics.transitionFast }
        }
    }
}
