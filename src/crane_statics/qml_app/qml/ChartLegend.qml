import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import BF.DesignSystem

Frame {
    id: root

    property var items: []
    property var visibilityByKey: ({})
    signal toggleRequested(string key)

    readonly property color surfaceColor: Theme.surface
    readonly property color borderColor: Theme.border
    readonly property color textColor: Theme.text
    readonly property color mutedTextColor: Theme.textMuted
    readonly property int layoutSpacing: Math.round(
        Metrics.spacing8 * Metrics.spacingMultiplier
    )

    padding: 8
    implicitWidth: 240
    implicitHeight: 180

    function isVisible(key) {
        return visibilityByKey[key] !== false
    }

    background: Rectangle {
        color: root.surfaceColor
        border.color: root.borderColor
        radius: 3
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: root.layoutSpacing

        RowLayout {
            Layout.fillWidth: true

            Label {
                text: qsTr("Series")
                font.bold: true
                color: root.textColor
            }

            Label {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignRight
                text: qsTr("%1 visible / %2").arg(root.items.filter(item => root.isVisible(item.id)).length).arg(root.items.length)
                color: root.mutedTextColor
                font.pixelSize: 11
            }
        }

        ListView {
            id: seriesList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: Math.max(2, root.layoutSpacing - 4)
            model: root.items
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: ItemDelegate {
                id: entry
                width: seriesList.width
                height: 30
                highlighted: activeFocus || hovered
                Accessible.name: qsTr("%1, %2").arg(modelData.label).arg(root.isVisible(modelData.id) ? qsTr("visible") : qsTr("hidden"))
                Accessible.role: Accessible.CheckBox
                onClicked: root.toggleRequested(modelData.id)

                contentItem: RowLayout {
                    spacing: root.layoutSpacing

                    Rectangle {
                        Layout.preferredWidth: 16
                        Layout.preferredHeight: 3
                        color: modelData.color || "#7A7A7A"
                        opacity: root.isVisible(modelData.id) ? 1.0 : 0.3
                    }

                    Label {
                        Layout.fillWidth: true
                        text: modelData.label
                        elide: Text.ElideRight
                        color: root.isVisible(modelData.id) ? root.textColor : root.mutedTextColor
                        opacity: root.isVisible(modelData.id) ? 1.0 : 0.75
                        ToolTip.visible: entry.hovered && truncated
                        ToolTip.text: modelData.label
                        property bool truncated: implicitWidth > width
                    }

                    Label {
                        text: root.isVisible(modelData.id) ? qsTr("Shown") : qsTr("Hidden")
                        color: root.mutedTextColor
                        font.pixelSize: 10
                    }
                }
            }
        }
    }
}
