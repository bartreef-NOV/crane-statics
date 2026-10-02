import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import BF.DesignSystem

Item {
    id: root

    SystemPalette { id: sysPalette }

    readonly property color surfaceColor: sysPalette.base
    readonly property color borderColor: sysPalette.mid
    readonly property color headerColor: sysPalette.alternateBase
    readonly property color headerTextColor: sysPalette.text
    readonly property color textColor: sysPalette.text
    readonly property color selectedColor: sysPalette.highlight
    readonly property color selectedTextColor: sysPalette.highlightedText
    readonly property color gridColor: sysPalette.mid
    readonly property int tableRowHeight: Metrics.tableRowHeight
    readonly property int layoutSpacing: Math.round(
        Metrics.spacing8 * Metrics.spacingMultiplier
    )

    property alias model: pointsList.model
    property int currentRow: -1

    signal addRequested()
    signal editRequested(int row)
    signal deleteRequested(int row)

    readonly property bool hasSelection: currentRow >= 0 && currentRow < pointsList.count

    ColumnLayout {
        anchors.fill: parent
        spacing: root.layoutSpacing

        RowLayout {
            Layout.fillWidth: true
            spacing: root.layoutSpacing

            Label {
                Layout.fillWidth: true
                text: qsTr("Contractual Points")
                font.bold: true
            }

            Button { text: "+"; ToolTip.visible: hovered; ToolTip.text: qsTr("Add"); implicitWidth: Metrics.controlHeight; implicitHeight: Metrics.controlHeight; padding: 0; onClicked: root.addRequested() }
            Button { text: "\u270e"; ToolTip.visible: hovered; ToolTip.text: qsTr("Edit"); implicitWidth: Metrics.controlHeight; implicitHeight: Metrics.controlHeight; padding: 0; enabled: root.hasSelection; onClicked: root.editRequested(root.currentRow) }
            Button { text: "\u00d7"; ToolTip.visible: hovered; ToolTip.text: qsTr("Delete"); implicitWidth: Metrics.controlHeight; implicitHeight: Metrics.controlHeight; padding: 0; enabled: root.hasSelection; onClicked: root.deleteRequested(root.currentRow) }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: root.surfaceColor
            border.color: root.gridColor
            border.width: Metrics.borderWidth

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Metrics.borderWidth
                spacing: 0

                Row {
                    Layout.fillWidth: true
                    height: root.tableRowHeight

                    Repeater {
                        model: [qsTr("Outreach (m)"), qsTr("Load (t)"), qsTr("Allowable (t)"), qsTr("Status")]

                        Rectangle {
                            required property string modelData
                            required property int index
                            width: root.width / 4
                            height: root.tableRowHeight
                            color: root.headerColor
                            border.color: root.gridColor
                            border.width: Metrics.borderWidth
                            Label {
                                anchors.fill: parent
                                leftPadding: Metrics.spacing6
                                rightPadding: Metrics.spacing6
                                bottomPadding: Metrics.spacing2
                                text: parent.modelData
                                color: root.headerTextColor
                                font.bold: true
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignBottom
                                elide: Text.ElideRight
                            }
                        }
                    }
                }

                ListView {
                    id: pointsList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds

                    ScrollBar.vertical: ScrollBar {}

                    onCountChanged: if (root.currentRow >= count) root.currentRow = -1

                    delegate: Rectangle {
                        id: pointRow

                        required property string outreach
                        required property string load
                        required property string allowable
                        required property string status
                        required property int index

                        readonly property bool selected: index === root.currentRow

                        width: pointsList.width
                        height: root.tableRowHeight
                        color: pointRow.selected
                            ? root.selectedColor
                            : (pointRow.index % 2 === 0 ? root.surfaceColor : sysPalette.alternateBase)
                        border.color: root.gridColor
                        border.width: Metrics.borderWidth

                        Row {
                            anchors.fill: parent

                            Repeater {
                                model: [pointRow.outreach, pointRow.load, pointRow.allowable, pointRow.status]

                                Label {
                                    required property string modelData
                                    required property int index
                                    width: root.width / 4
                                    height: root.tableRowHeight
                                    leftPadding: Metrics.spacing6
                                    text: modelData
                                    color: pointRow.selected ? root.selectedTextColor : root.textColor
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight

                                    Rectangle {
                                        anchors.top: parent.top
                                        anchors.bottom: parent.bottom
                                        anchors.right: parent.right
                                        width: Metrics.borderWidth
                                        color: root.gridColor
                                    }
                                }
                            }
                        }

                        TapHandler {
                            onSingleTapped: root.currentRow = pointRow.index
                            onDoubleTapped: {
                                root.currentRow = pointRow.index
                                root.editRequested(pointRow.index)
                            }
                        }
                    }
                }
            }

            Label {
                anchors.centerIn: parent
                text: qsTr("No contractual points for this hoist.")
                visible: pointsList.count === 0
            }
        }
    }
}


