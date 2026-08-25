---
name: Core Ledger
scope: Quintus Bookkeeping UI
version: 1.0
status: canonical

colors:
  navigation: '#041632'
  navigation-hover: '#102644'
  navigation-active: '#1b2b48'
  on-navigation: '#ffffff'
  on-navigation-muted: '#b7c7eb'

  primary: '#1b2b48'
  primary-hover: '#273a5d'
  primary-active: '#10213e'
  on-primary: '#ffffff'

  background: '#fbf8fb'
  surface: '#ffffff'
  surface-subtle: '#f5f3f6'
  surface-hover: '#efedf0'
  surface-selected: '#e5eaf3'

  text: '#1b1b1e'
  text-muted: '#545f72'
  text-subtle: '#75777e'
  text-inverse: '#ffffff'

  border: '#d5d4da'
  border-strong: '#b8bac2'
  focus: '#4f5e7e'

  success: '#2d6a4f'
  success-container: '#dcefe5'
  on-success-container: '#194c36'

  warning: '#8a5a00'
  warning-container: '#fff0cc'
  on-warning-container: '#684300'

  error: '#ba1a1a'
  error-container: '#ffdad6'
  on-error-container: '#93000a'

  info: '#315b8a'
  info-container: '#dce9f7'
  on-info-container: '#24496f'

typography:
  font-family: 'Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'

  display-lg:
    fontSize: 30px
    fontWeight: 700
    lineHeight: 38px
    letterSpacing: '-0.02em'

  headline-md:
    fontSize: 24px
    fontWeight: 600
    lineHeight: 32px
    letterSpacing: '-0.01em'

  title-sm:
    fontSize: 18px
    fontWeight: 600
    lineHeight: 24px

  body-md:
    fontSize: 14px
    fontWeight: 400
    lineHeight: 20px

  body-sm:
    fontSize: 13px
    fontWeight: 400
    lineHeight: 18px

  data-table:
    fontSize: 13px
    fontWeight: 400
    lineHeight: 16px

  form-label:
    fontSize: 13px
    fontWeight: 600
    lineHeight: 18px
    textTransform: none

  label-caps:
    fontSize: 11px
    fontWeight: 700
    lineHeight: 16px
    letterSpacing: '0.05em'
    textTransform: uppercase

rounded:
  sm: 2px
  default: 4px
  md: 6px
  lg: 8px
  xl: 12px
  full: 9999px

spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  gutter: 16px
  margin-mobile: 16px
  margin-tablet: 24px
  margin-desktop: 32px

layout:
  sidebar-width: 240px
  sidebar-rail-width: 64px
  content-max-width: none
  desktop-breakpoint: 1280px
  tablet-breakpoint: 768px
  mobile-breakpoint: 768px
---

# Core Ledger Design System

## 1. Purpose

Core Ledger is the canonical design system for the Quintus bookkeeping interface.

It is designed for frequent administrative work, financial review and data entry. It prioritizes clarity, consistency and efficient use of screen space over decorative presentation.

The interface should feel:

- professional;
- stable;
- precise;
- compact;
- predictable;
- calm during long work sessions.

This document is the visual and interaction source of truth. Individual pages must not introduce their own button styles, colors, spacing systems, status colors or modal patterns.

## 2. Design principles

### 2.1 Business first

Every visible element must support navigation, understanding, data entry or decision-making. Avoid decorative elements without a functional purpose.

### 2.2 Controlled density

The interface is compact but not cramped. Tables show useful amounts of information, while forms retain enough spacing to remain readable.

### 2.3 Predictability

Equivalent actions look and behave the same across all pages. Users should not need to relearn controls when moving between workflows.

### 2.4 Clear hierarchy

Each page has one clear title and normally no more than one visually primary action.

### 2.5 Progressive disclosure

Show the information required for the current task. Secondary information and uncommon actions may be placed in expandable areas, secondary actions or contextual menus.

### 2.6 Tonal depth

Hierarchy is communicated primarily through background tones, borders and spacing. Shadows are reserved for modals and temporary overlays.

## 3. Color system

### 3.1 Navigation

`navigation` is reserved for the global sidebar and other permanent navigation surfaces.

`primary` is used for:

- primary buttons;
- active controls;
- selected navigation details;
- focus indicators;
- important links.

Do not use `navigation` as a general button color.

### 3.2 Neutral surfaces

- `background` is the application background.
- `surface` is the active workspace, table or modal surface.
- `surface-subtle` separates secondary sections.
- `surface-hover` indicates hover without introducing shadows.
- `surface-selected` indicates a selected row or item.

### 3.3 Semantic colors

Semantic colors communicate meaning only:

- green for success or completed states;
- amber for warnings or attention;
- red for errors, destructive actions or failed states;
- blue for neutral information.

Semantic colors must not be used as decoration or to distinguish unrelated navigation sections.

Status labels and colors are mapped centrally from the existing Django status values. Templates must not select status colors individually.

### 3.4 Contrast

Text and interactive controls must meet WCAG AA contrast requirements.

Muted text must remain readable. Do not place muted navigation text on backgrounds where it fails contrast requirements.

## 4. Typography

Inter is the preferred application font. A system sans-serif stack is used as fallback.

### 4.1 Page headings

- Use `display-lg` only for exceptional dashboard-level headings.
- Use `headline-md` for normal page titles.
- Use `title-sm` for sections, modal titles and card headings.

### 4.2 Body text

- Use `body-md` for standard interface text.
- Use `body-sm` for secondary descriptions, metadata and helper text.
- Use `data-table` for table content.

### 4.3 Labels

Normal form labels use `form-label` in sentence case.

`label-caps` is reserved for:

- table headings;
- compact metadata captions;
- short grouping labels.

Do not render all form labels in uppercase.

### 4.4 Numeric data

Amounts use tabular numerals where supported:

```css
font-variant-numeric: tabular-nums;
```

Amounts are right-aligned in tables. Currency symbols and decimal separators must align consistently.

## 5. Layout

### 5.1 Desktop

At widths of 1280px and above:

- use the full sidebar at 240px;
- use up to 32px outer content margins;
- allow tables to use the available content width;
- use a 12-column fluid grid where a grid is helpful.

Do not artificially constrain data-heavy pages to a narrow marketing-style content column.

### 5.2 Tablet

Between 768px and 1279px:

- the sidebar may collapse to a 64px icon rail;
- use 24px content margins;
- reduce multi-column forms where necessary;
- preserve primary workflow actions.

### 5.3 Mobile

Below 768px:

- use 16px content margins;
- replace the sidebar with an appropriate compact navigation pattern;
- stack form columns;
- allow tables to scroll horizontally when meaningful column reduction is impossible;
- keep touch targets at least 44px high.

The application is desktop-first, but important workflows must remain usable on smaller screens.

## 6. Spacing

All spacing is based on a 4px unit.

Preferred values are:

- 4px for tightly related inline elements;
- 8px for control internals and compact groups;
- 16px for normal component separation;
- 24px for section separation;
- 32px for major page separation.

Do not introduce arbitrary spacing values unless required for precise alignment.

## 7. Shape and elevation

### 7.1 Border radius

- buttons and inputs: 4px;
- compact containers: 4px or 6px;
- cards and modals: 8px;
- status badges: 6px or 12px;
- circular icon controls: full radius.

Status badges must not automatically use a full pill shape.

### 7.2 Shadows

Normal cards, tables and panels do not use prominent shadows.

Use borders and tonal surfaces for separation.

Only modals, popovers and temporary overlays use a soft neutral shadow.

## 8. Component rules

### 8.1 Page header

Every standard page uses the shared page-header pattern.

A page header may contain:

- breadcrumbs;
- page title;
- short description;
- one primary action;
- one or more visually secondary actions.

Rules:

- there is normally only one primary action;
- primary actions appear consistently on the right;
- page descriptions remain short;
- do not place unrelated status cards inside the page header;
- do not create page-specific header layouts.

### 8.2 Buttons

#### Primary button

Use for the main action that advances or completes the current task.

Examples:

- Save;
- Upload;
- Create rule;
- Complete booking.

A page or modal normally contains only one primary button.

#### Secondary button

Use for valid alternatives that do not represent the principal next step.

Examples:

- Preview;
- Reapply rule;
- Add line;
- Open document.

#### Quiet action

Use for low-priority actions, navigation and contextual commands.

