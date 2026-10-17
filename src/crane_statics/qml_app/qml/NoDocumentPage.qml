import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts

Item {
    id: root

    signal openRequested()
    signal newRequested()

    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(520, root.width - 2 * 8)
        spacing: 16

        Label {
            Layout.fillWidth: true
            text: qsTr("Crane Statics")
            font.pointSize: 18
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
        }

        Label {
            Layout.fillWidth: true
            text: qsTr("Open a crane_input.json or .yaml file to begin analysis")
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
        }

        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: 8

            Button {
                text: qsTr("Choose File")
                onClicked: root.openRequested()
            }

            Button {
                text: qsTr("New Model")
                onClicked: root.newRequested()
            }
        }
    }
}


