# Component Usage & API Reference

Quick reference for using and creating components with design tokens.

## Import & Usage

### Import DesignTokens

```qml
import Crane.DesignTokens 1.0
```

### Basic Component Template

All reusable components should follow this pattern:

```qml
import QtQuick
import QtQuick.Controls.Fusion
import Crane.DesignTokens 1.0

Control {
    id: root
    
    // Expose customizable properties
    property string placeholder: ""
    property bool isError: false
    
    implicitHeight: DesignTokens.sizing.inputHeight
    implicitWidth: DesignTokens.sizing.minInputWidth
    
    palette.text: DesignTokens.colors.textPrimary
    palette.base: DesignTokens.colors.surface
    palette.mid: isError ? DesignTokens.colors.error : DesignTokens.colors.border
    
    background: Rectangle {
        color: DesignTokens.colors.surface
        border.color: DesignTokens.colors.border
        border.width: DesignTokens.sizing.borderNormal
        radius: DesignTokens.sizing.radiusSmall
    }
    
    // All focus/hover/error states should use design tokens
    states: [
        State {
            name: "focused"
            PropertyChanges {
                target: background
                border.color: DesignTokens.colors.focusRing
                border.width: DesignTokens.sizing.borderThick
            }
        },
        State {
            name: "error"
            PropertyChanges {
                target: background
                border.color: DesignTokens.colors.error
            }
        }
    ]
}
```

---

## Common Component Patterns

### Button Component

**Purpose:** Standard button with semantic styling

**Props:**
- `text`: Button label (string)
- `enabled`: Enable/disable state (bool)
- `isLoading`: Show loading spinner (bool)
- `semantic`: Button type: "primary" | "secondary" | "danger" (string)

**Example:**
```qml
import Crane.DesignTokens 1.0
import QtQuick.Controls.Fusion

Button {
    text: "Save"
    implicitHeight: DesignTokens.sizing.buttonHeight
    implicitWidth: Math.max(DesignTokens.sizing.minButtonWidth, contentWidth + 2 * DesignTokens.spacing.md)
    
    palette.button: enabled 
        ? DesignTokens.colors.primary 
        : DesignTokens.colors.primaryDisabled
    palette.buttonText: DesignTokens.colors.textInverse
    
    background: Rectangle {
        color: parent.pressed 
            ? DesignTokens.colors.primaryPressed 
            : (parent.hovered ? DesignTokens.colors.primaryHover : DesignTokens.colors.primary)
        radius: DesignTokens.sizing.radiusSmall
    }
}
```

**Accessibility:** Ensure focus ring is visible on keyboard navigation

---

### TextField Component

**Purpose:** Text input with consistent styling and validation states

**Props:**
- `isError`: Show error state (bool)
- `errorText`: Error message below field (string)
- `decimals`: For numeric fields, decimal places (int)

**Example:**
```qml
TextField {
    id: field
    
    implicitHeight: DesignTokens.sizing.inputHeight
    implicitWidth: DesignTokens.sizing.maxInputWidth
    
    palette.text: DesignTokens.colors.textPrimary
    palette.base: DesignTokens.colors.surface
    
    background: Rectangle {
        color: DesignTokens.colors.surface
        border.color: isError 
            ? DesignTokens.colors.error 
            : DesignTokens.colors.border
        border.width: DesignTokens.sizing.borderNormal
        radius: DesignTokens.sizing.radiusSmall
    }
}

// Error message below field
Text {
    visible: isError
    text: errorText
    font.pixelSize: DesignTokens.typography.caption
    color: DesignTokens.colors.error
}
```

---

### ComboBox Component

**Purpose:** Dropdown selector with token-based styling

**Props:**
- `model`: List of options (list)
- `currentIndex`: Selected index (int)
- `currentText`: Selected text (string)

**Example:**
```qml
ComboBox {
    implicitHeight: DesignTokens.sizing.inputHeight
    implicitWidth: DesignTokens.sizing.minInputWidth
    
    palette.text: DesignTokens.colors.textPrimary
    palette.base: DesignTokens.colors.surface
    palette.mid: DesignTokens.colors.border
    
    background: Rectangle {
        color: DesignTokens.colors.surface
        border.color: DesignTokens.colors.border
        border.width: DesignTokens.sizing.borderNormal
        radius: DesignTokens.sizing.radiusSmall
    }
    
    delegate: ItemDelegate {
        implicitHeight: DesignTokens.sizing.rowHeight
        background: Rectangle {
            color: highlighted ? DesignTokens.colors.primary : "transparent"
        }
        text: modelData
        palette.text: highlighted ? DesignTokens.colors.textInverse : DesignTokens.colors.textPrimary
    }
}
```

---

### Dialog Component

**Purpose:** Modal wrapper enforcing consistent title/button/padding sizing

**Props:**
- `title`: Dialog title (string)
- `message`: Main content text (string)
- `standardButtons`: Dialog.Ok | Dialog.Cancel | Dialog.Save (enum)

