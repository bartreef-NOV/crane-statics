import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import "../design" as Design
import "components" as Components

Components.Dialog {
    id: root

    property var overview: ({})

    function showOverview(newOverview) {
        overview = newOverview
        open()
    }

    title: overview.title !== undefined ? overview.title : qsTr("Load Contribution Overview")
    modal: true
    anchors.centerIn: Overlay.overlay
    width: Design.DesignTokens.sizing.dialogWidth
    standardButtons: Dialog.Close

    ColumnLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: Design.DesignTokens.spacing.sm

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
            color: Design.DesignTokens.colors.divider
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


