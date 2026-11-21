# D8 UX Integration Gap Audit

**Date:** 2026-11-21 (Asia/Bangkok)
**Audited base:** `feat/dashboard-d8-interactive-lab` at `1f5422e`
**Scope:** current local TypeScript app, snapshot adapter, tests, and checked-in evidence. This supersedes the pre-D8 baseline inventory in `D8_CURRENT_STATE_GAP_AUDIT.md` for current implementation status.

The inventory and gap list below record the pre-integration baseline at the audited commit. The implementation and verification update at the end records what changed afterward.

## Evidence checked

- The app source in `web/src/app.ts`, `web/src/data/`, and `web/src/styles.css`.
- Node tests in `web/tests/` and `web/package.json`.
- Existing screenshots in `web/evidence/`; these files exist but were not treated as proof of the current interactive behavior.
- Local branch and HEAD; no remote state was inspected.
- Baseline `npm test`: snapshot checksum/identity verification, TypeScript typecheck and compile, static copy, and all **31 tests passed**.

The loaded handoff remains the frozen Stage 06 snapshot with Evaluation ID `82572c8417041976e1ce540d921e29a5f28c1d5d2a2d953a74c03582e7ca9be2`, Replay ID `3cbf81eb9242d8894d2f67f39065a17ff1ef55a2e098773aead915949ab11b12`, and strict cutoff `2026-09-25`. The checked-in adapter exposes aggregate drift evidence but no event-level B3 update/checkpoint ledger.

## Current implementation inventory

| Area | Observed local behavior | Decision |
|---|---|---|
| Routes and shell | Eight stable hash routes: Overview, Models, Forecasts, Portfolio, Drift, Research, Provenance, Guide. Snapshot identity banner is shared across pages. | **REUSE**; keep route names and shell. |
| Overview | Verified-snapshot hero, two CTAs, official metrics, coverage, forecast chart, provenance/review state, and eight route cards. It does not yet present exactly three question-led entry cards. | **EXTEND**; keep source metrics and status, replace the equally prominent route-card grid with three entry questions. |
| Forecast replay | `/forecasts` contains Test-only recorded-session controls, date selector and slider, first/previous/next/last, play/pause/speed, as-of label gate, explicit reveal, B0–B3 same-date table, source details, and a Portfolio CTA. | **REUSE + EXTEND**; keep the route and safeguards, connect it to shared URL selection and cross-page context. |
| Portfolio | Uses a selected saved date/model row only when status and covariance are valid; re-calculates volatility from the row's three-asset covariance; has default, 60/20/20 and equal-weight presets. | **REUSE + EXTEND**; keep all-three-asset math and add shared selection plus a route back to Replay. |
| Models | Displays frozen Stage 06 metrics and comparisons, plus descriptive range scores calculated from valid mature common paired rows. | **REUSE**; preserve official and exploratory scopes as separate outputs. |
| Drift | Displays recorded rolling MAE20 and ADWIN Test timeline, zero-alert count, and selected-observation inspector. It has independent ticker/model/date controls; there is no event-level update/checkpoint source. | **REUSE + EXTEND**; synchronize compatible session context and preserve `UNAVAILABLE` for unsupported per-session event claims. |
| Guided tour | Six route-linked guide stops select a source-backed example when available and explain maturity, comparison, drift, and portfolio risk. | **REUSE + EXTEND**; route transitions need to preserve the selected session and support the reverse Portfolio handoff. |
| URL and shared selection | The router reads an exact hash path only. Replay state (`ticker`, `model`, `sessionIndex`, `asOf`) and Portfolio state (`date`, `model`) are separate local fields. Replay→Portfolio copies date/model in memory only. Deep links, Eval/Replay ID validation, invalid-selection explanations, and Back/Forward selection restoration are absent. | **ADD shared typed selection**; query state belongs inside the existing hash route and must validate against the verified bundle. |
| Playback lifecycle | Playback is local and stops on route changes and at the end; reduced-motion disables it when the page renders. | **EXTEND**; also stop on document visibility/focus changes and data errors. |
| Accessibility and responsive evidence | Controls include labels and reduced-motion handling. CSS has mobile layouts. Existing 390px/1440px screenshots are checked-in artifacts, but no current interactive browser review was completed in this audit. | **KEEP + VERIFY**; static CSS and old screenshots do not establish current responsive behavior. |

