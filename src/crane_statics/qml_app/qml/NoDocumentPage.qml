import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import "../design" as Design
import "components"

Item {
    id: root

    signal openRequested()
    signal newRequested()

    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(520, root.width - 2 * Design.DesignTokens.spacing.sm)
        spacing: Design.DesignTokens.spacing.md

        Label {
            Layout.fillWidth: true
            text: qsTr("Crane Statics")
            font.pointSize: 18
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
        }

        Label {
            Layout.fillWidth: true
            text: qsTr("Open a crane_input.json file to begin analysis")
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
        }

        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: Design.DesignTokens.spacing.controlGap

            Button {
                text: qsTr("Choose File")
                onClicked: root.openRequested()
            }

            Button {
                text: qsTr("New Model")
                semantic: "secondary"
                onClicked: root.newRequested()
            }
        }
    }
}


