import QtQuick
import QtQuick.Controls.Fusion
import "../design" as Design

Item {
    id: delegateRoot

    required property string name
    required property string unit
    required property string demand
    required property string limit
    required property string utilization
    required property real utilizationValue
    required property string utilState
    required property bool isGroupHeader
    required property bool nested
    required property bool clickable
    required property string tooltip
    required property int index

    property real nameWidth: 120

    readonly property color barColor: Design.DesignTokens.colors.primary
    readonly property color barTrackColor: Design.DesignTokens.colors.borderLight
    readonly property color surfaceColor: Design.DesignTokens.colors.surface
    readonly property color alternateSurfaceColor: Design.DesignTokens.colors.surfaceAlt
    readonly property color textColor: Design.DesignTokens.colors.textPrimary

    readonly property real cellWidth: (width - nameWidth) / 5

    signal barClicked()

    implicitHeight: Design.DesignTokens.sizing.rowHeightCompact
    height: Design.DesignTokens.sizing.rowHeightCompact

    Rectangle {
        anchors.fill: parent
        color: delegateRoot.index % 2 === 0
            ? delegateRoot.surfaceColor : delegateRoot.alternateSurfaceColor
        border.color: delegateRoot.barTrackColor
        border.width: Design.DesignTokens.sizing.borderThin
        visible: !delegateRoot.isGroupHeader
    }

    Label {
        visible: delegateRoot.isGroupHeader
        anchors.fill: parent
        anchors.leftMargin: Design.DesignTokens.spacing.compact + (delegateRoot.nested ? Design.DesignTokens.spacing.sm : 0)
        text: delegateRoot.name
        color: delegateRoot.textColor
        font.bold: true
        font.italic: delegateRoot.nested
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    Row {
        visible: !delegateRoot.isGroupHeader
        anchors.fill: parent
        spacing: 0

        Label {
            width: delegateRoot.nameWidth
            height: parent.height
            leftPadding: Design.DesignTokens.spacing.compact
            text: delegateRoot.name
            color: delegateRoot.textColor
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight

            ToolTip.visible: hoverHandler.hovered && delegateRoot.tooltip.length > 0
            ToolTip.text: delegateRoot.tooltip
            HoverHandler { id: hoverHandler }

            Rectangle {
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.right: parent.right
                width: Design.DesignTokens.sizing.borderThin
                color: delegateRoot.barTrackColor
            }
        }

        Label {
            width: delegateRoot.cellWidth
            height: parent.height
            leftPadding: Design.DesignTokens.spacing.compact
            text: delegateRoot.unit
            color: delegateRoot.textColor
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight

            Rectangle {
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.right: parent.right
                width: Design.DesignTokens.sizing.borderThin
                color: delegateRoot.barTrackColor
            }
        }

        Label {
            width: delegateRoot.cellWidth
            height: parent.height
            rightPadding: Design.DesignTokens.spacing.compact
            text: delegateRoot.demand
            color: delegateRoot.textColor
            horizontalAlignment: Text.AlignRight
            verticalAlignment: Text.AlignVCenter

            Rectangle {
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.right: parent.right
                width: Design.DesignTokens.sizing.borderThin
                color: delegateRoot.barTrackColor
            }
        }

        Label {
            width: delegateRoot.cellWidth
            height: parent.height
            rightPadding: Design.DesignTokens.spacing.compact
            text: delegateRoot.limit
            color: delegateRoot.textColor
            horizontalAlignment: Text.AlignRight
            verticalAlignment: Text.AlignVCenter

            Rectangle {
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.right: parent.right
                width: Design.DesignTokens.sizing.borderThin
                color: delegateRoot.barTrackColor
            }
        }

        Label {
            width: delegateRoot.cellWidth
            height: parent.height
            rightPadding: Design.DesignTokens.spacing.compact
            text: delegateRoot.utilization
            color: delegateRoot.textColor
            horizontalAlignment: Text.AlignRight
            verticalAlignment: Text.AlignVCenter

            Rectangle {
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.right: parent.right
                width: Design.DesignTokens.sizing.borderThin
                color: delegateRoot.barTrackColor
            }
        }

        Item {
            width: delegateRoot.cellWidth
            height: parent.height

            Rectangle {
                id: barTrack
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.leftMargin: Design.DesignTokens.spacing.compact
                anchors.rightMargin: Design.DesignTokens.spacing.compact
                height: 10
                radius: Design.DesignTokens.sizing.radiusNormal
                border.width: Design.DesignTokens.sizing.borderThin
                border.color: delegateRoot.barTrackColor

                Rectangle {
                    height: parent.height
                    width: parent.width * Math.max(0, Math.min(100, delegateRoot.utilizationValue)) / 100
                    radius: Design.DesignTokens.sizing.radiusNormal
                    color: delegateRoot.barColor
                }

                TapHandler {
                    enabled: delegateRoot.clickable
                    onTapped: delegateRoot.barClicked()
                }

                ToolTip.visible: barHover.hovered && delegateRoot.clickable
                ToolTip.text: qsTr("Click to view load-contribution overview")
                HoverHandler { id: barHover }
            }
        }
    }
}


