import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import "../../design"

TabButton {
    id: root

    property bool fillWidth: false

    implicitHeight: Math.round(DesignTokens.sizing.inputHeight * 1.125)
    implicitWidth: Math.max(
        DesignTokens.sizing.minButtonWidth,
        implicitContentWidth + 2 * DesignTokens.spacing.md
    )
    width: fillWidth && parent ? parent.width / Math.max(1, parent.count) : implicitWidth
    Layout.fillWidth: fillWidth
    padding: DesignTokens.spacing.sm

    Accessible.role: Accessible.PageTab
    Accessible.name: text

    contentItem: Text {
        text: root.text
        font: root.font
        color: root.checked
            ? DesignTokens.colors.primary
            : (root.enabled ? DesignTokens.colors.textPrimary : DesignTokens.colors.textDisabled)
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        color: root.checked
            ? DesignTokens.colors.surface
            : (root.hovered || root.activeFocus ? DesignTokens.colors.surfaceAlt : "transparent")
        border.color: root.checked ? DesignTokens.colors.primary : "transparent"
        border.width: root.checked ? DesignTokens.sizing.borderNormal : 0
        radius: DesignTokens.sizing.radiusSmall

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: DesignTokens.sizing.borderNormal
            color: DesignTokens.colors.primary
            visible: root.checked
        }

        Behavior on color {
            ColorAnimation { duration: DesignTokens.transitions.fast }
        }
    }
}
