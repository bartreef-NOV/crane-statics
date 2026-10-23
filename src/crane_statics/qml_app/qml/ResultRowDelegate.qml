import QtQuick
import QtQuick.Controls.Fusion

Item {
    id: delegateRoot

    required property string name
    required property string unit
    required property string demand
    required property string limit
    required property string utilization
    required property real utilizationValue
    required property bool isGroupHeader
    required property bool nested
    required property bool clickable
    required property string tooltip
    required property int index

    // Pixel widths of Name, Unit, Demand and Util, set by the table.
    property var columnWidths: [120, 60, 60, 60]

    SystemPalette { id: sysPalette }

    readonly property color barColor: sysPalette.highlight
    readonly property color barTrackColor: sysPalette.midlight
    readonly property color surfaceColor: sysPalette.base
    readonly property color alternateSurfaceColor: sysPalette.alternateBase
    readonly property color textColor: sysPalette.text

    signal demandClicked()

    implicitHeight: 24
    height: 24

    Rectangle {
        anchors.fill: parent
        color: delegateRoot.index % 2 === 0
            ? delegateRoot.surfaceColor : delegateRoot.alternateSurfaceColor
        border.color: delegateRoot.barTrackColor
        border.width: 1
        visible: !delegateRoot.isGroupHeader
    }

    Label {
        visible: delegateRoot.isGroupHeader
        anchors.fill: parent
        anchors.leftMargin: 6 + (delegateRoot.nested ? 8 : 0)
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
            width: delegateRoot.columnWidths[0]
            height: parent.height
            leftPadding: 6
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
                width: 1
                color: delegateRoot.barTrackColor
            }
        }

        Label {
            width: delegateRoot.columnWidths[1]
            height: parent.height
            leftPadding: 6
            text: delegateRoot.unit
            color: delegateRoot.textColor
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight

            Rectangle {
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.right: parent.right
                width: 1
                color: delegateRoot.barTrackColor
            }
        }

        Label {
            width: delegateRoot.columnWidths[2]
            height: parent.height
            rightPadding: 6
            text: delegateRoot.demand
            color: delegateRoot.textColor
            font.underline: delegateRoot.clickable && demandHover.hovered
            horizontalAlignment: Text.AlignRight
            verticalAlignment: Text.AlignVCenter

            TapHandler {
                enabled: delegateRoot.clickable
                onTapped: delegateRoot.demandClicked()
            }

            ToolTip.visible: demandHover.hovered && delegateRoot.clickable
            ToolTip.text: qsTr("Click to view load-contribution overview")
            HoverHandler {
                id: demandHover
                cursorShape: delegateRoot.clickable ? Qt.PointingHandCursor : Qt.ArrowCursor
            }

            Rectangle {
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.right: parent.right
                width: 1
                color: delegateRoot.barTrackColor
            }
        }

        Item {
            width: delegateRoot.columnWidths[3]
            height: parent.height

            readonly property bool hasLimit: delegateRoot.limit !== "-"

            ToolTip.visible: utilHover.hovered && hasLimit
            ToolTip.text: qsTr("Limit: %1 %2").arg(delegateRoot.limit).arg(delegateRoot.unit)
            HoverHandler { id: utilHover }

            Rectangle {
                id: barTrack
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.leftMargin: 6
                anchors.rightMargin: 6
                height: 18
                radius: 3
                border.width: 1
                border.color: delegateRoot.barTrackColor

                Rectangle {
                    height: parent.height
                    width: parent.width * Math.max(0, Math.min(100, delegateRoot.utilizationValue)) / 100
                    radius: 3
                    color: delegateRoot.barColor
                    // Translucent so the utilization text stays readable over the fill.
                    opacity: 0.45
                }

                Label {
                    anchors.centerIn: parent
                    text: delegateRoot.utilization
                    color: delegateRoot.textColor
                }
            }
        }
    }
}