Quiet actions must remain discoverable without competing with the primary action.

#### Destructive button

Use only for destructive or difficult-to-reverse operations.

Rules:

- destructive actions use the error color;
- destructive actions are never the normal page-level primary action;
- destructive actions require confirmation when data could be lost;
- do not use red for ordinary cancellation.

#### Icon-only buttons

Icon-only buttons require:

- an accessible name;
- a tooltip where the meaning is not obvious;
- a consistent icon size;
- a sufficiently large clickable area.

Icons must not be the only indication of an unfamiliar action.

#### Button states

All buttons support:

- default;
- hover;
- active;
- keyboard focus;
- disabled;
- loading.

Loading buttons retain their width where possible and prevent duplicate submission.

### 8.3 Data tables

Tables are a core application pattern.

Standard table styling:

- 13px data text;
- 32px minimum desktop row height;
- 8px vertical cell padding;
- 12px horizontal cell padding;
- subtle header background;
- one clear bottom border between rows;
- no full cell grid;
- subtle hover background;
- actions in the final column.

Rules:

- text columns align left;
- numeric and monetary columns align right;
- dates use a consistent format and do not wrap unnecessarily;
- row actions remain visually secondary;
- row selection must not rely on color alone;
- long content truncates only when the complete value remains accessible;
- sortable headings clearly indicate their state;
- empty tables use the shared empty-state component;
- avoid placing every row inside a separate card.

Tables share CSS classes and markup conventions. Do not create an over-generalized table template that hides page-specific columns or logic.

### 8.4 Forms

Standard form fields use:

- labels above controls;
- sentence-case labels;
- 1px neutral border;
- 4px radius;
- visible keyboard focus;
- helper text below the field;
- validation errors next to the affected field.

Focus uses the `focus` or `primary` color without a decorative glow.

Rules:

- required fields are indicated consistently;
- placeholders do not replace labels;
- read-only values should appear as values, not disabled form controls;
- related fields are grouped visually;
- forms should avoid unnecessary cards and nested containers;
- validation messages explain how to correct the problem.

### 8.5 Form modal

Create and edit operations may use the shared form-modal shell when the task is short and does not require a full workspace.

The shared modal contains:

1. title;
2. optional description;
3. page-specific form content;
4. validation summary when required;
5. footer actions.

Rules:

- modals are centered with a dark translucent overlay;
- modal radius is 8px;
- the footer is right-aligned;
- Cancel appears before the primary action;
- the primary action appears at the far right;
- submitting shows a loading state and prevents duplicate submission;
- focus moves into the modal when it opens;
- focus returns to the triggering control when it closes;
- Escape closes the modal unless an irreversible operation is in progress;
- validation errors do not close the modal.

Use a full page instead of a modal when:

- the form is long;
- the task contains multiple sections;
- the task requires document comparison;
- the user must retain substantial surrounding context;
- the workflow has several dependent steps.

### 8.6 Status badge

Status badges display state. They are not buttons unless they explicitly perform an action.

Rules:

- non-interactive badges have no pointer cursor;
- non-interactive badges have no hover state;
- status meaning is communicated through text as well as color;
- status labels come from a central mapping;
- unknown statuses use a neutral fallback;
- templates do not assign their own badge colors;
- badges remain compact and do not dominate table rows.

Suggested semantic mapping:

- completed, booked, exported: success;
- pending, imported, open: neutral or information;
- attention, incomplete, missing document: warning;
- failed, invalid, rejected: error;
- inactive, archived: neutral.

The actual mapping must use the status choices defined by the Django models.

### 8.7 Action bar

Edit and workflow pages use the shared action-bar pattern.

An action bar may contain:

- Back or Cancel;
- validation or workflow feedback;
- secondary actions;
- one primary action.

Rules:

- the primary action appears at the far right;
- the action order remains consistent;
- the action bar does not duplicate the full page header;
- errors remain visible near the actions they block;
- sticky positioning may be used on long forms when it does not obscure content.

### 8.8 Alerts

Supported alert types are:

- information;
- success;
- warning;
- error.

Alerts use a semantic container color, readable text and an icon where useful.

Rules:

- alerts communicate actionable information;
- success messages should be concise;
- errors explain what failed and what the user can do;
- alerts must not be used as decorative banners.

