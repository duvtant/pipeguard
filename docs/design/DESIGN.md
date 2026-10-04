# PipeGuard Design System

**The single source of truth for how PipeGuard looks, feels and moves.** It replaces the earlier `DESIGN_DIRECTION.md`.

| | |
|---|---|
| **Status** | **Approved by David as the spec (Gate 1 passed, Sat Oct 3).** Nothing is implemented in code yet. |
| **Reference** | **Mercury** (the banking dashboard). Your picks: [Mercury home](https://mobbin.com/screens/d8564614-5b4c-4cdc-8088-0891fc9260df), [Mercury transactions with chart and tooltip](https://mobbin.com/screens/38664478-d88e-4575-a0b0-78ec6c218ce9) |
| **Font** | **Figtree** (your choice) |
| **Gradients** | Three, each with one job (Insight, Calm, Attention) |
| **Mode** | **Light only.** Engineers and field crews, a projector, daylight on a phone |
| **Live mockup** | `docs/design/preview/mercury-explorer.html` (keys 1 to 5, `P` for projector mode). **When this document and the mockup disagree, the mockup shows the intent and this document gets fixed.** |

---

## 1. What "taste" means here
The first round of options felt generic because they had none of the three things that make a product feel considered. This system is built on them:

1. **Typographic craft.** A light, refined weight (not the default 400 and 700), tabular numerals, and small raised units next to big numbers (`3ᵘⁿⁱᵗˢ`, `$3.38ᴹ`), the same detail Mercury uses for raised cents.
2. **Considered colour.** Cool near-whites, one periwinkle accent, a raspberry (not harsh red) for risk, and soft gradients that each have a job. Colour is quiet, so status stands out.
3. **Finish.** Lavender-glow card edges instead of grey borders, gradient insight strips inside cards, circular icon buttons, soft tinted tiles, a dark tooltip with colour keys, and motion that is fast, small and purposeful.

## 2. The reference, and what we do and do not copy
We adopt Mercury's **visual language**: the structure, the soft depth, the gradient strips, the raised numerals, the pill actions and the restrained palette. We do **not** copy its logo, name, copy or imagery, and its custom typeface is not available to us. Mobbin screenshots are research only and are never shipped in the product, README or deck.

**Corrected record on fonts.** Mobbin does not expose typography; I originally stated Mercury's font from memory. It is now checked against third-party design-system breakdowns ([shadcn.io](https://www.shadcn.io/design/mercury), [Fonts In Use](https://fontsinuse.com/typefaces/3748/arcadia), [Refero](https://styles.refero.design/style/3172cd4d-118a-4a16-a259-6b634d32322e)): Mercury uses **Arcadia** and **Arcadia Display**, with custom weights **360, 400, 420 and 480** and body text at **420**. These sources are third party, not Mercury. They also list Mercury's indigo as `#5266eb`, which matches the `#5367EB` we measured from the screenshot independently.

**What we take from that:** the quiet quality of Mercury's type comes largely from its **in-between weights (420 body, 480 emphasis)**. Figtree is a variable font, so we use exactly those weights.

## 3. Foundations

### 3.1 Colour
All values were measured from Mercury screenshots, then adapted. Every text pair below was checked against WCAG.

**Neutrals**
| Token | Hex | Use |
|---|---|---|
| `--canvas` | `#FFFFFF` | Page and card surface |
| `--shell` | `#FAFCFE` | Sidebar (a cool near-white, measured) |
| `--pill` | `#F1F3F4` | Quick-action chips, active nav, icon buttons (measured) |
| `--line` | `#E8E9F4` | The soft lavender edge of a card (measured) |
| `--ink` | `#080911` | Headings, key numbers (near-black with a blue undertone, measured) |
| `--text` | `#2A2C3B` | Body |
| `--muted` | `#5B5E70` | Secondary text, axis labels |
| `--subtle` | `#6A6D82` | Meta text (the lightest text allowed) |

**Accent: periwinkle (never a status colour)**
| Token | Hex | Use |
|---|---|---|
| `--accent` | `#5367EB` | Primary button, focus ring, selected icon, the PipeGuard series (measured) |
| `--accent-ink` | `#3F52D4` | Links and accent text (4.7:1 on white or better) |
| `--accent-soft` | `#EEF0FE` | Timeline dots, selected backgrounds |
| `--accent-line` | `#7C88E8` | Default chart line (3.2:1, passes graphic contrast) |
| `--accent-fill` | `#E5E9FC` | Top of the chart area gradient (measured) |

**Status.** Tuned to Mercury's warmth. Every status always has its own icon and label (section 4).
| Status | Text/icon | Tint (pill and tile background) | Icon fill |
|---|---|---|---|
| Healthy | `#0E7A55` | `#E6F5EF` | `#1FA37A` |
| Watch | `#8F5600` | `#FFF1D6` | `#C47A00` |
| At risk | `#B3204F` (raspberry) | `#FCE8EF` | `#D43471` |
| Sensor issue | `#555B70` | `#EDEFF5` | `#7A8197` |
| Failed | `#20232F` | `#E8E9EF` | `#20232F` |

**Avatar pastels** (station and person bubbles, measured and extended): `#CCE6F2` sky, `#E3DDF6` lilac, `#F6E0E6` blush, `#D8EFE3` mint, `#FBEBCB` sand, `#CEE9EB` teal.

### 3.2 The three gradients
Each has one job. **A gradient is never the only signal: every gradient strip also carries an icon and words.**

| Gradient | Stops | Job | Icon |
|---|---|---|---|
| **Insight** (measured from Mercury) | `#EFEEF1` → `#F0EFF4` (40%) → `#F0E7E8` (75%) → `#EFE0E5` | Neutral guidance and next steps: "2 crews on shift per station" | `info` |
| **Calm** (proposed) | `#E8F3F2` → `#E5EFF7` (40%) → `#E7E9FB` (75%) → `#EBE3F8` | Good news and confirmations: "Service booked for Fri Nov 6", "Self-tuned beats default by $720K", all-clear states | `check-circle-fill` in `--ok` |
| **Attention** (proposed) | `#FCEFE4` → `#FBE7E3` (45%) → `#F9DEE7` | A person is needed: "EDS-14 needs a manager decision", the incoming call | `warning-octagon-fill` in `--risk` |

All text on the gradients passes: ink on them is above 16:1, and `--muted` on them is **at least 5.0:1**.
**Richer versions** (soft mesh gradients in the same three palettes) are generated as WebP for the sign-in page, the deck cover and large empty states (section 8). Inside the app, use the CSS gradients only.

### 3.3 Typography: Figtree
Install `@fontsource-variable/figtree` (OFL, bundled with the app so nothing loads from a CDN). The font family name is `Figtree Variable`.

| Role | Size / line | Weight | Notes |
|---|---|---|---|
| Page title | 38 / 44 | **420** | `letter-spacing: -0.01em` |
| KPI number | 46 / 50 | **480** | `-0.02em`, tabular figures |
| KPI number, small | 30 / 34 | 480 | Used in comparison rows |
| Stat number | 26 / 32 | 480 | Tabular |
| Card title | 16 / 24 | **420** | A quiet title (Mercury's card titles are light, not bold) |
| Body | 15 / 22 | **420** | |
| Secondary | 14 / 20 | 420, `--muted` | |
| Meta and axis labels | 13 / 18 | 420, `--muted` | The smallest size anywhere the audience must read |
| Pills | 13 | 600 | Status pills only |
| Emphasis | same size | **480** | Row titles, selected nav, links |

**Weights, revised at Gate 2.** Measured against Mercury, our text read heavier and darker (more near-black pixels in the same words). Standard mode now uses **400 body and 460 emphasis** (`--w-body`, `--w-strong`); projector mode uses **440 and 500**. Nav labels use `--text` instead of `--ink`. Everything above that says 420 or 480 means these tokens.

**Rules:** sentence case everywhere. **Tabular numerals** (`font-variant-numeric: tabular-nums`) for every number so values don't jitter when they change. **Raised units:** a small unit sits at the top right of a big number (`font-size: 0.4em`, shifted down 0.55em, 4 px left margin, `--muted`). Never go below weight 420 for text on a projector.

### 3.4 Shape, depth, spacing
| Thing | Value |
|---|---|
| Card | white, **18 px radius**, no border; edge is `box-shadow: 0 0 0 1px var(--line), 0 8px 24px -12px rgba(83,103,235,0.22)` (a faint lavender glow) |
| Card padding | 26 px vertical, 28 px horizontal |
| Gap between cards | see 3.5 (revised at Gate 2) |
| Tiles | 12 px radius |
| Chips, buttons | fully round (999 px) |
| Inputs, search | 12 px radius, 1 px `--line` |
| Icon buttons, avatars | circle (40 px, 36 px for list avatars) |
| Strip (card footer) | full card width, 16 px × 28 px padding, no radius of its own (the card clips it) |
| Floating layers | slide-over: `-20px 0 50px -20px rgba(8,9,17,0.3)`; tooltip: `0 10px 24px -8px rgba(0,0,0,0.4)` |
| Spacing scale | 4, 8, 12, 16, 20, 24, 28, 40 |
| Page width | sidebar flush left at full height; content centred in the remaining space (width in 3.5, revised at Gate 2) |

**Projector mode** (a real, shippable setting, press `P` in the mockup): card edge becomes `1.5px --line` where `--line` is `#C6C9E2`, secondary text darkens (`--muted #444859`, `--subtle #525669`), the chart line uses full `--accent` at 3.5 px. Use it in the judging room. The pale originals wash out on a projector.

### 3.5 Compact scale and shell layout (revised at Gate 2; supersedes any larger size elsewhere in this document)
**Method.** Mobbin's web captures are 1440 x 900 windows (this one is 2000 px wide, so 1 CSS px = 1.389 image px). Every number below was measured from Mercury's own screens at that size, then compared with our build's real layout (`getBoundingClientRect`), not by eye.

**Shell, Mercury at 1440 px vs ours**
| Thing | Mercury | Ours before | Ours now |
|---|---|---|---|
| Header band | 60 px + 1 px hairline, shared by sidebar and content | none | **73 px (72 + hairline)**, sticky. Deliberately taller than Mercury (David's call at the Gate 2 review) |
| Search box | 616 x 36, 12 px from the band top, left edge on the content edge | full width | **616 x 36**, centred in the band (18 px above and below) |
| Sidebar width | 205 | 216 | **205** |
| First nav item top | 84 | 102 | **111**: the first nav item is on the same line as the page title (their text centres match to the pixel, as in Mercury where "Home" and the title share a row) |
| Nav item | 34 tall, 11.5 left and 15 right inset, 38 pitch | 36, 14, 40 | **34, 11, 38** (icon 16 at 24 px, text at 53 px) |
| Content gap from sidebar | 24 | 104 | **24** |
| Content right margin | 37 | 104 | **36** |
| Title ink top | 94 (33 below the header line) | 77 | **117** (44 px under the header line; deliberately lower than Mercury's 33, David's call at the Gate 2 review) |
| Content width | fluid on tables, capped on Home | capped at 1080 | **fluid, capped at 1760** so it fills a 1920 screen |

Our nav items were never smaller than Mercury's (ours 36 tall, theirs 34). What read as "tight and floating" was the missing header band and 80 px of dead margin on each side.

**Type and component sizes**
| Thing | Was | Now |
|---|---|---|
| Page title | 38 / 44 | **28 / 36** |
| KPI number | 46 / 50 | **32 / 36** (medium 24, stat 22) |
| Card title | 16 | **15** |
| Body | 15 / 22 | **14 / 20** |
| Secondary and meta | 14 and 13 | **13** (the floor; never smaller) |
| Card padding | 26 / 28 | **20 / 24** |
| Card radius, tile radius | 18, 12 | **16, 10** |
| Card gaps | 28 / 44 | **24 across, 32 between rows** |
| Chips | 40 tall, 15 px text | **32 tall, 14 px text** |
| Search, date pill, icon buttons | 40 to 44 | **36** |
| Unit tile | 62 tall | **54 tall** |

**Projector mode multiplies the whole manager UI by 1.2** (`--zoom`), so the compact size is for a laptop and the large size is for the judging room.
**Target sizes.** Desktop controls are 32 to 36 px (WCAG 2.2 AA requires 24 px; the old 40 px rule was ours). The phone page keeps 44 px or more. Text never goes below 13 px.

## 4. The status system
Five statuses. **Each has its own colour, icon and label, so colour is never the only signal.** Healthy and watch have almost the same lightness (as do at-risk and sensor issue), so a colour-blind viewer cannot rely on colour alone.

| Status | Icon (Phosphor Fill) | Pill text | Tile treatment |
|---|---|---|---|
| Healthy | `check-circle-fill` | "Healthy" | White tile, lavender-glow ring, green check |
| Watch | `warning-fill` | "Watch" | `--warn-tint` background, no ring |
| At risk | `warning-octagon-fill` | "At risk" | `--risk-tint` background |
| Sensor issue | `wrench-fill` | "Sensor issue" | `--sens-tint` background |
| Failed | `x-circle-fill` | "Failed" | `--fail-tint` background, text reads "Failed" |

**At risk and a sensor issue together:** the tile stays at-risk red and gets a small **white circular wrench badge** (18 px, top right). A real risk is never hidden behind a sensor fault.

**Pill:** `13 px / 600`, padding `3px 10px 3px 8px`, a 15 px icon, tinted background, status-coloured text. It is the same component in tables, tiles, the legend and the panel header.

## 5. Components
All dimensions come from the approved mockup.

### 5.1 Shell
- **Layout:** a 250 px sidebar and the content area. Sidebar is `--shell` with a right 1 px `--line`.
- **Org switcher** (top of sidebar): a 34 px rounded-square avatar ("P"), the name "Prairie Gas" in weight 480, a chevron.
- **Nav item:** 9 × 12 px padding, 12 px radius, a **Phosphor Regular** icon (16 px) in `--muted`, label in `--ink`. **Active:** `--pill` background, weight 480, icon turns `--accent`. Group label ("Workflows") is 14 px `--subtle`, no uppercase.
- **Top bar:** a flexible search field (12 px radius, 1 px line, a `⌘ K` hint) that jumps to a unit by ID; a pill button with the simulated date ("Tue, Nov 3 · Day 29 ▾") in `--accent-ink`; a bell circle with a raspberry dot; an avatar circle.

### 5.2 Page header and quick actions
A 38 px page title, then a row of **chips** (pill-shaped, `--pill` background, 9 × 16 px padding, a 16 px icon). The first is **primary** (solid `--accent`, white text, weight 480): "Play replay". Others: "Simulate call", "Open weekly plan", "Work orders". A plain "Customize" sits at the far right.

### 5.3 Cards
- **Standard card:** title row (16 px, quiet), optional icon buttons on the right, content.
- **KPI chart card** (the signature one): title with a small verified badge, a **KPI number with raised unit**, a period selector row ("Last 30 days ▾") with a delta on the right ("↗ +1 this week" in `--risk`), a **gradient area chart** that bleeds to both card edges, and x-axis labels. The chart fills the card's remaining height.
- **List card:** a title row, rows with a 36 px avatar, a two-line label (name, then muted detail), and a right-aligned value or pill. Ends with an **insight strip**.
- **Stat card:** three or two columns, each a 14 px muted label above a 26 px number. May end with a strip.

### 5.4 Insight strips
The gradient footer inside a card: a 36 px white-translucent circle with an icon, a title (480) and a muted one-line subtitle, and on the right either a 36 px circular arrow button or a pill button ("Review"). Variants: Insight, Calm, Attention (section 3.2). The strip is where the product tells the user what to do next.

### 5.5 Unit tiles (the Fleet grid)
10 columns, 8 px gap, 12 px radius, `min-height: 62`. Anatomy: unit ID top left (13 px, 480, tabular, e.g. `EDS-07`), days remaining bottom left (`22 d`, 13 px muted), the status icon bottom right (16 px). A failed unit reads "Failed" instead of days. The wrench badge sits top right. Labels are deliberately short so nothing wraps (this fixed a real layout problem in the first explorer).

### 5.6 Tabs and toggles
- **Segmented icon toggle** (chart or table view): a 1 px `--line` outline, 10 px radius; the selected segment is white with an inset 1 px accent ring.
- **Text tabs:** the active tab has a 2 px `--accent` underline that slides between tabs (section 9).

### 5.7 Buttons and sliders
- **Primary:** solid `--accent`, white text, weight 480, pill. **Secondary:** `--pill` background, `--ink` text. Both have a 16 px leading icon.
- **Slider:** `--accent` track and thumb, a 6 px track, a large thumb, the live value to the right of the label (weight 480).

### 5.8 Tooltip
Dark `#1B1D2A`, 10 px radius, white text, a muted date line, then rows with a 3 × 12 px **colour key bar**, a label and a right-aligned bold value. A white marker with an accent ring sits on the chart point it describes.

### 5.9 Slide-over (unit detail)
A 430 px right panel over a washed scrim (`rgba(250,252,254,0.7)`, **no blur**). Header: unit ID (22 px), status pill, close icon; muted subtitle. Body: "Why it was flagged" (plain words), **three fact tiles** (Remaining life `22ᵈᵃʸˢ`, Range `14 to 35`, Confidence), a small gradient chart ("Failure probability, last 30 days"), then a **timeline** ("What happened": flagged, technician called, plan changed) with 24 px `--accent-soft` dots joined by a 1 px line. Footer: a **Calm insight strip** ("Service booked for Fri Nov 6") with a "View plan" pill.

### 5.10 Notices
- **Banner** (system notice such as "reconnecting" or "demo mode"): a full-width strip across the top of the content, in the Insight gradient or the Attention gradient for problems.
- **Toast:** small card, bottom right, an icon and one line ("Plan changed: EDS-07 moved to Fri Nov 6").
- **Dialog:** plain-language title and consequence, a primary action and a cancel. Never a browser `confirm()`.

### 5.11 Empty and loading states
- **All clear:** one warm line plus a small illustration on the Calm gradient.
- **Loading:** skeletons shaped like the final content, in `--pill`. Never a spinner over a blank page.
- **Reconnecting:** keep the last known data visible and show the banner.

## 6. Charts
Recharts, styled like Mercury: **no gridlines or axes lines**, only muted x-axis labels (13 px). The signature is a **gradient area**: a vertical gradient from `rgba(83,103,235,0.22)` to `0.02` under a `2.5 px` `--accent-line` line (`3.5 px` and full `--accent` in projector mode).
- **Comparison series** (Impact): Run until it breaks `#B8BCCB` dashed (6 6), Fixed schedule `#7A8197` solid, **PipeGuard `--accent` always strongest**, with the gradient only under PipeGuard.
- **Rule:** never separate series by colour alone. Add the dark tooltip with colour keys, and direct labels where space allows.
- **Live charts** do not animate their data (section 9); the initial draw and user-driven changes do.

## 7. Iconography
**Phosphor** via Iconify, **bundled at build time** with `unplugin-icons` + `@iconify-json/ph` (MIT, no attribution, no runtime fetch). All names below were checked against Iconify.

| Where | Weight | Icons |
|---|---|---|
| Navigation and actions | **Regular** (was Light; made bolder at the Gate 2 review) | `squares-four`, `calendar-check`, `chart-bar`, `list-checks`, `users`, `clipboard-text`, `gear`, `magnifying-glass`, `bell`, `clock`, `chart-line`, `table`, `sliders-horizontal`, `download-simple`, `arrows-clockwise`, `microphone`, `flask` |
| Status | **Fill** | `check-circle-fill`, `warning-fill`, `warning-octagon-fill`, `wrench-fill`, `x-circle-fill`, `seal-check-fill` |
| Small controls | Regular | `caret-down`, `caret-right`, `arrow-right`, `arrow-up-right`, `arrow-down-right`, `plus`, `dots-three-vertical`, `play-fill`, `x` |
| Voice | Regular | `phone-call`, `phone-x` |

Use **one** icon set for the UI. Status icons differ by shape. **Never use generated raster images for UI icons.**

## 8. Imagery (your image generator, exported as WebP)
Used sparingly. The UI carries the screen.

| Asset | Where | Size |
|---|---|---|
| Logo mark | Header, favicon, deck | SVG (vectorise the chosen raster), WebP fallback |
| Phone home-screen icon | Apple touch icon | 180 × 180 PNG, opaque white background |
| Manifest icons | Installed web app | 192 × 192 and 512 × 512 PNG, opaque white backgrounds |
| Social / preview image | GitHub issue, sharing, deck | 1200 × 630, PNG and WebP; compose the Insight mesh with the approved logo |
| Mesh gradient: Insight | Deck cover, sign-in background | 1920 × 1080 |
| Mesh gradient: Calm | "All clear" large empty state | 1200 × 800 |
| Mesh gradient: Attention | Rare: incident cover slide | 1200 × 800 |
| Empty-state illustrations (2) | "All clear", "waiting for a call" | 480 × 360 |
| Sign-in image | One-click sign-in | 1600 × 1000 |

**Export:** WebP quality about 80, under 120 KB for large images and under 40 KB for small ones, with `width` and `height` set. Check each on a washed-out screen before keeping it.

**Prompts** (swap the hex values if the palette changes):
- **Logo mark — selected by David:**
  > Use `docs/assets/proposedlogo.png` as the source of truth: a shield formed from rounded pipe segments with four coupling blocks and an open centre. It replaces the earlier generated shield/check candidates. Preserve this geometry; do not generate a replacement. Deliverables: `logo-mark.svg` (true vector paths), `logo-mark.webp`, and `logo-mark.png`, with transparent backgrounds. Favicon derivatives use the same mark with tighter framing. The SVG's flat blue is `#455FF0`, sampled from the supplied logo; PNG/WebP retain the original blue variation. This source-specific logo colour does not change the app's `#5367EB` accent token.
- **Mesh gradients** (one per palette): 
  > A soft abstract mesh gradient background, smooth blurred colour fields, no shapes, no text, no noise, no hard edges. Colours: lavender-grey #EFEEF1, soft blush #EFE0E5 and a hint of periwinkle #E5E9FC. 1920 by 1080. *(Calm: mint #E8F3F2, sky #E5EFF7, lilac #EBE3F8. Attention: peach #FCEFE4, soft coral #FBE7E3, rose #F9DEE7.)*
- **Empty state, all clear:**
  > A calm flat spot illustration of a small gas compressor station with a pipeline and one check-mark badge, 2 pixel line work in #5367EB with soft fills in #EEF0FE, white background, lots of empty space. No people, no text, no gradients, no shadows. 480 by 360.
- **Empty state, waiting for a call:**
  > A flat spot illustration of a simple mobile phone with a small bell, 2 pixel line work in #5367EB, very light #EEF0FE fills, white background, no people, no text, no gradients. 480 by 360.
- **Sign-in image:**
  > A wide, calm line-art illustration of a gas pipeline across rolling hills with two small compressor stations, 2 pixel line work in #5367EB, soft #EEF0FE and light-grey fills, white background, minimal detail, no people, no text, no gradients. 1600 by 1000.

A raster logo must be **vectorised** (Illustrator Image Trace, Inkscape or an online vectoriser) so we have a crisp SVG.

## 9. Motion
Polish comes from motion that is **fast, small, physical and purposeful**. It confirms that something happened and where to look. It is never decoration.

**Where this comes from.** I loaded the `high-end-visual-design` skill and took only the principles that suit a live operations dashboard. **Adopted:** custom cubic-bezier curves (no `linear` or default `ease`), animating only `transform` and `opacity`, a physical press on buttons, a small kinetic nudge on trailing icons, short staggers, no scroll listeners, blur only on fixed overlays (and we use none), and disciplined z-index layers. **Deliberately not adopted** because they conflict with the approved direction or suit marketing pages: dark "Ethereal Glass" styling, double-bezel containers on every card, a floating nav island, `py-24` section spacing, blur-in scroll reveals and grain overlays.

### 9.1 Tokens
```css
:root {
  /* Easing: custom curves only */
  --ease-out:   cubic-bezier(0.22, 1, 0.36, 1);   /* most entrances, hovers */
  --ease-fluid: cubic-bezier(0.32, 0.72, 0, 1);   /* panels, sheets, layout moves */
  --ease-exit:  cubic-bezier(0.4, 0, 1, 1);       /* exits, faster */

  /* Durations */
  --dur-instant: 90ms;    /* press */
  --dur-fast:   150ms;    /* hover, tooltip, colour changes */
  --dur-base:   240ms;    /* most entrances, tabs, toggles */
  --dur-slow:   360ms;    /* slide-over, plan moves */
  --dur-chart:  800ms;    /* chart draw, first load only */
  --dur-flash: 1200ms;    /* the "this just changed" highlight */
}
```
**Springs** (for the `motion` library): panels `{ type: "spring", stiffness: 380, damping: 34 }`; small icon pop `{ type: "spring", stiffness: 600, damping: 22 }` (the only place a hint of overshoot is allowed).

### 9.2 Choreography
| Moment | Animation | Timing |
|---|---|---|
| **Page enter** | Cards fade up 8 px (`opacity 0→1`, `translateY 8→0`), staggered 40 ms, **at most 6 items**. No blur. Only on a route change, never on live updates | 240 ms `--ease-out` |
| **KPI numbers** | Count from the previous value to the new one (from 0 on first load). Tabular figures prevent jitter. **Not** on every live tick: at most once per 2 s, and only when the value changes | 500 ms `--ease-out` |
| **Chart, first draw** | The line draws in (`pathLength` 0→1), the gradient area fades in 200 ms later | 800 ms `--ease-out` |
| **Chart, live update** | The new point slides in, no redraw, no re-animation of old data | 300 ms `--ease-out` |
| **Chart, slider-driven** | Short path transition so the user sees cause and effect | 250 ms, cancel in-flight |
| **Unit tile changes status** | Background cross-fades; a 3 px accent ring pulse fades out; the icon pops (`scale 0.85→1`, icon spring). **Only the changed tile**, and **at most 6 highlights per tick** (the rest change instantly) | 240 ms + 1200 ms flash |
| **Hover** (clickable cards, tiles, chips) | Card edge deepens; a tile lifts 1 px; a chip's background shifts | 150 ms `--ease-out` |
| **Press** (chips, buttons) | `scale 0.98` | 90 ms |
| **Press** (Answer and Decline) | `scale 0.94` | 90 ms |
| **Trailing icons / strip arrow** | Nudge 3 px right (arrow) or diagonally up-right (↗) on hover | 180 ms `--ease-out` |
| **Nav active pill, tab underline** | Slides to the new item (shared layout, `transform` only) | 240 ms `--ease-fluid` |
| **Slide-over** | Enters from `translateX(24px)` with opacity 0→1; scrim fades in over 200 ms; inner blocks stagger 30 ms, max 4. Exit is faster. Focus is trapped and returned on close | 360 ms enter, 180 ms exit, `--ease-fluid` |
| **Toast** | Rises 12 px and fades in; auto-dismisses after 4 s (pauses on hover); exits down 8 px | 240 ms in, 160 ms out |
| **Dialog** | `scale 0.98→1` with opacity; scrim 160 ms | 180 ms `--ease-out` |
| **Banner** (reconnecting) | Slides down from the top edge; on recovery a Calm flash, then dismisses | 240 ms |
| **Insight strip content changes** | Cross-fade the text; the icon pops | 200 ms |
| **Decision log, new event** | Slides in from the top (`translateY -8→0`), others shift down by layout move, a 1200 ms highlight fades | 240 ms + 1200 ms |
| **Impact sliders** | Thumb scales 1.12 while pressed; values update instantly; result numbers tween | 120 ms thumb, 250 ms numbers |

### 9.3 The signature moment: "Plan changed"
This is the moment of the demo (the technician says "not before Friday"), so it gets the most polish and must read clearly across the room:
1. The plan block **moves from its old slot to the new one** with a layout animation (FLIP, `transform` only, 400 ms, `--ease-fluid`).
2. The moved block gets the **1200 ms highlight**.
3. The **Plan strip** cross-fades to its new text, with a Calm gradient and an icon pop.
4. A **toast** rises: "Plan changed: EDS-07 moved to Fri Nov 6".
5. The unit tile and the decision log update in the same beat.

### 9.4 The phone page
- **Incoming call:** the card rises from below with a spring (about 320 ms). Two **concentric rings** expand behind the Answer button (`scale 1→1.6`, `opacity 0.35→0`, 1.6 s, `--ease-out`, repeating). **This is the only decorative looping animation in the product** (the only other loop is the button spinner, section 9.5). It stops the moment the call is answered or the ring expires.
- **In call:** a calm speaking indicator (three small bars) that moves only while the agent is speaking.
- **After call:** the three verdict buttons appear with a 40 ms stagger; a tapped verdict draws a check mark in 300 ms.

### 9.5 Rules
- **Animate only `transform` and `opacity`** (plus colour and `box-shadow` on a handful of elements for highlights). Never `top`, `left`, `width`, `height`. Use `will-change` sparingly, only on things animating right now.
- **Performance budget:** the fleet has 100 tiles and can tick every 0.25 s. **Never animate on every tick.** Batch updates into one `requestAnimationFrame`, cap concurrent highlights at 6, and keep the per-frame cost of a fleet update under 2 ms in the browser profiler.
- **Reduced motion.** The app respects the operating-system setting (`<MotionConfig reducedMotion="user">` and a `prefers-reduced-motion` media query). With it on: no transforms, draws, count-ups or rings; fades of at most 120 ms only; the status highlight becomes an instant colour change that stays for a second; the ringing indicator becomes a static ring.
- **Maximum durations:** UI motion 360 ms, chart draw 800 ms, highlight 1200 ms.
- **No** bounce (except the icon pop), parallax, scroll-jacking or scroll-triggered effects. No `filter: blur` anywhere in content, and no `backdrop-filter` on scrolling content. No scroll listeners, **except** one passive listener on a list container for functional pin detection (the "new events" pill, `useNewItems`); never on `window`, never for animation.
- **Three narrow exceptions** that come with the interaction components (`COMPONENTS.md`): (1) a **spinner** may loop, but only while a request is pending (it is static under reduced motion); (2) **linear easing** is allowed only for the Hold to Confirm fill, because a progress sweep must track elapsed time; (3) the passive container scroll listener above. Everything else follows the rules in this section.
- **Z-index layers** (and only these): base 0, sticky bars 10, scrim 20, slide-over 30, toast 40, dialog 50, tooltip 60.
- **Keyboard and focus always work during motion.** Animations never delay input.

### 9.6 Implementation
- **CSS** (the tokens above) for hover, press, colour and highlight transitions.
- **`motion`** (`motion/react`, MIT, supports React 19) for presence (slide-over, toast, dialog), layout moves (nav pill, tab underline, the plan move) and springs. Wrap the app in `<MotionConfig reducedMotion="user">`.
- A small **`useCountUp`** hook (tween with cancellation) and a **`useReducedMotion`** check.
- **Eight interaction components** are adapted from interior.dev (MIT): Hold to Confirm, Slide-over, Value Flash, Action Button, Skeleton hook, New Events pill, Segmented control, Slider with detents. The full adaptation spec, build order and cut order are in **`COMPONENTS.md`**; reference sources are in `vendor/interior/`. They need no new dependency beyond `motion`.
- No other animation library.

## 10. Accessibility and projector checklist
**Verified:** 40 colour pairs checked, **0 failures**. The lowest text ratio is 4.66:1 and the lowest graphic ratio is 3.07:1. Two real failures were found and fixed during checking (the amber icon was 2.77:1 and the default chart line was 2.76:1; they are now `#C47A00` and `#7C88E8`).
- Text is at least 13 px, key numbers are 26 to 46 px, no weight below 420.
- Status is always icon plus label plus colour.
- Every interactive element has a visible focus ring (2 px `--accent`, 2 px offset) and a minimum 40 px target (44 px on the phone page).
- Test at 1280 × 720 and 1920 × 1080, in **projector mode**, and on the real phone in daylight.

## 11. Screens
**Designed and mocked (in `mercury-explorer.html`):**
- **Fleet:** page title and quick-action chips; the KPI chart card ("Units needing attention") beside the **Stations** list card (with an Insight strip); the **Edson unit grid** card with a status legend; **This week's plan** (stat columns plus an Attention strip) beside **Voice calls**.
- **Impact:** a KPI chart card with three comparison figures (Run until it breaks, Fixed schedule, **PipeGuard** largest) and the dark-tooltip comparison chart; a "What if?" card with three sliders and a Calm strip; two stat cards (failures caught early, prediction error).
- **Unit panel:** the slide-over (section 5.9).
- **Phone call:** the incoming-call screen with unit, status pill, reason, an Attention strip with the question, and large Decline and Answer buttons.
- **Gradients:** the three gradients and their jobs.

**Derived, not yet mocked (to review at Gate 2):**
- **Plan:** a team-by-day grid in this language (rounded tinted blocks, an "Open" row for units needing a decision), per `UX_FLOWS.md`.
- **Decision log:** a filterable feed with timeline dots and expandable chains.
- **Roster:** a list card like Stations.
- **Work orders:** a table like Mercury's transactions, with the dark tooltip.
- **Settings:** cards with sliders and toggles.
- **Test mode:** an admin-gated page of chips and dialogs.

## 12. Implementation plan (after Gate 1)
**Install:** `@fontsource-variable/figtree`, `unplugin-icons`, `@iconify-json/ph`, `motion`. (All checked on npm; React 19 supported.)

**Files:**
```
web/src/design/tokens.css        colours, gradients, type, radius, shadow, motion tokens (@theme in Tailwind v4)
web/src/design/motion.ts         easing, durations, springs, variants
web/src/components/ui/           Card, KpiCard, InsightStrip, StatusPill, UnitTile, Chip, Tabs,
                                 Toggle, Slider, Tooltip, SlideOver, Toast, Banner, Dialog, Avatar
web/src/pages/design/Styleguide  one route that renders every token and component (Gate 2 review)
```
**Build order (Phase 2):** tokens, fonts, icons → shell and nav → Fleet → Impact → phone page → slide-over → motion pass → projector mode → accessibility check.

**Tailwind v4 mapping** (excerpt, in `tokens.css`):
```css
@import "@fontsource-variable/figtree";
@theme {
  --font-sans: "Figtree Variable", system-ui, sans-serif;
  --color-ink: #080911;      --color-text: #2A2C3B;   --color-muted: #5B5E70;  --color-subtle: #6A6D82;
  --color-canvas: #FFFFFF;   --color-shell: #FAFCFE;  --color-pill: #F1F3F4;   --color-line: #E8E9F4;
  --color-accent: #5367EB;   --color-accent-ink: #3F52D4; --color-accent-soft: #EEF0FE; --color-accent-line: #7C88E8;
  --color-ok: #0E7A55;   --color-ok-tint: #E6F5EF;   --color-ok-fill: #1FA37A;
  --color-warn: #8F5600; --color-warn-tint: #FFF1D6; --color-warn-fill: #C47A00;
  --color-risk: #B3204F; --color-risk-tint: #FCE8EF; --color-risk-fill: #D43471;
  --color-sens: #555B70; --color-sens-tint: #EDEFF5; --color-sens-fill: #7A8197;
  --color-fail: #20232F; --color-fail-tint: #E8E9EF;
  --radius-card: 18px; --radius-tile: 12px;
}
:root {
  --g-insight: linear-gradient(90deg,#EFEEF1 0%,#F0EFF4 40%,#F0E7E8 75%,#EFE0E5 100%);
  --g-calm:    linear-gradient(90deg,#E8F3F2 0%,#E5EFF7 40%,#E7E9FB 75%,#EBE3F8 100%);
  --g-attn:    linear-gradient(90deg,#FCEFE4 0%,#FBE7E3 45%,#F9DEE7 100%);
  --shadow-card: 0 0 0 1px #E8E9F4, 0 8px 24px -12px rgba(83,103,235,0.22);
}
body { font-weight: 420; }
```

## 13. Do and don't
**Do:** keep the periwinkle for interactive things and the PipeGuard series only; let status be the loudest colour on any screen; use raised units on big numbers; put the "what to do next" in a strip; keep the chart bleeding to the card edge; use projector mode in the judging room.
**Don't:** add a second accent colour; use green, amber or red for anything but status; use a gradient without an icon and words; put a grey border on a card; use weight 700; add a drop shadow darker than the lavender glow; animate on every live tick; use `window.confirm`; use a generated image as an icon; ship Mercury's logo, copy or imagery.

## 14. Open items
1. **Review this file and confirm it is the spec (Gate 1).** Tell me anything that does not match the mockup.
2. **The logo — resolved:** David selected `docs/assets/proposedlogo.png`; use its SVG, WebP, PNG and favicon derivatives in `docs/assets/`.
3. **The two proposed gradients** (Calm, Attention): confirm the colours, or ask for a fourth.
4. **Derived screens** (section 11): review when built, at Gate 2.
