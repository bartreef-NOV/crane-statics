import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import "../design" as Design

Item {
    id: root

    readonly property color surfaceColor: Design.DesignTokens.colors.surface
    readonly property color borderColor: Design.DesignTokens.colors.border
    readonly property color headerColor: Design.DesignTokens.colors.surfaceAlt
    readonly property color headerTextColor: Design.DesignTokens.colors.textPrimary
    readonly property color textColor: Design.DesignTokens.colors.textPrimary
    readonly property color gridColor: Design.DesignTokens.colors.border
    readonly property int tableRowHeight: Design.DesignTokens.layout.tableRowHeight
    readonly property int layoutSpacing: Math.round(
        Design.DesignTokens.spacing.sm * Design.DesignTokens.layout.spacingMultiplier
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
            border.width: Design.DesignTokens.sizing.borderThin

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Design.DesignTokens.sizing.borderThin
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
                            border.width: Design.DesignTokens.sizing.borderThin
                            Label {
                                anchors.fill: parent
                                anchors.leftMargin: Design.DesignTokens.spacing.compact
                                anchors.rightMargin: Design.DesignTokens.spacing.compact
                                anchors.bottomMargin: Design.DesignTokens.spacing.hairline
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


