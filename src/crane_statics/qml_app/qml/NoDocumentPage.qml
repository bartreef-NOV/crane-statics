import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import BF.DesignSystem

Item {
    id: root

    signal openRequested()
    signal newRequested()

    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(520, root.width - 2 * Metrics.spacing8)
        spacing: Metrics.spacing16

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
            spacing: Metrics.spacing8

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


