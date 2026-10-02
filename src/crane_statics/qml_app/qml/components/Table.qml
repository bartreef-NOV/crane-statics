import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import BF.DesignSystem
import "."

/**
 * Table Component
 *
 * Enhanced data table with consistent header/row styling,
 * and keyboard navigation. Builds on DataTable with token-aware design.
 *
 * Usage:
 *   import Crane.Components 1.0
 *   Table {
 *       title: "Data"
 *       model: listModel
 *       editable: true
 *       onEditRequested: vm.editRow(row)
 *   }
 *
 * Design tokens used:
 * - layout.tableRowHeight
 * - colors.surface, surfaceAlt, border, textPrimary
 * - sizing.borderThin
 * - typography.body, bodyLarge
 * - spacing.md, controlGap
 */

Rectangle {
    id: root

    property alias model: table.model
    property string title: ""
    property string emptyText: qsTr("No data.")
    property bool editable: false
    property int currentRow: -1

    signal addRequested()
    signal editRequested(int row)
    signal deleteRequested(int row)

    color: Theme.surface
    border.color: Theme.border
    border.width: Metrics.borderWidth
    radius: Metrics.radiusSmall

    Accessible.role: Accessible.Table
    Accessible.name: root.title.length > 0 ? root.title : qsTr("Data table")

    readonly property bool hasSelection: currentRow >= 0

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Metrics.spacing16
        spacing: Metrics.spacing16

        // Title bar with toolbar
        RowLayout {
            Layout.fillWidth: true
            spacing: Metrics.spacing8
            visible: root.title.length > 0 || root.editable

            Text {
                Layout.fillWidth: true
                text: root.title
                font.pixelSize: Typography.bodyLarge
                font.weight: Typography.weightSemiBold
                color: Theme.text
                visible: root.title.length > 0
            }

            IconButton {
                iconText: "+"
                tooltipText: qsTr("Add")
                visible: root.editable
                implicitHeight: Metrics.compactControlHeight
                onClicked: root.addRequested()
            }

            IconButton {
                iconText: "\u270e"
                tooltipText: qsTr("Edit")
                semantic: "secondary"
                visible: root.editable
                enabled: root.hasSelection
                implicitHeight: Metrics.compactControlHeight
                onClicked: root.editRequested(root.currentRow)
            }

            IconButton {
                iconText: "\u00d7"
                tooltipText: qsTr("Delete")
                visible: root.editable
                enabled: root.hasSelection
                semantic: "danger"
                implicitHeight: Metrics.compactControlHeight
                onClicked: root.deleteRequested(root.currentRow)
            }
        }

        // Table view
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            TableView {
                id: table

                columnSpacing: 0
                rowSpacing: 0
                rowHeight: Metrics.tableRowHeight

                delegate: Rectangle {
                    implicitHeight: Metrics.tableRowHeight
                    color: {
                        if (root.currentRow === row) return Theme.primary
                        return row % 2 === 0 ? Theme.surface : Theme.surfaceSubtle
                    }
                    border.color: Theme.border
                    border.width: Metrics.borderWidth

                    MouseArea {
                        anchors.fill: parent
                        onClicked: root.currentRow = row
                    }

                    Text {
                        anchors.fill: parent
                        anchors.margins: Metrics.spacing8
                        text: display || ""
                        font.pixelSize: Typography.body
                        color: root.currentRow === row ? Theme.textOnDark : Theme.text
                        verticalAlignment: Text.AlignVCenter
                        horizontalAlignment: Text.AlignLeft
                        elide: Text.ElideRight
                    }
                }
            }
        }

        // Empty state
        Text {
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: root.emptyText
            font.pixelSize: Typography.body
            color: Theme.textMuted
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            visible: !table.model || table.model.rowCount === 0 || table.model.length === 0
        }
    }
}
