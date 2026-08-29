# Theme Validation Checklist

Developer checklist for adding or modifying UI elements. Ensures consistency, accessibility, and proper theme support across light/dark modes.

## Before Committing Any UI Changes

Use this checklist to validate your work before opening a pull request.

### ✅ Token Compliance

- [ ] **No hardcoded colors** — All colors use `DesignTokens.colors.*` (not RGB hex values)
  - ❌ `Rectangle { color: "#0078d4" }`
  - ✅ `Rectangle { color: DesignTokens.colors.primary }`

- [ ] **No magic number spacing** — All spacing uses `DesignTokens.spacing.*`
  - ❌ `anchors.margins: 16`
  - ✅ `anchors.margins: DesignTokens.spacing.md`

- [ ] **No hardcoded font sizes** — All text sizes use `DesignTokens.typography.*`
  - ❌ `font.pixelSize: 14`
  - ✅ `font.pixelSize: DesignTokens.typography.body`

- [ ] **No hardcoded control heights** — All button/input heights use `DesignTokens.sizing.*`
  - ❌ `implicitHeight: 32`
  - ✅ `implicitHeight: DesignTokens.sizing.buttonHeight`

### 🎨 Light Mode Validation

1. **Start the app in light mode:**
   ```bash
   python -m crane_statics path/to/model.json
   ```
   (Windows automatically defaults to your Settings > Personalization > Colors preference)

2. **Check your modified UI:**
   - [ ] Text is readable against background (no low-contrast issues)
   - [ ] Form fields are clearly distinguishable from background
   - [ ] Borders and dividers are visible
   - [ ] Error/warning/success indicators are clear
   - [ ] Disabled controls look inactive
   - [ ] Hover states provide visual feedback

3. **Keyboard navigation:**
   - [ ] Tab through interactive elements
   - [ ] Focus ring is visible on all focusable controls
   - [ ] Focus ring color contrasts against background

### 🌙 Dark Mode Validation

1. **Switch to dark mode:**
   - Windows: Settings > Personalization > Colors > Dark
   - Or in-app: View > Appearance > Dark

2. **Relaunch the app** (Qt reloads theme on startup):
   ```bash
   python -m crane_statics path/to/model.json
   ```

3. **Check your modified UI:**
   - [ ] Text is readable against background
   - [ ] Form fields are clearly distinguishable from background
   - [ ] Borders and dividers are visible
   - [ ] Error/warning/success indicators are clear
   - [ ] Disabled controls look inactive
   - [ ] Hover states provide visual feedback
   - [ ] No "tofu boxes" (missing font rendering)

4. **Keyboard navigation:**
   - [ ] Tab through interactive elements
   - [ ] Focus ring is visible and contrasts against background

### 📋 Contrast Ratio Verification

Text must meet WCAG AA minimum:
- **Body text (13px):** 4.5:1 contrast ratio
- **Large text (18px+):** 3:1 contrast ratio
- **UI controls:** 3:1 contrast ratio

