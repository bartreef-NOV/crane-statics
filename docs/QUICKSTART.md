# Design Token Quick Start

Use this guide to apply the shared QML design tokens in a component.

---

## Import

```qml
import BF.DesignSystem
```

That's it. Now you have access to `Theme`, `Metrics`, and `Typography`.

---

## Common Use Cases

### Button

```qml
Button {
    text: "Save"
    implicitHeight: Metrics.controlHeight
    palette.button: Theme.primary
    palette.buttonText: Theme.onPrimary
}
```

Prefer `BfButton { text: "Save" }` directly — it already wires up hover,
pressed, and disabled states for the `primary` / `secondary` / `ghost` /
`danger` variants.

### Text Input

```qml
TextField {
    implicitHeight: Metrics.controlHeight
    palette.base: Theme.surface
    palette.text: Theme.text
}
```

Or use `BfTextField`, which wraps this plus an `isError`/`errorText` pattern.

### Container with Padding

```qml
Rectangle {
    color: Theme.surface
    anchors.margins: Metrics.spacing16  // 16px

    ColumnLayout {
        spacing: Metrics.spacing8  // 8px
    }
}
```

### Text Label

```qml
Text {
    text: "Label"
    font.pixelSize: Typography.body  // 13px
    font.weight: Typography.weightMedium  // 500
    color: Theme.text
}
```

### Error State

```qml
Rectangle {
    border.color: Theme.error
    color: Theme.surface
}

Text {
    text: "This field is required"
    color: Theme.error
    font.pixelSize: Typography.caption
}
```

### Status Badge

```qml
Rectangle {
    color: Theme.success  // NOV green
    // or use getStatusColor() for numeric levels (0-1)
    color: Theme.getStatusColor(0.3)  // Green for 0.3
    color: Theme.getStatusColor(0.7)  // Red for 0.7
}
```

Or use `BfStatusBadge { text: "Ready"; status: "success" }` directly — it
already picks a contrast-safe text color via `Theme.contrastText()`.

### Responsive Layout

```qml
Item {
    readonly property bool compact: width < Metrics.breakpointCompact

    GridLayout {
        columns: compact ? 1 : 2
    }
}
```

### Table Rows

```qml
TableView {
    rowHeight: Metrics.tableRowHeight
}
```

---

## Token Cheat Sheet

### Colors (`Theme`)
```
primary, primaryHover, primaryPressed, primaryDisabled, onPrimary  → Action states
accent, accentHover, accentPressed, onAccent                       → Accent actions
success, warning, error, info                                      → Status colors
successSurface, warningSurface, errorSurface, infoSurface          → Pastel status fills
onSuccess, onWarning, onError, onInfo                               → Contrast-safe text on the above
pageBackground, surface, surfaceSubtle                              → Backgrounds
text, textMuted, textOnDark, disabledText, disabledSurface          → Text & disabled fills
border, borderSubtle, focusRing                                     → Boundaries
selection, selectionText, overlay, shadowColor                      → Misc
```

### Spacing (`Metrics`, use instead of magic numbers)
```
spacing2=2px, spacing4=4px, spacing6=6px, spacing8=8px, spacing12=12px
spacing16=16px, spacing24=24px, spacing32=32px, spacing48=48px
```

There are no grouped names like `controlGap`/`panelPadding` anymore — pick the
`spacingN` token whose value matches the gap you need (e.g. a 12px panel
padding is `Metrics.spacing12`).

### Typography (`Typography`)
```
display (22px), headingLarge (18px), heading (16px)
subtitle (14px), bodyLarge (14px), body (13px), caption (11px)
fontFamily, monoFamily, weightLight–weightBold
```

### Sizing (`Metrics`)
```
controlHeight=36px, compactControlHeight=30px            → buttons & inputs
tableRowHeight=28px, compactRowHeight=24px
iconSmall=16px, iconNormal=24px, iconLarge=32px, iconXLarge=48px
radiusSmall=3px, radiusMedium=5px, radiusLarge=8px
```

### Breakpoints (`Metrics`)
```
breakpointCompact = 1240px      → 1-column layout
breakpointUltraWide = 1800px    → data-dense layout
```

---

## Rules

**DO:**
- ✅ `color: Theme.primary`
- ✅ `anchors.margins: Metrics.spacing16`
- ✅ `font.pixelSize: Typography.body`
- ✅ `implicitHeight: Metrics.controlHeight`

**DON'T:**
- ❌ `color: "#0078d4"`
- ❌ `anchors.margins: 16`
- ❌ `font.pixelSize: 14`
- ❌ `implicitHeight: 32`

---

## Testing

1. Launch the app.
2. Is text readable? Are form fields distinct from the background?
3. Do borders/dividers, disabled states, and error/success/warning states all
   read clearly?

The app is light-mode only — there is no theme toggle to check, and no dark
mode pass is needed.

---

## Need More Info?

| Need | File |
|------|------|
| Complete token reference | [DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md) |
| Code examples & patterns | [COMPONENT_USAGE.md](./COMPONENT_USAGE.md) |
| Pre-commit checklist | [THEME_VALIDATION_CHECKLIST.md](./THEME_VALIDATION_CHECKLIST.md) |
| JSON token export | [design-tokens.json](./design-tokens.json) |
| Token implementation | [Theme.qml](../src/crane_statics/qml_app/design/BF/DesignSystem/Theme.qml), [Metrics.qml](../src/crane_statics/qml_app/design/BF/DesignSystem/Metrics.qml), [Typography.qml](../src/crane_statics/qml_app/design/BF/DesignSystem/Typography.qml) |

---

**That's it!** You're ready to use design tokens. See THEME_VALIDATION_CHECKLIST.md before committing changes.
