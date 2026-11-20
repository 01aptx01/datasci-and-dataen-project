# ML Dataset Preparation

This package prepares the Stage 03 in-memory Prediction and Supervised views. It does not train models, fit a scaler, or write a derived Parquet table.

## Load and prepare the current tables

```python
from src.ml_dataset import DatasetConfig, load_validated_inputs, prepare_ml_dataset

config = DatasetConfig.from_yaml("config/ml_dataset.yaml")
inputs = load_validated_inputs(
    "data/curated/asset_volatility_features.parquet",
    "data/curated/asset_volatility_labels.parquet",
    "data/audit/features/run_id=<feature-run>/manifest.json",
    "data/audit/targets/run_id=<target-run>/manifest.json",
    "data/audit/features/run_id=<feature-run>/publish-transaction.json",
    "data/audit/targets/run_id=<target-run>/publish-transaction.json",
)
prepared = prepare_ml_dataset(inputs, config=config)

prediction_X = prepared.prediction.X
supervised_X = prepared.supervised.X
supervised_y = prepared.supervised.y
preparation_report = prepared.report.to_dict()

```

The loader binds each Parquet to its committed publish transaction, checks the checksum and schema, and verifies that both tables came from the same source input and declared source batch. Duplicate `(date, ticker)` keys and mismatched target windows or lineage fail explicitly.

## Eligibility and replay

- Prediction rows require an in-study anchor, a ready non-warm-up feature row, and finite values for the eight Core Features. A missing or pending label does not remove a Prediction row.
- Supervised rows additionally require a mature, validated five-observation label available by the effective as-of date. Train and Validation labels are purged when `target_end_date >=` the next split start.
- `replay_date` can be passed to `prepare_ml_dataset` to simulate an earlier replay. A backfilled label is unavailable until its `target_end_date <= replay_date`.
- `prepared.audit` records split membership, exclusions, fixed purge, and separate online-update eligibility. The update ledger can be passed as `(date, ticker)` keys to prevent duplicate B3 update candidates.
- The replay is simulated from a later-downloaded historical snapshot. It does not prove that the source was available on each historical date; the report records this limitation.
