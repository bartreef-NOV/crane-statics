import QtQuick
import QtQuick.Controls.Fusion
import BF.DesignSystem
import "components" as Components

/*!
    The editor a DataTable cell puts over itself while it is being edited.

    One editor serves every kind of authored field, because the table cannot know
    which column the operator will click: \c kind picks the control, \c initialValue
    seeds it and \c value reads back what was typed. Node references get the list of
    ids to offer in \c choices.

    Committing is guarded here rather than in the delegate, because Qt closes an
    editor for three different reasons and only two of them mean "keep this":
    Return commits, losing focus to another control commits, and Escape does not.
    Escape and Return both end with the editor losing focus, so without the guard a
    cancelled edit would be indistinguishable from an accepted one, and an accepted
    one would be written twice.

    The component library is imported qualified on purpose: it shadows \c ComboBox
    and \c TextField, and the node editor needs the Fusion combo box, whose content
    item an editable combo box replaces with a text input.
*/
FocusScope {
    id: root

    property string kind: "text"
    property var initialValue: ""
    property var choices: []

    readonly property var value: loader.item ? loader.item.cellValue : root.initialValue
    readonly property bool cancelled: root._cancelled

    property bool _cancelled: false
    property bool _committed: false

    signal commitRequested()

    implicitWidth: loader.implicitWidth
    implicitHeight: loader.implicitHeight

    function commit() {
        if (root._cancelled || root._committed)
            return
        root._committed = true
        root.commitRequested()
    }

    // Escape is left unaccepted so Qt still closes the editor; all this does is
    // record that the close must not write anything.
    function cancel() {
        root._cancelled = true
    }

    TableView.onCommit: root.commit()
    onActiveFocusChanged: if (!activeFocus) root.commit()

    Loader {
        id: loader
        anchors.fill: parent
        focus: true
        sourceComponent: {
            if (root.kind === "bool")
                return boolEditor
            if (root.kind === "node")
                return nodeEditor
            if (root.kind === "number")
                return numberEditor
            if (root.kind === "int")
                return intEditor
            return textEditor
        }
    }

    Component {
        id: textEditor
        Components.TextField {
            readonly property var cellValue: text
            focus: true
            text: root.initialText()
            Component.onCompleted: selectAll()
            Keys.onEscapePressed: event => root.cancelOn(event)
        }
    }

    Component {
        id: numberEditor
        NumberField {
            readonly property var cellValue: text
            focus: true
            text: root.initialText()
            Component.onCompleted: selectAll()
            Keys.onEscapePressed: event => root.cancelOn(event)
        }
    }

    Component {
        id: intEditor
        Components.TextField {
            readonly property var cellValue: text
            focus: true
            text: root.initialText()
            horizontalAlignment: TextInput.AlignRight
            validator: IntValidator { bottom: 0 }
            Component.onCompleted: selectAll()
            Keys.onEscapePressed: event => root.cancelOn(event)
        }
    }

    Component {
        id: boolEditor
        Components.StyledCheckBox {
            readonly property var cellValue: checked
            focus: true
            checked: root.initialValue === true
            Keys.onEscapePressed: event => root.cancelOn(event)
        }
    }

    Component {
        id: nodeEditor
        ComboBox {
            readonly property var cellValue: editText
            focus: true
            editable: true
            model: root.choices
            font.pixelSize: Typography.body
            Component.onCompleted: {
                const index = model ? model.indexOf(root.initialText()) : -1
                if (index >= 0)
                    currentIndex = index
                else
                    editText = root.initialText()
                // Typing has to reach the text input, not the combo box's own
                // keyboard search, since a rope may be reeved through a node the
                // list does not offer.
                contentItem.forceActiveFocus()
                contentItem.selectAll()
            }
            Keys.onEscapePressed: event => root.cancelOn(event)
        }
    }

    function initialText() {
        return root.initialValue === undefined || root.initialValue === null
            ? "" : String(root.initialValue)
    }

    function cancelOn(event) {
        root.cancel()
        event.accepted = false
    }
}
