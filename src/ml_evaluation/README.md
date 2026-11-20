# ML Final Evaluation and Portfolio Risk

Stage 06 evaluates the immutable predictions from one completed Stage 05 Final Replay. It does not retrain models, change predictions, select on Test, or add a logical data table.

## Run

From the repository root, after Stage 03, Stage 04, and Stage 05 artifacts are available at the paths in `config/ml_evaluation.yaml`:

```powershell
.venv\Scripts\python.exe -m src.ml_evaluation.run --config config/ml_evaluation.yaml
```

The configuration locks the XNYS split dates, strict cutoff, B0-B3 identities, eight core features, Train P80 high-volatility threshold, 20-session rolling window, H1-H3 settings, and default portfolio weights. The paths section binds a run to the current local Stage 03-05 artifacts; update the run-specific paths when upstream artifacts are regenerated.

`rolling_minimum_evaluable: 10` and `minimum_pairs_per_ticker: 30` are explicit implementation details because the approved design leaves these gates configurable. Fewer than 30 paired observations for any ETF yields `Insufficient Evidence` for H2/H3. Rolling diagnostics are omitted until at least 10 of the 20 XNYS sessions have mature, evaluable errors.

## Integrity and scoring

- Validate Stage 03 Parquet inputs against their manifests and publish transactions, then cross-check lineage against the Final Replay.
- Verify checksums and locked metadata for Final Replay outputs, Stage 04 selected artifacts, and Stage 03 H1 evidence. Verify the saved Replay evaluations against independently joined Labels and immutable Predictions.
- Use only Test anchors from 2025-10-01 through 2026-09-25 for final Test metrics. Pending labels remain visible in coverage and do not count as forecast failures.
- Report B0-B3 metrics on their common mature/evaluable Test panel, and report pair-specific B3 comparisons using only matching date/ticker rows. Macro metrics give equal weight to each ETF.
- Set each ETF's High-Vol threshold from eligible, purge-clean Train labels only. Keep monthly and yearly metrics split-separated. Rolling metrics use fixed XNYS-session windows.
- Reconcile B3's Test ADWIN error stream one-to-one with its mature/evaluable Test predictions. ADWIN remains a monitor; alerts do not change model state or scores.
- Compute forecast-based portfolio risk for each model/date from all three forecasts and same-date 20-session correlations. Invalid, incomplete, or non-PSD inputs produce `INCOMPLETE_INPUTS`. Default weights are 50/30/20; the pure risk consumer accepts different valid weights without loading or retraining a model.
- Reuse the Stage 03 H1 Train-only OLS/HAC/Holm results. Run H2/H3 on paired Final Test errors using the locked synchronized block bootstrap and Holm correction. Test results do not tune models, thresholds, or analysis settings.

The replay is a **Simulated Historical Replay**. Its source snapshot was downloaded after the historical dates, so point-in-time source availability is not claimed. Outputs describe the fixed snapshot and do not establish prospective performance or causality.

## Outputs

The output root receives a new content-addressed evaluation directory; an existing matching directory is checksum-verified and returned unchanged. A different result is never written over an existing directory.

- `evaluation.csv`, `forecast_audit.csv`, `forecast_exceptions.csv`, and `coverage.csv`
- `model_metrics.csv`, `pair_comparisons.csv`, and `high_volatility_metrics.csv`
- `monthly_metrics.csv`, `yearly_metrics.csv`, and `rolling_mae20.csv`
- `drift_error_timeline.csv` and `portfolio_risk.csv`
- `hypotheses_plan.json`, `hypothesis_results.csv`, and `bootstrap_diagnostics.csv`
- Copied H1 results, Train audit, sensitivity output, specification, and plot evidence
- `evaluation_summary.md` and `execution_manifest.json` with lineage, software versions, counts, and output checksums

Generated data remain under the ignored `data/processed/ml_evaluation/` tree and are not committed.
