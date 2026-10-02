# Crane Statics Design System

## Overview

The Crane Statics Design System is a token-based, QML-native system designed for engineering-focused professionals. It prioritizes **clarity, efficiency, and consistency** over decorative styling.

### Key Principles

1. **Token-First**: All visual properties are defined as reusable tokens (colors, spacing, typography, sizing)
2. **Brand-Native**: Built from the fixed BF/NOV color palette; Qt's Fusion style renders the controls
3. **Minimal Customization**: No hardcoded colors or custom theme machinery — every value comes from `Theme`, `Metrics`, or `Typography`
4. **Responsive**: Adapts layout based on window size
5. **Accessible**: Ensures WCAG AA contrast; pastel semantic tones use `Theme.contrastText()`/`Theme.getOnSemanticColor()` to pick a legible text color automatically

---

## Token System

All design tokens are defined in three singletons under the **`BF.DesignSystem`** module: `Theme` (colors + helper functions), `Metrics` (spacing/sizing/radii/breakpoints), and `Typography` (font family/weights/sizes). Import the module in any QML file:

```qml
import BF.DesignSystem

Rectangle {
    color: Theme.surface
    anchors.margins: Metrics.spacing16
    font.pixelSize: Typography.body
}
```

The module also ships five ready-made controls that already apply these tokens — `BfButton`, `BfTextField`, `BfCard`, `BfStatusBadge`, `BfPage` — see [Component Catalog](#component-catalog) below. It resolves via `engine.addImportPath()` pointed at the `design/` folder in `app.py`; there is no CMake build step in this app.

### Token Categories

#### 1. **Colors** (Semantic Roles, `Theme`)

The app is light-mode only. All color tokens resolve to fixed values built from the BF/NOV brand palette — there is no `SystemPalette` binding and no dark variant.

| Token | Role | Value | Usage |
|-------|------|-------|-------|
| `Theme.surface` | Primary surface | `white` (`#FFFFFF`) | Tables, inputs, cards, default background |
| `Theme.surfaceSubtle` | Secondary surface | `novPurple50Tint` (`#CCC1D4`) | Panels, section groups, alternate backgrounds |
| `Theme.pageBackground` | App background | `white` (`#FFFFFF`) | Window / page background |
| `Theme.text` | Main text | `black` (`#000000`) | Body text, labels, primary information |
| `Theme.textMuted` | Supporting text | `novGrey` (`#78757B`) | Form labels, hints, secondary information |
| `Theme.disabledText` | Disabled text | `Qt.lighter(novGrey, 120)` | Disabled controls, inactive state |
| `Theme.disabledSurface` | Disabled fill | `Qt.lighter(novGrey, 155)` | Disabled control backgrounds |
| `Theme.textOnDark` | Text on dark/solid fills | `white` (`#FFFFFF`) | Fallback inverse text |
| `Theme.primary` | Primary action | `novBlue` (`#007096`) | Buttons, links, active selection |
| `Theme.primaryHover` | Primary hover | `Qt.lighter(novBlue, 112)` | Hover feedback |
| `Theme.primaryPressed` | Primary pressed | `Qt.darker(novBlue, 115)` | Pressed feedback |
| `Theme.primaryDisabled` | Primary disabled | `Qt.lighter(novBlue, 170)` | Disabled primary buttons |
| `Theme.onPrimary` | Text on `primary` | `white` | Button labels on a primary fill |
| `Theme.accent` | Accent action | `novYellow` (`#FFCD00`) | Secondary emphasis |
| `Theme.onAccent` | Text on `accent` | `black` | Labels on an accent fill |
| `Theme.success` | Success state | `novGreen` (`#A9C47F`) | Checkmarks, valid indicators, success alerts |
| `Theme.warning` | Warning state | `novOrange` (`#DC9575`) | Caution alerts, non-critical warnings |
| `Theme.error` | Error state | `novRed` (`#DA291C`) | Invalid inputs, error messages, failures |
| `Theme.info` | Information | `novTeal` (`#00A499`) | Tooltips, help text, information alerts |
| `Theme.successSurface`/`warningSurface`/`errorSurface`/`infoSurface` | Pastel status fills | `novGreen50Tint`/`novOrange50Tint`/`novDarkRed50Tint`/`novTeal50Tint` | Badge/pill backgrounds, subtle status callouts |
| `Theme.onSuccess`/`onWarning`/`onError`/`onInfo` | Contrast-safe text | computed by `Theme.contrastText()` | Text/icons placed on top of a solid status tone |
| `Theme.border` | Borders & dividers | `novGrey` (`#78757B`) | Table borders, input borders, rule lines |
| `Theme.borderSubtle` | Subtle border | `novPurple50Tint` (`#CCC1D4`) | Low-emphasis dividers |
| `Theme.focusRing` | Keyboard focus | `novBlue` (`#007096`) | Focus outlines |
| `Theme.selection` | Selection fill | `novBlue50Tint` (`#82B4C9`) | Selected rows/text — a light tint, not a solid fill |
| `Theme.selectionText` | Text on selection | `Theme.text` (dark) | Selected text stays the normal dark color since the fill is a light tint |
| `Theme.overlay` | Modal/dialog overlay | `rgba(0, 0, 0, 0.5)` | Dimming behind dialogs |
| `Theme.shadowColor` | Shadow tint | `rgba(0, 0, 0, 0.15)` | `MultiEffect`/drop-shadow color for elevated surfaces |

All raw BF/NOV palette swatches (`novBlue`, `novYellow`, `novPurple`, `novTeal`, etc.) are also exposed directly on `Theme` for one-off brand accents; prefer the semantic names above for anything that isn't a deliberate brand callout.

**When to use semantic colors instead of hardcoding:**

- ❌ **Don't:** `Rectangle { color: "#007096" }`
- ✅ **Do:** `Rectangle { color: Theme.primary }`

This ensures consistency across all views and keeps contrast guarantees centralized in `Theme`.

#### 2. **Typography** (Font Sizes, Families, Weights, `Typography`)

Font sizes are in logical pixels (scale with system DPI):

| Token | Size | Usage | Example |
|-------|------|-------|---------|
| `Typography.caption` | 11px | Small labels, help text | Form hints, table captions |
| `Typography.body` | 13px | Default text | Table cells, input text, paragraph text |
| `Typography.bodyLarge` | 14px | Larger body text | Important body, data summaries |
| `Typography.subtitle` | 14px | Subtitles, secondary headings | Subsection titles, group labels |
| `Typography.heading` | 16px | Section headings | Dialog titles, panel headers |
| `Typography.headingLarge` | 18px | Major headings | Workspace titles, main section headers |
| `Typography.display` | 22px | Large titles | Application title |

**Font families:**
- `Typography.fontFamily`: "Segoe UI, Ubuntu, 'Liberation Sans', sans-serif"
- `Typography.monoFamily`: "'Consolas', 'Monaco', 'Courier New', monospace"

**Font weights:**
- `Typography.weightLight`: 300
- `Typography.weightRegular`: 400 (default)
- `Typography.weightMedium`: 500
- `Typography.weightSemiBold`: 600
- `Typography.weightBold`: 700

**Example:**
```qml
Text {
    text: "Form Field Label"
    font.family: Typography.fontFamily
    font.pixelSize: Typography.body
    font.weight: Typography.weightMedium
}
```

Note: `Metrics` also defines its own small internal font-size scale
(`fontSizeSmall`/`fontSizeBody`/`fontSizeSubtitle`/`fontSizeTitle` — 12/14/16/22px)
used by the `Bf*` controls for their own chrome (e.g. `BfButton` labels use
`Metrics.fontSizeBody`, `BfStatusBadge` uses `Metrics.fontSizeSmall`). For your
own QML, prefer the `Typography.*` scale above; it's the general-purpose scale
this document and `COMPONENT_USAGE.md` build examples around.

#### 3. **Spacing** (Margins, Padding, Gaps, `Metrics`)

The spacing scale is a flat, numerically-named set (no semantic aliases like `xs`/`md` anymore — pick the value that matches the gap you need):

| Token | Value |
|-------|-------|
| `Metrics.spacing2` | 2px |
| `Metrics.spacing4` | 4px |
| `Metrics.spacing6` | 6px |
| `Metrics.spacing8` | 8px |
| `Metrics.spacing12` | 12px |
| `Metrics.spacing16` | 16px |
| `Metrics.spacing24` | 24px |
| `Metrics.spacing32` | 32px |
| `Metrics.spacing48` | 48px |

There is no `controlGap`/`rowGap`/`sectionGap`/`panelPadding`/`dialogPadding` grouping anymore. If you're porting old code that used one of those, use the `spacingN` token with the matching value (e.g. old `panelPadding` was 12px → `Metrics.spacing12`; old `sectionGap`/`dialogPadding` were 16px → `Metrics.spacing16`).

**Example:**
```qml
ColumnLayout {
    spacing: Metrics.spacing8

    Button { text: "Save" }
    Button { text: "Cancel" }
}

Rectangle {
    anchors.margins: Metrics.spacing16
}
```

#### 4. **Sizing** (Control Dimensions, `Metrics`)

| Token | Value | Usage |
|-------|-------|-------|
| `Metrics.controlHeight` | 36px | Standard button/input height |
| `Metrics.compactControlHeight` | 30px | Compact button/input height |
| `Metrics.buttonMinWidth` | 96px | Minimum button width |
| `Metrics.fieldMinWidth` | 160px | Minimum input field width |
| `Metrics.minInputWidth` | 60px | Smallest allowed input width |
| `Metrics.maxInputWidth` | 200px | Largest allowed input width |
| `Metrics.dialogWidth` | 480px | Default dialog width |
| `Metrics.tableRowHeight` | 28px | Table/list row height |
| `Metrics.compactRowHeight` | 24px | Compact table row |

There's no separate `buttonHeight` vs. `inputHeight` anymore — both use `controlHeight`/`compactControlHeight`. There's also no "relaxed" row height variant.

**Icon sizes:**
- `Metrics.iconSmall`: 16px (inline icons)
- `Metrics.iconNormal`: 24px (standard icons)
- `Metrics.iconLarge`: 32px (large standalone icons)
- `Metrics.iconXLarge`: 48px (hero/empty-state icons)

**Border widths & radii:**
- `Metrics.borderWidth`: 1px (standard hairline border)
- `Metrics.borderWidthNormal`: 2px (emphasized border, e.g. error state)
- `Metrics.focusWidth`: 2px (focus ring width)
- `Metrics.radiusSmall`: 3px (subtle curves)
- `Metrics.radiusMedium`: 5px (standard corners)
- `Metrics.radiusLarge`: 8px (pronounced curves)

There's no `radiusNone` (use the literal `0`) and no dedicated 3px "thick" border width — use `borderWidthNormal` or `focusWidth` for emphasis.

#### 5. **Shadows**

There's no `elevation1`/`elevation2`/`elevation3` preset table anymore. Elevated
surfaces provide their own offset/blur and tint with `Theme.shadowColor`
(`rgba(0, 0, 0, 0.15)`), the way `BfCard.qml` does it:

```qml
layer.enabled: true
layer.effect: MultiEffect {
    shadowEnabled: true
    shadowColor: Theme.shadowColor
    shadowBlur: 0.35
    shadowVerticalOffset: 2
}
```

Note this uses `QtQuick.Effects`' `MultiEffect`, not the old `DropShadow` type — `shadowBlur` is a normalized `0..1` value, not a pixel radius.

#### 6. **Layout** (Responsive Breakpoints, `Metrics`)

**Breakpoints:**
- **Compact** (`< 1240px`): 1-column layout, stacked panels (narrow windows)
- **Wide** (`≥ 1240px`): 2-column layout, side-by-side panels (standard windows)
- **Ultra-Wide** (`≥ 1800px`): 3-column or data-dense table layouts (large monitors)

There's a single `Metrics.breakpointCompact` (1240) and `Metrics.breakpointUltraWide` (1800) — "wide" is simply "not compact," so there's no separate `breakpointWide` constant.

Access the shared row height and spacing multiplier:
```qml
TableView {
    rowHeight: Metrics.tableRowHeight
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
| `Table.qml` | Enhanced data table | Consistent header/row styling |
| `StyledCheckBox.qml` / `StyledRadioButton.qml` | Selection controls | Semantic colors and keyboard focus states |
| `StyledTabButton.qml` | Tab control | Token-aware tab styling |
| `IconButton.qml` | Icon command control | Compact, accessible command affordance |

### The `BF.DesignSystem` controls

Alongside the components above, `BF.DesignSystem` ships five controls that already apply `Theme`/`Metrics`/`Typography` internally, for the most common cases:

| Control | Purpose | Notes |
|---------|---------|-------|
| `BfButton.qml` | Standard button | `variant`: `"primary"` \| `"secondary"` \| `"ghost"` \| `"danger"` |
| `BfTextField.qml` | Text input | `isError`/`errorText` built in |
| `BfCard.qml` | Elevated container | Default property alias `content`; shadow via `MultiEffect` |
| `BfStatusBadge.qml` | Status pill | `status`: `"success"` \| `"warning"` \| `"error"` \| `"info"` \| `"neutral"`; contrast-safe text via `Theme.contrastText()` |
| `BfPage.qml` | Themed root container | `padding` property, default property alias `content` |

Reach for a `Bf*` control before hand-rolling the equivalent pattern with a raw Fusion control plus tokens.

### Using Existing Components

Use Qt Controls with token bindings when an available wrapper does not fit the required interaction:

```qml
import QtQuick.Controls.Fusion
import BF.DesignSystem

Button {
    text: "Save"
    implicitHeight: Metrics.controlHeight
    palette.buttonText: Theme.onPrimary
    palette.button: Theme.primary
}
```

---

## Color Semantics

### Primary Actions

Use for buttons, links, and active selections:
```qml
Button {
    palette.button: Theme.primary
    palette.buttonText: Theme.onPrimary
}
```

### Status Colors

Use for validation feedback and state indicators:

| Semantic | Color | Usage |
|----------|-------|-------|
| **Success** | NOV green (`#A9C47F`) | Valid inputs, confirmation, successful operations |
| **Warning** | NOV orange (`#DC9575`) | Non-critical alerts, caution states |
| **Error** | NOV red (`#DA291C`) | Invalid inputs, errors, failed operations |
| **Info** | NOV teal (`#00A499`) | Help text, tooltips, informational messages |

### Engineering Data Visualization

For crane loading analysis (stress levels, capacity usage):

**Numeric Level to Color Mapping** (0.0 = safe, 1.0 = critical):
```qml
// 0.0–0.4: Safe (Green)
color: Theme.success

// 0.4–0.7: Caution (Orange)
color: Theme.warning

// 0.7–1.0: Critical/Overload (Red)
color: Theme.error

// Programmatic:
color: Theme.getStatusColor(stressLevel)  // stressLevel: 0.0–1.0
```

---

## Responsive Design

### Adapting to Window Size

Check breakpoint to adjust layout:

```qml
Item {
    readonly property bool compact: width < Metrics.breakpointCompact

    GridLayout {
        columns: root.compact ? 1 : 2
        columnSpacing: Metrics.spacing16
        rowSpacing: Metrics.spacing16
    }
}
```

**Existing:** [ModelWorkspace.qml](../../src/crane_statics/qml_app/qml/ModelWorkspace.qml#L10) already implements this pattern.

### Shared Row Height and Spacing

All table rows, spacing, and control sizes come from the tokens:

```qml
TableView {
    rowHeight: Metrics.tableRowHeight
}

ColumnLayout {
    spacing: Math.round(Metrics.spacing16 * Metrics.spacingMultiplier)
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
- All text meets WCAG AA against its documented background
- The nov palette's semantic tones (`success`/`warning`/`error`/`info`) are pastel, so `Theme.onSuccess`/`onWarning`/`onError`/`onInfo` (backed by `Theme.contrastText()`) pick whichever of black/white actually clears 4.5:1 against that tone — don't assume a fixed inverse text color is safe on a status fill

### Focus Indicators

All interactive controls must show a focus ring on keyboard navigation:

```qml
Control {
    focusRectangle.border.color: Theme.focusRing
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
    font.pixelSize: Typography.heading
    font.weight: Typography.weightSemiBold  // 600
}

// Form label
Text {
    text: "Hoist Load (kg):"
    font.pixelSize: Typography.body
    font.weight: Typography.weightMedium    // 500
}

// Body text
Text {
    text: "This is a description..."
    font.pixelSize: Typography.body
    font.weight: Typography.weightRegular   // 400
}
```

### Line Height Guidelines

- **Headings** (22px–16px): line height 1.2 (tight, professional look)
- **Body text** (13px–14px): line height 1.5 (readable, standard)
- **Help text / descriptions**: line height 1.8 (relaxed, emphasis on readability)

```qml
Text {
    text: "Help text..."
    font.pixelSize: Typography.caption
    lineHeight: Typography.lineHeightRelaxed  // 1.8
}
```

---

## Common Patterns

### Form Field with Label

```qml
ColumnLayout {
    spacing: Metrics.spacing8

    Text {
        text: "Field Label"
        font.pixelSize: Typography.body
        font.weight: Typography.weightMedium
        color: Theme.text
    }

    TextField {
        implicitHeight: Metrics.controlHeight
        palette.text: Theme.text
        palette.base: Theme.surface
        palette.mid: Theme.border
    }
}
```

### Table with Consistent Styling

```qml
DataTable {
    title: "Results"
    model: resultsModel

    delegate: ItemDelegate {
        implicitHeight: Metrics.tableRowHeight
        background: Rectangle {
            color: hovered ? Theme.surfaceSubtle : Theme.surface
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
            implicitHeight: Metrics.controlHeight
            palette.button: Theme.primary
            palette.buttonText: Theme.onPrimary
        }
    }
}
```

### Status Indicator

```qml
Rectangle {
    width: Metrics.iconNormal
    height: Metrics.iconNormal
    radius: height / 2
    color: Theme.getStatusColor(stressLevel)  // 0.0–1.0
}
```

Or simply use `BfStatusBadge { status: "success"; text: "OK" }` for the labeled-pill version.

---

## Related Guides

- [QUICKSTART.md](QUICKSTART.md) introduces the token singletons and common bindings.
- [COMPONENT_USAGE.md](COMPONENT_USAGE.md) provides component APIs and usage patterns.
- [THEME_VALIDATION_CHECKLIST.md](THEME_VALIDATION_CHECKLIST.md) covers token and accessibility checks.

---

## Developer Quick Reference

### Import the Design System in Your QML

```qml
import BF.DesignSystem
```

### Common Token Shortcuts

```qml
// Colors (Theme)
Theme.surface          // Primary background for tables, inputs
Theme.text              // Main text color
Theme.primary           // Primary action (buttons, links)
Theme.success/warning/error/info  // Semantic status colors

// Spacing (Metrics)
Metrics.spacing8   // 8px
Metrics.spacing16  // 16px
Metrics.spacing24  // 24px

// Typography
Typography.body           // 13px default text
Typography.heading        // 16px section heading
Typography.fontFamily     // Font family string

// Sizing (Metrics)
Metrics.controlHeight     // 36px, buttons & inputs
Metrics.tableRowHeight    // 28px

// Breakpoints (Metrics)
Metrics.breakpointCompact  // 1240px (switch to 1-column)
```

### Never Use Hardcoded Values

- ❌ `color: "#007096"` → ✅ `color: Theme.primary`
- ❌ `anchors.margins: 16` → ✅ `anchors.margins: Metrics.spacing16`
- ❌ `implicitHeight: 32` → ✅ `implicitHeight: Metrics.controlHeight`
- ❌ `font.pixelSize: 13` → ✅ `font.pixelSize: Typography.body`

---

## Questions & Support

For design system questions or to propose new tokens/components:

1. Check [design-tokens.json](./design-tokens.json) for current token definitions
2. Review existing component usage in [src/crane_statics/qml_app/qml/](../../src/crane_statics/qml_app/qml/)
3. Open an issue describing the missing token/component with use case
4. Follow the component creation steps in COMPONENT_USAGE.md

---

**Last Updated:** 2026-09-24
**Design System Version:** 2.0.0
**Platform:** Qt 6.x, PyQt6, QML
**Style:** Fusion, light-mode only (BF/NOV brand palette)
