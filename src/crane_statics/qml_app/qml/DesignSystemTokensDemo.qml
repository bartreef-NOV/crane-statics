import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import "../design"

ApplicationWindow {
    id: root
    width: 900
    height: 800
    visible: true
    title: "Design System Token Reference"

    background: Rectangle {
        color: DesignTokens.colors.background
    }

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true

        ColumnLayout {
            width: parent.width
            anchors.margins: DesignTokens.spacing.xl
            spacing: DesignTokens.spacing.lg

            // Header
            Text {
                text: "Design System Token Reference"
                font.pixelSize: DesignTokens.typography.display
                font.weight: DesignTokens.typography.weightBold
                color: DesignTokens.colors.textPrimary
            }

            Text {
                text: "This QML file demonstrates all available design tokens. Resize the window or switch themes to see responsive behavior."
                font.pixelSize: DesignTokens.typography.body
                color: DesignTokens.colors.textSecondary
                wrapMode: Text.Wrap
            }

            // Color Tokens Section
            ColumnLayout {
                spacing: DesignTokens.spacing.md

                Text {
                    text: "Colors"
                    font.pixelSize: DesignTokens.typography.headingLarge
                    font.weight: DesignTokens.typography.weightSemiBold
                    color: DesignTokens.colors.textPrimary
                }

                GridLayout {
                    columns: 4
                    columnSpacing: DesignTokens.spacing.md
                    rowSpacing: DesignTokens.spacing.md

                    // Color swatches
                    ColorSwatch { label: "Surface"; color: DesignTokens.colors.surface }
                    ColorSwatch { label: "Surface Alt"; color: DesignTokens.colors.surfaceAlt }
                    ColorSwatch { label: "Primary"; color: DesignTokens.colors.primary }
                    ColorSwatch { label: "Success"; color: DesignTokens.colors.success }

                    ColorSwatch { label: "Warning"; color: DesignTokens.colors.warning }
                    ColorSwatch { label: "Error"; color: DesignTokens.colors.error }
                    ColorSwatch { label: "Info"; color: DesignTokens.colors.info }
                    ColorSwatch { label: "Border"; color: DesignTokens.colors.border }
                }
            }

            // Typography Section
            ColumnLayout {
                spacing: DesignTokens.spacing.md

                Text {
                    text: "Typography"
                    font.pixelSize: DesignTokens.typography.headingLarge
                    font.weight: DesignTokens.typography.weightSemiBold
                    color: DesignTokens.colors.textPrimary
                }

                TypographySample { sampleText: "Display (22px)"; pixelSize: DesignTokens.typography.display }
                TypographySample { sampleText: "Heading Large (18px)"; pixelSize: DesignTokens.typography.headingLarge }
                TypographySample { sampleText: "Heading (16px)"; pixelSize: DesignTokens.typography.heading }
                TypographySample { sampleText: "Subtitle (14px)"; pixelSize: DesignTokens.typography.subtitle }
                TypographySample { sampleText: "Body (13px)"; pixelSize: DesignTokens.typography.body }
                TypographySample { sampleText: "Caption (11px)"; pixelSize: DesignTokens.typography.caption }
            }

            // Spacing Section
            ColumnLayout {
                spacing: DesignTokens.spacing.md

                Text {
                    text: "Spacing Scale"
                    font.pixelSize: DesignTokens.typography.headingLarge
                    font.weight: DesignTokens.typography.weightSemiBold
                    color: DesignTokens.colors.textPrimary
                }

                RowLayout {
                    spacing: DesignTokens.spacing.lg

                    SpacingBar { label: "xs"; size: DesignTokens.spacing.xs }
                    SpacingBar { label: "sm"; size: DesignTokens.spacing.sm }
                    SpacingBar { label: "md"; size: DesignTokens.spacing.md }
                    SpacingBar { label: "lg"; size: DesignTokens.spacing.lg }
                    SpacingBar { label: "xl"; size: DesignTokens.spacing.xl }
                    SpacingBar { label: "xxl"; size: DesignTokens.spacing.xxl }
                }
            }

            // Sizing Section
            ColumnLayout {
                spacing: DesignTokens.spacing.md

                Text {
                    text: "Control Sizes"
                    font.pixelSize: DesignTokens.typography.headingLarge
                    font.weight: DesignTokens.typography.weightSemiBold
                    color: DesignTokens.colors.textPrimary
                }

                SizeRow { label: "Button Height"; value: DesignTokens.sizing.buttonHeight }
                SizeRow { label: "Input Height"; value: DesignTokens.sizing.inputHeight }
                SizeRow { label: "Table Row Height"; value: DesignTokens.sizing.rowHeight }
                SizeRow { label: "Icon Normal"; value: DesignTokens.sizing.iconNormal }
            }

            // Component Examples Section
            ColumnLayout {
                spacing: DesignTokens.spacing.md

                Text {
                    text: "Component Examples"
                    font.pixelSize: DesignTokens.typography.headingLarge
                    font.weight: DesignTokens.typography.weightSemiBold
                    color: DesignTokens.colors.textPrimary
                }

                // Buttons
                RowLayout {
                    spacing: DesignTokens.spacing.controlGap

                    Button {
                        text: "Primary Button"
                        implicitHeight: DesignTokens.sizing.buttonHeight
                        palette.button: DesignTokens.colors.primary
                        palette.buttonText: DesignTokens.colors.textInverse
                    }

                    Button {
                        text: "Secondary Button"
                        implicitHeight: DesignTokens.sizing.buttonHeight
                        palette.button: DesignTokens.colors.surfaceAlt
                        palette.buttonText: DesignTokens.colors.textPrimary
                    }

                    Button {
                        text: "Disabled"
                        implicitHeight: DesignTokens.sizing.buttonHeight
                        enabled: false
                    }
                }

                // Text Input
                TextField {
                    implicitHeight: DesignTokens.sizing.inputHeight
                    placeholderText: "Text input (token-sized)"
                    palette.text: DesignTokens.colors.textPrimary
                    palette.base: DesignTokens.colors.surface
                }

                // Status Badges
                RowLayout {
                    spacing: DesignTokens.spacing.controlGap

                    Rectangle {
                        implicitWidth: 80
                        implicitHeight: DesignTokens.sizing.buttonHeightSmall
                        color: DesignTokens.colors.success
                        radius: DesignTokens.border.radiusRound
                        Text {
                            anchors.centerIn: parent
                            text: "Success"
                            color: DesignTokens.colors.textInverse
                            font.pixelSize: DesignTokens.typography.caption
                        }
                    }

                    Rectangle {
                        implicitWidth: 80
                        implicitHeight: DesignTokens.sizing.buttonHeightSmall
                        color: DesignTokens.colors.warning
                        radius: DesignTokens.border.radiusRound
                        Text {
                            anchors.centerIn: parent
                            text: "Warning"
                            color: DesignTokens.colors.textInverse
                            font.pixelSize: DesignTokens.typography.caption
                        }
                    }

                    Rectangle {
                        implicitWidth: 80
                        implicitHeight: DesignTokens.sizing.buttonHeightSmall
                        color: DesignTokens.colors.error
                        radius: DesignTokens.border.radiusRound
                        Text {
                            anchors.centerIn: parent
                            text: "Error"
                            color: DesignTokens.colors.textInverse
                            font.pixelSize: DesignTokens.typography.caption
                        }
                    }
                }
            }

            // Layout Breakpoint Info
            ColumnLayout {
                spacing: DesignTokens.spacing.md

                Text {
                    text: "Responsive Info"
                    font.pixelSize: DesignTokens.typography.headingLarge
                    font.weight: DesignTokens.typography.weightSemiBold
                    color: DesignTokens.colors.textPrimary
                }

                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: DesignTokens.sizing.rowHeight
                    color: DesignTokens.colors.surfaceAlt
                    radius: DesignTokens.sizing.radiusSmall
                    border.color: DesignTokens.colors.border
                    border.width: DesignTokens.sizing.borderThin

                    Text {
                        anchors.fill: parent
                        anchors.margins: DesignTokens.spacing.md
                        text: {
                            var mode = "Window Width: " + root.width + "px"
                            if (root.width < DesignTokens.layout.breakpointCompact) {
                                mode += " (Compact: 1-column layout)"
                            } else if (root.width < DesignTokens.layout.breakpointUltraWide) {
                                mode += " (Wide: 2-column layout)"
                            } else {
                                mode += " (Ultra-wide: data-dense layout)"
                            }
                            return mode
                        }
                        font.pixelSize: DesignTokens.typography.body
                        color: DesignTokens.colors.textPrimary
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }

            Item { Layout.fillHeight: true }
        }
    }

    // Helper component: Color swatch
    component ColorSwatch: ColumnLayout {
        required property string label
        required property color color

        spacing: DesignTokens.spacing.xs

        Rectangle {
            implicitWidth: 80
            implicitHeight: 80
            color: parent.color
            radius: DesignTokens.sizing.radiusSmall
            border.color: DesignTokens.colors.border
            border.width: DesignTokens.sizing.borderThin
        }

        Text {
            text: label
            font.pixelSize: DesignTokens.typography.caption
            color: DesignTokens.colors.textSecondary
            horizontalAlignment: Text.AlignHCenter
            Layout.fillWidth: true
        }
    }

    // Helper component: Typography sample
    component TypographySample: Text {
        required property string sampleText
        required property int pixelSize

        text: sampleText
        font.pixelSize: pixelSize
        font.family: DesignTokens.typography.fontFamily
        color: DesignTokens.colors.textPrimary
    }

    // Helper component: Spacing bar
    component SpacingBar: ColumnLayout {
        required property string label
        required property int size

        spacing: DesignTokens.spacing.xs

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: size
            color: DesignTokens.colors.primary
            radius: DesignTokens.sizing.radiusSmall
        }

        Text {
            text: label + " (" + size + "px)"
            font.pixelSize: DesignTokens.typography.caption
            color: DesignTokens.colors.textSecondary
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
        }
    }

    // Helper component: Size row
    component SizeRow: RowLayout {
        required property string label
        required property int value

        spacing: DesignTokens.spacing.md

        Text {
            text: label
            font.pixelSize: DesignTokens.typography.body
            color: DesignTokens.colors.textPrimary
            Layout.preferredWidth: 150
        }

        Rectangle {
            implicitWidth: value
            implicitHeight: 24
            color: DesignTokens.colors.primary
            radius: DesignTokens.sizing.radiusSmall
        }

        Text {
            text: value + "px"
            font.pixelSize: DesignTokens.typography.caption
            color: DesignTokens.colors.textSecondary
        }

        Item { Layout.fillWidth: true }
    }
}
