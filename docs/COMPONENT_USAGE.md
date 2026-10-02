# Component Usage & API Reference

Quick reference for using and creating components with design tokens.

## Import & Usage

### Import the Design System

```qml
import BF.DesignSystem
```

This gives you `Theme` (colors + helper functions), `Metrics` (spacing/sizing/radii), and `Typography` (font family/weights/sizes), plus five ready-made controls: `BfButton`, `BfTextField`, `BfCard`, `BfStatusBadge`, `BfPage`. Reach for one of those before hand-rolling the equivalent pattern below — the patterns in this doc are for cases the `Bf*` controls don't cover, or for extending `qml/components/`.

### Basic Component Template

All reusable components should follow this pattern:

```qml
import QtQuick
import QtQuick.Controls.Fusion
import BF.DesignSystem

Control {
    id: root

    // Expose customizable properties
    property string placeholder: ""
    property bool isError: false

    implicitHeight: Metrics.controlHeight
    implicitWidth: Metrics.minInputWidth

    palette.text: Theme.text
    palette.base: Theme.surface
    palette.mid: isError ? Theme.error : Theme.border

    background: Rectangle {
        color: Theme.surface
        border.color: Theme.border
        border.width: Metrics.borderWidth
        radius: Metrics.radiusSmall
    }

    // All focus/hover/error states should use design tokens
    states: [
        State {
            name: "focused"
            PropertyChanges {
                target: background
                border.color: Theme.focusRing
                border.width: Metrics.focusWidth
            }
        },
        State {
            name: "error"
            PropertyChanges {
                target: background
                border.color: Theme.error
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

`BfButton` already implements exactly this pattern (`variant`: `"primary"` \| `"secondary"` \| `"ghost"` \| `"danger"`, with hover/pressed/disabled states) — prefer it over the hand-rolled version below unless you need something it doesn't support.

**Example:**
```qml
import BF.DesignSystem
import QtQuick.Controls.Fusion

