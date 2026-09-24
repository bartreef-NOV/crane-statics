pragma Singleton

import QtQuick

QtObject {
    // ------------------------------------------------------------------------
    // BF / NOV raw palette
    // ------------------------------------------------------------------------
    readonly property color novYellow50Tint: "#FFE592"
    readonly property color novOrange: "#DC9575"
    readonly property color novOrange50Tint: "#F6CDB3"
    readonly property color novYellow: "#FFCD00"
    readonly property color novPurple50Tint: "#CCC1D4"
    readonly property color novRed: "#DA291C"
    readonly property color novGrey: "#78757B"
    readonly property color novGreen: "#A9C47F"
    readonly property color novTeal: "#00A499"
    readonly property color novBlue: "#007096"
    readonly property color novBrown: "#C6A992"
    readonly property color novDarkRed: "#A6093D"
    readonly property color novGreen50Tint: "#D4E0BD"
    readonly property color novTeal50Tint: "#82CEC9"
    readonly property color novBlue50Tint: "#82B4C9"
    readonly property color novBrown50Tint: "#E3D2C6"
    readonly property color novDarkRed50Tint: "#D18488"
    readonly property color novPurple: "#A192B2"

    readonly property color black: "#000000"
    readonly property color white: "#FFFFFF"

    // ------------------------------------------------------------------------
    // Semantic roles used by the shared controls
    // ------------------------------------------------------------------------
    readonly property color primary: novBlue
    readonly property color primaryHover: Qt.lighter(novBlue, 112)
    readonly property color primaryPressed: Qt.darker(novBlue, 115)
    readonly property color onPrimary: white

    readonly property color accent: novYellow
    readonly property color accentHover: Qt.lighter(novYellow, 108)
    readonly property color accentPressed: Qt.darker(novYellow, 110)
    readonly property color onAccent: black

    readonly property color pageBackground: white
    readonly property color surface: white
    readonly property color surfaceSubtle: novPurple50Tint
    readonly property color border: novGrey
    readonly property color borderSubtle: novPurple50Tint

    readonly property color text: black
    readonly property color textMuted: novGrey
    readonly property color textOnDark: white
    readonly property color disabledSurface: Qt.lighter(novGrey, 155)
    readonly property color disabledText: Qt.lighter(novGrey, 120)

    readonly property color success: novGreen
    readonly property color successSurface: novGreen50Tint
    readonly property color warning: novOrange
    readonly property color warningSurface: novOrange50Tint
    readonly property color error: novRed
    readonly property color errorSurface: novDarkRed50Tint
    readonly property color info: novTeal
    readonly property color infoSurface: novTeal50Tint

    readonly property color focusRing: novBlue
    readonly property color selection: novBlue50Tint
}
