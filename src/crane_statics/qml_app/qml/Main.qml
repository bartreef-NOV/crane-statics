import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Dialogs
import QtQuick.Layouts

ApplicationWindow {
    id: window
    width: 1400
    height: 900
    visible: true
    title: appVm.title

    // Action deferred until the unsaved-changes prompt is answered.
    property string pendingAction: ""
    property bool closeApproved: false

    function runGuarded(action) {
        if (!appVm.dirty) {
            window.perform(action)
            return
        }
        pendingAction = action
        unsavedDialog.open()
    }

    function perform(action) {
        if (action === "new")
            appVm.newDocument()
        else if (action === "open")
            openDialog.open()
        else if (action === "close")
            appVm.closeDocument()
        else if (action === "quit")
            Qt.quit()
    }

    onClosing: close => {
        if (window.closeApproved) {
            window.closeApproved = false
        } else if (appVm.dirty) {
            close.accepted = false
            runGuarded("quit")
        }
    }

    menuBar: MenuBar {
        Menu {
            title: qsTr("&File")
            Action { text: qsTr("&New"); shortcut: StandardKey.New; onTriggered: window.runGuarded("new") }
            Action { text: qsTr("&Open..."); shortcut: StandardKey.Open; onTriggered: window.runGuarded("open") }
            MenuSeparator {}
            Action {
                text: qsTr("&Save")
                shortcut: StandardKey.Save
                enabled: appVm.hasDocument
                onTriggered: appVm.currentPath.length > 0 ? appVm.save() : saveDialog.open()
            }
            Action {
                text: qsTr("Save &As...")
                shortcut: StandardKey.SaveAs
                enabled: appVm.hasDocument
                onTriggered: saveDialog.open()
            }
            Action {
                text: qsTr("&Close")
                shortcut: StandardKey.Close
                enabled: appVm.hasDocument
                onTriggered: window.runGuarded("close")
            }
            MenuSeparator {}
            Action { text: qsTr("E&xit"); shortcut: StandardKey.Quit; onTriggered: window.runGuarded("quit") }
        }

        Menu {
            title: qsTr("&View")
            Action {
                text: qsTr("&Reset Layout")
                enabled: appVm.hasDocument
                onTriggered: appVm.resetLayout()
            }
        }
    }

    header: TabBar {
        id: workspaceTabs
        objectName: "workspaceTabs"
        visible: appVm.hasDocument

        TabButton { text: qsTr("Scene"); Layout.fillWidth: true }
        TabButton { text: qsTr("Load Chart"); Layout.fillWidth: true }
        TabButton { text: qsTr("Model"); Layout.fillWidth: true }
    }

    StackLayout {
        anchors.fill: parent
        currentIndex: appVm.hasDocument ? 1 : 0

        NoDocumentPage {
            onOpenRequested: window.runGuarded("open")
            onNewRequested: window.runGuarded("new")
        }

        StackLayout {
            currentIndex: workspaceTabs.currentIndex

            Loader { active: appVm.hasDocument; sourceComponent: sceneComponent }
            Loader { active: appVm.hasDocument; sourceComponent: chartComponent }
            Loader { active: appVm.hasDocument; sourceComponent: modelComponent }
        }
    }

    footer: ToolBar {
        implicitHeight: 24
        Label {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 8
            anchors.rightMargin: 8
            text: appVm.statusText
            elide: Text.ElideRight
        }
    }

    Component { id: sceneComponent; SceneWorkspace {} }
    Component { id: chartComponent; LoadChartWorkspace {} }
    Component { id: modelComponent; ModelWorkspace {} }

    FileDialog {
        id: openDialog
        title: qsTr("Open Crane Model")
        nameFilters: [qsTr("Crane Model Files (*.json *.yaml *.yml)"), qsTr("JSON Files (*.json)"), qsTr("YAML Files (*.yaml *.yml)"), qsTr("All Files (*)")]
        onAccepted: appVm.open(selectedFile)
    }

    FileDialog {
        id: saveDialog
        title: qsTr("Save Crane Model As")
        fileMode: FileDialog.SaveFile
        defaultSuffix: "yaml"
        nameFilters: [qsTr("YAML Files (*.yaml *.yml)"), qsTr("JSON Files (*.json)"), qsTr("All Files (*)")]
        onAccepted: {
            const saved = appVm.saveAs(selectedFile)
            if (!saved) {
                window.pendingAction = ""
                return
            }
            if (window.pendingAction === "")
                return
            const action = window.pendingAction
            window.pendingAction = ""
            window.perform(action)
        }
        onRejected: window.pendingAction = ""
    }

    MessageDialog {
        id: unsavedDialog
        title: qsTr("Unsaved Changes")
        text: qsTr("Save changes before closing?")
        buttons: MessageDialog.Save | MessageDialog.Discard | MessageDialog.Cancel

        onButtonClicked: (button, role) => {
            if (button === MessageDialog.Cancel) {
                window.pendingAction = ""
                return
            }
            if (button === MessageDialog.Discard && window.pendingAction === "quit")
                window.closeApproved = true
            if (button === MessageDialog.Save) {
                if (appVm.currentPath.length === 0) {
                    saveDialog.open()
                    return
                }
                if (!appVm.save())
                    return
            }
            const action = window.pendingAction
            window.pendingAction = ""
            window.perform(action)
        }
    }

    MessageDialog {
        id: errorDialog
        title: qsTr("Crane Statics")
        buttons: MessageDialog.Ok
    }

    Connections {
        target: appVm

        function onNotification(message, level) {
            if (level === "error") {
                errorDialog.text = message
                errorDialog.open()
            } else {
                appVm.setStatusText(message)
            }
        }

        function onLayoutResetRequested() {
            workspaceTabs.currentIndex = 0
        }
    }

    Connections {
        target: sceneVm
        function onStatusMessage(message) {
            appVm.setStatusText(message)
        }
    }

    Connections {
        target: chartVm
        // A governing case was applied to the Scene: show it (the Scene is tab 0).
        function onShowSceneRequested() {
            workspaceTabs.currentIndex = 0
        }
    }
}


