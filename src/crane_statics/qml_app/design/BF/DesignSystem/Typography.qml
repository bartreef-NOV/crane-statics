pragma Singleton

import QtQuick

QtObject {
    readonly property string fontFamily: "Segoe UI, Ubuntu, 'Liberation Sans', sans-serif"
    readonly property string monoFamily: "'Consolas', 'Monaco', 'Courier New', monospace"

    readonly property int weightLight: 300
    readonly property int weightRegular: 400
    readonly property int weightMedium: 500
    readonly property int weightSemiBold: 600
    readonly property int weightBold: 700

    readonly property int caption: 11
    readonly property int body: 13
    readonly property int bodyLarge: 14
    readonly property int subtitle: 14
    readonly property int heading: 16
    readonly property int headingLarge: 18
    readonly property int display: 22

    readonly property real lineHeightTight: 1.2
    readonly property real lineHeightNormal: 1.5
    readonly property real lineHeightRelaxed: 1.8

    readonly property real letterSpacingNormal: 0
    readonly property real letterSpacingWide: 0.5
}
