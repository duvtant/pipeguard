# PipeGuard UX Flows

**Status: PROPOSED, awaiting your approval.** Researched on Mobbin. Mobbin has no industrial tools, so each flow borrows a pattern from a product that does the same job in another domain. The flows are independent of the visual style, so they apply to the chosen direction (`DESIGN.md`).

## The spine: the pitch is the product flow
The product should read in the same order as the five-minute pitch:

**Glance → Drill → Decide → Act → Verify → So what?**
Spot the red unit, see why, the voice call acts, the plan visibly changes, and the Impact tab shows it was worth it.

## The eight flows
| # | Flow | Pattern to use | Where it comes from | Why it fits PipeGuard |
|---|---|---|---|---|
| 1 | **Glance at the fleet** (manager's home) | A "Healthy / N at risk" summary panel on top, then tiles grouped by station | [Customer.io "Healthy" panel](https://mobbin.com/screens/d34734b2-6009-4343-bed5-650566cfa5ff), [Supabase service-health grid](https://mobbin.com/screens/704ea722-33ea-44f5-ba70-03005b33a9f9) | A manager decides in seconds whether anything needs attention. The summary answers "is everything OK?", the grid shows where |
| 2 | **Drill into a unit** | A **slide-over side panel** over the fleet: cause in plain words, three key facts, history chart | [LangSmith alert detail](https://mobbin.com/flows/966f89b1-8a18-4626-83de-f68e9f922593), [Klaviyo monitor detail](https://mobbin.com/flows/17504249-b131-4819-8304-00da758948ea), [Better Stack incident detail](https://mobbin.com/flows/fc2ba92b-4783-43da-92c7-8acf4f16a080) (layout only, it is dark) | The manager stays in the fleet context and live updates keep running behind the panel. Cause plus three fact tiles maps to our reason, range and confidence |
| 3 | **Follow what happens next** | A visible state chain: At risk → Calling → Answered → Re-planned → Serviced, with a confirming banner at each step | [incident.io incident list with stage chips](https://mobbin.com/flows/cc2ec60c-da99-47b7-a135-65be48f2135a), [incident.io timeline](https://mobbin.com/screens/bf6f64ff-6ebc-4a7f-b354-f2a22066b03b) | The voice call is invisible unless the screen shows it. This makes "the technician's answer changed the plan" visible |
| 4 | **The weekly plan** | A team-by-day grid with coloured job blocks, a warnings chip ("2 conflicts, Fix warnings") and an "Open shifts" row | [Square scheduling](https://mobbin.com/screens/66ea4b9b-7284-4f6a-bc5f-cb0860a34724), [Deputy](https://mobbin.com/screens/238cdb58-7f42-4423-bda9-f30c426d8292), [7shifts conflicts](https://mobbin.com/screens/d704059e-d550-4420-8aa0-121b7787f54e) | A crew-limited schedule is a shift roster, which everyone already reads. "Open shifts" is our "needs manager decision": an unassigned unit that must stay visible |
| 5 | **What-if Impact** | Sliders with a **sticky summary bar**, results shown as ranges, an itemised breakdown on demand | [Apollo credits sliders](https://mobbin.com/flows/24b4970f-6b9b-4f49-9301-7e202ca57da0), [Zillow cost calculator](https://mobbin.com/flows/67104e02-245f-48d1-9e88-9d095b622cd0) | Totals stay on screen while you drag. Zillow shows a range ("$2,083 to $2,918"), matching our low/likely/high stance |
| 6 | **Decision log** | A filterable activity feed with one expandable chain per alert | [Vercel activity feed with filters](https://mobbin.com/screens/a111dca7-48a2-4456-bba7-acec68ff70f0), incident.io timeline | An audit trail. Filters by unit, type and date plus an expandable transcript keep it usable at 100 units |
| 7 | **The technician's call** (phone) | Incoming call with huge Decline / Accept → in-call with a huge End and a live transcript → a one-tap verdict afterwards, skippable | [iOS incoming call](https://mobbin.com/flows/7214f955-ded7-44e3-a26a-614ea9f0885a), [Badoo end-of-call feedback](https://mobbin.com/flows/01db9ecc-c272-4251-b4a5-fc0a6879d641), [Truecaller assistant with live text and thumbs](https://mobbin.com/flows/5e927efa-1f17-4b5d-9b52-c4e32a74065d) | One-handed use outdoors; a familiar call screen needs no training; a one-tap verdict gets more feedback, which feeds our learning loop |
| 8 | **Test mode: reset and kill sensor** | Reset opens an in-page plain-language dialog; kill sensor is instant with an undo toast | [GoDaddy "Want to start over?"](https://mobbin.com/screens/e6a78ef8-d065-4a53-9fd6-321ec3a8ea3a), [Clerk typed confirmation](https://mobbin.com/screens/de2ed754-dcb1-4e66-867f-45c5f6c9ed41) (only for irreversible actions) | A reset is recoverable, so a typed confirmation would only slow a live demo |

**Cross-cutting patterns:** an "all clear" empty state ([incident.io home](https://mobbin.com/screens/bf6f64ff-6ebc-4a7f-b354-f2a22066b03b)); a live-change toast for "Plan changed" ([Workable](https://mobbin.com/screens/ec118178-3e4d-4bb4-ba08-f8c38190a293)); a top notice banner for "reconnecting" and "demo mode" (the Customer.io banner).

**Deliberately skipped:** onboarding checklists, upsell banners and promo cards.

## Proposed navigation
- **Manager:** left sidebar groups: Monitor (Fleet, Plan), Analyse (Impact, Decision log), Manage (Roster, Work orders, Settings). A global search jumps to a unit by ID. Test mode is a separate route, not in the sidebar.
- **Technician:** no navigation. One screen at a time (idle → ringing → in call → after call).

## Open questions for you
1. Are these eight flows right? Anything missing (a step, a screen) or unnecessary?
2. Should unit detail be a slide-over (proposed) or a full page?
3. Should the plan be a team-by-day grid (proposed) or a simple table?
4. Is a global search worth including for the demo?
