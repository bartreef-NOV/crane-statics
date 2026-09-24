import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import "../design" as Design
import "components"

Item {
    id: root

    readonly property color surfaceColor: Design.DesignTokens.colors.surface
    readonly property color headerColor: Design.DesignTokens.colors.surfaceAlt
    readonly property color headerTextColor: Design.DesignTokens.colors.textPrimary
    readonly property color textColor: Design.DesignTokens.colors.textPrimary
    readonly property color selectedColor: Design.DesignTokens.colors.selection
    readonly property color selectedTextColor: Design.DesignTokens.colors.selectionText
    readonly property color gridColor: Design.DesignTokens.colors.border
    readonly property int tableRowHeight: Design.DesignTokens.layout.tableRowHeight
    readonly property int layoutSpacing: Math.round(
        Design.DesignTokens.spacing.sm * Design.DesignTokens.layout.spacingMultiplier
    )

    property alias model: table.model
    property string title: ""
    property string emptyText: qsTr("No entries.")
    property bool editable: false
    property int currentRow: -1
    property int currentColumn: 0
    // Node ids offered by the cells that hold a node reference.
    property var editorChoices: []
    activeFocusOnTab: true
    focus: true

    Accessible.role: Accessible.Table
    Accessible.name: root.title.length > 0 ? root.title : qsTr("Data table")

    signal addRequested()
    signal deleteRequested(int row)

    Keys.onPressed: event => {
        if (event.key === Qt.Key_Up) {
            root.currentRow = Math.max(0, root.currentRow < 0 ? 0 : root.currentRow - 1)
            event.accepted = true
        } else if (event.key === Qt.Key_Down) {
            root.currentRow = Math.min(table.rows - 1, root.currentRow + 1)
            event.accepted = true
        } else if (event.key === Qt.Key_Left) {
            root.currentColumn = Math.max(0, root.currentColumn - 1)
            event.accepted = true
        } else if (event.key === Qt.Key_Right) {
            root.currentColumn = Math.min(table.columns - 1, root.currentColumn + 1)
            event.accepted = true
        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            root.startEdit(root.currentRow, root.currentColumn)
            event.accepted = true
        } else if (event.key === Qt.Key_Delete) {
            if (root.editable && root.hasSelection)
                root.deleteRequested(root.currentRow)
            event.accepted = true
        }
    }

    readonly property bool hasSelection: currentRow >= 0 && currentRow < table.rows

    /*  Editing happens in the cell, so the table asks the model which cells accept
        it: one row holds records that share a table but not a set of authored
        fields, and several columns are derived rather than authored. Asking also
        keeps Qt quiet, since editing a read-only index warns. */
    function canEdit(row, column) {
        if (!root.editable || row < 0 || column < 0)
            return false
        if (!root.model || typeof root.model.isCellEditable !== "function")
            return false
        return root.model.isCellEditable(row, column)
    }

    function startEdit(row, column) {
        if (!root.canEdit(row, column))
            return
        table.edit(table.index(row, column))
    }

    function commitCell(row, column, value) {
        if (root.model && typeof root.model.commitCell === "function")
            root.model.commitCell(row, column, value)
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: root.layoutSpacing

        RowLayout {
            Layout.fillWidth: true
            spacing: root.layoutSpacing
            visible: root.title.length > 0 || root.editable

            Label {
                Layout.fillWidth: true
                text: root.title
                font.bold: true
            }

            IconButton {
                iconText: "+"
                tooltipText: qsTr("Add")
                visible: root.editable
                onClicked: root.addRequested()
            }

            IconButton {
                iconText: "\u00d7"
                tooltipText: qsTr("Delete")
                semantic: "danger"
                visible: root.editable
                enabled: root.hasSelection
                onClicked: root.deleteRequested(root.currentRow)
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: root.tableRowHeight * 4
            implicitHeight: root.tableRowHeight * 8
            color: root.surfaceColor
            border.color: root.gridColor
            border.width: Design.DesignTokens.sizing.borderThin

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Design.DesignTokens.sizing.borderThin
                spacing: 0

                HorizontalHeaderView {
                    id: header
                    Layout.fillWidth: true
                    syncView: table
                    clip: true

                    delegate: Rectangle {
                        id: headerCell
                        required property string display
                        required property int column
                        implicitWidth: 100
                        implicitHeight: root.tableRowHeight
                        color: root.headerColor
                        border.color: root.gridColor
                        border.width: Design.DesignTokens.sizing.borderThin

                        Label {
                            anchors.fill: parent
                            anchors.leftMargin: Design.DesignTokens.spacing.sm
                            anchors.rightMargin: Design.DesignTokens.spacing.sm
                            anchors.bottomMargin: Design.DesignTokens.spacing.hairline
                            text: headerCell.display
                            color: root.headerTextColor
                            font.pixelSize: Design.DesignTokens.typography.caption
                            font.bold: true
                            elide: Text.ElideRight
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignBottom
                        }

                        // Double-click near the right edge auto-fits the column to its content.
                        MouseArea {
                            width: 6
                            anchors.top: parent.top
                            anchors.bottom: parent.bottom
                            anchors.right: parent.right
                            cursorShape: Qt.SplitHCursor
                            onDoubleClicked: table.forceLayout()
                        }
                    }
                }

                TableView {
                    id: table
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    columnSpacing: 0
                    rowSpacing: 0
                    boundsBehavior: Flickable.StopAtBounds
                    editTriggers: TableView.DoubleTapped

                    onRowsChanged: if (root.currentRow >= rows) root.currentRow = -1

                    ScrollBar.vertical: ScrollBar {}
                    ScrollBar.horizontal: ScrollBar {}

                    delegate: Rectangle {
                        id: cell

                        required property string display
                        required property bool numeric
                        required property bool editable
                        required property string editorKind
                        required property var edit
                        required property int row
                        required property int column
                        required property bool editing

                        readonly property bool selected: row === root.currentRow
                        readonly property bool current: selected && column === root.currentColumn
                        property bool hovered: false

                        implicitWidth: Math.max(80, cellText.implicitWidth + 2 * Design.DesignTokens.spacing.sm)
                        implicitHeight: root.tableRowHeight
                        color: cell.selected
                            ? root.selectedColor
                            : (cell.hovered
                                ? Design.DesignTokens.colors.surfaceAlt
                                : (cell.row % 2 === 0
                                    ? root.surfaceColor
                                    : Design.DesignTokens.colors.surfaceAlt))

                        border.color: cell.current && root.activeFocus
                            ? Design.DesignTokens.colors.focusRing
                            : root.gridColor
                        border.width: Design.DesignTokens.sizing.borderThin

                        Label {
                            id: cellText
                            anchors.fill: parent
                            anchors.leftMargin: Design.DesignTokens.spacing.sm
                            anchors.rightMargin: Design.DesignTokens.spacing.sm
                            text: cell.display
                            color: cell.selected ? root.selectedTextColor : root.textColor
                            font.pixelSize: Design.DesignTokens.typography.body
                            elide: Text.ElideRight
                            verticalAlignment: Text.AlignVCenter
                            horizontalAlignment: cell.numeric ? Text.AlignRight : Text.AlignLeft
                            visible: !cell.editing
                        }

                        TapHandler {
                            onSingleTapped: {
                                root.currentRow = cell.row
                                root.currentColumn = cell.column
                                root.forceActiveFocus()
                            }
                            onDoubleTapped: {
                                root.currentRow = cell.row
                                root.currentColumn = cell.column
                                root.startEdit(cell.row, cell.column)
                            }
                        }

                        HoverHandler {
                            cursorShape: cell.editable && root.editable
                                ? Qt.IBeamCursor
                                : Qt.ArrowCursor
                            onHoveredChanged: cell.hovered = hovered
                        }

                        TableView.editDelegate: CellEditor {
                            anchors.fill: parent
                            kind: cell.editorKind
                            initialValue: cell.edit
                            choices: root.editorChoices
                            onCommitRequested: root.commitCell(cell.row, cell.column, value)
                        }
                    }
                }
            }

            Label {
                anchors.centerIn: parent
                text: root.emptyText
                visible: table.rows === 0
            }
        }
    }
}


