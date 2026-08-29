# Crane Statics Design System

## Overview

The Crane Statics Design System is a token-based, QML-native system designed for engineering-focused professionals. It prioritizes **clarity, efficiency, and consistency** over decorative styling.

### Key Principles

1. **Token-First**: All visual properties are defined as reusable tokens (colors, spacing, typography, sizing)
2. **Fusion-Native**: Leverages Qt's Fusion style and SystemPalette for OS-aware light/dark themes
3. **Minimal Customization**: Follows OS conventions; no hardcoded colors or custom theme machinery
4. **Responsive**: Adapts layout and density based on window size and user preference
5. **Accessible**: Ensures WCAG AA contrast standards in both light and dark modes

---

## Token System

All design tokens are defined in the **`DesignTokens.qml`** singleton. Import it in any QML file:

```qml
import Crane.DesignTokens 1.0

Rectangle {
    color: DesignTokens.colors.surface
    anchors.margins: DesignTokens.spacing.md
    font.pixelSize: DesignTokens.typography.body
}
```

### Token Categories

#### 1. **Colors** (Semantic Roles)

All color tokens automatically adapt to light/dark theme via SystemPalette:

| Token | Role | Light Mode | Dark Mode | Usage |
|-------|------|-----------|----------|-------|
| `colors.surface` | Primary surface | #ffffff | #2d2d2d | Tables, inputs, cards, default background |
| `colors.surfaceAlt` | Secondary surface | #f0f0f0 | #383838 | Panels, section groups, alternate backgrounds |
| `colors.background` | App background | #f3f3f3 | #1e1e1e | Window background |
| `colors.textPrimary` | Main text | #000000 | #ffffff | Body text, labels, primary information |
| `colors.textSecondary` | Supporting text | #777777 | #b0b0b0 | Form labels, hints, secondary information |
| `colors.textDisabled` | Disabled text | #999999 | #666666 | Disabled controls, inactive state |
| `colors.primary` | Primary action | #0078d4 | #4fa3ff | Buttons, links, active selection |
| `colors.success` | Success state | #4caf50 | #4caf50 | Checkmarks, valid indicators, success alerts |
| `colors.warning` | Warning state | #ff9800 | #ff9800 | Caution alerts, non-critical warnings |
| `colors.error` | Error state | #f44336 | #f44336 | Invalid inputs, error messages, failures |
| `colors.info` | Information | #2196f3 | #2196f3 | Tooltips, help text, information alerts |
| `colors.border` | Borders & dividers | #cccccc | #444444 | Table borders, input borders, rule lines |

**When to use semantic colors instead of hardcoding:**

- ❌ **Don't:** `Rectangle { color: "#0078d4" }`
- ✅ **Do:** `Rectangle { color: DesignTokens.colors.primary }`

This ensures automatic theme adaptation and consistency across all views.

#### 2. **Typography** (Font Sizes, Families, Weights)

Font sizes are in logical pixels (scale with system DPI):

| Token | Size | Usage | Example |
|-------|------|-------|---------|
| `typography.caption` | 11px | Small labels, help text | Form hints, table captions |
| `typography.body` | 13px | Default text | Table cells, input text, paragraph text |
| `typography.bodyLarge` | 14px | Larger body text | Important body, data summaries |
| `typography.subtitle` | 14px | Subtitles, secondary headings | Subsection titles, group labels |
| `typography.heading` | 16px | Section headings | Dialog titles, panel headers |
| `typography.headingLarge` | 18px | Major headings | Workspace titles, main section headers |
| `typography.display` | 22px | Large titles | Application title |

**Font families:**
- `typography.fontFamily`: "Segoe UI, Ubuntu, 'Liberation Sans', sans-serif"
- `typography.monoFamily`: "'Consolas', 'Monaco', 'Courier New', monospace"

**Font weights:**
- `typography.weightLight`: 300
- `typography.weightRegular`: 400 (default)
- `typography.weightMedium`: 500
- `typography.weightSemiBold`: 600
- `typography.weightBold`: 700

