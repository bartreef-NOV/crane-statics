import QtQuick
import QtQuick.Controls.Fusion
import BF.DesignSystem

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

    readonly property color barColor: Theme.primary
    readonly property color barTrackColor: Theme.borderSubtle
    readonly property color surfaceColor: Theme.surface
    readonly property color alternateSurfaceColor: Theme.surfaceSubtle
    readonly property color textColor: Theme.text

    readonly property real cellWidth: (width - nameWidth) / 5

    signal barClicked()

    implicitHeight: Metrics.compactRowHeight
    height: Metrics.compactRowHeight

    Rectangle {
        anchors.fill: parent
        color: delegateRoot.index % 2 === 0
            ? delegateRoot.surfaceColor : delegateRoot.alternateSurfaceColor
        border.color: delegateRoot.barTrackColor
        border.width: Metrics.borderWidth
        visible: !delegateRoot.isGroupHeader
    }

    Label {
        visible: delegateRoot.isGroupHeader
        anchors.fill: parent
        anchors.leftMargin: Metrics.spacing6 + (delegateRoot.nested ? Metrics.spacing8 : 0)
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
            leftPadding: Metrics.spacing6
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
                width: Metrics.borderWidth
                color: delegateRoot.barTrackColor
            }
        }

        Label {
            width: delegateRoot.cellWidth
            height: parent.height
            leftPadding: Metrics.spacing6
            text: delegateRoot.unit
            color: delegateRoot.textColor
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight

            Rectangle {
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.right: parent.right
                width: Metrics.borderWidth
                color: delegateRoot.barTrackColor
            }
        }

        Label {
            width: delegateRoot.cellWidth
            height: parent.height
            rightPadding: Metrics.spacing6
            text: delegateRoot.demand
            color: delegateRoot.textColor
            horizontalAlignment: Text.AlignRight
            verticalAlignment: Text.AlignVCenter

            Rectangle {
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.right: parent.right
                width: Metrics.borderWidth
                color: delegateRoot.barTrackColor
            }
        }

        Label {
            width: delegateRoot.cellWidth
            height: parent.height
            rightPadding: Metrics.spacing6
            text: delegateRoot.limit
            color: delegateRoot.textColor
            horizontalAlignment: Text.AlignRight
            verticalAlignment: Text.AlignVCenter

            Rectangle {
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.right: parent.right
                width: Metrics.borderWidth
                color: delegateRoot.barTrackColor
            }
        }

        Label {
            width: delegateRoot.cellWidth
            height: parent.height
            rightPadding: Metrics.spacing6
            text: delegateRoot.utilization
            color: delegateRoot.textColor
            horizontalAlignment: Text.AlignRight
            verticalAlignment: Text.AlignVCenter

            Rectangle {
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.right: parent.right
                width: Metrics.borderWidth
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
                anchors.leftMargin: Metrics.spacing6
                anchors.rightMargin: Metrics.spacing6
                height: 10
                radius: Metrics.radiusMedium
                border.width: Metrics.borderWidth
                border.color: delegateRoot.barTrackColor

                Rectangle {
                    height: parent.height
                    width: parent.width * Math.max(0, Math.min(100, delegateRoot.utilizationValue)) / 100
                    radius: Metrics.radiusMedium
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