**Example:**
```qml
Dialog {
    id: dialog
    
    title: "Confirm Delete"
    
    background: Rectangle {
        color: DesignTokens.colors.background
        border.color: DesignTokens.colors.border
        border.width: DesignTokens.sizing.borderNormal
        radius: DesignTokens.sizing.radiusNormal
    }
    
    header: Rectangle {
        color: DesignTokens.colors.surfaceAlt
        height: DesignTokens.sizing.buttonHeight + 2 * DesignTokens.spacing.md
        
        Text {
            anchors.margins: DesignTokens.spacing.md
            text: dialog.title
            font.pixelSize: DesignTokens.typography.heading
            color: DesignTokens.colors.textPrimary
        }
    }
    
    contentItem: Text {
        anchors.margins: DesignTokens.spacing.dialogPadding
        text: "Are you sure?"
        font.pixelSize: DesignTokens.typography.body
        color: DesignTokens.colors.textPrimary
    }
    
    footer: DialogButtonBox {
        Button {
            text: "Delete"
            palette.button: DesignTokens.colors.error
            palette.buttonText: DesignTokens.colors.textInverse
        }
        Button {
            text: "Cancel"
            palette.button: DesignTokens.colors.surfaceAlt
            palette.buttonText: DesignTokens.colors.textPrimary
        }
    }
}
```

---

### Card Component

**Purpose:** Elevated container for grouping content

**Props:**
- `title`: Card title (string)
- `elevation`: Shadow level 1-3 (int)

**Example:**
```qml
Rectangle {
    id: card
    
    color: DesignTokens.colors.surface
    radius: DesignTokens.sizing.radiusNormal
    border.color: DesignTokens.colors.border
    border.width: DesignTokens.sizing.borderThin
    
    layer.enabled: true
    layer.effect: DropShadow {
        xOffset: 0
        yOffset: 2
        blur: 6
        color: DesignTokens.shadows.getShadowColor()
        opacity: 0.15
    }
    
    ColumnLayout {
        anchors.margins: DesignTokens.spacing.panelPadding
        spacing: DesignTokens.spacing.md
        
        Text {
            text: "Card Title"
            font.pixelSize: DesignTokens.typography.heading
            font.weight: DesignTokens.typography.weightSemiBold
            color: DesignTokens.colors.textPrimary
        }
        
        // Card content goes here
    }
}
```

---

### Table

**Purpose:** Data table using the shared row-height token

**Example:**
```qml
TableView {
    id: table
    
    rowHeight: DesignTokens.layout.tableRowHeight
    
    delegate: ItemDelegate {
        implicitHeight: DesignTokens.layout.tableRowHeight
        
        background: Rectangle {
            color: row % 2 === 0 ? DesignTokens.colors.surface : DesignTokens.colors.surfaceAlt
        }
        
        contentItem: Text {
            text: display
            font.pixelSize: DesignTokens.typography.body
            color: DesignTokens.colors.textPrimary
            verticalAlignment: Text.AlignVCenter
            leftPadding: DesignTokens.spacing.sm
        }
    }
}
```

---

### Status Indicator / Badge

**Purpose:** Visual indicator for status (success, warning, error, info)

**Props:**
- `status`: "success" | "warning" | "error" | "info" (string)
- `text`: Badge label (string)

**Example:**
```qml
Rectangle {
    id: badge
    
    property string status: "success"  // "success", "warning", "error", "info"
    
    implicitWidth: text.width + 2 * DesignTokens.spacing.sm
    implicitHeight: DesignTokens.sizing.buttonHeightSmall
    
    color: DesignTokens.getSemanticColor(status)
    radius: DesignTokens.sizing.radiusRound
    
    Text {
        id: text
        anchors.centerIn: parent
        text: "Success"
        font.pixelSize: DesignTokens.typography.caption
        font.weight: DesignTokens.typography.weightMedium
        color: DesignTokens.colors.textInverse
    }
}
```

---

## State Patterns

### Error State

For form inputs with validation errors:

```qml
TextField {
    property bool isError: false
    property string errorMessage: ""
    
    palette.mid: isError ? DesignTokens.colors.error : DesignTokens.colors.border
    
    background: Rectangle {
        border.color: isError ? DesignTokens.colors.error : DesignTokens.colors.border
        border.width: isError ? DesignTokens.sizing.borderThick : DesignTokens.sizing.borderNormal
    }
}

// Error message label
Text {
    visible: parent.isError
    text: parent.errorMessage
    color: DesignTokens.colors.error
    font.pixelSize: DesignTokens.typography.caption
}
```

### Loading State

For async operations:

```qml
Button {
    property bool isLoading: false
    
    text: isLoading ? "Loading..." : "Save"
    enabled: !isLoading
    opacity: isLoading ? 0.7 : 1.0
    
    BusyIndicator {
        visible: isLoading
        running: isLoading
    }
}
```

