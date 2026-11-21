# 01 — Experiment Overview

## Research question

For SPY, IEF, and GLD, how accurately do the approved baseline, static, and online models forecast Forward RV5, and does ONLINE_SGD improve paired Test MAE over STATIC_SGD and the rolling baseline?

The target is realized volatility over the next five XNYS trading sessions, expressed as an annualized decimal. It is a volatility forecast, not a return forecast.

## Models and inputs

| ID | Contract name | Role |
|---|---|---|
| B0 | `CONSTANT_BASELINE` | Per-ETF constant reference based on the Train target mean. |
| B1 | `ROLLING_20D_BASELINE` | Rolling 20-session realized-volatility reference. |
| B2 | `STATIC_SGD` | Train-fitted SGD model with Train-only, frozen RobustScaler. |
| B3 | `ONLINE_SGD` | Starts from the same initial state and selected ETF hyperparameters as B2; updates only when labels mature and without duplicate updates. |

B2/B3 use the eight contracted features: `ret_1d_t`, `ret_lag_1d`, `ret_lag_2d`, `ret_trailing_5d`, `ret_trailing_20d`, `rv_5d`, `rv_20d`, and `rv_60d`.

## Fixed periods

| Split | Prediction dates |
|---|---|
| Train | 2021-09-27 to 2024-09-30 |
| Validation | 2024-10-01 to 2025-09-30 |
| Test | 2025-10-01 to 2026-09-25 |
| Strict data cutoff | 2026-09-25 |

H1 is Train-only. H2/H3 and the primary model comparison are Test-only. Test results were not used for feature, hyperparameter, threshold, or method selection. Macro metrics weight the three ETFs equally; the 50/30/20 portfolio weights are used only in the separate portfolio diagnostic.

## Replay and source vintage

The Test forecasts come from Final Replay `3cbf81eb9242d8894d2f67f39065a17ff1ef55a2e098773aead915949ab11b12`. The replay follows the contracted Predict → Save → Evaluate → ADWIN → Update → Checkpoint order; B3 updates only with mature labels. ADWIN is monitor-only.

This is **Simulated Historical Replay** on a historical snapshot downloaded after the observation period. The run uses the contracted target-maturity and data-validation rules, but historical point-in-time source availability is not verified. The results describe this frozen snapshot and protocol; they do not establish live future performance or causality.

## Identity

- Evaluation ID: `82572c8417041976e1ce540d921e29a5f28c1d5d2a2d953a74c03582e7ca9be2`
- Final Replay ID: `3cbf81eb9242d8894d2f67f39065a17ff1ef55a2e098773aead915949ab11b12`
- Baseline Git commit: `b0b0782ad426923f58814c5540fbb7f7e0abf887`
- Source status: Stage 06 and Stage 05 completed; source hashes verified.

All reported volatility and error values remain annualized decimals. Percent formatting belongs in the presentation layer only.
