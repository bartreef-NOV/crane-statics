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

    property alias model: limitsList.model
    property string title: ""

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
                    height: root.tableRowHeight

                    Repeater {
                        model: [qsTr("Limit"), qsTr("Unit"), qsTr("Max"), qsTr("On"), qsTr("")]

                        Rectangle {
                            required property string modelData
                            required property int index
                            width: index === 0 ? root.width * 0.38 : root.width * 0.15
                            height: root.tableRowHeight
                            color: root.headerColor
                            border.color: root.gridColor
                            border.width: 1
                            Label {
                                anchors.fill: parent
                                leftPadding: 6
                                rightPadding: 6
                                bottomPadding: 2
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
                    id: limitsList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds

                    ScrollBar.vertical: ScrollBar {}

                    delegate: Item {
                        id: limitRow

                        required property string limitId
                        required property string name
                        required property string unit
                        required property string maxValue
                        required property bool limitEnabled
                        required property int index

                        width: limitsList.width
                        height: root.tableRowHeight

                        Rectangle {
                            anchors.fill: parent
                            color: limitRow.index % 2 === 0
                                ? "transparent" : sysPalette.alternateBase
                            border.color: root.gridColor
                            border.width: 1
                        }

                        Row {
                            anchors.fill: parent

                            Label {
                                width: root.width * 0.38
                                height: parent.height
                                leftPadding: 6
                                text: limitRow.name
                                verticalAlignment: Text.AlignVCenter
                                elide: Text.ElideRight

                                Rectangle {
                                    anchors.top: parent.top
                                    anchors.bottom: parent.bottom
                                    anchors.right: parent.right
                                    width: 1
                                    color: root.gridColor
                                }
                            }

                            Label {
                                width: root.width * 0.15
                                height: parent.height
                                leftPadding: 6
                                text: limitRow.unit
                                verticalAlignment: Text.AlignVCenter

                                Rectangle {
                                    anchors.top: parent.top
                                    anchors.bottom: parent.bottom
                                    anchors.right: parent.right
                                    width: 1
                                    color: root.gridColor
                                }
                            }

                            TextField {
                                width: root.width * 0.15
                                height: parent.height
                                text: limitRow.maxValue
                                horizontalAlignment: TextInput.AlignRight
                                selectByMouse: true
                                validator: DoubleValidator { notation: DoubleValidator.StandardNotation }
                                onEditingFinished: chartVm.setLimitMax(limitRow.limitId, text)
                            }

                            Item {
                                width: root.width * 0.15
                                height: parent.height

                                CheckBox {
                                    anchors.centerIn: parent
                                    checked: limitRow.limitEnabled
                                    onToggled: chartVm.setLimitEnabled(limitRow.limitId, checked)
                                }
                            }

                            Button {
                                width: root.width * 0.15
                                height: parent.height
                                text: qsTr("Auto")
                                onClicked: chartVm.autoSetLimit(limitRow.limitId)
                            }
                        }
                    }
                }
            }

            Label {
                anchors.centerIn: parent
                text: qsTr("No design limits")
                visible: limitsList.count === 0
            }
        }
    }
}