**For semantic status colors**, verify in both light and dark modes:
- [ ] Error red (#f44336) text is readable on light/dark background
- [ ] Success green (#4caf50) text is readable on light/dark background
- [ ] Warning orange (#ff9800) text is readable on light/dark background

**Quick verification (no tool required):**
1. Look at error text in light mode → readable?
2. Look at same error text in dark mode → readable?
3. Repeat for warning and success colors
4. If ANY are hard to read, use `DesignTokens.getStatusColor()` helper instead of hardcoding

### 🎯 Responsive Breakpoint Check

If your change affects layout:

- [ ] **Compact mode** (`width < 1240px`): Layout reflows to 1-column correctly
- [ ] **Wide mode** (`width ≥ 1240px`): Layout uses 2-column or intended layout
- [ ] **Ultra-wide mode** (`width ≥ 1800px`): Data-dense tables work (if applicable)

**Test:**
1. Resize window narrower/wider
2. Verify layout adapts smoothly
3. Check no text overflows or gets cut off

### 📊 Density Mode Check

If your change includes tables or spacing:

- [ ] **Relaxed density:** Spacing is comfortable, rows are readable
- [ ] **Normal density:** Spacing is balanced
- [ ] **Compact density:** Rows are still readable (not cramped)

**Test:**
1. Run the app
2. View > Appearance > Density Relaxed/Normal/Compact
3. Verify table rows and spacing respond correctly

### ♿ Accessibility Checks

- [ ] **Focus indicators:** All interactive controls have visible focus ring
- [ ] **Keyboard navigation:** Can tab through all interactive elements
- [ ] **No color dependency:** Information isn't conveyed by color alone
  - ❌ Red text to indicate error (colorblind users can't distinguish)
  - ✅ Red text + error icon + error message text
- [ ] **Disabled state clarity:** Disabled controls are clearly inactive
- [ ] **Error state clarity:** Error states are prominent and have error icon + message

### 🧪 Test Suite Pass

- [ ] Run `pytest tests/ -v` — **All tests pass**
- [ ] No new warnings or errors in test output
- [ ] If you added new QML, run QML linter: `qmllint path/to/your/file.qml`

### 📸 Visual Regression Spot-Check

For significant UI changes:

- [ ] Take screenshot in light mode
- [ ] Take screenshot in dark mode
- [ ] Take screenshot in compact density mode
- [ ] Compare with previous version (ask reviewer or keep a reference)
- [ ] Verify no unintended visual changes

### 📝 Documentation

- [ ] If creating a new component, add comments:
  ```qml
  /**
   * MyNewComponent
   *
   * Purpose: Brief description
   * 
   * Usage:
   *   MyNewComponent { ... }
   *
   * Design tokens used:
   * - colors.primary (for button state)
   * - spacing.md (for padding)
   * - typography.body (for text)
   */
  ```

- [ ] If adding new UI pattern, update COMPONENT_USAGE.md with example
- [ ] If adding new tokens (non-standard), update DESIGN_SYSTEM.md

---

## Scenario Checklist

### Adding a New Button

- [ ] Uses `DesignTokens.sizing.buttonHeight` for implicitHeight
- [ ] Uses `DesignTokens.colors.primary` for button background (or appropriate semantic color)
- [ ] Uses `DesignTokens.colors.textInverse` for button text
- [ ] Hover state uses `DesignTokens.colors.primaryHover`
- [ ] Pressed state uses `DesignTokens.colors.primaryPressed`
- [ ] Disabled state uses `DesignTokens.colors.primaryDisabled`
- [ ] Focus ring uses `DesignTokens.colors.focusRing`
- [ ] Works in light mode (readable text, clear states)
- [ ] Works in dark mode (readable text, clear states)

### Adding a New Text Input

- [ ] Uses `DesignTokens.sizing.inputHeight` for implicitHeight
- [ ] Uses `DesignTokens.colors.surface` for background
- [ ] Uses `DesignTokens.colors.textPrimary` for text
- [ ] Border uses `DesignTokens.colors.border`
- [ ] Error state uses `DesignTokens.colors.error` (red border + error message)
- [ ] Focus ring uses `DesignTokens.colors.focusRing`
- [ ] Disabled text uses `DesignTokens.colors.textDisabled`
- [ ] Works in light mode (field visible against background)
- [ ] Works in dark mode (field visible against background)

### Adding a New Dialog

- [ ] Title uses `DesignTokens.typography.heading` (16px)
- [ ] Body text uses `DesignTokens.typography.body` (13px)
- [ ] Padding uses `DesignTokens.spacing.dialogPadding` (16px)
- [ ] Buttons use `DesignTokens.sizing.buttonHeight`
- [ ] Dialog background uses `DesignTokens.colors.background`
- [ ] Header background uses `DesignTokens.colors.surfaceAlt`
- [ ] Dialog overlay is semi-transparent (DesignTokens.colors.overlay)
- [ ] Button colors use appropriate semantic colors (primary, error, etc.)
- [ ] Works in light mode (readable, clear button states)
- [ ] Works in dark mode (readable, clear button states)

### Adding a New Table/Data Grid

- [ ] Row height uses `DesignTokens.layout.tableRowHeight` (responds to density)
- [ ] Rows alternate: `DesignTokens.colors.surface` and `DesignTokens.colors.surfaceAlt`
- [ ] Header background uses `DesignTokens.colors.surfaceAlt`
- [ ] Header text uses `DesignTokens.colors.textPrimary` with medium weight
- [ ] Body text uses `DesignTokens.colors.textPrimary`
- [ ] Borders use `DesignTokens.colors.border`
- [ ] Hover state uses different background (slight contrast)
- [ ] Selection uses `DesignTokens.colors.primary` background
- [ ] Selection text uses `DesignTokens.colors.textInverse`
- [ ] Works in light mode (rows readable, alternating visible)
- [ ] Works in dark mode (rows readable, alternating visible)
- [ ] Works in compact density (rows still readable, not cramped)

### Adding a New Form/Panel

- [ ] Labels use `DesignTokens.typography.body` with medium weight
- [ ] Text inputs use `DesignTokens.sizing.inputHeight`
- [ ] Row gaps use `DesignTokens.spacing.rowGap` (8px)
- [ ] Section gaps use `DesignTokens.spacing.sectionGap` (16px)
- [ ] Panel background uses `DesignTokens.colors.surface` or `DesignTokens.colors.surfaceAlt`
- [ ] Panel padding uses `DesignTokens.spacing.panelPadding` (12px)
- [ ] Error messages use `DesignTokens.colors.error`
- [ ] Success messages use `DesignTokens.colors.success`
- [ ] Works in light mode (form fields clear, labels readable)
- [ ] Works in dark mode (form fields clear, labels readable)

---

## Red Flags 🚩

Stop and fix if you see:

- [ ] ❌ Hardcoded color: `color: "#0078d4"`
- [ ] ❌ Hardcoded spacing: `anchors.margins: 16` or `spacing: 8`
- [ ] ❌ Hardcoded font size: `font.pixelSize: 14`
- [ ] ❌ Hardcoded control height: `implicitHeight: 32`
- [ ] ❌ No focus ring on interactive controls
- [ ] ❌ Text unreadable in dark mode
- [ ] ❌ Text unreadable in light mode
- [ ] ❌ Form fields same color as background (can't see where to type)
- [ ] ❌ Error messages only shown in red (colorblind users won't notice)
- [ ] ❌ Hover/pressed states not visually distinct
- [ ] ❌ Component breaks in compact density mode
- [ ] ❌ Tests failing or new warnings in test output

---

## Rapid Verification Workflow

**Fast path for small changes:**

1. **Token check:** Grep for hardcoded colors/spacing/sizes → replace with tokens
2. **Light mode:** Load app in light mode, verify change looks good
3. **Dark mode:** Switch to dark mode, reload app, verify change looks good
4. **Tests:** Run `pytest tests/ -v` → all pass
5. **Done!** Ready to commit

**Typical time:** 5–10 minutes for small UI tweaks

---

## Slow Path for Large Changes

**For major layout/component additions:**

1. **Token review:** Audit all colors, spacing, fonts in your change
2. **Light mode:** Load app, check readability and state clarity
3. **Dark mode:** Switch modes, verify readability and state clarity
4. **Compact density:** Set to compact, verify spacing and row heights
5. **Responsive:** Resize window, verify layout reflows correctly
6. **Keyboard nav:** Tab through all interactive elements
7. **Tests:** Run full suite, verify no regressions
8. **Screenshots:** Take light/dark/compact mode screenshots for review
9. **Done!** Ready for PR review

**Typical time:** 20–30 minutes for significant changes

---

## Still Stuck?

1. **Colors:** Check [design-tokens.json](./design-tokens.json) for all available semantic colors
2. **Spacing:** Check [DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md#spacing-margins-padding-gaps) for spacing scale
3. **Typography:** Check [DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md#typography-scale--usage) for font sizes
4. **Components:** Check [COMPONENT_USAGE.md](./COMPONENT_USAGE.md) for code examples
5. **DesignTokens.qml:** Check [implementation](../../src/crane_statics/qml_app/design/DesignTokens.qml) for available properties

---

**Last Updated:** 2026-08-14  
**Design System Version:** 1.0.0
