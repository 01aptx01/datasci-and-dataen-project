# 05 — Data Dictionary

## Shared result file groups

| File group | Files | Purpose |
|---|---|---|
| Run identity | `execution_manifest.json`, `stage05_experiment_manifest.json`, `source_identity.json` | Run IDs, status, lineage, config/code identities, source and export hashes. The packaged Stage 05/06 manifests have local absolute paths redacted; original hashes are recorded separately. |
| Model metrics | `model_metrics.csv`, `pair_comparisons.csv`, `high_volatility_metrics.csv` | Split-specific error metrics, paired B3 comparisons, and Train-P80 Test subset. |
| Hypotheses | `H1_results.csv`, `H1_sensitivity.csv`, `H1_scatter_data.csv`, `H1_hypothesis_spec.json`, `hypotheses_plan.json`, `hypothesis_results.csv`, `bootstrap_diagnostics.csv` | H1 Train evidence, H2/H3 Test evidence, and planned sensitivity settings. |
| Coverage / forecasts | `coverage.csv`, `forecast_audit.csv`, `forecast_exceptions.csv`, `evaluation.csv` | Forecast validity, label maturity, pending/evaluable status, and mature paired Test actuals/predictions. |
| Time series | `monthly_metrics.csv`, `yearly_metrics.csv`, `rolling_mae20.csv`, `drift_error_timeline.csv` | Temporal scores and ONLINE_SGD ADWIN error observations. |
| Portfolio | `portfolio_risk.csv` | Forecast-based annualized portfolio-volatility diagnostic and input covariance. |
| Summary | `evaluation_summary.md` | Stage 06 source narrative. |

Other small Stage 06 H1 audit/report files are included unchanged in `approved_results/` for traceability.

## Key fields

| Field | Meaning / unit |
|---|---|
| `evaluation_id` | Identity for this frozen Stage 06 result set. |
| `experiment_id` | Final Replay ID on evaluation rows. It is distinct from the Evaluation ID. |
| `prediction_date` | XNYS session on which the forecast is anchored. |
| `target_start_date`, `target_end_date` | Start/end of the five-session Forward RV5 target window. |
| `split` | `train`, `validation`, or `test`; do not combine splits when reporting results. |
| `ticker` | `SPY`, `IEF`, or `GLD`; `MACRO` is an equal-weight aggregate in metric outputs. |
| `model_name` | Contracted B0–B3 model identity. |
| `target_realized_vol_5d`, `predicted_vol_annualized` | Actual Forward RV5 and forecast, annualized decimal. |
| `absolute_error`, `mae`, `rmse`, `delta_mae_baseline_minus_online`, `effect_size` | Error/effect quantities in annualized-decimal units, except squared error. Positive DeltaMAE means B3 has lower paired absolute error. |
| `raw_p_value`, `adjusted_p_value` | Stage 06 one-sided test p-values; H1 and H2/H3 use their separately specified Holm families. |
| `confidence_interval_95` | Stage 06 two-sided 95% interval. It is not a probability that the null is true. |
| `label_status` | Target status such as `MATURE` or `PENDING`. |
| `forecast_status` | Forecast validity, such as `VALID`; this is distinct from label maturity. |
| `evaluation_status` | Whether the forecast/target pair is `EVALUABLE` or still Pending. |
| `drift_detected` | ADWIN alert flag for the corresponding B3 error observation. ADWIN is monitor-only. |
| `portfolio_vol_annualized` | Forecast-based portfolio volatility, annualized decimal; not a return. |
| `covariance_matrix` | Covariance input used by the portfolio formula; entries are squared annualized-decimal units. |

## Coverage and filtering rules

- `evaluation.csv` contains mature, evaluable Test rows only; the Test file has 2,916 rows.
- `forecast_audit.csv` retains all 2,976 Test prediction rows, including 60 `PENDING_LABEL` rows.
- `forecast_exceptions.csv` is empty in this run; it is retained so the absence of exceptions is auditable.
- Pending labels are not forecast failures and do not receive an error score.
- H1 outputs use Train only. H2/H3 outputs use paired Test rows only.
- Raw stored volatility values use decimal units. Multiply by 100 only in a presentation layer that labels the resulting scale clearly.
