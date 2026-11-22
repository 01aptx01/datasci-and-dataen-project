# DEDS Final Dashboard UX Baseline Audit

**Date:** 2026-11-22 (Asia/Bangkok)  
**Branch / baseline HEAD:** `feat/dashboard-final-ux-acceptance` / `e5b637c`  
**Scope:** Final UX acceptance baseline for the eight existing DEDS dashboard routes. The attached acceptance plan is treated as requirements; its operational instructions do not authorize push, merge, release, or deployment.

## Frozen source and build baseline

- Evaluation ID: `82572c8417041976e1ce540d921e29a5f28c1d5d2a2d953a74c03582e7ca9be2`
- Replay ID: `3cbf81eb9242d8894d2f67f39065a17ff1ef55a2e098773aead915949ab11b12`
- Source ZIP SHA-256: `20dff91705ffbb60ab579f5c1f907537015ec2f52be001d5dfd24ea8978ae3f5`
- `npm test`: passed, 58/58 tests, including snapshot verification, TypeScript typecheck/compile, static copy, and Node tests.
- `npm run build`: passed with the same pinned source IDs and ZIP hash.
- Browser: local built preview at `http://127.0.0.1:4173/`; no error or warning console entries were reported during this baseline.
- The requested 1440×900 browser override produced a page viewport of 1309×818 CSS pixels in the in-app browser. This is the measured viewport for the observations below; it is not evidence for the plan's 1366/1440/1920 desktop sizes.

## Routes inspected

Overview, Models, Forecasts, Portfolio, Drift, Research, Provenance, and Guide were opened from the dashboard navigation. Their titles, principal headings, selection context, and rendered text sizes were inspected. Selection state was carried in the hash query through navigation.

## Observed P0 issues

### Replay controls and result leave the same sightline

On Forecasts at the baseline viewport, the Replay step buttons began at document Y≈627; the selected forecast cards began at Y≈1132 and the same-date comparison began at Y≈1275. When the forecast cards were brought into view, the Next button was at viewport Y≈−121 while the forecast and comparison were visible. Activating Next through the browser moved the viewport upward by about 510px (scrollY 748→238) to rediscover the control; the date advanced from 2025-10-01 to 2025-10-02.

After the update, focus was on `body` instead of the Next button. `render()` replaces the full app root with `innerHTML`, which also rebuilds the active control.

### Portfolio route keeps the previous page scroll offset

Opening Portfolio from the Replay session retained the selected date/model/IDs in the URL, but the page stayed at scrollY≈947. The Portfolio heading was at document Y≈390 and date/model controls at Y≈475, so both were above the viewport on entry. Users had to scroll back to establish the new page context.

### Scenario editing loses keyboard continuity

In Scenario Lab, the three numeric A/B weight fields rendered at 12px. Changing Scenario A SPY from 50% to 60% showed the expected 110% validation state; after leaving the invalid field with Tab, focus moved to the paired slider rather than remaining on a stable edited field. The application rerenders the whole root for invalid and committed weight changes.

## Typography and target baseline

The global role tokens are 10px micro, 11px compact, 12px support, and 13px control. Sampled Models, Drift, Research, and Portfolio controls included 11–13px descriptions/labels; the Scenario numeric editor is 12px. Several replay and portfolio controls are 32–40px tall, below the plan's 44px minimum target. These are candidates for role-based token and hit-area changes; decorative metadata may remain secondary if it does not carry an action, status, or interpretation.

## Constraints retained

- Do not alter Stage 01–06 sources, frozen metrics/results, forecast data, or snapshot artifacts.
- Preserve D8 shared selection and D9 exact same-date/model covariance calculations, Pending/As-of protections, report approval state, and no-live-inference boundary.
- The three-first-time-user study has not been conducted. A final report must state this directly and must not call the result a scientific UX study.
- No baseline browser screenshots were saved into the repository. Browser observations above are measured from the live local preview; later evidence must be captured only when an actual screenshot is saved.
- All Git work remains local. The D9 branch tracks `origin/feat/dashboard-ux-integration-d8-d9`; the acceptance branch has no upstream.
