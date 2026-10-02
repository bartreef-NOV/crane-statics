pragma Singleton

import QtQuick

QtObject {
    id: root

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
    // Semantic roles
    // ------------------------------------------------------------------------
    readonly property color primary: novBlue
    readonly property color primaryHover: Qt.lighter(novBlue, 112)
    readonly property color primaryPressed: Qt.darker(novBlue, 115)
    readonly property color primaryDisabled: Qt.lighter(novBlue, 170)
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

    readonly property color onSuccess: contrastText(success)
    readonly property color onWarning: contrastText(warning)
    readonly property color onError: contrastText(error)
    readonly property color onInfo: contrastText(info)

    readonly property color focusRing: novBlue
    readonly property color selection: novBlue50Tint
    readonly property color selectionText: text

    readonly property color overlay: Qt.rgba(0, 0, 0, 0.5)
    readonly property color shadowColor: Qt.rgba(0, 0, 0, 0.15)

    // ------------------------------------------------------------------------
    // Chart / scene-canvas semantic colors
    // ------------------------------------------------------------------------
    readonly property color chartCanvasBackground: pageBackground
    readonly property color chartPlotBackground: surface
    readonly property color chartGrid: Qt.lighter(novGrey, 160)
    readonly property color chartAxisText: textMuted
    readonly property color chartAxisBorder: border
    readonly property color chartCrosshair: textMuted
    readonly property color chartTooltipBackground: surface
    readonly property color chartTooltipBorder: border
    readonly property color chartTooltipText: text
    readonly property color chartSeriesFallback: textMuted
    readonly property color chartPass: success
    readonly property color chartFail: error
    readonly property color chartPending: warning
    readonly property color chartContractual: success

    // ------------------------------------------------------------------------
    // Helper functions
    // ------------------------------------------------------------------------
    function colorWithAlpha(baseColor, alpha) {
        return Qt.rgba(baseColor.r, baseColor.g, baseColor.b, alpha)
    }

    function relativeLuminance(baseColor) {
        function channel(value) {
            return value <= 0.03928 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * channel(baseColor.r) + 0.7152 * channel(baseColor.g) + 0.0722 * channel(baseColor.b)
    }

    function contrastText(background) {
        return relativeLuminance(background) > 0.4 ? black : white
    }

    function getSemanticColor(semantic) {
        switch (semantic) {
        case "success": return success
        case "warning": return warning
        case "error": return error
        case "info": return info
        case "primary": return primary
        default: return text
        }
    }

    function getOnSemanticColor(semantic) {
        switch (semantic) {
        case "success": return onSuccess
        case "warning": return onWarning
        case "error": return onError
        case "info": return onInfo
        case "primary": return onPrimary
        default: return textOnDark
        }
    }

    function getStatusColor(level) {
        if (level < 0.4) return success
        if (level < 0.7) return warning
        return error
    }
}
