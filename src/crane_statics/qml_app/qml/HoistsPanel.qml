import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts

/*  Hoist inputs as a list and a form: pick a hoist on the left, edit it on the right.
    Only the groups that apply to the selected hoist are shown -- the boom hoist owns a
    rope and nothing else, and the split-mode fields appear only for a splittable block.
    The hoist's rope segments and load chart follow the form, so one tab holds everything
    that belongs to a hoist.
    Every edit commits on its own through modelVm.setHoistField, the same validated path
    the Add dialog uses. */
RowLayout {
    id: root

    readonly property int layoutSpacing: Math.round(
        8
    )
    // The selected hoist's authored values, re-read whenever the document changes.
    property var fields: ({})
    readonly property int hoistRow: hoistList.currentIndex
    readonly property bool hasHoist: hoistRow >= 0 && fields.id !== undefined
    readonly property bool isBoom: hasHoist && !!fields.is_boom_hoist
    readonly property bool isPayload: hasHoist && !fields.is_boom_hoist

    signal addRequested()
    signal addSegmentRequested()
    signal addContractualPointRequested()

    spacing: root.layoutSpacing

    function reload() {
        fields = hoistRow >= 0 ? modelVm.hoistFields(hoistRow) : ({})
    }

    function syncSelection() {
        const list = modelVm.hoistList
        const index = list.findIndex(h => h.id === modelVm.selectedHoistId)
        if (index !== hoistList.currentIndex)
            hoistList.currentIndex = index
        reload()
    }

    function commit(field, value) {
        if (hoistRow >= 0)
            modelVm.setHoistField(hoistRow, field, value)
    }

    Component.onCompleted: syncSelection()

    Connections {
        target: modelVm
        function onHoistsChanged() { root.syncSelection() }
        function onSelectedHoistChanged() { root.syncSelection() }
    }

    /*  One labelled number input. An empty field commits as "unset" when nullable. */
    component NumberRow: RowLayout {
        id: numberRow

        property string label: ""
        property string fieldKey: ""
        property int decimals: 3
        property bool nullable: false

        Layout.fillWidth: true
        spacing: root.layoutSpacing

        function show() {
            const v = root.fields[numberRow.fieldKey]
            if (v === null || v === undefined)
                numberField.clear()
            else
                numberField.setValue(v)
        }

        Label {
            Layout.fillWidth: true
            text: numberRow.label
            elide: Text.ElideRight
        }

        NumberField {
            id: numberField
            objectName: "hoistField_" + numberRow.fieldKey
            Layout.preferredWidth: 110
            decimals: numberRow.decimals
            onEditingFinished: {
                if (numberRow.nullable && numberField.text.trim() === "")
                    root.commit(numberRow.fieldKey, "")
                else
                    root.commit(numberRow.fieldKey, numberField.value)
            }
        }

        Connections {
            target: root
            function onFieldsChanged() {
                if (!numberField.activeFocus)
                    numberRow.show()
            }
        }
        Component.onCompleted: show()
    }

    component IntRow: RowLayout {
        id: intRow

        property string label: ""
        property string fieldKey: ""
        property int maximum: 99

        Layout.fillWidth: true
        spacing: root.layoutSpacing

        Label {
            Layout.fillWidth: true
            text: intRow.label
            elide: Text.ElideRight
        }

        SpinBox {
            id: intSpin
            objectName: "hoistField_" + intRow.fieldKey
            Layout.preferredWidth: 110
            from: 1
            to: intRow.maximum
            editable: true
            value: root.fields[intRow.fieldKey] || 1
            onValueModified: root.commit(intRow.fieldKey, value)
        }
    }

    ColumnLayout {
        Layout.preferredWidth: 220
        Layout.fillHeight: true
        spacing: root.layoutSpacing

        ListView {
            id: hoistList
            objectName: "hoistList"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: modelVm.hoistList
            currentIndex: -1
            boundsBehavior: Flickable.StopAtBounds

            delegate: ItemDelegate {
                required property int index
                required property var modelData

                width: ListView.view.width
                text: modelData.isBoom ? qsTr("%1 (boom hoist)").arg(modelData.id) : modelData.id
                highlighted: ListView.isCurrentItem
                onClicked: modelVm.selectHoist(modelData.id)
            }

            Label {
                anchors.centerIn: parent
                visible: hoistList.count === 0
                text: qsTr("No hoists defined.")
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: root.layoutSpacing

            Button {
                Layout.fillWidth: true
                text: qsTr("Add Hoist…")
                onClicked: root.addRequested()
            }

            Button {
                Layout.fillWidth: true
                text: qsTr("Delete")
                enabled: root.isPayload
                onClicked: modelVm.deleteHoist(root.hoistRow)
            }
        }
    }

    ScrollView {
        id: formScroll
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: formScroll.availableWidth
            spacing: root.layoutSpacing

            Label {
                visible: root.hasHoist
                text: root.isBoom ? qsTr("%1 - boom hoist").arg(root.fields.id) : (root.fields.id || "")
                font.bold: true
            }

            GroupBox {
                Layout.fillWidth: true
                visible: root.isPayload
                title: qsTr("Hook")

                ColumnLayout {
                    anchors.fill: parent
                    spacing: root.layoutSpacing

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: root.layoutSpacing

                        Label { Layout.fillWidth: true; text: qsTr("Support Node") }
                        ComboBox {
                            objectName: "hoistField_support_node_id"
                            Layout.preferredWidth: 160
                            editable: true
                            model: modelVm.editableNodeIds
                            currentIndex: model.indexOf(root.fields.support_node_id)
                            onActivated: root.commit("support_node_id", currentText)
                        }
                    }

                    IntRow { label: qsTr("Falls"); fieldKey: "falls" }
                    NumberRow { label: qsTr("Hook Mass (t)"); fieldKey: "hook_mass_t" }
                    NumberRow { label: qsTr("DAF"); fieldKey: "hook_daf" }
                }
            }

            GroupBox {
                Layout.fillWidth: true
                visible: root.isPayload
                title: qsTr("Leads")

                ColumnLayout {
                    anchors.fill: parent
                    spacing: root.layoutSpacing

                    NumberRow { label: qsTr("Offlead (deg)"); fieldKey: "offlead_deg" }
                    NumberRow { label: qsTr("Sidelead (deg)"); fieldKey: "sidelead_deg" }
                }
            }

            GroupBox {
                Layout.fillWidth: true
                visible: root.hasHoist
                title: qsTr("Rope")

                ColumnLayout {
                    anchors.fill: parent
                    spacing: root.layoutSpacing

                    NumberRow { label: qsTr("Linear Mass (kg/m)"); fieldKey: "linear_mass_kg_m" }
                    NumberRow {
                        visible: root.isPayload
                        label: qsTr("Lowest Hook Height (m)")
                        fieldKey: "lowest_hook_height_m"
                    }
                    // Only the boom hoist authors a rope length; a payload hoist derives it.
                    NumberRow {
                        visible: root.isBoom
                        label: qsTr("Rope Length (m)")
                        fieldKey: "rope_length_m"
                        nullable: true
                    }
                }
            }

            GroupBox {
                Layout.fillWidth: true
                visible: root.isPayload
                title: qsTr("Split Mode")

                ColumnLayout {
                    anchors.fill: parent
                    spacing: root.layoutSpacing

                    CheckBox {
                        objectName: "hoistField_splitable_block"
                        text: qsTr("Splittable block")
                        checked: !!root.fields.splitable_block
                        onToggled: root.commit("splitable_block", checked)
                    }

                    IntRow {
                        visible: !!root.fields.splitable_block
                        label: qsTr("Split Falls")
                        fieldKey: "split_falls"
                        maximum: Math.max(1, root.fields.falls || 1)
                    }
                    NumberRow {
                        visible: !!root.fields.splitable_block
                        label: qsTr("Split Hook Mass (t)")
                        fieldKey: "split_hook_mass_t"
                    }
                }
            }

            DataTable {
                Layout.fillWidth: true
                Layout.preferredHeight: 220
                visible: root.hasHoist
                title: qsTr("Rope Segments")
                emptyText: qsTr("No rope segments for this hoist.")
                editable: true
                model: modelVm.ropeSegmentsModel
                editorChoices: modelVm.editableNodeIds
                onAddRequested: root.addSegmentRequested()
                onDeleteRequested: row => modelVm.deleteRopeSegment(row)
            }

            // The boom hoist has no hook, so no load chart.
            RowLayout {
                Layout.fillWidth: true
                spacing: root.layoutSpacing
                visible: root.isPayload && modelVm.hoistSplitable

                Label { text: qsTr("Hook Configuration") }

                Button {
                    text: qsTr("Normal")
                    checkable: true
                    checked: modelVm.contractualMode === "normal"
                    onClicked: modelVm.setContractualMode("normal")
                }

                Button {
                    text: qsTr("Split")
                    checkable: true
                    checked: modelVm.contractualMode === "split"
                    onClicked: modelVm.setContractualMode("split")
                }

                Item { Layout.fillWidth: true }
            }

            DataTable {
                Layout.fillWidth: true
                Layout.preferredHeight: 220
                visible: root.isPayload
                title: qsTr("Load Chart")
                emptyText: qsTr("No contractual points for this hoist.")
                editable: true
                model: modelVm.contractualModel
                onAddRequested: root.addContractualPointRequested()
                onDeleteRequested: row => modelVm.deleteContractualPoint(row)
            }
        }
    }
}