**Example:**
```qml
Text {
    text: "Form Field Label"
    font.family: DesignTokens.typography.fontFamily
    font.pixelSize: DesignTokens.typography.body
    font.weight: DesignTokens.typography.weightMedium
}
```

#### 3. **Spacing** (Margins, Padding, Gaps)

Base unit is **4px**. Scale: xs=4, sm=8, md=16, lg=24, xl=32, xxl=48

| Token | Value | Usage |
|-------|-------|-------|
| `spacing.xs` | 4px | Tight spacing, borders, minimal gaps |
| `spacing.sm` | 8px | Small spacing, compact form fields |
| `spacing.md` | 16px | Medium spacing, standard margins, panel padding |
| `spacing.lg` | 24px | Large spacing, section gaps |
| `spacing.xl` | 32px | Extra large spacing, workspace separation |
| `spacing.xxl` | 48px | Double extra large, major page sections |

**Grouped spacings:**
- `spacing.controlGap`: 8px (gap between inline controls)
- `spacing.rowGap`: 8px (gap between form rows)
- `spacing.sectionGap`: 16px (gap between major sections)
- `spacing.panelPadding`: 12px (padding inside panels/cards)
- `spacing.dialogPadding`: 16px (padding inside dialogs)

**Example:**
```qml
ColumnLayout {
    spacing: DesignTokens.spacing.rowGap
    
    Button { text: "Save" }
    Button { text: "Cancel" }
}

Rectangle {
    anchors.margins: DesignTokens.spacing.md
}
```

#### 4. **Sizing** (Control Dimensions)

| Token | Value | Usage |
|-------|-------|-------|
| `sizing.buttonHeight` | 32px | Standard button height |
| `sizing.buttonHeightSmall` | 24px | Compact button height |
| `sizing.inputHeight` | 32px | Text input, combo box, spinner |
| `sizing.inputHeightSmall` | 24px | Compact input field |
| `sizing.rowHeight` | 28px | Table/list row height |
| `sizing.rowHeightCompact` | 24px | Compact table row (density mode) |
| `sizing.rowHeightRelaxed` | 32px | Relaxed table row (density mode) |

**Icon sizes:**
- `sizing.iconSmall`: 16px (inline icons)
- `sizing.iconNormal`: 24px (standard icons)
- `sizing.iconLarge`: 32px (large standalone icons)

**Border radii:**
- `sizing.radiusNone`: 0px
- `sizing.radiusSmall`: 2px (subtle curves)
- `sizing.radiusNormal`: 4px (standard corners)
- `sizing.radiusLarge`: 8px (pronounced curves)

#### 5. **Shadows** (Elevation Levels)

Elevation shadows provide visual hierarchy for modals, popovers, and floating elements:

```qml
DropShadow {
    // elevation1: subtle shadow for hover states
    xOffset: 0
    yOffset: 1
    blur: 3
    color: DesignTokens.shadows.getShadowColor()
    opacity: 0.12
}
```

#### 6. **Layout** (Responsive Breakpoints & Density)

**Breakpoints:**
- **Compact** (`< 1240px`): 1-column layout, stacked panels (narrow windows)
- **Wide** (`≥ 1240px`): 2-column layout, side-by-side panels (standard windows)
- **Ultra-Wide** (`≥ 1800px`): 3-column or data-dense table layouts (large monitors)

**Density Modes** (settable from View menu):
- **Relaxed**: Row height ×1.15, spacing ×1.25 (comfortable for data entry)
- **Normal**: Row height ×1.0, spacing ×1.0 (balanced default)
- **Compact**: Row height ×0.85, spacing ×0.75 (efficient for data-heavy tables)

Access computed row height and spacing:
```qml
TableView {
    rowHeight: DesignTokens.layout.tableRowHeight  // Automatically adjusts with density mode
}
```

---

## Component Catalog

Reusable, token-aware components are located in `src/crane_statics/qml_app/qml/components/`.

