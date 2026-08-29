import QtQuick
import QtQuick.Controls.Fusion
import QtQuick.Layouts
import "../design"
import "components"

ApplicationWindow {
    id: root
    width: 1000
    height: 900
    visible: true
    title: "Component Library Showcase"

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
                text: "Component Library Showcase"
                font.pixelSize: DesignTokens.typography.display
                font.weight: DesignTokens.typography.weightBold
                color: DesignTokens.colors.textPrimary
            }

            Text {
                text: "All components use design tokens and automatically respond to light/dark theme changes and density mode."
                font.pixelSize: DesignTokens.typography.body
                color: DesignTokens.colors.textSecondary
                wrapMode: Text.Wrap
            }

            // Buttons Section
            Section {
                title: "Buttons"
                Layout.fillWidth: true
                
                contentItem: GridLayout {
                    columns: 4
                    columnSpacing: DesignTokens.spacing.md
                    rowSpacing: DesignTokens.spacing.md

                    Button { text: "Primary" }
                    Button { text: "Secondary"; semantic: "secondary" }
                    Button { text: "Danger"; semantic: "danger" }
                    Button { text: "Disabled"; enabled: false }

                    Button { text: "Small"; implicitHeight: DesignTokens.sizing.buttonHeightSmall }
                    Button { text: "Long Button Text"; Layout.columnSpan: 2 }
                    Button { text: "Focus"; focus: true }
                }
            }

            // Text Input Section
            Section {
                title: "Text Inputs"
                Layout.fillWidth: true

                contentItem: ColumnLayout {
                    spacing: DesignTokens.spacing.md

                    TextField {
                        placeholderText: "Standard text input"
                        Layout.fillWidth: true
                    }

                    TextField {
                        text: "Disabled input"
                        enabled: false
                        Layout.fillWidth: true
                    }

                    ColumnLayout {
                        spacing: DesignTokens.spacing.sm
                        Layout.fillWidth: true

                        TextField {
                            isError: true
                            placeholderText: "Error state"
                            Layout.fillWidth: true
                        }

                        Text {
                            text: "This field has an error"
                            font.pixelSize: DesignTokens.typography.caption
                            color: DesignTokens.colors.error
                        }
                    }
                }
            }

            // ComboBox Section
            Section {
                title: "ComboBox"
                Layout.fillWidth: true

                contentItem: ColumnLayout {
                    spacing: DesignTokens.spacing.md

                    ComboBox {
                        model: ["Option A", "Option B", "Option C", "Option D"]
                        Layout.fillWidth: true
                    }

                    ComboBox {
                        model: ["Disabled Option A", "Disabled Option B"]
                        enabled: false
                        Layout.fillWidth: true
                    }
                }
            }

            // Badges / Status Section
            Section {
                title: "Badges"
                Layout.fillWidth: true

                contentItem: RowLayout {
                    spacing: DesignTokens.spacing.lg
                    Layout.fillWidth: true

                    Badge { text: "Success"; semantic: "success" }
                    Badge { text: "Warning"; semantic: "warning" }
                    Badge { text: "Error"; semantic: "error" }
                    Badge { text: "Info"; semantic: "info" }
                    Badge { text: "Primary"; semantic: "primary" }

                    Item { Layout.fillWidth: true }
                }
            }

            // Cards Section
            Section {
                title: "Cards"
                Layout.fillWidth: true

                contentItem: RowLayout {
                    spacing: DesignTokens.spacing.md
                    Layout.fillWidth: true

                    Card {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 120
                        contentItem: ColumnLayout {
                            spacing: DesignTokens.spacing.sm
                            Text {
                                text: "Card Title"
                                font.weight: DesignTokens.typography.weightSemiBold
                                color: DesignTokens.colors.textPrimary
                            }
                            Text {
                                text: "Card content goes here. This card has consistent padding and elevation."
                                font.pixelSize: DesignTokens.typography.caption
                                color: DesignTokens.colors.textSecondary
                                wrapMode: Text.Wrap
                            }
                        }
                    }

                    Card {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 120
                        contentItem: ColumnLayout {
                            spacing: DesignTokens.spacing.sm
                            Text {
                                text: "Another Card"
                                font.weight: DesignTokens.typography.weightSemiBold
                                color: DesignTokens.colors.textPrimary
                            }
                            Text {
                                text: "Cards automatically use design tokens for consistent styling."
                                font.pixelSize: DesignTokens.typography.caption
                                color: DesignTokens.colors.textSecondary
                                wrapMode: Text.Wrap
                            }
                        }
                    }
                }
            }

            // Form Example
            Section {
                title: "Form Example"
                Layout.fillWidth: true

                contentItem: ColumnLayout {
                    spacing: DesignTokens.spacing.rowGap
                    Layout.fillWidth: true

                    RowLayout {
                        spacing: DesignTokens.spacing.controlGap
                        Layout.fillWidth: true

                        ColumnLayout {
                            spacing: DesignTokens.spacing.sm
                            Layout.fillWidth: true

                            Text {
                                text: "Full Name"
                                font.pixelSize: DesignTokens.typography.body
                                font.weight: DesignTokens.typography.weightMedium
                                color: DesignTokens.colors.textPrimary
                            }

                            TextField {
                                placeholderText: "Enter your full name"
                                Layout.fillWidth: true
                            }
                        }

                        ColumnLayout {
                            spacing: DesignTokens.spacing.sm
                            Layout.fillWidth: true

                            Text {
                                text: "Status"
                                font.pixelSize: DesignTokens.typography.body
                                font.weight: DesignTokens.typography.weightMedium
                                color: DesignTokens.colors.textPrimary
                            }

                            ComboBox {
                                model: ["Active", "Inactive", "Pending"]
                                Layout.fillWidth: true
                            }
                        }
                    }

                    RowLayout {
                        spacing: DesignTokens.spacing.controlGap
                        Layout.fillWidth: true

                        Button { text: "Save"; Layout.alignment: Qt.AlignRight }
                        Button { text: "Cancel"; semantic: "secondary"; Layout.alignment: Qt.AlignRight }
                    }
                }
            }

            // Design System Info
            Section {
                title: "Design System Info"
                Layout.fillWidth: true

                contentItem: ColumnLayout {
                    spacing: DesignTokens.spacing.md
                    Layout.fillWidth: true

                    Text {
                        text: "Window Width: " + root.width + "px"
                        font.pixelSize: DesignTokens.typography.body
                        color: DesignTokens.colors.textPrimary
                    }

                    Text {
                        text: {
                            var mode = ""
                            if (root.width < DesignTokens.layout.breakpointCompact) {
                                mode = "Compact layout (1-column)"
                            } else if (root.width < DesignTokens.layout.breakpointUltraWide) {
                                mode = "Wide layout (2-column)"
                            } else {
                                mode = "Ultra-wide layout (data-dense)"
                            }
                            return mode
                        }
                        font.pixelSize: DesignTokens.typography.body
                        color: DesignTokens.colors.textSecondary
                    }

                    Text {
                        text: "Table Row Height: " + DesignTokens.layout.tableRowHeight + "px"
                        font.pixelSize: DesignTokens.typography.caption
                        color: DesignTokens.colors.textSecondary
                    }
                }
            }

            Item { Layout.fillHeight: true }
        }
    }
}
