pragma Singleton
import QtQuick
import QtQuick.Controls.Fusion

/**
 * DesignTokens Singleton
 *
 * Central source of truth for all visual design properties in the Crane Statics
 * application. All tokens bind to SystemPalette for automatic light/dark theme
 * support via Fusion style.
 *
 * Usage:
 *   import Crane.DesignTokens 1.0
 *   // or
 *   import "path/to/design" as Design
 *   
 *   Rectangle {
 *       color: DesignTokens.colors.surface
 *       width: DesignTokens.sizing.buttonHeight
 *       anchors.margins: DesignTokens.spacing.md
 *       font.pixelSize: DesignTokens.typography.body
 *   }
 *
 * Token Categories:
 * - colors:       Semantic color roles for UI surfaces, text, borders, states
 * - typography:   Font families, sizes, weights, and line-height ratios
 * - spacing:      Consistent spacing scale (4px base unit) for margins, gaps, padding
 * - sizing:       Control dimensions (button height, input height, table row height, etc.)
 * - shadows:      Elevation levels for modals, cards, tooltips
 * - border:       Border widths and radius values
 * - transitions:  Animation durations for theme switching and interactions
 * - layout:       Responsive breakpoints
 */

Item {
    id: root

    // "system" delegates to Fusion/SystemPalette; explicit schemes use the
    // deterministic semantic palettes below so manual overrides affect QML.
    property string colorScheme: "system"

    // System palette for automatic light/dark theme binding
    SystemPalette {
        id: systemPalette
        colorGroup: SystemPalette.Active
    }

    /**
     * COLORS: Semantic roles for UI elements
     * All bind to SystemPalette for automatic light/dark theme support.
     * Values in Light mode and Dark mode are managed by Fusion's built-in palettes.
     */
    readonly property QtObject colors: QtObject {
        // Surface & Container colors
        readonly property color surface: root.colorScheme === "dark" ? "#24282d" : (root.colorScheme === "light" ? "#ffffff" : systemPalette.base)
        readonly property color surfaceAlt: root.colorScheme === "dark" ? "#30363d" : (root.colorScheme === "light" ? "#f2f4f6" : systemPalette.button)
        readonly property color background: root.colorScheme === "dark" ? "#1b1e22" : (root.colorScheme === "light" ? "#f7f8fa" : systemPalette.window)
        readonly property color chartCanvasBackground: root.colorScheme === "dark" ? "#1b1e22" : (root.colorScheme === "light" ? "#f7f8fa" : systemPalette.window)
        readonly property color chartPlotBackground: root.colorScheme === "dark" ? "#15181c" : (root.colorScheme === "light" ? "#ffffff" : systemPalette.base)
        readonly property color chartGrid: root.colorScheme === "dark" ? "#35404a" : (root.colorScheme === "light" ? "#cbd5e1" : systemPalette.midlight)
        readonly property color chartAxisText: root.colorScheme === "dark" ? "#c4cdd6" : (root.colorScheme === "light" ? "#4b5563" : systemPalette.text)
        readonly property color chartAxisBorder: root.colorScheme === "dark" ? "#697783" : (root.colorScheme === "light" ? "#b8bdc7" : systemPalette.mid)
        readonly property color chartCrosshair: root.colorScheme === "dark" ? "#aebbc7" : (root.colorScheme === "light" ? "#667085" : systemPalette.mid)
        readonly property color chartTooltipBackground: root.colorScheme === "dark" ? "#24282d" : (root.colorScheme === "light" ? "#ffffff" : systemPalette.base)
        readonly property color chartTooltipBorder: root.colorScheme === "dark" ? "#5a6570" : (root.colorScheme === "light" ? "#98a2b3" : systemPalette.mid)
        readonly property color chartTooltipText: root.colorScheme === "dark" ? "#f1f3f5" : (root.colorScheme === "light" ? "#1f2937" : systemPalette.text)
        readonly property color chartSeriesFallback: root.colorScheme === "dark" ? "#d5dde5" : (root.colorScheme === "light" ? "#7a7a7a" : systemPalette.mid)
        readonly property color chartPass: root.colorScheme === "dark" ? "#66bb6a" : "#198754"
        readonly property color chartFail: root.colorScheme === "dark" ? "#ef7775" : "#c0392b"
        readonly property color chartPending: root.colorScheme === "dark" ? "#f0b35a" : "#b07a00"
        readonly property color chartContractual: root.colorScheme === "dark" ? "#66bb6a" : colors.success
        readonly property color overlay: Qt.rgba(0, 0, 0, root.colorScheme === "dark" ? 0.68 : 0.5)

        // Text colors (hierarchy)
        readonly property color textPrimary: root.colorScheme === "dark" ? "#f1f3f5" : (root.colorScheme === "light" ? "#202428" : systemPalette.text)
        readonly property color textSecondary: root.colorScheme === "dark" ? "#b8c0c8" : (root.colorScheme === "light" ? "#5d6670" : systemPalette.mid)
        readonly property color textDisabled: root.colorScheme === "dark" ? "#727b84" : (root.colorScheme === "light" ? "#9aa2aa" : systemPalette.midlight)
        readonly property color textInverse: root.colorScheme === "dark" ? "#101316" : (root.colorScheme === "light" ? "#ffffff" : systemPalette.highlightedText)

        // Interactive state colors
        readonly property color primary: root.colorScheme === "dark" ? "#68b5e8" : (root.colorScheme === "light" ? "#1769aa" : systemPalette.highlight)
        readonly property color primaryHover: root.colorScheme === "dark" ? "#8bcaf0" : (root.colorScheme === "light" ? "#0f568d" : Qt.darker(systemPalette.highlight, 1.15))
        readonly property color primaryPressed: root.colorScheme === "dark" ? "#4398cc" : (root.colorScheme === "light" ? "#0b426d" : Qt.darker(systemPalette.highlight, 1.3))
        readonly property color primaryDisabled: root.colorScheme === "dark" ? "#4d5963" : (root.colorScheme === "light" ? "#b8c1c9" : systemPalette.midlight)

        // Semantic colors
        readonly property color success: root.colorScheme === "dark" ? "#66bb6a" : "#2e7d32"      // Success, valid state
        readonly property color successAlt: root.colorScheme === "dark" ? "#81c995" : "#66bb6a"   // Light success
        readonly property color warning: root.colorScheme === "dark" ? "#f0b35a" : "#a35f00"       // Warning, caution state
        readonly property color warningAlt: root.colorScheme === "dark" ? "#f5c988" : "#f0a000"    // Light warning
        readonly property color error: root.colorScheme === "dark" ? "#ef7775" : "#c62828"         // Error, invalid state
        readonly property color errorAlt: root.colorScheme === "dark" ? "#f2a19f" : "#e57373"      // Light error
        readonly property color info: root.colorScheme === "dark" ? "#5c9ce6" : "#1565c0"          // Information state
        readonly property color infoAlt: root.colorScheme === "dark" ? "#8bc0f0" : "#42a5f5"       // Light info

        // Borders & dividers
        readonly property color border: root.colorScheme === "dark" ? "#5a6570" : (root.colorScheme === "light" ? "#c6cdd3" : systemPalette.mid)
        readonly property color borderLight: root.colorScheme === "dark" ? "#414a53" : (root.colorScheme === "light" ? "#e1e5e8" : systemPalette.midlight)
        readonly property color divider: root.colorScheme === "dark" ? "#414a53" : (root.colorScheme === "light" ? "#e1e5e8" : systemPalette.midlight)

        // Focus & highlight
        readonly property color focusRing: colors.primary
        readonly property color selection: colors.primary
        readonly property color selectionText: colors.textInverse
    }

    /**
     * TYPOGRAPHY: Font sizes, families, weights, and line-height
     * Based on a 16px base (system default). All pixel sizes are in logical pixels (pt).
     */
    readonly property QtObject typography: QtObject {
        // Font family (cross-platform)
        readonly property string fontFamily: "Segoe UI, Ubuntu, 'Liberation Sans', sans-serif"
        readonly property string monoFamily: "'Consolas', 'Monaco', 'Courier New', monospace"

        // Font weights
        readonly property int weightLight: 300
        readonly property int weightRegular: 400
        readonly property int weightMedium: 500
        readonly property int weightSemiBold: 600
        readonly property int weightBold: 700

        // Font sizes (logical pixels, scales with system DPI)
        readonly property int caption: 11      // Small labels, help text
        readonly property int body: 13         // Body text, default
        readonly property int bodyLarge: 14    // Larger body text
        readonly property int subtitle: 14     // Subtitles, secondary headings
        readonly property int heading: 16      // Section headings
        readonly property int headingLarge: 18 // Major headings, titles
        readonly property int display: 22      // Large display titles

        // Line height (as pixel offset, not multiplier)
        readonly property real lineHeightTight: 1.2   // Headings
        readonly property real lineHeightNormal: 1.5  // Body text
        readonly property real lineHeightRelaxed: 1.8 // Help text, descriptions

        // Letter spacing (in logical pixels)
        readonly property real letterSpacingNormal: 0
        readonly property real letterSpacingWide: 0.5
    }

    /**
     * SPACING: Consistent scale for margins, padding, gaps
     * Base unit: 4px. Tokens: xs=4, sm=8, md=16, lg=24, xl=32, xxl=48
     * Use these instead of magic numbers for all layout spacing.
     */
    readonly property QtObject spacing: QtObject {
        readonly property int xs: 4        // Tight spacing (borders, minimal gaps)
        readonly property int sm: 8        // Small spacing (compact form fields)
        readonly property int md: 16       // Medium spacing (standard margins, panel padding)
        readonly property int lg: 24       // Large spacing (section gaps, major layout)
        readonly property int xl: 32       // Extra large spacing (workspace separation)
        readonly property int xxl: 48      // Double extra large (major page sections)

        // Common grouped spacings
        readonly property int controlGap: 8        // Gap between inline controls
        readonly property int rowGap: 8            // Gap between form rows
        readonly property int sectionGap: 16       // Gap between major sections
        readonly property int panelPadding: 12     // Padding inside panels/cards
        readonly property int dialogPadding: 16    // Padding inside dialogs
        readonly property int compact: 6           // Table cell / group box padding
        readonly property int hairline: 2          // Bottom padding under a single-line cell
    }

    /**
     * SIZING: Dimensions for common control types
     * Ensures consistent proportions across the UI.
     */
    readonly property QtObject sizing: QtObject {
        // Control heights (in pixels)
        readonly property int buttonHeight: 32        // Standard button height
        readonly property int buttonHeightSmall: 24   // Compact button height
        readonly property int inputHeight: 32         // Text input, combo box, spinner
        readonly property int inputHeightSmall: 24    // Compact input field
        readonly property int rowHeight: 28           // Table/list row height
        readonly property int rowHeightCompact: 24    // Table row in compact mode
        readonly property int rowHeightRelaxed: 32    // Table row in relaxed mode

        // Control widths
        readonly property int minInputWidth: 60       // Minimum input field width
        readonly property int maxInputWidth: 200      // Maximum single-value input width
        readonly property int dialogWidth: 480        // Standard overview/dialog width
        readonly property int minButtonWidth: 80      // Minimum button width

        // Icon sizes
        readonly property int iconSmall: 16           // Small inline icons
        readonly property int iconNormal: 24          // Standard icon size
        readonly property int iconLarge: 32           // Large standalone icons
        readonly property int iconXLarge: 48          // Extra large icons

        // Border widths
        readonly property int borderThin: 1
        readonly property int borderNormal: 2
        readonly property int borderThick: 3

        // Corner radius
        readonly property int radiusNone: 0
        readonly property int radiusSmall: 2
        readonly property int radiusNormal: 4
        readonly property int radiusLarge: 8
    }

    /**
     * SHADOWS: Elevation levels for visual hierarchy
     * Used for modals, popovers, tooltips, and floating elements.
     */
    readonly property QtObject shadows: QtObject {
        // Elevation 1: Subtle shadow (hover states, subtle elevation)
        readonly property list<real> elevation1: [0, 1, 3, 0.12]  // [offsetX, offsetY, blur, opacity]

        // Elevation 2: Medium shadow (cards, popovers)
        readonly property list<real> elevation2: [0, 2, 6, 0.15]

        // Elevation 3: Strong shadow (modals, tooltips)
        readonly property list<real> elevation3: [0, 4, 12, 0.20]

        // Helper function to apply shadow via DropShadow
        function getShadowColor() {
            return Qt.rgba(0, 0, 0, 0.15)  // Uses opacity from elevation levels
        }
    }

    /**
     * BORDER: Border and corner radius tokens
     */
    readonly property QtObject border: QtObject {
        readonly property int widthThin: 1
        readonly property int widthNormal: 2
        readonly property int radiusNone: 0
        readonly property int radiusSmall: 2
        readonly property int radiusNormal: 4
        readonly property int radiusLarge: 8
        readonly property int radiusRound: 20  // For pill buttons, badges
    }

    /**
     * TRANSITIONS: Animation durations for interactions and theme changes
     * (in milliseconds)
     */
    readonly property QtObject transitions: QtObject {
        readonly property int fast: 100         // Quick feedback (hover, focus)
        readonly property int normal: 200       // Standard interaction (opacity, position)
        readonly property int slow: 300         // Deliberate animation (modal entrance)
        readonly property int theme: 400        // Theme switching duration

        // Easing curves (used with Transition animations)
        // Use: easing.type: Easing.InOutQuad for smooth motion
        readonly property int easingType: Easing.InOutQuad
    }

    /**
     * LAYOUT: Responsive breakpoints
     * Workspace layout adapts based on window width.
     */
    readonly property QtObject layout: QtObject {
        // Responsive breakpoints (in logical pixels)
        readonly property int breakpointCompact: 1240    // < 1240px → 1-column layout
        readonly property int breakpointWide: 1240       // ≥ 1240px → 2-column layout
        readonly property int breakpointUltraWide: 1800  // ≥ 1800px → 3-column or data-dense tables

        // Row height and spacing are fixed; the multipliers remain as the seam
        // callers already multiply through, so they are simply unity.
        readonly property real rowHeightMultiplier: 1.0
        readonly property real spacingMultiplier: 1.0

        readonly property int tableRowHeight: sizing.rowHeight
        readonly property int effectiveSpacing: spacing.md
    }

    /**
     * Convenience function: Apply a color overlay tint
     * Usage: colorWithAlpha(colors.primary, 0.5) → color with 50% alpha
     */
    function colorWithAlpha(color, alpha) {
        return Qt.rgba(color.r, color.g, color.b, alpha)
    }

    /**
     * Convenience function: Get a semantic color by name (for dynamic binding)
     * Usage: getSemanticColor("success") → colors.success
     */
    function getSemanticColor(semantic) {
        switch (semantic) {
            case "success": return colors.success
            case "warning": return colors.warning
            case "error": return colors.error
            case "info": return colors.info
            case "primary": return colors.primary
            default: return colors.textPrimary
        }
    }

    /**
     * Convenience function: Get a status color based on numeric level
     * Useful for crane loading analysis (stress levels, capacity usage)
     * Level: 0-1 (0=safe/green, 0.5=caution/orange, 1.0=critical/red)
     */
    function getStatusColor(level) {
        if (level < 0.4) return colors.success      // Safe
        if (level < 0.7) return colors.warning      // Caution
        return colors.error                         // Critical/Overload
    }
}