Each component:
- Uses design tokens for all sizing, spacing, colors
- Supports enabled/disabled/hovered/active states
- Includes keyboard accessibility (focus indicators, keyboard navigation)
- Has comprehensive usage documentation

### Available Components

| Component | Purpose | Notes |
|-----------|---------|-------|
| `Button.qml` | Standard button with states | Padding, text size, hover/pressed states via tokens |
| `TextField.qml` | Text input wrapper | Consistent height, padding, border via tokens |
| `ComboBox.qml` | Dropdown selector | Token spacing, semantic colors |
| `Dialog.qml` | Base modal wrapper | Enforces title/footer/button sizing consistency |
| `Card.qml` | Container with elevation | Token padding, shadow, radius |
| `Section.qml` | Titled collapsible group | Token spacing, typography hierarchy |
| `Badge.qml` | Small indicators | Semantic colors (success, warning, error, info) |
| `Table.qml` | Enhanced data table | Consistent header/row styling, density support |
| `StyledCheckBox.qml` / `StyledRadioButton.qml` | Selection controls | Semantic colors and keyboard focus states |
| `StyledTabButton.qml` | Tab control | Token-aware tab styling |
| `IconButton.qml` | Icon command control | Compact, accessible command affordance |

### Using Existing Components

Use Qt Controls with token bindings when an available wrapper does not fit the required interaction:

```qml
import QtQuick.Controls.Fusion
import Crane.DesignTokens 1.0

Button {
    text: "Save"
    implicitHeight: DesignTokens.sizing.buttonHeight
    palette.buttonText: DesignTokens.colors.textInverse
    palette.button: DesignTokens.colors.primary
}
```

---

## Color Semantics

### Primary Actions

Use for buttons, links, and active selections:
```qml
Button {
    palette.button: DesignTokens.colors.primary
    palette.buttonText: DesignTokens.colors.textInverse
}
```

### Status Colors

Use for validation feedback and state indicators:

