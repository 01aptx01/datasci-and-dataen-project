# D8.0 — Current State and Gap Audit

**Date:** 2026-11-21 (Asia/Bangkok)  
**Base:** `feat/dashboard-d8-interactive-lab` from local D7 HEAD `5103c72`  
**Scope:** inspect the existing D1–D7 dashboard and verified handoff before D8 changes.

## Existing

- The app already has eight hash routes: Overview, Models, Forecasts, Portfolio, Drift, Research, Provenance, and Guide. The data loader verifies the pinned snapshot before exposing its typed data.
- Overview and Models use the stored Stage 06 metrics. Forecasts already has a Test-only single-model/single-ticker session selector, previous/next buttons, a recorded-date slider, play/pause, a first-date reset, forecast/actual/error cards, pending-label treatment, and an exportable filter view.
- Portfolio already uses the selected stored row's covariance for `sqrt(wᵀΣw)`, has slider/number inputs, the recorded-weight and equal-weight presets, input validation, a local what-if, and a same-row comparison to the saved value.
- Drift already plots the fixed rolling MAE20 and recorded ADWIN timeline. Research and Provenance expose the frozen statistical results and source identity.
- `prepare_snapshot.py` verified the pinned ZIP SHA, Evaluation ID `82572c8417041976e1ce540d921e29a5f28c1d5d2a2d953a74c03582e7ca9be2`, Replay ID `3cbf81eb9242d8894d2f67f39065a17ff1ef55a2e098773aead915949ab11b12`, strict cutoff `2026-09-25`, and the snapshot's expected counts. Test has 2,976 forecast rows: 2,916 evaluable and 60 Pending. The verified files include 1,992 portfolio rows, 5,520 rolling MAE20 rows, and 729 drift timeline rows.
- Source review confirms the public handoff ZIP contains `stage05_experiment_manifest.json` and aggregate `drift_error_timeline.csv`, but no per-session B3 update/checkpoint event log. D8 must not draw update markers from the aggregate drift file.

## Needs improvement

- Date exploration is possible, but the control is still an index slider plus previous/next; it lacks explicit first/last controls, a date picker restricted to saved sessions, an as-of date, a maturity reveal, and an all-four-model comparison for the same ticker/date. Playback has no speed control. This is the main interaction to improve because users need to move through trading dates with confidence.
- Forecast status and label maturity are shown for the final frozen source state only. There is no separate teaching overlay for what would be eligible as of a selected saved date; current actual/error display is bound to the final evaluation join.
- The custom range control filters saved forecasts, but Models does not calculate a descriptive MAE/RMSE from the common mature paired rows in a selected range.
- The app has no six-stop guided tour or presentation/demo flow. Existing Guide is a reference page rather than a route-linked walkthrough.
- Portfolio exploration is functional, but lacks the plan's 50/30/20 and 60/20/20 teaching presets and a clear one-click reset to the default teaching allocation.
- Mobile and small-screen layout needs direct browser review for actual tap target size, date-control usability, and chart/table navigation.

## Missing

- A source-record drawer that connects the selected forecast, target window, source status, and Evaluation/Replay IDs.
- A linked selected ticker/date/model across Forecasts, Drift, and Portfolio, with exact-key matching and an explicit explanation when no complete portfolio row exists.
- A six-step tour using validated records, with previous/next/skip and source/method context.
- A demo script and a presentation mode that keeps the selected observation and snapshot status visible.
- A per-point drift evidence inspector for `adwin_delta`, width, estimate, and the alert flag.

## Blocked by artifact or environment

- Event-level B3 update and checkpoint markers are unavailable in the supplied published handoff ZIP; show that limitation rather than inventing an update history.
- The browser UI runner could not reach the workspace's local preview server (`ERR_CONNECTION_REFUSED`) even after serving the built site on the permitted local preview ports. Consequently, direct manual visual QA at desktop and 360/390/430 px has not been completed in this environment. This remains an explicit D8.7 verification item.
- `npm test` cannot run its standard TypeScript `typecheck` stage here because the repository has no installed dependencies and `tsc` is unavailable (`sh: 1: tsc: not found`). An ephemeral Node 24 TypeScript-transform build completed and all 19 existing Node tests passed; this does not substitute for the missing `tsc --noEmit` check.

## D8 implementation decision

- Reuse the existing `/forecasts` route as the Daily Replay Lab; do not add a parallel `/lab` route or recreate the D1–D7 shell.
- Implement the safe as-of viewer and same-date comparison first, then descriptive custom-range scoring, the guided tour, teaching-oriented portfolio presets/reset, and evidence-backed drift/demo improvements.
- Keep the official Stage 06 results and snapshot files immutable. Any new client calculation must be labeled descriptive and must use only verified, mature, common paired rows.
