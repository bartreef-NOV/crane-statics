# Design Token Quick Start

Use this guide to apply the shared QML design tokens in a component.

---

## Import

```qml
import Crane.DesignTokens 1.0
```

That's it. Now you have access to all tokens.

---

## Common Use Cases

### Button

```qml
Button {
    text: "Save"
    implicitHeight: DesignTokens.sizing.buttonHeight
    palette.button: DesignTokens.colors.primary
    palette.buttonText: DesignTokens.colors.textInverse
}
```

### Text Input

```qml
TextField {
    implicitHeight: DesignTokens.sizing.inputHeight
    palette.base: DesignTokens.colors.surface
    palette.text: DesignTokens.colors.textPrimary
}
```

### Container with Padding

```qml
Rectangle {
    color: DesignTokens.colors.surface
    anchors.margins: DesignTokens.spacing.md  // 16px
    
    ColumnLayout {
        spacing: DesignTokens.spacing.sm  // 8px
    }
}
```

### Text Label

```qml
Text {
    text: "Label"
    font.pixelSize: DesignTokens.typography.body  // 13px
    font.weight: DesignTokens.typography.weightMedium  // 500
    color: DesignTokens.colors.textPrimary
}
```

### Error State

```qml
Rectangle {
    border.color: DesignTokens.colors.error
    color: DesignTokens.colors.surface
}

Text {
    text: "This field is required"
    color: DesignTokens.colors.error
    font.pixelSize: DesignTokens.typography.caption
}
```

### Status Badge

```qml
Rectangle {
    color: DesignTokens.colors.success  // Green
    // or use getStatusColor() for numeric levels (0-1)
    color: DesignTokens.getStatusColor(0.3)  // Green for 0.3
    color: DesignTokens.getStatusColor(0.7)  // Red for 0.7
}
```

### Responsive Layout

```qml
Item {
    readonly property bool compact: width < DesignTokens.layout.breakpointCompact
    
    GridLayout {
        columns: compact ? 1 : 2
    }
}
```

### Density-Aware Table

```qml
TableView {
    rowHeight: DesignTokens.layout.tableRowHeight  // Auto-adjusts
}
```

---

## Token Cheat Sheet

### Colors
```
primary, primaryHover, primaryPressed, primaryDisabled  → Action states
success, warning, error, info                           → Status colors
surface, surfaceAlt, background                         → Backgrounds
textPrimary, textSecondary, textDisabled, textInverse  → Text
border, borderLight, divider, focusRing                 → Boundaries
```

### Spacing (use instead of magic numbers)
```
xs=4px, sm=8px, md=16px, lg=24px, xl=32px, xxl=48px
controlGap, rowGap, sectionGap, panelPadding, dialogPadding
```

### Typography
```
display (22px), headingLarge (18px), heading (16px)
subtitle (14px), bodyLarge (14px), body (13px), caption (11px)
fontFamily, monoFamily, weightLight–weightBold
```

### Sizing
```
buttonHeight=32px, inputHeight=32px, rowHeight=28px
iconSmall=16px, iconNormal=24px, iconLarge=32px
radiusNone, radiusSmall, radiusNormal, radiusLarge
```

### Layout
```
breakpointCompact = 1240px    → 1-column layout
breakpointWide = 1240px       → 2-column layout
breakpointUltraWide = 1800px  → data-dense layout
tableRowHeight                → Responds to density mode
```

---

## Rules

**DO:**
- ✅ `color: DesignTokens.colors.primary`
- ✅ `anchors.margins: DesignTokens.spacing.md`
- ✅ `font.pixelSize: DesignTokens.typography.body`
- ✅ `implicitHeight: DesignTokens.sizing.buttonHeight`

**DON'T:**
- ❌ `color: "#0078d4"`
- ❌ `anchors.margins: 16`
- ❌ `font.pixelSize: 14`
- ❌ `implicitHeight: 32`

---

## Testing

### Light Mode
1. Windows: Settings > Personalization > Colors > Light
2. Relaunch app
3. Is text readable? Are form fields distinct from background?

### Dark Mode
1. Windows: Settings > Personalization > Colors > Dark
2. Relaunch app
3. Is text readable? Are form fields distinct from background?

### Density Modes
1. Run app
2. View > Appearance > Relaxed / Normal / Compact
3. Do tables still look good? Is spacing appropriate?

---

## Need More Info?

| Need | File |
|------|------|
| Complete token reference | [DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md) |
| Code examples & patterns | [COMPONENT_USAGE.md](./COMPONENT_USAGE.md) |
| Pre-commit checklist | [THEME_VALIDATION_CHECKLIST.md](./THEME_VALIDATION_CHECKLIST.md) |
| JSON token export | [design-tokens.json](./design-tokens.json) |
| Token implementation | [DesignTokens.qml](../src/crane_statics/qml_app/design/DesignTokens.qml) |
| Visual demo | [DesignSystemTokensDemo.qml](../src/crane_statics/qml_app/qml/DesignSystemTokensDemo.qml) |

---

**That's it!** You're ready to use design tokens. See THEME_VALIDATION_CHECKLIST.md before committing changes.
