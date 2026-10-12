pragma Singleton

import QtQuick

/**
 * Theme
 *
 * The app's UI chrome now comes from the native Qt Quick Controls style
 * (Fusion) and SystemPalette, not from this singleton. Theme only still
 * supplies colors for the two custom-painted (non-Controls) surfaces: the
 * Load Chart canvas (QuickChartPlot.qml) and the 3D scene canvas
 * (scene/QuickSceneCanvas.qml), plus the brand-accent utilization bar in
 * ResultRowDelegate.qml.
 */
QtObject {
    // ------------------------------------------------------------------------
    // BF / NOV raw palette (only entries a kept semantic token still depends on)
    // ------------------------------------------------------------------------
    readonly property color novBlue: "#007096"
    readonly property color novGrey: "#78757B"
    readonly property color novPurple50Tint: "#CCC1D4"
    readonly property color novGreen: "#A9C47F"
    readonly property color novRed: "#DA291C"
    readonly property color novOrange: "#DC9575"
    readonly property color novTeal: "#00A499"

    readonly property color black: "#000000"
    readonly property color white: "#FFFFFF"

    // ------------------------------------------------------------------------
    // Semantic roles
    // ------------------------------------------------------------------------
    readonly property color primary: novBlue

    readonly property color pageBackground: white
    readonly property color surface: white
    readonly property color surfaceSubtle: novPurple50Tint
    readonly property color border: novGrey
    readonly property color borderSubtle: novPurple50Tint

    readonly property color text: black
    readonly property color textMuted: novGrey

    readonly property color success: novGreen
    readonly property color warning: novOrange
    readonly property color error: novRed
    readonly property color info: novTeal

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
}
