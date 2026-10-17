import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts

Dialog {
    id: root

    property var overview: ({})

    SystemPalette { id: sysPalette }

    function showOverview(newOverview) {
        overview = newOverview
        open()
    }

    title: overview.title !== undefined ? overview.title : qsTr("Load Contribution Overview")
    modal: true
    anchors.centerIn: Overlay.overlay
    width: 480
    standardButtons: Dialog.Close

    ColumnLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: 8

        Label {
            Layout.fillWidth: true
            text: (root.overview.section !== undefined ? root.overview.section : "")
                  + " — " + (root.overview.row_name !== undefined ? root.overview.row_name : "")
            font.bold: true
            elide: Text.ElideRight
        }

        Repeater {
            model: root.overview.terms !== undefined ? root.overview.terms : []

            RowLayout {
                required property var modelData
                Layout.fillWidth: true

                Label {
                    Layout.fillWidth: true
                    text: modelData.name
                }

                Label {
                    text: Number(modelData.value_kN).toFixed(1) + " "
                          + (root.overview.unit !== undefined ? root.overview.unit : "kN")
                    horizontalAlignment: Text.AlignRight
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: sysPalette.mid
        }

        RowLayout {
            Layout.fillWidth: true

            Label {
                Layout.fillWidth: true
                text: qsTr("Total")
                font.bold: true
            }

            Label {
                text: root.overview.reconstructed_kN !== undefined
                      ? Number(root.overview.reconstructed_kN).toFixed(1) : ""
                font.bold: true
            }
        }
    }
}


