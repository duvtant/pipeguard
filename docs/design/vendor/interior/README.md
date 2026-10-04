# interior.dev reference copies (not part of the app)

These are **unmodified copies** of ten React components from [interior.dev](https://www.interior.dev/) ([repo](https://github.com/ddoemonn/interior)), saved so we can study and adapt them. They are **MIT licensed, copyright (c) 2026 ozzy** (see `LICENSE`).

- **Reference only.** Nothing imports from this folder, it is outside `web/`, and it is not built or shipped.
- The eight in this folder (and their adaptation plan) are specified in `../../COMPONENTS.md`. The two in `optional/` are not scheduled.
- When a component is adapted into `web/src/components/ui/`, the new file keeps this notice at the top:
  `// Adapted from interior.dev (MIT, (c) 2026 ozzy): https://github.com/ddoemonn/interior`
  and is listed in `THIRD_PARTY_NOTICES.md` at the repo root (task P3.18).
- Source captured on 2026-10-03 from the site's public registry (`https://www.interior.dev/r/<name>.json`).

| File | Becomes | Used for |
|---|---|---|
| `hold-to-confirm.tsx` | `HoldToConfirm` | Reset demo |
| `drawer.tsx` | `SlideOver` | Unit detail panel |
| `value-flash.tsx` | `ValueFlash` | Live KPI numbers |
| `loading-button.tsx` | `ActionButton` | Run simulation, Simulate call, Tune now, Work orders |
| `skeleton-swap.tsx` | `useSkeletonSwap` + our skeletons | Loading states |
| `new-items-pill.tsx` | `NewEventsPill` | Decision log live feed |
| `segmented-control.tsx` | `Segmented` | Chart/table toggle |
| `slider-detents.tsx` | `Slider` | Impact sliders |