## Integration gaps to close

1. Add one typed `ExperimentSelection` and URL contract carrying pinned Evaluation/Replay IDs, split, prediction date, model, ticker context, as-of date, optional range, and view.
2. Parse and validate hash queries without silently replacing a requested date/model/split when the verified snapshot lacks that record.
3. Use the same selection for Replay, compatible Drift inspection, and exact-row Portfolio handoff in both directions; keep Portfolio calculations over SPY, IEF, and GLD.
4. Restore selection through browser Back/Forward and stop local playback when the document is hidden or route/data state changes.
5. Reduce Overview's prominent entry choices to the three questions in v1.1 while retaining all eight stable routes in navigation and contextual links.
6. Add tests for URL round-trip, invalid identity and selection, unavailable portfolio rows, and no-fallback behavior; then perform current responsive/browser checks if the local browser can load the preview.

## Explicit reuse and non-goals

- Keep the existing `/forecasts` replay route; do not create a duplicate `/lab` page.
- Reuse and preserve existing frozen metrics, common-pair range calculations, source details, drift inspector, tour, and portfolio presets.
- Do not change Stage 01–06 code or results, create inference, make up per-day ADWIN/update/checkpoint events, or recalculate official statistical decisions.
- Keep all eight routes and the report-approval-pending status.

## Baseline verification limits

`npm test` passed locally before the integration changes. Direct browser behavior and mobile tap/layout quality remain unverified until the updated app is opened at desktop and 360/390/430px widths. The current screenshot files are not sufficient to claim those checks passed.

## D8 v1.1 implementation and verification update

**Updated:** 2026-11-21 (Asia/Bangkok)
**Local branch:** `feat/dashboard-d8-interactive-lab`; no remote action was taken.

### Implemented

- Added the typed `ExperimentSelection` hash-query contract for pinned Evaluation/Replay IDs, Test or Validation split, exact prediction date/model/ticker, as-of date, view, and shareable range preset/bounds.
- Validated deep links against the verified snapshot. Invalid or unavailable dates, models, splits, and exact portfolio rows show an explanation without silently selecting a substitute.
- Connected Forecasts, Portfolio, Drift, and Models to the shared selection. Portfolio and Drift reject non-Test sessions; Portfolio uses the exact saved Test row and retains all three assets in its risk calculation. Drift explains when the selected source observation is absent.
- Preserved selection through route navigation and URL changes, added hash-change restoration and playback stopping on route changes, page hiding, window blur, and reduced-motion changes.
- Changed Overview to three question-led entry cards while retaining the verified snapshot status, research question, tour, saved-session link, and stable route navigation.
- Kept exploratory range selection separate from frozen Stage 06 metrics and synchronized its range preset and dates in shareable links.

### Verification completed

- `npm test` — passed, **39/39 tests**. This freshly verified pinned snapshot identity/checksums, typecheck, compile/static build, and the complete Node test suite.
- `git diff --check` — passed with no whitespace errors.
- Opened the built preview at `http://127.0.0.1:4173/` in Edge at **1920×1032**. Visually inspected Overview and Forecasts; navigated Forecasts → Portfolio → Drift and confirmed the URL retained the same Evaluation/Replay IDs, Test split, date, ticker, model, and as-of selection. Drift showed an explicit missing-observation state for the selected date instead of substituting another row.
- No screenshot was written into the repository. The desktop view was inspected in the active browser session.

### Verification limits

- Mobile widths (360/390/430px), browser console output, browser Back/Forward, and playback interruption while navigating were not independently exercised. The route restoration and playback-stop code paths were reviewed, and normal route navigation was exercised, but those specific interactions are not claimed as browser-verified.
- Playwright CLI could not start in this environment: its WSL wrapper returned `Bash/Service/CreateInstance/E_ACCESSDENIED`; direct `npx` then failed because `@playwright/cli` was not cached (`ENOTCACHED`) and network access was restricted. The existing Edge session was used for the desktop review.
- The unreadable `.pytest-tmp-handoff/` directory produced a `git status` permission warning; it was not read, changed, or staged.

No Stage 01–06 source/artifacts were changed. No push, merge, PR, release, deploy, or remote publication was performed.