| Semantic | Color | Usage |
|----------|-------|-------|
| **Success** | Green (#4caf50) | Valid inputs, confirmation, successful operations |
| **Warning** | Orange (#ff9800) | Non-critical alerts, caution states |
| **Error** | Red (#f44336) | Invalid inputs, errors, failed operations |
| **Info** | Blue (#2196f3) | Help text, tooltips, informational messages |

### Engineering Data Visualization

For crane loading analysis (stress levels, capacity usage):

**Numeric Level to Color Mapping** (0.0 = safe, 1.0 = critical):
```qml
// 0.0–0.4: Safe (Green)
color: DesignTokens.colors.success

// 0.4–0.7: Caution (Orange)
color: DesignTokens.colors.warning

// 0.7–1.0: Critical/Overload (Red)
color: DesignTokens.colors.error

// Programmatic:
color: DesignTokens.getStatusColor(stressLevel)  // stressLevel: 0.0–1.0
```

---

## Responsive Design

### Adapting to Window Size

Check breakpoint to adjust layout:

```qml
Item {
    readonly property bool compact: width < DesignTokens.layout.breakpointCompact
    
    GridLayout {
        columns: root.compact ? 1 : 2
        columnSpacing: DesignTokens.spacing.md
        rowSpacing: DesignTokens.spacing.md
    }
}
```

**Existing:** [ModelWorkspace.qml](../../src/crane_statics/qml_app/qml/ModelWorkspace.qml#L10) already implements this pattern.

### Adapting to Density Mode

All table rows, spacing, and control sizes automatically adapt:

```qml
TableView {
    rowHeight: DesignTokens.layout.tableRowHeight  // Responds to density changes
}

ColumnLayout {
    spacing: Math.round(DesignTokens.spacing.md * DesignTokens.layout.spacingMultiplier)
}
```

---

## Accessibility

### Contrast Requirements (WCAG AA)

All color combinations must meet minimum contrast ratios:
- **Body text on background**: 4.5:1 (minimum)
- **Large text (18px+) on background**: 3:1 (minimum)
- **UI controls on background**: 3:1 (minimum)

**Current Status:**
- Light mode: All text meets WCAG AA (verified via SystemPalette bindings)
- Dark mode: All text meets WCAG AA (verified via SystemPalette bindings)
- Fusion's built-in palettes are designed to meet accessibility standards

### Focus Indicators

All interactive controls must show a focus ring on keyboard navigation:

```qml
Control {
    focusRectangle.border.color: DesignTokens.colors.focusRing
    focusRectangle.border.width: 2
}
```

### Text & Color Dependency

Never rely on color alone to convey information:

- ❌ **Don't:** Red text to indicate error (colorblind users can't distinguish)
- ✅ **Do:** Red text **+ error icon + error message** to indicate error

### Keyboard Navigation

All controls must be keyboard accessible:
- Tab key navigates between interactive elements
- Enter/Space activates buttons
- Arrow keys navigate in lists/tables
- Escape closes modals

---

## Dark / Light Mode

### How Theming Works

1. **OS Level**: Windows Settings > Personalization > Colors → App follows automatically
2. **App Level**: View > Appearance menu allows manual override (Light / Dark / Follow System)
3. **Technical**: `QGuiApplication.styleHints().setColorScheme()` sets the theme
4. **Automatic**: SystemPalette reflects the chosen theme; all token colors update instantly

### Theme-Aware Colors

All semantic color tokens automatically adapt:

```qml
// This works in both light and dark modes without extra code:
Rectangle {
    color: DesignTokens.colors.surface  // #ffffff in light, #2d2d2d in dark
}

Text {
    color: DesignTokens.colors.textPrimary  // #000000 in light, #ffffff in dark
}
```

### Verification Checklist

When adding new UI elements, verify in both light and dark modes:

- [ ] Text is readable (contrast ≥ 4.5:1 for body text)
- [ ] Colors use semantic tokens (not hardcoded RGB values)
- [ ] Borders/dividers are visible in both modes
- [ ] Form fields are distinguishable from background
- [ ] Disabled states are clearly indicated
- [ ] Error/success/warning states are legible
- [ ] Charts/plots have sufficient color contrast

### Testing Theme Switch

1. Open the app in light mode
2. Switch to dark mode: View > Appearance > Dark
3. Visually inspect all panels, tables, dialogs, charts
4. Run test suite (should pass with no visual regression)

---

## Typography Scale & Usage

### Font Size Hierarchy

```
Display (22px) — Application title
  ↓
Heading Large (18px) — Workspace titles, main section headers
  ↓
Heading (16px) — Dialog titles, panel headers
  ↓
Subtitle (14px) — Subsection titles, group labels
  ↓
Body Large (14px) — Important body text, data summaries
  ↓
Body (13px) — Standard text, table cells, inputs
  ↓
Caption (11px) — Form hints, table captions
```

### Font Weight Hierarchy

**Headings** (use weights to create emphasis):
```qml
// Section heading
Text {
    text: "Model Parameters"
    font.pixelSize: DesignTokens.typography.heading
    font.weight: DesignTokens.typography.weightSemiBold  // 600
}

// Form label
Text {
    text: "Hoist Load (kg):"
    font.pixelSize: DesignTokens.typography.body
    font.weight: DesignTokens.typography.weightMedium    // 500
}

// Body text
Text {
    text: "This is a description..."
    font.pixelSize: DesignTokens.typography.body
    font.weight: DesignTokens.typography.weightRegular   // 400
}
```

### Line Height Guidelines

- **Headings** (22px–16px): line height 1.2 (tight, professional look)
- **Body text** (13px–14px): line height 1.5 (readable, standard)
- **Help text / descriptions**: line height 1.8 (relaxed, emphasis on readability)

```qml
Text {
    text: "Help text..."
    font.pixelSize: DesignTokens.typography.caption
    lineHeight: DesignTokens.typography.lineHeightRelaxed  // 1.8
}
```

---

## Common Patterns

### Form Field with Label

```qml
ColumnLayout {
    spacing: DesignTokens.spacing.sm
    
    Text {
        text: "Field Label"
        font.pixelSize: DesignTokens.typography.body
        font.weight: DesignTokens.typography.weightMedium
        color: DesignTokens.colors.textPrimary
    }
    
    TextField {
        implicitHeight: DesignTokens.sizing.inputHeight
        palette.text: DesignTokens.colors.textPrimary
        palette.base: DesignTokens.colors.surface
        palette.mid: DesignTokens.colors.border
    }
}
```

### Table with Consistent Styling

```qml
DataTable {
    title: "Results"
    model: resultsModel
    
    delegate: ItemDelegate {
        implicitHeight: DesignTokens.layout.tableRowHeight
        background: Rectangle {
            color: hovered ? DesignTokens.colors.surfaceAlt : DesignTokens.colors.surface
        }
    }
}
```

### Dialog with Styled Buttons

```qml
Dialog {
    title: "Confirm Action"
    standardButtons: Dialog.Ok | Dialog.Cancel
    
    footer: DialogButtonBox {
        Button {
            text: "OK"
            implicitHeight: DesignTokens.sizing.buttonHeight
            palette.button: DesignTokens.colors.primary
            palette.buttonText: DesignTokens.colors.textInverse
        }
    }
}
```

### Status Indicator

```qml
Rectangle {
    width: DesignTokens.sizing.iconNormal
    height: DesignTokens.sizing.iconNormal
    radius: DesignTokens.sizing.radiusRound
    color: DesignTokens.getStatusColor(stressLevel)  // 0.0–1.0
}
```

---

## Related Guides

- [QUICKSTART.md](QUICKSTART.md) introduces the token singleton and common bindings.
- [COMPONENT_USAGE.md](COMPONENT_USAGE.md) provides component APIs and usage patterns.
- [THEME_VALIDATION_CHECKLIST.md](THEME_VALIDATION_CHECKLIST.md) covers theme, density, and accessibility checks.

---

## Developer Quick Reference

### Import DesignTokens in Your QML

```qml
import Crane.DesignTokens 1.0
```

### Common Token Shortcuts

```qml
// Colors
colors.surface          // Primary background for tables, inputs
colors.textPrimary      // Main text color
colors.primary          // Primary action (buttons, links)
colors.success/warning/error/info  // Semantic status colors

// Spacing
spacing.sm  // 8px
spacing.md  // 16px
spacing.lg  // 24px

// Typography
typography.body           // 13px default text
typography.heading        // 16px section heading
typography.fontFamily     // Font family string

// Sizing
sizing.buttonHeight       // 32px
sizing.inputHeight        // 32px
sizing.rowHeight          // 28px (or density-adjusted)

// Layout
layout.breakpointCompact  // 1240px (switch to 1-column)
layout.tableRowHeight     // Density-aware row height
```

### Never Use Hardcoded Values

- ❌ `color: "#0078d4"` → ✅ `color: DesignTokens.colors.primary`
- ❌ `anchors.margins: 16` → ✅ `anchors.margins: DesignTokens.spacing.md`
- ❌ `implicitHeight: 32` → ✅ `implicitHeight: DesignTokens.sizing.buttonHeight`
- ❌ `font.pixelSize: 13` → ✅ `font.pixelSize: DesignTokens.typography.body`

---

## Questions & Support

For design system questions or to propose new tokens/components:

1. Check [design-tokens.json](./design-tokens.json) for current token definitions
2. Review existing component usage in [src/crane_statics/qml_app/qml/](../../src/crane_statics/qml_app/qml/)
3. Open an issue describing the missing token/component with use case
4. Follow the component creation steps in COMPONENT_USAGE.md

---

**Last Updated:** 2026-08-14  
**Design System Version:** 1.0.0  
**Platform:** Qt 6.x, PyQt6, QML  
**Style:** Fusion (OS-aware light/dark theming)
