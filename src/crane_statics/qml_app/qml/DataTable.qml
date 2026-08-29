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
    activeFocusOnTab: true
    focus: true

    Accessible.role: Accessible.Table
    Accessible.name: root.title.length > 0 ? root.title : qsTr("Data table")

    signal addRequested()
    signal editRequested(int row)
    signal deleteRequested(int row)

    Keys.onPressed: event => {
        if (event.key === Qt.Key_Up) {
            root.currentRow = Math.max(0, root.currentRow < 0 ? 0 : root.currentRow - 1)
            event.accepted = true
        } else if (event.key === Qt.Key_Down) {
            root.currentRow = Math.min(table.rows - 1, root.currentRow + 1)
            event.accepted = true
        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            if (root.editable && root.hasSelection)
                root.editRequested(root.currentRow)
            event.accepted = true
        } else if (event.key === Qt.Key_Delete) {
            if (root.editable && root.hasSelection)
                root.deleteRequested(root.currentRow)
            event.accepted = true
        }
    }

    readonly property bool hasSelection: currentRow >= 0 && currentRow < table.rows

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
                iconText: "\u270e"
                tooltipText: qsTr("Edit")
                semantic: "secondary"
                visible: root.editable
                enabled: root.hasSelection
                onClicked: root.editRequested(root.currentRow)
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

                    onRowsChanged: if (root.currentRow >= rows) root.currentRow = -1

                    ScrollBar.vertical: ScrollBar {}
                    ScrollBar.horizontal: ScrollBar {}

                    delegate: Rectangle {
                        id: cell

                        required property string display
                        required property bool numeric
                        required property int row

                        readonly property bool selected: row === root.currentRow
                        property bool hovered: false

                        implicitWidth: Math.max(80, cellText.implicitWidth + 2 * 8)
                        implicitHeight: root.tableRowHeight
                        color: cell.selected
                            ? root.selectedColor
                            : (cell.hovered
                                ? Design.DesignTokens.colors.surfaceAlt
                                : (cell.row % 2 === 0
                                    ? root.surfaceColor
                                    : Design.DesignTokens.colors.surfaceAlt))

                        border.color: root.gridColor
                        border.width: 1

                        Label {
                            id: cellText
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 8
                            text: cell.display
                            color: cell.selected ? root.selectedTextColor : root.textColor
                            font.pixelSize: Design.DesignTokens.typography.body
                            elide: Text.ElideRight
                            verticalAlignment: Text.AlignVCenter
                            horizontalAlignment: cell.numeric ? Text.AlignRight : Text.AlignLeft
                        }

                        TapHandler {
                            onSingleTapped: {
                                root.currentRow = cell.row
                                root.forceActiveFocus()
                            }
                            onDoubleTapped: {
                                root.currentRow = cell.row
                                if (root.editable)
                                    root.editRequested(cell.row)
                            }
                        }

                        HoverHandler {
                            onHoveredChanged: cell.hovered = hovered
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


