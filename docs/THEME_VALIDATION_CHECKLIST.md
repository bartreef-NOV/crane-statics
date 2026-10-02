# Theme Validation Checklist

Developer checklist for adding or modifying UI elements. Ensures consistency and accessibility, and that every visual value comes from `Theme`/`Metrics`/`Typography`. The app is light-mode only — there is no dark mode or theme toggle to validate against.

## Before Committing Any UI Changes

Use this checklist to validate your work before opening a pull request.

### ✅ Token Compliance

- [ ] **No hardcoded colors** — All colors use `Theme.*` (not RGB hex values)
  - ❌ `Rectangle { color: "#007096" }`
  - ✅ `Rectangle { color: Theme.primary }`

- [ ] **No magic number spacing** — All spacing uses `Metrics.spacing*`
  - ❌ `anchors.margins: 16`
  - ✅ `anchors.margins: Metrics.spacing16`

- [ ] **No hardcoded font sizes** — All text sizes use `Typography.*`
  - ❌ `font.pixelSize: 14`
  - ✅ `font.pixelSize: Typography.body`

- [ ] **No hardcoded control heights** — All button/input heights use `Metrics.*`
  - ❌ `implicitHeight: 32`
  - ✅ `implicitHeight: Metrics.controlHeight`

### 🎨 Visual / Readability Validation

1. **Start the app:**
   ```bash
   python -m crane_statics path/to/model.json
   ```

2. **Check your modified UI:**
   - [ ] Text is readable against background (no low-contrast issues)
   - [ ] Form fields are clearly distinguishable from background
   - [ ] Borders and dividers are visible
   - [ ] Error/warning/success indicators are clear
   - [ ] Disabled controls look inactive
   - [ ] Hover states provide visual feedback
   - [ ] No "tofu boxes" (missing font rendering)

3. **Keyboard navigation:**
   - [ ] Tab through interactive elements
   - [ ] Focus ring is visible on all focusable controls
   - [ ] Focus ring color contrasts against background

### 📋 Contrast Ratio Verification

Text must meet WCAG AA minimum:
- **Body text (13px):** 4.5:1 contrast ratio
- **Large text (18px+):** 3:1 contrast ratio
- **UI controls:** 3:1 contrast ratio

**For semantic status colors**, verify readability against their typical background:
- [ ] Error red (`Theme.error`, `#DA291C`) text is readable
- [ ] Success green (`Theme.success`, `#A9C47F`) text is readable
- [ ] Warning orange (`Theme.warning`, `#DC9575`) text is readable

**Quick verification (no tool required):**
1. Look at error text → readable?
2. Repeat for warning and success colors
3. If placing text *on top of* a solid status fill (a badge/pill), use `Theme.getOnSemanticColor()`/`Theme.contrastText()` instead of a fixed inverse color — the nov palette's tones don't all clear WCAG AA against the same fixed text color

### 🎯 Responsive Breakpoint Check

If your change affects layout:

- [ ] **Compact mode** (`width < Metrics.breakpointCompact` / 1240px): Layout reflows to 1-column correctly
- [ ] **Wide mode** (`width ≥ 1240px`): Layout uses 2-column or intended layout
- [ ] **Ultra-wide mode** (`width ≥ Metrics.breakpointUltraWide` / 1800px): Data-dense tables work (if applicable)

**Test:**
1. Resize window narrower/wider
2. Verify layout adapts smoothly
3. Check no text overflows or gets cut off

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

