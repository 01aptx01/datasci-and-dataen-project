# D3–D7 Verification Record

**Date:** 2026-11-21 (Asia/Bangkok)
**Branch:** `feat/dashboard-d1-d2`
**Mode:** local, static, read-only verification; no deployment or remote action

## Frozen source identity

- Evaluation ID: `82572c8417041976e1ce540d921e29a5f28c1d5d2a2d953a74c03582e7ca9be2`
- Replay ID: `3cbf81eb9242d8894d2f67f39065a17ff1ef55a2e098773aead915949ab11b12`
- Handoff ZIP SHA-256: `20dff91705ffbb60ab579f5c1f907537015ec2f52be001d5dfd24ea8978ae3f5`
- Strict cutoff: `2026-09-25`; mode: `Simulated Historical Replay`; report approval: `PENDING`.
- Point-in-time market-source availability remains unverified.

The dashboard uses the pinned handoff and the allowlisted CSV members only. Browser-side computation is limited to portfolio what-if volatility using covariance from the selected stored row. No training, replay, hypothesis inference, or Stage 06 changes were made.

## Commands

Run from `web/`, sequentially so the snapshot preparation steps do not write to the same files concurrently:

```text
npm test
npm run build
```

Results on 2026-11-21:

- `npm test`: passed, 19 tests; typecheck and compile passed as part of the script. Snapshot preparation confirmed the pinned Evaluation ID, Replay ID, ZIP hash, and 60 Test Pending labels.
- `npm run build`: passed; produced the static site in `web/dist` after verifying the pinned snapshot.
- `git diff --check`: passed. Git emitted a line-ending notice for `web/README.md` and could not enumerate the existing `.pytest-tmp-handoff/` directory under the sandbox; neither changed the check result.
- Source scope: tracked changes are under `web/`; no tracked changes were made to Python `src/`, model configuration, logical-table contracts, or Stage 06 results.

## Browser checks

Checks used the Codex in-app browser's Playwright-backed page controls against the local static preview. The exact browser version is not exposed by the supported inspection API.

- **Routes and responsive layout:** all 8 routes loaded with the pinned IDs and `REVIEW READY` state at CSS viewport widths 360, 390, 430, 1280, and 1440 px (40 route/viewport pairs). No document-level horizontal overflow was found. Tables wider than mobile are inside horizontal-scroll containers.
- **Navigation and static paths:** desktop navigation opened Models; a nested `/qa-nested/#/guide` URL loaded and remained on Guide after reload.
- **Fail-closed behavior:** removing `evaluation.csv` produced “A required verified CSV is missing from the snapshot.” Changing a byte in `model_metrics.csv` produced “SHA-256 mismatch for model_metrics.csv.” Both cases rendered zero result rows and zero metric cards.
- **Overview:** showed B3 Test Macro MAE at 4.89%, B3-vs-B2 delta at 0.36%, and 2,916 evaluable out of 2,976 valid/expected forecasts with 60 Pending labels.
- **Pending:** filtered rows retained the forecast while Actual and Absolute error showed `—`; the exact “Not scored: target pending by cutoff” label appeared on the cells/status for keyboard and assistive-technology access.
- **Portfolio:** three range sliders and three numeric inputs stayed synchronized in both directions. Keyboard adjustment exposed visible focus. An invalid 101% total showed a no-result message and `—`; returning to 50/30/20 restored 8.13%, matching the stored row. Pure-function tests also reject negative, non-finite, non-unit-sum, malformed, and asymmetric inputs.
- **Drift and research:** ADWIN showed 0 recorded alerts and stated that no client-side alert rule is used. H1 remained Train-only; H2/H3 remained Test-only. IEF high-volatility rows showed `Insufficient Evidence (n=0)` and `—`, with no zero score. Source footers exposed filename, split, selection, N, units, and Evaluation ID.
- **Accessibility:** keyboard opening of the H1 chart's disclosure displayed the 752-row table alternative and retained visible focus. Controls have accessible names. This was a DOM/keyboard check, not a formal screen-reader audit.
- **Console:** no browser console errors were returned after the final static QA cases.

## P0 acceptance matrix

| Criterion | Result | Evidence / limit |
|---|---|---|
| AC-01 | Pass | Full pinned IDs are available on every route via accessible labels; short IDs are visible in the shared snapshot banner. |
| AC-02 | Pass | Missing and byte-tampered QA copies failed closed with no result rows/cards. |
| AC-03 | Pass | Overview showed B3 Test Macro MAE 4.89%; source-value rendering uses the stored metric. |
| AC-04 | Pass | H2/H3 effect, adjusted p, CI, paired N, decision, and method were displayed from source rows; no client bootstrap. |
| AC-05 | Pass | Source and Overview showed 2,976 valid/expected, 2,916 evaluable, and 60 Pending. |
| AC-06 | Pass | Pending Actual/error were blank and the required explanatory label was present. |
| AC-07 | Pass | Explicit 0 recorded alerts; no client-side alert rule. |
| AC-08 | Pass | IEF Test subset showed `Insufficient Evidence (n=0)` with no MAE/RMSE score. |
| AC-09 | Pass | Default 50/30/20 what-if equaled the stored 8.13%; exact parity is covered by a `1e-10` unit test. |
| AC-10 | Pass | Slider and numeric edits update a local pure function using the selected stored covariance row; identity remained pinned. |
| AC-11 | Pass | Invalid sum showed no result in the UI; unit tests cover negative, NaN, bad sum, and incomplete/malformed covariance inputs. |
| AC-12 | Pass | H1 is Train-only; H2/H3 are Test-only; no live-performance claim is shown. |
| AC-13 | Pass | 1280/1440 widths had no document overflow; desktop route navigation worked. |
| AC-14 | Pass | 360/390/430 widths had no document overflow; tables use horizontal scrolling and Portfolio exposes sliders. |
| AC-15 | Partial | Keyboard focus and chart-table alternatives were checked. A formal screen-reader audit was not performed. |
| AC-16 | Pass | Chart/table footers include source file, split, selection, N, units, and Evaluation ID. |
| AC-17 | Partial | Unit tests verify source CSV column names and the separate metadata schema/hash. Browser download contents were not independently verified; see limitation below. |
| AC-18 | Pass | Nested static path and hash-route reload worked. |
| AC-19 | Pass | Current tracked change list is confined to `web/`. |
| AC-20 | Pass | Shared banner says `REVIEW READY`; the page also keeps report approval `PENDING`, marks the data as non-live, and states the source-availability limitation. |

## Screenshots

- [Desktop Overview — 1440 px](../evidence/desktop-1440-overview.jpg)
- [Mobile Overview — 390 px](../evidence/mobile-390-overview.jpg)

These are full-page screenshots captured at 1440×1000 and 390×844 CSS-pixel viewports, respectively.

## Known limitations

- Browser download transport is not verified end-to-end. The export CSV and metadata builders are covered by unit tests and the UI provides separate buttons. An earlier CSV browser check created `filtered_forecasts.csv` in the user's Downloads folder; the in-app browser would not expose a reliable downloaded-file confirmation, and its internal Downloads page was blocked by browser policy. The metadata download was not independently confirmed.
- No standalone Playwright E2E dependency or checked-in browser test suite is present in `web/package.json`; the browser workflows above were exercised through the Playwright-backed in-app browser controls.
- Report approval remains pending, and the snapshot does not prove point-in-time availability of the market source data.
- No deployment, publish, push, PR, or merge was performed.