Button {
    text: "Save"
    implicitHeight: Metrics.controlHeight
    implicitWidth: Math.max(Metrics.buttonMinWidth, contentWidth + 2 * Metrics.spacing16)

    palette.button: enabled
        ? Theme.primary
        : Theme.primaryDisabled
    palette.buttonText: Theme.onPrimary

    background: Rectangle {
        color: parent.pressed
            ? Theme.primaryPressed
            : (parent.hovered ? Theme.primaryHover : Theme.primary)
        radius: Metrics.radiusSmall
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

`BfTextField` ships this `isError`/`errorText` pattern directly — prefer it over the hand-rolled version below.

**Example:**
```qml
TextField {
    id: field

    implicitHeight: Metrics.controlHeight
    implicitWidth: Metrics.maxInputWidth

    palette.text: Theme.text
    palette.base: Theme.surface

    background: Rectangle {
        color: Theme.surface
        border.color: isError
            ? Theme.error
            : Theme.border
        border.width: Metrics.borderWidthNormal
        radius: Metrics.radiusSmall
    }
}

// Error message below field
Text {
    visible: isError
    text: errorText
    font.pixelSize: Typography.caption
    color: Theme.error
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
    implicitHeight: Metrics.controlHeight
    implicitWidth: Metrics.minInputWidth

    palette.text: Theme.text
    palette.base: Theme.surface
    palette.mid: Theme.border

    background: Rectangle {
        color: Theme.surface
        border.color: Theme.border
        border.width: Metrics.borderWidthNormal
        radius: Metrics.radiusSmall
    }

    delegate: ItemDelegate {
        implicitHeight: Metrics.tableRowHeight
        background: Rectangle {
            color: highlighted ? Theme.primary : "transparent"
        }
        text: modelData
        palette.text: highlighted ? Theme.onPrimary : Theme.text
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
    width: Metrics.dialogWidth

    background: Rectangle {
        color: Theme.pageBackground
        border.color: Theme.border
        border.width: Metrics.borderWidthNormal
        radius: Metrics.radiusMedium
    }

    header: Rectangle {
        color: Theme.surfaceSubtle
        height: Metrics.controlHeight + 2 * Metrics.spacing16

        Text {
            anchors.margins: Metrics.spacing16
            text: dialog.title
            font.pixelSize: Typography.heading
            color: Theme.text
        }
    }

    contentItem: Text {
        anchors.margins: Metrics.spacing16
        text: "Are you sure?"
        font.pixelSize: Typography.body
        color: Theme.text
    }

    footer: DialogButtonBox {
        Button {
            text: "Delete"
            palette.button: Theme.error
            palette.buttonText: Theme.onPrimary
        }
        Button {
            text: "Cancel"
            palette.button: Theme.surfaceSubtle
            palette.buttonText: Theme.text
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

`BfCard` already implements this pattern (default property alias `content`, `MultiEffect`-based shadow) — prefer it over the hand-rolled version below.

**Example:**
```qml
import QtQuick.Effects

Rectangle {
    id: card

    color: Theme.surface
    radius: Metrics.radiusLarge
    border.color: Theme.border
    border.width: Metrics.borderWidth

    layer.enabled: true
    layer.effect: MultiEffect {
        shadowEnabled: true
        shadowColor: Theme.shadowColor
        shadowBlur: 0.35
        shadowVerticalOffset: 2
    }

    ColumnLayout {
        anchors.margins: Metrics.spacing12
        spacing: Metrics.spacing16

        Text {
            text: "Card Title"
            font.pixelSize: Typography.heading
            font.weight: Typography.weightSemiBold
            color: Theme.text
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

    rowHeight: Metrics.tableRowHeight

    delegate: ItemDelegate {
        implicitHeight: Metrics.tableRowHeight

        background: Rectangle {
            color: row % 2 === 0 ? Theme.surface : Theme.surfaceSubtle
        }

        contentItem: Text {
            text: display
            font.pixelSize: Typography.body
            color: Theme.text
            verticalAlignment: Text.AlignVCenter
            leftPadding: Metrics.spacing8
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

`BfStatusBadge` implements exactly this — prefer `BfStatusBadge { text: "Success"; status: "success" }` over the hand-rolled version below. Note it uses `Theme.contrastText()` (via `Theme.getOnSemanticColor()`) rather than a fixed inverse text color, since the nov palette's pastel-adjacent solid tones don't all clear WCAG AA against a single fixed color.

**Example:**
```qml
Rectangle {
    id: badge

    property string status: "success"  // "success", "warning", "error", "info"

    implicitWidth: text.width + 2 * Metrics.spacing8
    implicitHeight: Metrics.spacing24
    radius: height / 2

    color: Theme.getSemanticColor(status)

    Text {
        id: text
        anchors.centerIn: parent
        text: "Success"
        font.pixelSize: Metrics.fontSizeSmall
        font.weight: Typography.weightMedium
        color: Theme.getOnSemanticColor(status)
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

    palette.mid: isError ? Theme.error : Theme.border

    background: Rectangle {
        border.color: isError ? Theme.error : Theme.border
        border.width: isError ? Metrics.borderWidthNormal : Metrics.borderWidth
    }
}

// Error message label
Text {
    visible: parent.isError
    text: parent.errorMessage
    color: Theme.error
    font.pixelSize: Typography.caption
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
    palette.text: isDisabled ? Theme.disabledText : Theme.text
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
        ? Theme.surfaceSubtle
        : Theme.surface

    Behavior on color {
        ColorAnimation { duration: Metrics.transitionFast }
    }
}
```

---

## Layout Patterns

### Responsive Column Layout

```qml
ColumnLayout {
    id: root
    readonly property bool compact: width < Metrics.breakpointCompact

    anchors.margins: Metrics.spacing24
    spacing: Metrics.spacing16

    GridLayout {
        Layout.fillWidth: true
        columns: root.compact ? 1 : 2
        columnSpacing: Metrics.spacing16
        rowSpacing: Metrics.spacing16

        // Form fields in each column
    }
}
```

### Consistent Margins

```qml
Item {
    anchors {
        fill: parent
        margins: Metrics.spacing16  // Use tokens instead of magic numbers
    }
}
```

### Spacing Between Controls

```qml
RowLayout {
    spacing: Metrics.spacing8  // Gap between inline controls

    Button { text: "OK" }
    Button { text: "Cancel" }
}

ColumnLayout {
    spacing: Metrics.spacing8  // Gap between form rows

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
- [ ] **Semantic Tokens:** No hardcoded colors (use `Theme.*`)
- [ ] **Text Sizing:** Use typography tokens (don't hardcode px values)
- [ ] **Accessible Name:** Components have `Accessible.name` for screen readers

**Keyboard Test:**
1. Tab through the component
2. Shift+Tab backward navigation
3. Space/Enter to activate buttons
4. Arrow keys to navigate lists/tables

**Color Test:**
1. View the component → is text readable against its background?
2. Run OS high-contrast mode → any issues?

---

## Visual Validation

When adding new UI or modifying existing components:

1. **Readability:** Check text readability, border/divider visibility, and form field distinction from background.

2. **High Contrast:** Settings > Ease of Access > High Contrast
   - Ensure all UI elements remain visible
   - Check focus indicators are prominent

---

## Common Mistakes to Avoid

❌ **Hardcoding colors:**
```qml
// WRONG
Rectangle { color: "#007096" }
Text { color: "#ffffff" }
```

✅ **Using design tokens:**
```qml
// RIGHT
Rectangle { color: Theme.primary }
Text { color: Theme.onPrimary }
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
anchors.margins: Metrics.spacing16
columnSpacing: Metrics.spacing8
padding: Metrics.spacing12
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
font.pixelSize: Typography.body
```

---

## Questions?

Refer to:
- [DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md) — Comprehensive token reference
- [design-tokens.json](./design-tokens.json) — Token values and metadata
- [Theme.qml](../../src/crane_statics/qml_app/design/BF/DesignSystem/Theme.qml), [Metrics.qml](../../src/crane_statics/qml_app/design/BF/DesignSystem/Metrics.qml), [Typography.qml](../../src/crane_statics/qml_app/design/BF/DesignSystem/Typography.qml) — Implementation

---

**Last Updated:** 2026-09-24
**Design System Version:** 2.0.0
