# Daily ML Replay

Stage 05 consumes a Stage 03 `PreparedDataset`, the Stage 03 label frame, and a
checksum-verified Stage 04 training artifact. It runs B0–B3 in chronological
XNYS order and preserves the locked Validation-to-Test state transition.

```python
from src.ml_dataset import load_validated_inputs, prepare_ml_dataset
from src.ml_replay import run_final_replay

inputs = load_validated_inputs(...)
prepared = prepare_ml_dataset(inputs)
result = run_final_replay(
    prepared,
    inputs.labels,
    initial_model_artifact_dir="data/processed/ml_training/run-<id>",
    output_root="data/processed/ml_replay",
)
```

By default the replay runs from `2024-10-01` through the strict cutoff
`2026-09-25`. `replay_end_date` can bound an acceptance or diagnostic run; the
experiment manifest records whether that run covers the strict cutoff. Use the
default end date for the final study. `stop_after_session` makes
a committed partial run that can later be resumed with `resume=True`.
`failure_injector` is a test hook for simulating an interruption between daily
stages.

## Daily order and saved state

Each XNYS session runs:

1. Predict with pre-update state and stage immutable B0–B3 forecasts.
2. Evaluate only forecasts whose valid five-session label has
   `target_end_date <= replay_date`.
3. Feed each mature B3 absolute error to that ETF's ADWIN monitor once.
4. Call B3 `partial_fit` once per ETF for the deterministic batch of newly
   mature eligible labels. B2 stays frozen and the RobustScaler stays frozen.
5. Save the post-update model, detector, ledgers, and session outputs in one
   checksummed daily directory, then atomically rename it into `committed/`.

The commit marker is trusted only when its manifest and every listed file pass
SHA-256 validation. Resume restores the latest compatible committed state;
uncommitted staging directories are ignored. A checkpoint includes the full
pending forecast set, updated-label and processed-error ledgers, River ADWIN
state, B3 state, frozen scaler, and hashes of the unchanged Stage 04 B2 states.

## Files

Each experiment is stored under
`<output_root>/experiments/<experiment_id>/`:

- `experiment_manifest.json` records the source snapshot, selected parameters,
  code and dependency versions, IDs, replay window, and the historical
  point-in-time limitation.
- `checkpoints/committed/<session>/` stores that session's immutable outputs,
  checkpoint, hashes, manifest, and `COMMITTED` marker.
- `outputs/asset_volatility_predictions.csv` retains the exact existing
  16-column prediction schema.
- `outputs/evaluation.csv` contains only successfully matched mature-label
  evaluations. Drift errors/alerts, B3 update rows, failures, and coverage are
  separate supporting files; they do not create logical tables.

Forecasts with negative, NaN, or infinite values are rejected and recorded in
the failure and coverage outputs. ADWIN is monitor-only: an alert never resets,
re-trains, or retunes a model. The historical replay simulates label
availability from maturity and `target_end_date`; the later-downloaded source
snapshot does not prove point-in-time source availability.
