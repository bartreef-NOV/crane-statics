import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import BF.DesignSystem
import "components"

Item {
    id: root

    readonly property color surfaceColor: Theme.surface
    readonly property color borderColor: Theme.border
    readonly property color headerColor: Theme.surfaceSubtle
    readonly property color headerTextColor: Theme.text
    readonly property color textColor: Theme.text
    readonly property color gridColor: Theme.border
    readonly property int tableRowHeight: Metrics.tableRowHeight
    readonly property int layoutSpacing: Math.round(
        Metrics.spacing8 * Metrics.spacingMultiplier
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
            border.width: Metrics.borderWidth

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Metrics.borderWidth
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
                                ? "transparent" : Theme.surfaceSubtle
                            border.color: root.gridColor
                            border.width: Metrics.borderWidth
                        }

                        Row {
                            anchors.fill: parent

                            Label {
                                width: root.width * 0.38
                                height: parent.height
                                leftPadding: Metrics.spacing6
                                text: limitRow.name
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

                            Label {
                                width: root.width * 0.15
                                height: parent.height
                                leftPadding: Metrics.spacing6
                                text: limitRow.unit
                                verticalAlignment: Text.AlignVCenter

                                Rectangle {
                                    anchors.top: parent.top
                                    anchors.bottom: parent.bottom
                                    anchors.right: parent.right
                                    width: Metrics.borderWidth
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

                                StyledCheckBox {
                                    anchors.centerIn: parent
                                    checked: limitRow.limitEnabled
                                    onToggled: chartVm.setLimitEnabled(limitRow.limitId, checked)
                                }
                            }

                            Button {
                                width: root.width * 0.15
                                height: parent.height
                                text: qsTr("Auto")
                                semantic: "secondary"
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


