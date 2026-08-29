import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import "../design" as Design

RowLayout {
    id: root

    property string label: ""
    property real from: -1e9
    property real to: 1e9
    property real value: 0
    property int decimals: 3
    property bool flippable: false
    property bool inputEnabled: true

    signal committed(real newValue)

    Accessible.role: Accessible.Grouping
    Accessible.name: root.label
    Accessible.description: qsTr("Numeric input")

    spacing: Math.round(Design.DesignTokens.spacing.sm * Design.DesignTokens.layout.spacingMultiplier)

    onValueChanged: if (!field.activeFocus) field.setValue(value)
    Component.onCompleted: field.setValue(value)

    Label {
        Layout.fillWidth: true
        Layout.minimumHeight: Math.max(Design.DesignTokens.sizing.inputHeightSmall, implicitHeight)
        Layout.maximumHeight: Math.round(42 * Design.DesignTokens.layout.spacingMultiplier)
        text: root.label
        wrapMode: Text.WordWrap
    }

    NumberField {
        id: field
        Layout.preferredWidth: 96
        decimals: root.decimals
        enabled: root.inputEnabled
        Accessible.name: root.label

        function commit() {
            const clamped = Math.max(root.from, Math.min(root.to, value))
            setValue(clamped)
            root.committed(clamped)
        }

        flippable: root.flippable
        onFlipDirectionRequested: {
            setValue(-value)
            commit()
        }
        onEditingFinished: commit()
    }
}


