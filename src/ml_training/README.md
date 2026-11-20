# ML Training and Validation

Stage 04 consumes the in-memory `PreparedDataset` from Stage 03 and its label
table. It fits B0–B3 per ETF, evaluates the locked 27 SGD configurations per
ETF on Validation, and creates clean B2/B3 initial pairs using the selected
configuration. It does not run the Final Replay, ADWIN, Test evaluation, or
write to a logical data table.

```python
from src.ml_dataset import load_validated_inputs, prepare_ml_dataset
from src.ml_training import run_training_selection

inputs = load_validated_inputs(...)
prepared = prepare_ml_dataset(inputs)
result = run_training_selection(
    prepared,
    inputs.labels,
    artifact_dir="data/processed/ml_training/run-<unique-id>",
)
```

The output directory must be new. It contains the 81 Validation trial rows,
the selected configuration per ETF, the clean initial model/scaler bundle, a
copy of the effective config, and a manifest with source lineage, package
versions, state hashes, and checksums. Artifacts are staged in the destination
parent and exposed by one final directory rename.

## Training and selection rules

- B0 is the mean of eligible, fixed-purge-clean Train labels for its ETF.
- B1 predicts with that date's `rv_20d` feature.
- `RobustScaler` is fit separately for each ETF, using only fixed-purge-clean
  Train rows, then remains frozen.
- B2 and B3 are independent estimator copies from the same fitted state.
  B2 stays frozen; B3 updates once per session from labels mature on that
  session, after the day's forecasts are recorded. Fitted Train keys seed the
  update ledger; later-maturing Train rows purged at the fixed boundary may
  still update B3.
- A candidate is selectable only when B2 and B3 both produce valid forecasts
  for every expected fixed-purge-clean Validation anchor. Invalid predictions
  remain visible in the audit and are never clipped or silently omitted.
- Select one candidate per ETF by the mean of B2 and B3 Validation MAE. Scores
  within absolute tolerance `1e-12` tie; the first candidate in configured
  grid order wins. If an ETF has no fully covered candidate, selection fails
  with an explicit error instead of selecting on reduced coverage.
- Validation trials use only Train and Validation anchors. Test rows and
  labels do not enter scaler fitting, model fitting, online updates, or
  selection. Historical source availability is simulated using mature labels
  and `target_end_date <= replay_date`; the source snapshot does not prove
  point-in-time availability.

## Interface

`run_training_selection(prepared, labels, artifact_dir=...)` returns the trial
table, selected configurations, fresh initial model pairs, B0/B1 baseline
metadata, and manifest. `evaluate_candidate(...)` exposes one candidate's
Validation forecast rows and online update events for focused verification.
