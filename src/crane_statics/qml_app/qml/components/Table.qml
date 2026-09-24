import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import "../../design"
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

    color: DesignTokens.colors.surface
    border.color: DesignTokens.colors.border
    border.width: DesignTokens.sizing.borderThin
    radius: DesignTokens.sizing.radiusSmall

    Accessible.role: Accessible.Table
    Accessible.name: root.title.length > 0 ? root.title : qsTr("Data table")

    readonly property bool hasSelection: currentRow >= 0

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: DesignTokens.spacing.md
        spacing: DesignTokens.spacing.md

        // Title bar with toolbar
        RowLayout {
            Layout.fillWidth: true
            spacing: DesignTokens.spacing.controlGap
            visible: root.title.length > 0 || root.editable

            Text {
                Layout.fillWidth: true
                text: root.title
                font.pixelSize: DesignTokens.typography.bodyLarge
                font.weight: DesignTokens.typography.weightSemiBold
                color: DesignTokens.colors.textPrimary
                visible: root.title.length > 0
            }

            IconButton {
                iconText: "+"
                tooltipText: qsTr("Add")
                visible: root.editable
                implicitHeight: DesignTokens.sizing.buttonHeightSmall
                onClicked: root.addRequested()
            }

            IconButton {
                iconText: "\u270e"
                tooltipText: qsTr("Edit")
                semantic: "secondary"
                visible: root.editable
                enabled: root.hasSelection
                implicitHeight: DesignTokens.sizing.buttonHeightSmall
                onClicked: root.editRequested(root.currentRow)
            }

            IconButton {
                iconText: "\u00d7"
                tooltipText: qsTr("Delete")
                visible: root.editable
                enabled: root.hasSelection
                semantic: "danger"
                implicitHeight: DesignTokens.sizing.buttonHeightSmall
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
                rowHeight: DesignTokens.layout.tableRowHeight

                delegate: Rectangle {
                    implicitHeight: DesignTokens.layout.tableRowHeight
                    color: {
                        if (root.currentRow === row) return DesignTokens.colors.primary
                        return row % 2 === 0 ? DesignTokens.colors.surface : DesignTokens.colors.surfaceAlt
                    }
                    border.color: DesignTokens.colors.border
                    border.width: DesignTokens.sizing.borderThin

                    MouseArea {
                        anchors.fill: parent
                        onClicked: root.currentRow = row
                    }

                    Text {
                        anchors.fill: parent
                        anchors.margins: DesignTokens.spacing.sm
                        text: display || ""
                        font.pixelSize: DesignTokens.typography.body
                        color: root.currentRow === row ? DesignTokens.colors.textInverse : DesignTokens.colors.textPrimary
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
            font.pixelSize: DesignTokens.typography.body
            color: DesignTokens.colors.textSecondary
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            visible: !table.model || table.model.rowCount === 0 || table.model.length === 0
        }
    }
}
