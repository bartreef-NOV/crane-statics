import QtQuick
import QtQuick.Controls.Fusion
import "../../design"

RadioButton {
    id: root

    implicitHeight: DesignTokens.sizing.inputHeight
    implicitWidth: indicator.implicitWidth + spacing + label.implicitWidth
    spacing: DesignTokens.spacing.sm
    leftPadding: DesignTokens.sizing.iconNormal + DesignTokens.spacing.sm
    rightPadding: 0

    background: Item {}

    Accessible.role: Accessible.RadioButton
    Accessible.name: text

    indicator: Rectangle {
        id: indicator
        implicitWidth: DesignTokens.sizing.iconNormal
        implicitHeight: DesignTokens.sizing.iconNormal
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        radius: width / 2
        color: DesignTokens.colors.surface
        border.width: root.activeFocus ? DesignTokens.sizing.borderNormal : DesignTokens.sizing.borderThin
        border.color: root.activeFocus
            ? DesignTokens.colors.focusRing
            : (root.enabled ? DesignTokens.colors.border : DesignTokens.colors.borderLight)

        Rectangle {
            anchors.centerIn: parent
            width: 10
            height: 10
            radius: width / 2
            color: DesignTokens.colors.primary
            visible: root.checked
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
