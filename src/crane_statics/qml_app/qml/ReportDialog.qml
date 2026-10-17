import QtQuick
import QtQuick.Controls.Fusion

Dialog {
    id: root

    property alias model: reportList.model

    SystemPalette { id: sysPalette }

    modal: true
    anchors.centerIn: Overlay.overlay
    width: Math.min(900, Math.max(520, Overlay.overlay ? Overlay.overlay.width * 0.8 : 720))
    height: Math.min(700, Math.max(360, Overlay.overlay ? Overlay.overlay.height * 0.7 : 520))
    standardButtons: Dialog.Close

    ListView {
        id: reportList
        objectName: "reportList"
        anchors.fill: parent
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        ScrollBar.vertical: ScrollBar {}

        header: Row {
            width: reportList.width
            height: 28

            Repeater {
                model: [qsTr("Item"), qsTr("Fx"), qsTr("Fz"), qsTr("|F|"), qsTr("X"), qsTr("Z"), qsTr("M")]

                Rectangle {
                    required property string modelData
                    required property int index
                    width: index === 0 ? reportList.width * 0.34 : reportList.width * 0.11
                    height: 28
                    color: sysPalette.alternateBase
                    border.color: sysPalette.mid
                    border.width: 1
                    Label {
                        anchors.fill: parent
                        leftPadding: 6
                        rightPadding: 6
                        bottomPadding: 2
                        text: parent.modelData
                        font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignBottom
                    }
                }
            }
        }

        delegate: Item {
            id: reportRow

            required property string label
            required property string kind
            required property string fx
            required property string fz
            required property string magnitude
            required property string posX
            required property string posZ
            required property string moment
            required property bool passed
            required property int index

            width: reportList.width
            height: 28

            readonly property bool section: kind === "section"
            Rectangle {
                anchors.fill: parent
                color: reportRow.section
                    ? sysPalette.alternateBase
                    : (reportRow.index % 2 === 0
                        ? sysPalette.base
                        : sysPalette.alternateBase)
                border.color: sysPalette.mid
                border.width: 1
            }

            Row {
                anchors.fill: parent

                Label {
                    width: reportList.width * 0.34
                    height: parent.height
                    leftPadding: 6
                    text: reportRow.label
                    font.bold: reportRow.section
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight

                    Rectangle {
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        anchors.right: parent.right
                        width: 1
                        color: sysPalette.mid
                    }
                }

                Repeater {
                    model: [reportRow.fx, reportRow.fz, reportRow.magnitude,
                            reportRow.posX, reportRow.posZ, reportRow.moment]

                    Label {
                        required property string modelData
                        width: reportList.width * 0.11
                        height: 28
                        rightPadding: 6
                        text: modelData
                        horizontalAlignment: Text.AlignRight
                        verticalAlignment: Text.AlignVCenter

                        Rectangle {
                            anchors.top: parent.top
                            anchors.bottom: parent.bottom
                            anchors.right: parent.right
                            width: 1
                            color: sysPalette.mid
                        }
                    }
                }
            }
        }
    }
}


