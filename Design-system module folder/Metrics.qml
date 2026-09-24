pragma Singleton

import QtQuick

QtObject {
    readonly property int spacing2: 2
    readonly property int spacing4: 4
    readonly property int spacing8: 8
    readonly property int spacing12: 12
    readonly property int spacing16: 16
    readonly property int spacing24: 24
    readonly property int spacing32: 32

    readonly property int controlHeight: 36
    readonly property int compactControlHeight: 30
    readonly property int buttonMinWidth: 96
    readonly property int fieldMinWidth: 160

    readonly property int radiusSmall: 3
    readonly property int radiusMedium: 5
    readonly property int radiusLarge: 8
    readonly property int borderWidth: 1
    readonly property int focusWidth: 2

    readonly property int fontSizeSmall: 12
    readonly property int fontSizeBody: 14
    readonly property int fontSizeSubtitle: 16
    readonly property int fontSizeTitle: 22
}
