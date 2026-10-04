# Interaction Components: Build Spec for Phase 3

**Status:** approved list, **not built yet**. This is the exact plan for adapting eight components from [interior.dev](https://www.interior.dev/) (MIT, copyright 2026 ozzy, [repo](https://github.com/ddoemonn/interior)) into PipeGuard. Reference copies of the original source are in `docs/design/vendor/interior/` (see its README). They are **reference only**: never import from that folder.

**Why these eight, and nothing else.** They fix real problems in our product (an accidental demo reset, an inaccessible slide-over, silent live numbers, buttons that jump, loading that flashes, a jumping live feed, a fiddly slider). Everything else on the three sites was decoration, a duplicate, or too heavy. `generative-loaders` and BeUI were rejected (see the review in the project history): nothing from them is used.

**Read first:** `DESIGN.md` (tokens, motion rules) and `UX_FLOWS.md` (where each interaction lives).

---

## 1. How we bring them in

1. **Copy, do not install.** The shadcn CLI wants a `components.json`, which clashes with our decision to drop shadcn. Each component imports only `motion` and `react`, so copying the file is clean.
2. **Each component becomes our own file** in `web/src/components/ui/`, renamed to our vocabulary, restyled with our tokens, with the original MIT notice kept at the top:
   ```tsx
   // Adapted from interior.dev (MIT, (c) 2026 ozzy): https://github.com/ddoemonn/interior
   ```
3. **`THIRD_PARTY_NOTICES.md`** at the repo root carries the full MIT text and the list of adapted files, and the README's originality section gets one line. This also satisfies the handbook's attribution rule. (Task P3.18.)
4. **Motion setup once:** install `motion`, wrap the app in `<MotionConfig reducedMotion="user">`. Every component already calls `useReducedMotion`, and the wrapper makes the OS setting apply to the rest.
5. **Show each one in the style-guide route** (`/design`) in every state, before it is used on a real screen.

## 2. Changes that apply to all eight
These are the same everywhere, so do them mechanically:

| In the original | Replace with |
|---|---|
| Every `dark:` class and the `"use client"` line | Delete (we are light only; the directive is Next.js-only and harmless but noise) |
| `bg-white`, `bg-[#1D1D1A]` | `bg-canvas` |
| `bg-stone-100/70`, `bg-stone-200`, skeleton bars | `bg-pill` |
| `border-stone-200`, `border-white/[0.16]` | the card edge: `shadow-card` (lavender glow), or `ring-1 ring-line` on small controls |
| `text-stone-700` | `text-ink` (headings, values) or `text-text` (body) |
| `text-stone-500`, `text-stone-400` | `text-muted` |
| `bg-stone-800 text-white` (fills and thumbs) | `bg-ink text-white`, or `bg-accent` / `bg-risk` where stated per component |
| `emerald-*` | `text-ok` / `bg-ok-tint`, **only** for success |
| `red-*` | `text-risk` / `bg-risk-tint`, **only** for errors |
| Focus colour `#4568FF` ring and shadow | `focus-visible:ring-2 ring-accent ring-offset-2` |
| `rounded-[9px]` | `rounded-full` (chips, buttons), `rounded-xl` (inputs and tracks) |
| `font-mono text-[11px]` and `text-[12.5px]` | our sans at **14 px minimum**, `tabular-nums` (we never go below 13 px) |
| `filter: blur(...)` in animations | **Remove.** No blur in content (DESIGN.md section 9.5). Use opacity and 3 to 8 px `y` movement only |
| The component's own spring constants | Keep unless noted. Where DESIGN.md gives a token, use ours |
| Inline SVG icons (check, close, arrow) | Phosphor Fill or Regular via `unplugin-icons` |

## 3. The eight components (ranked by impact against effort)

Effort is for a coding agent working from this spec, plus review. S is under an hour, M is one to two hours.

### 1. Hold to Confirm → `HoldToConfirm.tsx` (S)
**Where:** Test mode, **Reset demo**. Reference: `vendor/interior/hold-to-confirm.tsx`.
**Why:** one stray click on Reset mid-pitch wipes the scenario. A dialog is two quick clicks that presenters click through. A deliberate hold is fast and accident-proof.

**How it works (read from the source):** `useHoldToConfirm` runs a `requestAnimationFrame` loop that accumulates held time, decays it on release, and fires `onConfirm` at `duration`. It cancels on pointer movement beyond 10 px, window blur, tab hide and Escape. Space and Enter hold from the keyboard. The visual is a `clipPath` sweep of an inverted copy of the label.

**Adapt:**
- `duration` default **900 ms** (original 1800). `steps` 20, `releaseRate` 2.5 unchanged. Set `haptic` false.
- Idle: `bg-pill text-ink`, pill shape, 40 px tall, a leading icon (`arrow-clockwise-light`). Sweep layer: `bg-risk text-white` (**6.49:1**).
- Labels: idle "Hold to reset demo", `confirmLabel` "Demo reset" (sentence case). Replace the inline check SVG with `check-circle-fill`.
- The sweep uses `ease: "linear"` on purpose: a fill that tracks elapsed time must be linear. **This is the one allowed linear motion** (see amendments, section 5).
- Wire `onConfirm` to `POST /api/admin/reset`; the screen then refetches the fleet.
- Keep the screen-reader text ("Press and hold for 0.9 seconds to confirm. Releasing early cancels and nothing happens.") and the status announcement on commit.

**Verify:** a 900 ms hold fires once; releasing at 500 ms does not; Space and Enter work; Escape cancels mid-hold; alt-tabbing cancels; with reduced motion the fill appears instantly but the full hold is still required; a second hold within `resetAfter` is ignored.

### 2. Drawer → `SlideOver.tsx` (M)
**Where:** the **unit detail panel** opened from a Fleet tile, a plan item or a decision-log row. Reference: `vendor/interior/drawer.tsx`.
**Why:** a slide-over done by hand usually misses focus handling. This one has all of it: a **focus trap**, **focus returns to the trigger** on close, the rest of the page is made **`inert`**, page scroll is locked (with scrollbar-gutter compensation), Escape closes, `role="dialog"` with `aria-modal`, `aria-labelledby`, and a screen-reader hint. It also supports drag-to-dismiss on touch.

**Adapt:**
- `width` **430**, `side="right"`, `container="viewport"` (modal).
- `title` becomes `ReactNode`, and add a **`headerExtra`** slot so the status pill sits next to "EDS-07". Header per DESIGN.md 5.9: the unit ID at 22 px, no bottom border, no drag-grab cursor on desktop. Keep drag-to-dismiss for touch only.
- Close button: `x` icon (Phosphor), `text-muted`, `hover:bg-pill`, round, 40 px target.
- Scrim `bg-[rgba(250,252,254,0.7)]`, **no blur**. Panel: `rounded-l-[18px]`, no border, shadow `-20px 0 50px -20px rgba(8,9,17,0.3)`.
- **z-index:** the container is `z-50`; change to **`z-30`** (our scale: scrim 20, slide-over 30, toast 40, dialog 50, tooltip 60).
- Spring `DISCLOSE` (stiffness 150) feels lazy for our spec. **Use `{ stiffness: 380, damping: 34 }`** (DESIGN.md 9.1). Check the settle time by eye in the style guide.
- Add `footerBleed`: a prop that removes the footer's padding and top border so the **Calm insight strip** runs edge to edge.
- Body: facts, a small gradient chart, and the timeline (DESIGN.md 5.9). Load with the skeleton hook (component 5).

**Verify:** Tab cycles inside the panel only; Shift+Tab wraps; Escape closes and **returns focus to the clicked tile**; the background is not clickable; live SSE updates keep rendering behind the scrim; reduced motion makes it instant; the body does not jump when scroll is locked.
**Watch out:** inert siblings include any toast portal. Render toasts inside the app root or accept that they are not clickable while the panel is open (they auto-dismiss, so acceptable).

### 3. Value Flash → `ValueFlash.tsx` (S)
**Where:** **live numbers only**: the KPI ("3 units"), the Stations list counts, the plan stat columns (Scheduled, Needs decision, Completed) and the Impact figures. **Never on the 100 tiles.** Reference: `vendor/interior/value-flash.tsx`.
**Why:** numbers change silently, so nobody sees what moved. It briefly marks the change. Its screen-reader behaviour is the key feature for us: `announceAfter` announces only the **settled** value, so a number that changes four times a second does not spam a screen reader.

**Adapt (this is the biggest rework of the eight):**
- **Remove the green-up, red-down meaning.** In PipeGuard a rising number is not "good" (more units at risk is bad). Flash tint is `bg-accent-soft` with `text-accent-ink` (**5.50:1**); no colour difference by direction.
- Drop the direction arrow by default (add `showDirection`, default false; when on, use `arrow-up-right` and `arrow-down-right` in `text-muted`).
- Delete the fixed `text-[13px] px-1.5 py-[3px]`. Let the component **inherit the font size** so it works at 46 px. Add a `unit` prop for the **raised unit** (`3ᵘⁿⁱᵗˢ`).
- Remove `filter: blur` from the digit roll. Keep the vertical roll (opacity and `y` 0.85em) but shorten it. At KPI size drop the `scale` lift.
- **Throttle the input** with a tiny `useThrottledValue(value, 2000)` hook before passing `value`, to honour "at most once per 2 s" (DESIGN.md 9.2). `hold` 1200 ms (our flash token). `announceAfter` 1500 ms.

**Verify:** a value changing rapidly flashes at most once per 2 s; the screen reader says the final value once; reduced motion shows an instant tint with no roll; `tabular-nums` prevents width jitter.

### 4. Loading Button → `ActionButton.tsx` (S)
**Where:** **Simulate call**, **Tune now**, **Download work orders**. Reference: `vendor/interior/loading-button.tsx`.
**Why:** today a click gives no feedback, labels change width, and a double click fires twice. All four faces (idle, pending, success, error) share one grid cell, so the **button never changes width**, and a second click while pending is ignored. `aria-busy` and a polite status announce the result.

**Adapt:**
- Two variants: `primary` (solid `--accent`, white text, 4.66:1) and `chip` (`bg-pill text-ink`, pill, 40 px).
- Add an **`icon`** prop (a leading 16 px Phosphor icon in the idle face), since our chips all have one.
- Success face: `text-ok` and `check-circle-fill`; error face: `text-risk` and `warning-fill`. Labels: "Done", "Try again" or specific ("Downloaded").
- Remove the `filter: blur(3px)` from the face cross-fade (opacity and 3 px `y` only).
- The spinner loops while pending. **That is the one allowed second looping animation** (see amendments). It is already still under reduced motion.
- `onAction` returns the request promise (`fetch(...)`); errors map to the error face and `onError`.

**Verify:** width never changes across states; double click fires once; keyboard Enter and Space work; the status announces "Done" or "Try again"; reduced motion has no spinner rotation.

### 5. Skeleton Swap → `useSkeletonSwap` plus our own skeletons (S)
**Where:** Fleet first load, the Impact results while `POST /api/simulate` is in flight, the unit panel body. Reference: `vendor/interior/skeleton-swap.tsx`.
**Why:** skeletons that flash on fast loads and content that jumps in feel slower than a plain wait. The timing logic fixes both: `delay` 120 ms (no skeleton at all for fast loads) and `minVisible` 380 ms (once shown, it stays long enough not to flicker).

**Take the hook, not the wrapper.** The wrapper sets a **fixed `height` and `overflow-y: auto`**, which is built for blocks of text and would clip or scroll a card. So:
- Keep **`useSkeletonSwap({ ready, delay, minVisible })`** as is.
- Build our own **`Skeleton`** primitives (bar, circle, tile) in `bg-pill`, shaped like the final content, and a small **`Reveal`** component that stacks skeleton and content in **one grid cell** (height = the taller of the two, so nothing clips) and cross-fades with opacity only (200 ms), **no blur, no scale**.
- For Impact, prefer **keeping the last result visible but dimmed** (DESIGN.md 3 of UX flow 5) and use the skeleton only on the first load.

**Verify:** a 50 ms response shows no skeleton; a 200 ms response shows one for at least 380 ms; no layout shift; `aria-busy` while loading; reduced motion cross-fades instantly.

### 6. New Items Pill → `NewEventsPill.tsx` plus `useNewItems` (S)
**Where:** the **Decision log** feed. Reference: `vendor/interior/new-items-pill.tsx`.
**Why:** live events either shove the list around while you read, or arrive unseen. `useNewItems` keeps your reading position when new items arrive above, counts them, and a pill ("3 new events") lets you jump up when you choose. When you are already at the top, new items just appear.

**Adapt:**
- Use `anchor="top"` (newest first), `itemCount` = number of loaded events, and give the scroll container the returned `scrollProps` (fixed height, `overflow-y: auto`).
- Pill: `rounded-full`, solid `--accent`, white text, an `arrow-up` icon, lavender shadow; label "3 new events". Replace the inline arrow SVG.
- **Count only genuinely new events.** The server replays a few old events on reconnect (UX/SSE rule): de-duplicate by `event_id` **before** counting.
- The hook uses a **passive scroll listener on the list container** for pin detection. That is functional, not decorative, and allowed (amendments).

**Verify:** scrolled down, new events do not move the viewport and the count rises; clicking jumps to the top (instantly under reduced motion); at the top, events appear in place; the count announces once, not per event.

### 7. Segmented Control → `Segmented.tsx` (S)
**Where:** the **chart/table toggle** on KPI cards, and any two-to-three-way view switch (for example plan view). Reference: `vendor/interior/segmented-control.tsx`.
**Why:** a plain button pair makes the selection jump. This one slides a thumb, is a true `radiogroup` (`role="radio"`, `aria-checked`, roving tabindex) and supports Arrow, Home and End keys.

**Adapt:**
- Options become `{ value, label (screen reader text), icon?: ReactNode }`; **icon-only options must keep `label`** (it becomes the `sr-only` text).
- **Drop the label-inversion mask** (the duplicated, clipped dark layer). Our toggle (DESIGN.md 5.6) is a **white thumb with an inset 1 px accent ring** on a 1 px `--line` outline, 10 px radius. The selected icon is `--accent`, the others `--muted`. This is simpler: keep the motion-value thumb and the keyboard code, delete the mask.
- Hover and focus: `focus-visible:ring-2 ring-accent`.
- **Text tabs with the sliding underline** (Fleet filters) are **not** this component. Build them with `motion` `layoutId` in about 20 lines.

**Verify:** Arrow keys move and select; Home and End work; the thumb is instant under reduced motion; screen reader reads the group label and each option.

### 8. Slider Detents → `Slider.tsx` (M)
**Where:** **Impact** sliders: crews per station (0 to 5), cost of a breakdown, cost of a service. Reference: `vendor/interior/slider-detents.tsx`.
**Why:** hitting exactly 2 crews, or getting back to $200,000, is fiddly with a plain range input. Detents give snap points: a whole crew count, and the default value.
**Confirmed accessible:** it exposes `role="slider"`, `aria-valuemin`, `aria-valuemax`, `aria-valuenow`, `aria-valuetext` (including the detent label, "default") and full keyboard support (arrows, Shift+arrow to the next detent, PageUp and PageDown, Home, End). (My first-pass flag about a missing role was wrong.)

**Adapt:**
- Track `bg-line` (`#E8E9F4`); fill `bg-accent`; detent ticks `bg-accent/35`; thumb white with a 2 px accent ring (or solid `--accent`), **22 px** for projectors. Remove the `stone` colours.
- Label and value: **14 px** sans, value in `text-ink` weight 480 with `tabular-nums` (remove `font-mono text-[11px]`). Keep the invisible "widest label" trick: it prevents the value from shifting the layout.
- Detents: crews `[0,1,2,3,4,5]`; breakdown cost `[{ value: 200000, label: "default" }]`; service cost `[{ value: 20000, label: "default" }]`. `haptic={false}` (desktop and projector).
- `format` for dollars (`$200,000`) and crews (`2 crews`).
- Upstream: debounce the value about 200 ms and cancel the previous `/api/simulate` with an `AbortController` (UX flow 5).
- Uses `toSorted` and `findLast`: fine, our TypeScript target is ES2023.

**Verify:** snaps to a detent when within `pull` of it; keyboard reaches every value; `aria-valuetext` reads "$200,000, default"; reduced motion makes the thumb jump; the thumb is at least 22 px.

## 4. Optional, only if time allows
Kept in `vendor/interior/optional/`, **not scheduled**:
- **Tooltip Group** (526 lines): neighbouring tooltips appear instantly when scanning across the 100 tiles. Restyle to the dark tooltip with colour keys. Nice, not essential.
- **Collapsible Banner** (291 lines): for the "demo mode" and "reconnecting" notices (folds to its title, Escape, `aria-live`). Use the Insight or Attention gradient.

## 5. Amendments to DESIGN.md (applied)
Adopting these needs three honest exceptions to the motion rules, now recorded in `DESIGN.md` section 9.5:
1. **One more allowed loop:** the Loading Button spinner, only while a request is pending and still under reduced motion. (Before: only the phone ring.)
2. **Linear easing is allowed only** for the Hold to Confirm fill, because a progress sweep must track elapsed time.
3. **A passive scroll listener on a list container** is allowed for functional pin detection (`useNewItems`). Scroll listeners for animation, and any on `window`, remain banned.

## 6. Build order and cut rule
1. **Foundations:** `motion` installed, `MotionConfig`, the token mapping in section 2, `/design` style-guide route.
2. **SlideOver** (core flow, build it first), then **Skeleton** and **ValueFlash** (used inside it).
3. **ActionButton** and **HoldToConfirm** (used by Test mode and chips).
4. **NewEventsPill**, **Segmented**, **Slider**.

**If time runs short, cut in this order:** Slider (fall back to a styled range input), Segmented (two plain buttons), NewEventsPill (live feed just prepends). **Never cut:** SlideOver, HoldToConfirm, ActionButton.

## 7. Costs
- **Runtime:** `motion` is about **46 KB gzipped** for a full import (bundlephobia). It is already in the plan for presence and layout animation, so these components add **no new dependency**. The eight components themselves are roughly 2,300 lines of source, estimated at **20 to 30 KB gzipped** (an estimate: measure it in the real build).
- **Optimisation if needed:** `LazyMotion` with `domAnimation` and `m.*` components can cut `motion` to roughly a third, but it means rewriting `motion.*` as `m.*` in these files, so only do it if the bundle is a problem.
- **Maintenance:** copy-paste means **no upstream updates**. That is acceptable for a hackathon, and we own the code.

## 8. Acceptance for the whole set
- [ ] Every component is in `/design` in all of its states, in normal and reduced-motion modes.
- [ ] Contrast of every state passes (the adapted pairs checked so far: 4.66:1 to 19.9:1).
- [ ] Keyboard-only walkthrough of Test mode, a unit panel open and close, the Impact sliders and the decision log works.
- [ ] No `dark:` classes, no `filter: blur`, no `z-50` on the slide-over, no stone or emerald colours left (`grep` the folder).
- [ ] `THIRD_PARTY_NOTICES.md` exists and each adapted file keeps its notice.
