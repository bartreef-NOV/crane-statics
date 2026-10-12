pragma Singleton

import QtQuick

QtObject {
    readonly property int spacing2: 2
    readonly property int spacing4: 4
    readonly property int spacing6: 6
    readonly property int spacing8: 8
    readonly property int spacing12: 12
    readonly property int spacing16: 16
    readonly property int spacing24: 24
    readonly property int spacing32: 32
    readonly property int spacing48: 48

    readonly property real spacingMultiplier: 1.0

    readonly property int controlHeight: 36
    readonly property int compactControlHeight: 30
    readonly property int buttonMinWidth: 96
    readonly property int fieldMinWidth: 160
    readonly property int minInputWidth: 60
    readonly property int maxInputWidth: 200
    readonly property int dialogWidth: 480

    readonly property int tableRowHeight: 28
    readonly property int compactRowHeight: 24

    readonly property int iconSmall: 16
    readonly property int iconNormal: 24
    readonly property int iconLarge: 32
    readonly property int iconXLarge: 48

    readonly property int radiusSmall: 3
    readonly property int radiusMedium: 5
    readonly property int radiusLarge: 8
    readonly property int borderWidth: 1
    readonly property int borderWidthNormal: 2
    readonly property int focusWidth: 2

    readonly property int fontSizeSmall: 12
    readonly property int fontSizeBody: 14
    readonly property int fontSizeSubtitle: 16
    readonly property int fontSizeTitle: 22

    readonly property int transitionFast: 100
    readonly property int transitionNormal: 200
    readonly property int transitionSlow: 300

    readonly property int breakpointCompact: 1240
    readonly property int breakpointUltraWide: 1800
}
