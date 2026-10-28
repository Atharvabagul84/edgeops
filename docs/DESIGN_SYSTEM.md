# Design System

Recorded from `frontend/styles.css`, `cloud.css` and `responsive.css`. Follow these values; don't add new ones.

## 01 Brand Identity
Calm, operational, precise, light.

## 02 Colour Palette
| Name | Hex | Use for |
|---|---|---|
| Text | #172338 | Main text |
| Background | #f6f8fb | Page background |
| Surface | #ffffff | Panels, topbar |
| Navy (`--navy`) | #111d30 | Sidebar |
| Blue (`--blue`) | #3c70ed | Primary buttons, links |
| Blue hover | #295cd6 | Primary button hover |
| Focus | #477cf2 | Focus outline |
| Green (`--green`) | #159779 | Healthy / success |
| Danger | #d84444 | Destructive actions, incidents |
| Muted (`--muted`) | #7b8799 | Secondary text |
| Line (`--line`) | #e8edf3 | Borders, dividers |
| Info background | #edf3ff | Demo banner |

## 03 Typography
- **Font:** Inter, then system UI fonts; monospace `ui-monospace, SFMono-Regular, Consolas`
- **Base:** 14px
- **H1:** 28px, weight 650, letter-spacing −0.85px
- **Panel headings:** 12–13px, weight 520–620
- **UI text / buttons:** 11–12px, weight 510–550
- **Labels and eyebrows:** 8–10px, uppercase eyebrows with 1.65px letter-spacing

## 04 Spacing
- Common steps: 8, 13, 17, 20, 25, 33, 38px
- Main content max width 1580px; page padding 33px 38px (desktop)

## 05 Border Radius
- Buttons, inputs: 6px
- Nav items, banners: 7–9px
- Panels (`--radius`): 11px; auth panel 14px
- Status dots and avatars: 50%

## 06 Components
- **Primary button:** `--blue` background, white text, 6px radius, min-height 36px
- **Secondary button:** white background, 1px #dfe5ec border, hover #f2f5fa
- **Inputs:** 1px #d8e1ed border, 6px radius, #fbfcfe background
- **Focus:** 2px solid #477cf2 outline with offset on every interactive element
- **Motion:** respect `prefers-reduced-motion` (all animation disabled)

## 07 Icons
Inline SVG icons from `frontend/icons.js`, 17–19px, `currentColor`.

## 08 Breakpoints
- ≥1600px: wide desktop
- ≤1220px, ≤1010px: compact sidebar, then icon-only sidebar
- ≤800px: stacked layout
- ≤520px: phone, bottom navigation bar

## Rules
- Never use colours outside this palette
- Every view must work at 375px width
- Demo data is always labelled as synthetic
