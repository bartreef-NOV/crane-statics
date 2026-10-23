import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts

Item {
    id: root

    SystemPalette { id: sysPalette }

    readonly property color surfaceColor: sysPalette.base
    readonly property color borderColor: sysPalette.mid
    readonly property color headerColor: sysPalette.alternateBase
    readonly property color headerTextColor: sysPalette.text
    readonly property color textColor: sysPalette.text
    readonly property color gridColor: sysPalette.mid
    readonly property int tableRowHeight: 28
    readonly property int layoutSpacing: Math.round(
        8
    )

    property alias model: rowsList.model
    property string title: ""
    property string section: ""

    // Share of the table width taken by Name, Unit, Demand and Util; dragging a header
    // edge moves width between that column and the next, so the total stays the width.
    property var columnFractions: [0.34, 0.2, 0.23, 0.23]
    readonly property var columnWidths: columnFractions.map(f => f * root.width)
    readonly property real minColumnFraction: 0.1

    signal demandClicked(int row)

    function resizeColumn(column, deltaPx) {
        if (root.width <= 0 || column < 0 || column >= columnFractions.length - 1)
            return
        const pair = columnFractions[column] + columnFractions[column + 1]
        const next = Math.max(minColumnFraction,
                              Math.min(pair - minColumnFraction,
                                       columnFractions[column] + deltaPx / root.width))
        const fractions = columnFractions.slice()
        fractions[column] = next
        fractions[column + 1] = pair - next
        columnFractions = fractions
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: root.layoutSpacing

        Label {
            text: root.title
            font.bold: true
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: root.surfaceColor
            border.color: root.gridColor
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 1
                spacing: 0

                Row {
                    Layout.fillWidth: true
                    Layout.preferredHeight: root.tableRowHeight
                    spacing: 0

                    Repeater {
                        model: [qsTr("Name"), qsTr("Unit"), qsTr("Demand"), qsTr("Util")]

                        Rectangle {
                            required property string modelData
                            required property int index

                            width: root.columnWidths[index]
                            height: root.tableRowHeight
                            color: root.headerColor
                            border.color: root.gridColor
                            border.width: 1
                            Label {
                                anchors.fill: parent
                                anchors.leftMargin: 6
                                anchors.rightMargin: 6
                                anchors.bottomMargin: 2
                                text: parent.modelData
                                color: root.headerTextColor
                                font.bold: true
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignBottom
                                elide: Text.ElideRight
                            }

                            // Drag the right edge to resize against the next column.
                            MouseArea {
                                width: 6
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                anchors.right: parent.right
                                visible: parent.index < root.columnWidths.length - 1
                                cursorShape: Qt.SplitHCursor
                                preventStealing: true
                                property real pressX: 0
                                onPressed: mouse => pressX = mapToItem(root, mouse.x, 0).x
                                onPositionChanged: mouse => {
                                    const x = mapToItem(root, mouse.x, 0).x
                                    root.resizeColumn(parent.index, x - pressX)
                                    pressX = x
                                }
                            }
                        }
                    }
                }

                ListView {
                    id: rowsList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds

                    ScrollBar.vertical: ScrollBar {}

                    delegate: ResultRowDelegate {
                        width: rowsList.width
                        columnWidths: root.columnWidths
                        onDemandClicked: root.demandClicked(index)
                    }
                }
            }

            Label {
                anchors.centerIn: parent
                text: qsTr("No data")
                visible: rowsList.count === 0
            }
        }
    }
}


