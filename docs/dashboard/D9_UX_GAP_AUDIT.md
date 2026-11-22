# D9 Financial Decision Lab Gap Audit

**Date:** 2026-11-21 (Asia/Bangkok)
**Audited base:** `main` at `617bfd6` (D8 merge)
**Working branch:** `feat/dashboard-ux-integration-d8-d9`, created locally from that base
**Scope:** Existing `/portfolio` page, D8 selection contract, snapshot schema/adapter, quantitative source contract, and baseline tests.

This records the local pre-D9 implementation baseline. The attached v1.1 plan is treated as product and numerical requirements. Its referenced parent `DEDS_D9_Financial_Portfolio_Decision_Lab_Implementation_Plan_v1.0.md` is not present in the current working tree; its numerical constraints are also directly specified in v1.1 and checked against the available Python math contract and frozen snapshot.

## Local source and baseline evidence

- D8 shared query contract: `web/src/data/selection.ts`; app shell and Portfolio route: `web/src/app.ts`.
- Portfolio calculation: `web/src/data/portfolio.ts`; source parsing and validation: `web/src/data/schemas.ts`, `web/src/data/loadSnapshot.ts`.
- Quantitative contract: `src/ml_evaluation/portfolio.py`; verified frozen input: `portfolio_risk.csv` in the snapshot named by Evaluation ID `82572c8417041976e1ce540d921e29a5f28c1d5d2a2d953a74c03582e7ca9be2`.
- Baseline `npm test` on the new branch: snapshot identity and checksums verified; TypeScript typecheck/compile/static build passed; **39/39 tests passed**.
- The local Stage 06 file contains **1,992** portfolio rows, including **992 Test** rows; every Test row is `OK` and correlation-ready, with **248** rows per model.
- Independent parity check across all 992 Test rows: default 50/30/20 volatility exactly matched `portfolio_vol_annualized` (`max absolute error = 0`); covariance reconstructed from the three stored forecasts and stored 20-session correlations matched the stored covariance (`max absolute element error ≈ 6.94e-18`); no Test correlation matrix violated the `-1e-10` PSD tolerance.
- Python source math uses weight-sum tolerance `1e-8`, correlation symmetry tolerance `1e-12`, and minimum correlation eigenvalue `-1e-10`.

## Reuse / extend decisions

| Area | Current local behavior | Decision |
|---|---|---|
| Route and shared session | `/portfolio` reads D8's exact date/model/split/identity selection and returns to Replay with that selection. The selected ticker is context; source portfolio rows contain all three ETFs. | **REUSE + EXTEND**; retain the single route and D8 contract. |
| Portfolio what-if | Exact Test row covariance, four source/derived result cards, three forecast cards, correlation values derived from covariance, sliders/numeric inputs, and saved presets. | **REUSE + EXTEND**; retain local `sqrt(wᵀΣw)` calculation and presets; add dated risk history, same-day comparison, signed contributions, Scenario A/B, and user budget. |
| Snapshot adapter | Parses the three forecasts/statuses, stored covariance, status, weights, input IDs, and missing inputs. It currently discards `corr_spy_ief_20d`, `corr_spy_gld_20d`, `corr_ief_gld_20d`, `is_corr_ready`, and `correlation_run_id` despite those fields being present in the exact checked-in source header. | **EXTEND** the typed source row and preserve/validate these fields before rendering a heatmap. |
| Risk presentation | No date-based risk timeline, prior-comparable KPI, contribution breakdown, correlation matrix view, budget, or deterministic decision narrative. | **ADD** the D9-U1–U5 work packages on `/portfolio`; keep the experience read-only and source-bound. |
| Tests and data | Existing tests cover one stored portfolio parity fixture, weight validation, malformed covariance, and snapshot integrity. | **EXTEND** with all-row parity, contribution conservation/sign/zero, URL state validation, budget counts, and source-gap/As-of series tests. |

## Scope boundaries

- Do not create a second app or a new top-level route.
- Use the exact row for the selected date/model; preserve missing-input reasons and allow a user-selected eligible date rather than silently substituting one.
- The `portfolio_risk.csv` 20-session correlation fields are the displayed correlation source; derived correlation from covariance is not a substitute for those source fields.
- Historical chart points remain five-session Forward RV5 portfolio-volatility estimates, not one-day risk, realized portfolio volatility, returns, P&L, or current-market advice.
- User-defined budget has no default. Weight changes remain client-only calculations against stored same-day covariance.
- Optional allocation-risk simplex map is outside the essential D9-U1–U5 scope.

## Implementation and verification update

The local `/portfolio` route now hosts the D9 Risk Center, Risk Drivers, and Scenario Lab using the shared D8 selection. D9 scenario state is validated and serialized with the existing selection URL. The UI uses the exact selected date/model covariance, preserves the source correlation fields, reports signed risk contributions, compares fixed A/B weights over the same historical rows, and supports an explicitly user-entered risk budget. Trust & Methods exposes source identity, model context, strict cutoff, PIT limitation, formulas, and links back to Replay and evidence pages.

The optional D9-U6 allocation simplex is deferred; it is P1 in the plan and is not required for the core D9-U1–U5 workflow.

### Acceptance evidence

| Criteria | Evidence / status |
|---|---|
| D9U-01–06 | Baseline audit completed. Route keeps one shared D8 selection, all three ETF inputs, exact-date/model row validation, and matching-model covariance. Browser flow confirmed selection context and return route. |
| D9U-07 | All eligible Test rows reproduce stored default risk and covariance source math; automated test passed. |
| D9U-08–10 | Invalid weights and covariance fail closed; contribution signs and zero-risk guard tested. |
| D9U-11–12 | Correlation table renders stored `corr_*_20d`; same-day A/B comparison uses percentage-point deltas. Source values and delta units tested in the renderer. |
| D9U-13–15 | Scenario A/B timelines recalculate with each date's same-model covariance; invalid source rows break segments. Prior comparable date and gap count are named. Tests cover gap and prior-date behavior. |
| D9U-16–18 | Budget is blank by default, uses annualized decimal internally, counts valid dates only, and labels As-of versus Retrospective. Browser reload retained the entered threshold and selected view. |
| D9U-19–23 | Source IDs, target horizon, unit, cutoff, PIT status and model Test metrics are visible. Copy and labels avoid return/P&L, advice, causality, and optimization claims. The app performs no fit or external market-data request. |
| D9U-24–26 | Browser review covered desktop plus 390/360px layouts, route/query restoration, scenario edits, budget, source correlations, and same-session Replay navigation. The latest Scenario Lab render showed both timeline lines and synchronized number/slider controls; keyboard slider input produced an explicit 101% validation state without changing the saved URL scenario. `npm test` passed 58/58, including snapshot verification, typecheck, compile, and static build. |

### Source-verified demo

`D9_DEMO_EVIDENCE.md` records the selected B3 Test row, source IDs, exact default-risk parity, illustrative 60/20/20 result, and interpretation limits. The selected date is 2026-09-25; no live/current-market value is presented.

### Remaining scope

- The v1.0 parent D9 plan referenced by v1.1 is absent from this checkout. Numerical and QA contracts used here are explicit in v1.1 and cross-checked against `src/ml_evaluation/portfolio.py` and the frozen snapshot.
- The optional allocation map remains deferred.
- Browser screenshots were reviewed in the local CUA session but are not committed as project artifacts. All Git changes remain local; no push, merge, publication, or deployment was performed.
