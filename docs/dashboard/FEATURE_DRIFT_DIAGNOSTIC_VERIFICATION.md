# Feature Drift Diagnostic Verification

**Status:** implemented and locally verified
**Branch:** `feature/feature-drift-diagnostic`
**Base:** `feature/portfolio-web-redesign` at `220066d65af0973c6a9ad570b175a891d7e16ed6`
**Scope:** read-only diagnostic and dashboard integration; no Stage 01–06 result was rewritten.

## Source identity and evidence

The diagnostic is pinned to the frozen Stage 06 Evaluation `82572c8417041976e1ce540d921e29a5f28c1d5d2a2d953a74c03582e7ca9be2`, Replay `3cbf81eb9242d8894d2f67f39065a17ff1ef55a2e098773aead915949ab11b12`, and cutoff `2026-09-25`. The frozen handoff ZIP SHA-256 is `20dff91705ffbb60ab579f5c1f907537015ec2f52be001d5dfd24ea8978ae3f5`.

| Input | Verified identity |
|---|---|
| Feature run | `feat_readiness_20261115_01`, feature set `2.0.0`; Parquet SHA-256 `973eeeb1ddee1953728f6b0a496ba5e3a045cbcfa61037983ce5f95dcaf0166d` |
| Target run | `target_integration_20261118_04`; Parquet SHA-256 `f4affff83e801476039fb60c1ef853db5451ef356066365534efcf5a35c14c49` |
| Stage 03 | `stage03_h1_20261120_01`; report and lineage verified |
| Stage 04 | `stage04_20261121_03`; training run `f130ea25-4763-4dc7-a5f0-b72ca9cb4f46` |
| Stage 06 | Pinned Evaluation/Replay above; source lineage agrees with the frozen handoff |

Each ETF has 1,255 eligible feature rows: 752 Train, 245 Validation, and 243 model-eligible Test rows. The calculation separately follows 248 Test XNYS feature sessions through the cutoff, so a feature diagnostic may exist even when a corresponding forecast label is pending. The Core 8 feature rows reconcile to the frozen Stage 04 training reference. Stage 03 quality passed with three feature-quality findings and no quarantined rows. Historical availability at each original observation date is **not verified**.

## Locked diagnostic contract

- Calculate each of the eight Core Features separately for SPY, IEF, and GLD; never pool ETF distributions.
- Use exactly the model-eligible Train rows as the fixed reference. Use Validation only to calibrate per-ETF/per-feature thresholds; Test never tunes a threshold.
- Compute trailing 60-session windows as the primary view and 120 sessions as a separate sensitivity view. Windows end on the selected XNYS date and include no later feature row. Missing sessions are not filled; incomplete windows cannot receive a signal.
- Primary metric: 1D Wasserstein distance divided by the fixed Train IQR. Secondary metric: PSI using ten Train-derived quantile bins and 0.5 Jeffreys smoothing on both distributions. Validation thresholds use the linear 95th percentile; each ticker/feature/window series has 250 calibration windows, above the configured minimum of 100.
- `DRIFT_SIGNAL` / `NO_SIGNAL` status is based on normalized W1 only. PSI has its own displayed value and threshold. Neither threshold is a significance test.
- Future-label maturity, prediction error, ADWIN, forecasts, portfolio calculations, and H1–H3 are separate from this calculation.

The implementation and pinned configuration are in `src/ml_diagnostics/` and `config/feature_drift.yaml`. The dashboard validates the independent sidecar before display; it does not recalculate metrics in JavaScript.

## Generated local diagnostic

The reproducible output is ignored under `data/processed/feature_drift/` and was not committed. Two runs produced the same identity and package checksum.

| Artifact | Value |
|---|---|
| Diagnostic ID | `fca7560f77d0ea22075d9bf4eaecc3d9c28428a90b915183b36d1cd66e171952` |
| Package SHA-256 | `c8dced2cc4dbf8392de61ff769ec46f4b22047c56fb076f20a10c2bf48ac764a` |
| Test metric rows | 11,904 |
| Test histogram rows | 119,040 |
| Test statuses | 6,414 `DRIFT_SIGNAL`; 5,490 `NO_SIGNAL`; 0 incomplete windows |
| Calibration groups | 48 (24 ETF × feature streams × two window sizes) |

The build publishes only the checksum-verified, allowlisted browser files to `web/dist/feature-drift/current/`. Corrupted packages, changed source lineage, mismatched snapshot identity, unsupported scope, bad counts, or inconsistent histogram proportions fail closed. The separate generated package remains outside the repository by default.

## Dashboard and browser verification

- Replay shows the selected date and ETF, three highest relative changes, per-metric values and thresholds, and a Monitoring link that carries the same date, ETF, model, and selected feature. A B0/B1 selection explicitly describes Core 8 as input-feature context used by B2/B3.
- Monitoring links back to the same Replay context. Browser Back returned to IEF on `2026-09-23` with B0 context intact.
- W1 and PSI selection updates the trend and URL; the selected-date marker follows the selected record. Missing metric values split chart paths. Only the selected/first valid chart point is in the Tab order; the date control remains available for exact date selection.
- Keyboard Home/End switches the Feature Drift and Error Drift tabs and moves focus to the selected tab. Error Drift retains the original Rolling MAE20 / recorded ADWIN evidence, including the recorded zero-alert context.
- Browser layout checks at 360, 390, 430, 1280, and 1440 CSS pixels found no document-width overflow. At mobile widths the 620px feature table scrolls within its own wrapper, and the selection toolbar is not sticky. At desktop width 1280, the five controls remain sticky below the application header while scrolling.
- Replay, Monitoring, PSI, error-tab, model-context, and browser-back behavior were inspected in the local browser.

## Checks run

| Check | Result |
|---|---|
| `.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q` | 216 passed |
| `npm run test` in `web/` | 36 passed; includes TypeScript typecheck, build, static snapshot verification, sidecar publication and dashboard tests |
| Repeat diagnostic generation | Same Diagnostic ID and package SHA-256 on both runs |
| Sidecar tamper and identity tests | Rejected as expected |
| `git diff --cached --check` | Passed on staged changes before the documentation commit |

## Limits and interpretation

This is a **simulated historical analysis**, not prospective monitoring: point-in-time availability of downloaded source data has not been independently verified. A marginal feature-distribution shift does not establish concept drift, causality, future performance degradation, or a forecastable volatility event. Overlapping windows and the 24 Core Feature streams are correlated; reported status is a heuristic diagnostic. No feature-to-error association panel was added, because the plan marked it optional and keeping Feature Drift separate from ADWIN avoids suggesting a causal relationship.

The local browser preview did not retain a requested 1920px viewport, and actual browser zoom at 200% was not verified. The 360–1440px checks, mobile table interaction, and desktop sticky controls were verified as described above. Browser accessibility behavior for reduced-motion settings was not separately audited.

## Three-minute walkthrough

1. In Replay, choose SPY, a recorded Test date, and B3. Read the matching Feature Drift summary without revealing a pending Actual.
2. Open Monitoring. Confirm the same date and ETF, inspect normalized W1 against the Validation threshold, then choose PSI to compare its independent threshold.
3. Compare Train and selected-window histogram bars. Explain that this measures distribution change only.
4. Switch to Error Drift and show the recorded Rolling MAE20 / ADWIN evidence separately; do not infer causality or a prospective warning.