### 8.9 Empty states

Empty states explain:

- what is missing;
- whether this is expected;
- what the user can do next.

Empty states remain compact and professional. Do not use oversized illustrations, marketing text or excessive whitespace.

### 8.10 Navigation

The desktop interface uses a 240px vertical sidebar.

Navigation contains:

- icon;
- visible text label;
- clear active state;
- logical grouping where required.

The active state uses:

- a 4px primary-colored left indicator;
- a subtle background change;
- high-contrast text.

Rules:

- navigation remains stable between bookkeeping pages;
- do not move ordinary page actions into global navigation;
- icons use one consistent visual family;
- collapsed navigation retains accessible names and tooltips;
- navigation labels remain concise.

### 8.11 Cards and panels

Cards are used only when content forms a meaningful independent group.

Rules:

- do not wrap every page section in a card;
- use white surfaces, subtle borders and 8px radius;
- avoid decorative shadows;
- card headings use `title-sm`;
- nested cards should be avoided.

## 9. Interaction feedback

Every user action must provide an appropriate response:

- hover for pointer interaction;
- visible focus for keyboard interaction;
- loading feedback for asynchronous or longer operations;
- confirmation after successful changes;
- clear validation feedback after failure;
- disabled states only when the reason is apparent.

Do not use animation as decoration. Short transitions may clarify hover, modal and state changes.

## 10. Content and language

The application uses concise, task-oriented German interface text.

Button labels use actions such as:

- Speichern;
- Hochladen;
- Regel erstellen;
- Erneut anwenden;
- Buchung abschließen.

Avoid vague labels such as:

- OK;
- Weiter, when the destination is unclear;
- Absenden, when a more specific action exists.

Status labels use clear nouns or completed-state descriptions and remain consistent throughout the application.

## 11. Accessibility

All components must support:

- keyboard navigation;
- visible focus states;
- semantic HTML;
- accessible labels;
- appropriate ARIA attributes where native HTML is insufficient;
- WCAG AA color contrast;
- error messages associated with their fields;
- non-color indicators for status and validation.

Interactive controls must not be implemented using non-interactive elements solely for styling.

## 12. Implementation rules

The interface uses:

- Django templates;
- the existing Bootstrap installation for grid, layout and supported behavior;
- project-owned CSS for the Core Ledger visual design;
- the existing JavaScript approach.

Do not introduce React, Tailwind or another frontend framework for this design system.

Bootstrap defaults are not the visual source of truth. Project CSS maps Bootstrap-compatible components to the tokens defined in this document.

### Required architecture

Reusable templates belong in a shared component directory:

```text
bookkeeping/templates/bookkeeping/new_ui/components/
```

Expected shared components include:

```text
_page_header.html
_status_badge.html
_form_modal.html
_action_bar.html
_empty_state.html
_alert.html
```

Shared design CSS should be separated into:

```text
bookkeeping/static/bookkeeping/css/new_ui/tokens.css
bookkeeping/static/bookkeeping/css/new_ui/components.css
```

Adapt paths to the actual repository structure where necessary.

### Prohibited patterns

Individual pages must not introduce:

- arbitrary colors;
- page-specific button variants;
- page-specific modal shells;
- duplicated status mappings;
- inconsistent action ordering;
- decorative shadows;
- highly rounded SaaS-style cards;
- oversized dashboard typography;
- new spacing values without justification;
- inline styles for reusable visual rules.

## 13. Component showcase

A component showcase page must display:

- all button variants and states;
- page headers;
- table states;
- form fields and validation;
- modal examples;
- status badges;
- action bars;
- alerts;
- empty states;
- long-text behavior;
- disabled and loading states.

The showcase is the visual reference for implementation.

A component must be corrected in the shared system instead of patched separately on an individual business page.

## 14. Change control

This document and the component showcase are the design source of truth.

New visual patterns require an explicit design-system decision.

When an existing component does not support a legitimate requirement:

1. identify the missing state;
2. determine whether it is reusable;
3. extend the shared component;
4. update the showcase;
5. update this document or `docs/UI_COMPONENTS.md`;
6. only then use it on a business page.

Do not silently create a new pattern while implementing an individual page.