- [ ] Take a screenshot of the change
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
   * - Theme.primary (for button state)
   * - Metrics.spacing16 (for padding)
   * - Typography.body (for text)
   */
  ```

- [ ] If adding new UI pattern, update COMPONENT_USAGE.md with example
- [ ] If adding new tokens (non-standard), update DESIGN_SYSTEM.md

---

## Scenario Checklist

### Adding a New Button

- [ ] Uses `Metrics.controlHeight` for implicitHeight
- [ ] Uses `Theme.primary` for button background (or appropriate semantic color)
- [ ] Uses `Theme.onPrimary` for button text
- [ ] Hover state uses `Theme.primaryHover`
- [ ] Pressed state uses `Theme.primaryPressed`
- [ ] Disabled state uses `Theme.primaryDisabled`
- [ ] Focus ring uses `Theme.focusRing`
- [ ] Text is readable and states are clear (or use `BfButton` directly, which already covers all of the above)

### Adding a New Text Input

- [ ] Uses `Metrics.controlHeight` for implicitHeight
- [ ] Uses `Theme.surface` for background
- [ ] Uses `Theme.text` for text
- [ ] Border uses `Theme.border`
- [ ] Error state uses `Theme.error` (red border + error message)
- [ ] Focus ring uses `Theme.focusRing`
- [ ] Disabled text uses `Theme.disabledText`
- [ ] Field is visible against background and states are clear (or use `BfTextField` directly)

### Adding a New Dialog

- [ ] Title uses `Typography.heading` (16px)
- [ ] Body text uses `Typography.body` (13px)
- [ ] Padding uses `Metrics.spacing16` (there's no dedicated `dialogPadding` token anymore — 16px is the equivalent value)
- [ ] Buttons use `Metrics.controlHeight`
- [ ] Dialog background uses `Theme.pageBackground`
- [ ] Header background uses `Theme.surfaceSubtle`
- [ ] Dialog overlay uses `Theme.overlay`
- [ ] Button colors use appropriate semantic colors (primary, error, etc.)
- [ ] Readable with clear button states

### Adding a New Table/Data Grid

- [ ] Row height uses `Metrics.tableRowHeight`
- [ ] Rows alternate: `Theme.surface` and `Theme.surfaceSubtle`
- [ ] Header background uses `Theme.surfaceSubtle`
- [ ] Header text uses `Theme.text` with medium weight (`Typography.weightMedium`)
- [ ] Body text uses `Theme.text`
- [ ] Borders use `Theme.border`
- [ ] Hover state uses different background (slight contrast)
- [ ] Selection uses `Theme.selection` background
  - Note: `Theme.selection` is a light tint (`novBlue50Tint`), not a solid fill, so selected text stays `Theme.selectionText` (which equals `Theme.text`, the normal dark text) rather than an inverse/white color — don't pair `Theme.selection` with `Theme.onPrimary`.
- [ ] Rows readable, alternating visible

### Adding a New Form/Panel

- [ ] Labels use `Typography.body` with medium weight
- [ ] Text inputs use `Metrics.controlHeight`
- [ ] Row gaps use `Metrics.spacing8` (there's no dedicated `rowGap` token anymore — 8px is the equivalent value)
- [ ] Section gaps use `Metrics.spacing16` (there's no dedicated `sectionGap` token anymore — 16px is the equivalent value)
- [ ] Panel background uses `Theme.surface` or `Theme.surfaceSubtle`
- [ ] Panel padding uses `Metrics.spacing12` (there's no dedicated `panelPadding` token anymore — 12px is the equivalent value)
- [ ] Error messages use `Theme.error`
- [ ] Success messages use `Theme.success`
- [ ] Form fields clear, labels readable

---

## Red Flags 🚩

Stop and fix if you see:

- [ ] ❌ Hardcoded color: `color: "#007096"`
- [ ] ❌ Hardcoded spacing: `anchors.margins: 16` or `spacing: 8`
- [ ] ❌ Hardcoded font size: `font.pixelSize: 14`
- [ ] ❌ Hardcoded control height: `implicitHeight: 32`
- [ ] ❌ No focus ring on interactive controls
- [ ] ❌ Text unreadable against its background
- [ ] ❌ Form fields same color as background (can't see where to type)
- [ ] ❌ Error messages only shown in red (colorblind users won't notice)
- [ ] ❌ Hover/pressed states not visually distinct
- [ ] ❌ Tests failing or new warnings in test output

---

## Rapid Verification Workflow

**Fast path for small changes:**

1. **Token check:** Grep for hardcoded colors/spacing/sizes → replace with tokens
2. **Visual check:** Load the app, verify the change looks good
3. **Tests:** Run `pytest tests/ -v` → all pass
4. **Done!** Ready to commit

**Typical time:** 5–10 minutes for small UI tweaks

---

## Slow Path for Large Changes

**For major layout/component additions:**

1. **Token review:** Audit all colors, spacing, fonts in your change
2. **Visual check:** Load the app, check readability and state clarity
3. **Responsive:** Resize window, verify layout reflows correctly
4. **Keyboard nav:** Tab through all interactive elements
5. **Tests:** Run full suite, verify no regressions
6. **Screenshots:** Take a screenshot for review
7. **Done!** Ready for PR review

**Typical time:** 20–30 minutes for significant changes

---

## Still Stuck?

1. **Colors:** Check [design-tokens.json](./design-tokens.json) for all available semantic colors
2. **Spacing:** Check [DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md#spacing-margins-padding-gaps) for spacing scale
3. **Typography:** Check [DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md#typography-scale--usage) for font sizes
4. **Components:** Check [COMPONENT_USAGE.md](./COMPONENT_USAGE.md) for code examples
5. **Implementation:** Check [Theme.qml](../../src/crane_statics/qml_app/design/BF/DesignSystem/Theme.qml), [Metrics.qml](../../src/crane_statics/qml_app/design/BF/DesignSystem/Metrics.qml), [Typography.qml](../../src/crane_statics/qml_app/design/BF/DesignSystem/Typography.qml) for available properties

---

**Last Updated:** 2026-09-24
**Design System Version:** 2.0.0
