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

    signal barClicked(int row)

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
                        model: [qsTr("Name"), qsTr("Unit"), qsTr("Demand"), qsTr("Limit"), qsTr("Util"), qsTr("")]

                        Rectangle {
                            required property string modelData
                            required property int index

                            width: index === 0 ? Math.max(90, root.width * 0.30) : (root.width - Math.max(90, root.width * 0.30)) / 5
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
                        nameWidth: Math.max(90, root.width * 0.30)
                        onBarClicked: root.barClicked(index)
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