### Disabled State

For unavailable controls:

```qml
Control {
    property bool isDisabled: true
    
    enabled: !isDisabled
    opacity: isDisabled ? 0.5 : 1.0
    palette.text: isDisabled ? DesignTokens.colors.textDisabled : DesignTokens.colors.textPrimary
}
```

### Hover State

For interactive feedback:

```qml
Rectangle {
    id: item
    
    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: true
    }
    
    color: mouseArea.containsMouse 
        ? DesignTokens.colors.surfaceAlt 
        : DesignTokens.colors.surface
    
    Behavior on color {
        ColorAnimation { duration: DesignTokens.transitions.fast }
    }
}
```

---

## Layout Patterns

### Responsive Column Layout

```qml
ColumnLayout {
    id: root
    readonly property bool compact: width < DesignTokens.layout.breakpointCompact
    
    anchors.margins: DesignTokens.spacing.lg
    spacing: DesignTokens.spacing.md
    
    GridLayout {
        Layout.fillWidth: true
        columns: root.compact ? 1 : 2
        columnSpacing: DesignTokens.spacing.md
        rowSpacing: DesignTokens.spacing.md
        
        // Form fields in each column
    }
}
```

### Consistent Margins

```qml
Item {
    anchors {
        fill: parent
        margins: DesignTokens.spacing.md  // Use tokens instead of magic numbers
    }
}
```

### Spacing Between Controls

```qml
RowLayout {
    spacing: DesignTokens.spacing.controlGap  // 8px
    
    Button { text: "OK" }
    Button { text: "Cancel" }
}

ColumnLayout {
    spacing: DesignTokens.spacing.rowGap  // 8px
    
    TextField { }
    TextField { }
}
```

---

## Accessibility Checklist

When creating a new component, verify:

- [ ] **Focus Ring:** Visible focus indicator for keyboard navigation
- [ ] **Color Contrast:** Text meets WCAG AA minimum (4.5:1 for body, 3:1 for large text)
- [ ] **Keyboard Navigation:** Tab through all interactive elements
- [ ] **State Indication:** Enabled/disabled/error states clearly visible
- [ ] **Semantic Tokens:** No hardcoded colors (use `DesignTokens.colors.*`)
- [ ] **Text Sizing:** Use typography tokens (don't hardcode px values)
- [ ] **Accessible Name:** Components have `Accessible.name` for screen readers

**Keyboard Test:**
1. Tab through the component
2. Shift+Tab backward navigation
3. Space/Enter to activate buttons
4. Arrow keys to navigate lists/tables

**Color Test:**
1. View component in light mode → is text readable?
2. View component in dark mode → is text readable?
3. Run OS high-contrast mode → any issues?

---

## Theme Testing

When adding new UI or modifying existing components:

1. **Light Mode:** Settings > Personalization > Colors > Light
   - Check text readability
   - Check border/divider visibility
   - Check form field distinction from background

2. **Dark Mode:** Settings > Personalization > Colors > Dark
   - Check text readability
   - Check border/divider visibility
   - Check form field distinction from background

3. **High Contrast:** Settings > Ease of Access > High Contrast
   - Ensure all UI elements remain visible
   - Check focus indicators are prominent

---

## Common Mistakes to Avoid

❌ **Hardcoding colors:**
```qml
// WRONG
Rectangle { color: "#0078d4" }
Text { color: "#ffffff" }
```

✅ **Using design tokens:**
```qml
// RIGHT
Rectangle { color: DesignTokens.colors.primary }
Text { color: DesignTokens.colors.textInverse }
```

---

❌ **Magic number spacing:**
```qml
// WRONG
anchors.margins: 16
columnSpacing: 8
padding: 12
```

✅ **Using spacing tokens:**
```qml
// RIGHT
anchors.margins: DesignTokens.spacing.md
columnSpacing: DesignTokens.spacing.controlGap
padding: DesignTokens.spacing.panelPadding
```

---

❌ **Hardcoding font sizes:**
```qml
// WRONG
font.pixelSize: 14
```

✅ **Using typography tokens:**
```qml
// RIGHT
font.pixelSize: DesignTokens.typography.body
```

---

❌ **Not testing in both themes:**
```qml
// WRONG: Component looks good in light mode only
Rectangle { color: "#ffffff" }
Text { color: "#000000" }
```

✅ **Testing in both themes:**
```qml
// RIGHT: Works in light and dark modes
Rectangle { color: DesignTokens.colors.surface }
Text { color: DesignTokens.colors.textPrimary }
```

---

## Questions?

Refer to:
- [DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md) — Comprehensive token reference
- [design-tokens.json](./design-tokens.json) — Token values and metadata
- [DesignTokens.qml](../../src/crane_statics/qml_app/design/DesignTokens.qml) — Implementation

---

**Last Updated:** 2026-08-14  
**Design System Version:** 1.0.0
