# Future Dashboard Data Requirements

Preparation only. This document does not define or implement an API, server, or dashboard. The Stage 06 artifacts remain the source of truth; a future UI must not change metrics or recalculate hypothesis decisions.

## Required views and source data

| View | Source files | Useful fields |
|---|---|---|
| Model comparison | `model_metrics.csv`, `pair_comparisons.csv` | `split`, `ticker`, `model_name`, `paired_n`, `mae`, `rmse`, `delta_mae_baseline_minus_online`, `relative_improvement_pct` |
| Forecast vs actual | `evaluation.csv`, `forecast_audit.csv` | `prediction_date`, `ticker`, `model_name`, `predicted_vol_annualized`, `target_realized_vol_5d`, `absolute_error`, `label_status`, `evaluation_status` |
| Coverage | `coverage.csv`, `forecast_audit.csv`, `forecast_exceptions.csv` | expected forecasts, valid/invalid/missing forecasts, mature, Pending, and evaluable counts |
| Temporal error / ADWIN | `rolling_mae20.csv`, `drift_error_timeline.csv` | `window_end`, `mae`, `absolute_error_adwin`, `drift_detected`, `adwin_delta`, `adwin_width` |
| H1–H3 evidence | `H1_results.csv`, `H1_sensitivity.csv`, `hypothesis_results.csv`, `bootstrap_diagnostics.csv` | N, effect, raw/adjusted p, confidence interval, method, split, decision |
| High-volatility view | `high_volatility_metrics.csv` | Train P80 threshold, Test subset count, MAE/RMSE, coverage |
| Portfolio-risk diagnostic | `portfolio_risk.csv` | prediction date, model, weights, portfolio volatility, input status, correlations |

## Filters and display conventions

- Default split: Test for model comparison; provide Validation and Train only where the source table supports them.
- Default assets: SPY, IEF, GLD. Treat `MACRO` as the equal-weight ETF aggregate provided in metric outputs, not as an asset.
- Model names must retain the contracted identities B0–B3.
- Volatility, MAE, RMSE, and DeltaMAE are annualized decimal values in stored files. Any percentage formatting is display-only and must be labeled.
- Keep Pending labels separate from forecast failures. Do not score a Pending label or silently drop it from coverage.
- Show `Insufficient Evidence` when a subset has no usable rows, such as IEF Test observations above its Train P80 threshold.
- Display evaluation and replay IDs with exported plots and tables so views cannot silently mix runs.
- Preserve H1 Train-only and H2/H3 paired Test-only scope. Render the Stage 06 p-values, intervals, methods, and decisions as provided.
- ADWIN is monitor-only; an alert is a signal for review, not an automatic retraining instruction or proof of drift.
- Portfolio volatility is a forecast-based risk diagnostic, not a return or investment-performance metric.

## Ownership boundary

Future presentation layers may filter and format the frozen artifacts. They must not retrain models, alter replay state, tune on Test, recompute p-values/intervals, or override the Stage 06 source outputs.
