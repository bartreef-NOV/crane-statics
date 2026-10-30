import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts

Item {
    id: root

    SystemPalette { id: sysPalette }

    readonly property color surfaceColor: sysPalette.base
    readonly property color headerColor: sysPalette.alternateBase
    readonly property color headerTextColor: sysPalette.text
    readonly property color textColor: sysPalette.text
    readonly property color selectedColor: sysPalette.highlight
    readonly property color selectedTextColor: sysPalette.highlightedText
    readonly property color gridColor: sysPalette.mid
    readonly property int tableRowHeight: 28
    readonly property int layoutSpacing: Math.round(
        8
    )

    property alias model: table.model
    property string title: ""
    property string emptyText: qsTr("No entries.")
    property bool editable: false
    // Whether rows can be added and deleted; cells stay editable either way.
    property bool rowsEditable: true
    // Extra toolbar items, placed before the add and delete buttons.
    property alias toolbarExtras: extras.data
    // The column that grows to fill the table's width; -1 leaves every column at its content width.
    property int stretchColumn: -1
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
    // A group header row was activated; the owner collapses or expands that group.
    signal groupToggleRequested(int row)

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
            root.activateCell(root.currentRow, root.currentColumn)
            event.accepted = true
        } else if (event.key === Qt.Key_Delete) {
            if (root.editable && root.rowsEditable && root.hasSelection)
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

    // Enter and double-click: a group header toggles; other cells open their editor, and
    // check boxes flip in place rather than opening one.
    function activateCell(row, column) {
        const action = root.model && typeof root.model.cellAction === "function"
            ? root.model.cellAction(row, column) : "edit"
        if (action === "group")
            root.groupToggleRequested(row)
        else if (action === "check")
            root.model.toggleCheck(row, column)
        else
            root.startEdit(row, column)
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

            RowLayout {
                id: extras
                spacing: root.layoutSpacing
            }

            Button {
                text: "+"
                ToolTip.visible: hovered
                ToolTip.text: qsTr("Add")
                padding: 0
                visible: root.editable && root.rowsEditable
                onClicked: root.addRequested()
            }

            Button {
                text: "\u00d7"
                ToolTip.visible: hovered
                ToolTip.text: qsTr("Delete")
                padding: 0
                visible: root.editable && root.rowsEditable
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
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 1
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
                        border.width: 1

                        Label {
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 8
                            anchors.bottomMargin: 2
                            text: headerCell.display
                            color: root.headerTextColor
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

                    // Every column takes its content width; with a stretch column, that
                    // one also takes whatever width the others leave over.
                    columnWidthProvider: function (column) {
                        const natural = table.implicitColumnWidth(column)
                        if (column !== root.stretchColumn)
                            return natural
                        let others = 0
                        for (let c = 0; c < table.columns; ++c) {
                            if (c !== column)
                                others += Math.max(80, table.implicitColumnWidth(c))
                        }
                        return Math.max(natural, table.width - others)
                    }

                    onRowsChanged: if (root.currentRow >= rows) root.currentRow = -1
                    onWidthChanged: if (root.stretchColumn >= 0) forceLayout()
                    Component.onCompleted: if (root.stretchColumn >= 0) Qt.callLater(forceLayout)

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
                        required property bool checkable
                        required property int checkState
                        required property bool groupRow

                        readonly property bool selected: row === root.currentRow
                        readonly property bool current: selected && column === root.currentColumn
                        property bool hovered: false

                        implicitWidth: Math.max(80, cellText.implicitWidth + 2 * 8)
                        implicitHeight: root.tableRowHeight
                        color: cell.selected
                            ? root.selectedColor
                            : (cell.groupRow
                                ? sysPalette.midlight
                                : (cell.hovered
                                    ? sysPalette.alternateBase
                                    : (cell.row % 2 === 0
                                        ? root.surfaceColor
                                        : sysPalette.alternateBase)))

                        border.color: cell.current && root.activeFocus
                            ? sysPalette.highlight
                            : root.gridColor
                        border.width: 1

                        Label {
                            id: cellText
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 8
                            text: cell.display
                            color: cell.selected ? root.selectedTextColor : root.textColor
                            elide: Text.ElideRight
                            font.bold: cell.groupRow
                            verticalAlignment: Text.AlignVCenter
                            horizontalAlignment: cell.numeric ? Text.AlignRight : Text.AlignLeft
                            visible: !cell.editing && !cell.checkable
                        }

                        // Edits go through the model, which refreshes the state shown here.
                        CheckBox {
                            anchors.centerIn: parent
                            visible: cell.checkable
                            enabled: cell.editable && root.editable
                            tristate: true
                            checkState: cell.checkState
                            nextCheckState: () => cell.checkState === Qt.Checked
                                ? Qt.Unchecked : Qt.Checked
                            onClicked: {
                                root.currentRow = cell.row
                                root.currentColumn = cell.column
                                root.model.toggleCheck(cell.row, cell.column)
                            }
                        }

                        TapHandler {
                            onSingleTapped: {
                                root.currentRow = cell.row
                                root.currentColumn = cell.column
                                root.forceActiveFocus()
                                // A group header folds on one click, like a tree row.
                                if (cell.groupRow && cell.column === 0)
                                    root.groupToggleRequested(cell.row)
                            }
                            onDoubleTapped: {
                                root.currentRow = cell.row
                                root.currentColumn = cell.column
                                if (!cell.groupRow)
                                    root.activateCell(cell.row, cell.column)
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


