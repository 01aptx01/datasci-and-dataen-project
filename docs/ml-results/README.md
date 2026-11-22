# DEDS ML Results Handoff

## Status

**SOURCE VERIFIED · REVIEW READY · REPORT APPROVAL PENDING**

This folder contains several immutable result generations. The reports and handoff listed below are the original Stage 06 review pack (Evaluation `82572c84…`, Replay `3cbf81eb…`); their IDs, numbers, and claims describe that frozen run only. The newer baseline and Champion ADWIN policy results are documented in [06_champion_adwin_only.md](06_champion_adwin_only.md): baseline Evaluation `12b9f92c…` / Replay `0f6dad49…`, and policy Evaluation `b2dfc853…` / Replay `77e80d8e…`. The dashboard uses the newer baseline with a separate policy sidecar, as pinned in [`web/snapshot.policy.json`](../../web/snapshot.policy.json).

The output folder named `approved_results` follows the implementation plan's directory name; it does not mean the report has been approved by the project owner. The original pack is ready for review, but has not been published to a team share.

The earlier [05_champion_challenger_policy.md](05_champion_challenger_policy.md) is another historical policy generation (policy Evaluation `f6dd8cb1…` against baseline `ae5cc8cc…`); it is distinct from the later policy Evaluation `b2dfc853…` now paired with the `12b9f92c…` dashboard baseline.

The project now includes an implemented read-only static dashboard in [`web/`](../../web/). [dashboard_data_requirements.md](dashboard_data_requirements.md) remains a design reference for data needs; it is not evidence that an API exists. The dashboard reads verified frozen snapshots and does not run the Python ML pipeline.

## Start here

1. Read the [experiment overview](01_experiment_overview.md), [model performance](02_model_performance.md), [H1–H3 results](03_hypotheses_h1_h3.md), [portfolio and drift report](04_portfolio_and_drift.md), and [data dictionary](05_data_dictionary.md).
2. Browse the [eight report figures](figures/); the charts are also embedded in the relevant report pages.
3. Use the read-only [review notebook](../../notebooks/03_ml_results_review.ipynb) for tables, figures, and explanations.
4. Download the [standalone offline HTML report](https://raw.githubusercontent.com/01aptx01/datasci-and-dataen-project/docs/ml-results-handoff/docs/ml-results/downloads/ml_results_review.html).
5. Download the [complete ZIP bundle](https://raw.githubusercontent.com/01aptx01/datasci-and-dataen-project/docs/ml-results-handoff/docs/ml-results/downloads/ml-results-handoff-82572c84.zip).
6. Verify the downloaded files with [SHA256SUMS.txt](downloads/SHA256SUMS.txt). After extracting the ZIP, verify its contents with [bundle-CHECKSUMS.sha256](downloads/bundle-CHECKSUMS.sha256).

The direct download URLs point to this branch and will work after the reviewed files are committed and pushed. GitHub can display the Markdown reports and figures directly from this folder. The original generated `dist/` directory remains local and ignored by Git.

## Frozen identity

The identity below belongs to the **original review pack**, not the newer dashboard snapshot.

| Item | Value |
|---|---|
| Evaluation ID | `82572c8417041976e1ce540d921e29a5f28c1d5d2a2d953a74c03582e7ca9be2` |
| Final Replay ID | `3cbf81eb9242d8894d2f67f39065a17ff1ef55a2e098773aead915949ab11b12` |
| Source status | Stage 06 and Stage 05 `COMPLETED`; output and lineage hashes verified |
| Baseline Git commit | `b0b0782ad426923f58814c5540fbb7f7e0abf887` |
| Assets / market | SPY, IEF, GLD / XNYS |
| Test / strict cutoff | 2025-10-01 through 2026-09-25 / 2026-09-25 |
| Unit | Annualized decimal unless a field says otherwise |

All model, hypothesis, and drift outputs in this handoff refer to this same Evaluation ID. The Final Replay ID identifies the predictions consumed by Stage 06.

## What is inside

- [01_experiment_overview.md](01_experiment_overview.md) — research question, scope, periods, target, and limitations.
- [02_model_performance.md](02_model_performance.md) — Test metrics, paired comparisons, coverage, and high-volatility subset.
- [03_hypotheses_h1_h3.md](03_hypotheses_h1_h3.md) — Stage 06 H1–H3 results and sensitivity outputs.
- [04_portfolio_and_drift.md](04_portfolio_and_drift.md) — the original pack's B3 ADWIN monitor and forecast-based portfolio risk; see `06_champion_adwin_only.md` for the later monitor design and run.
- [05_data_dictionary.md](05_data_dictionary.md) — key columns, units, statuses, and file groups.
- [verification_report.md](verification_report.md) — source, notebook, statistical, security, and packaging gates.
- [dashboard_data_requirements.md](dashboard_data_requirements.md) — dashboard data requirements retained as a design reference; the current static dashboard is documented in [`web/DASHBOARD_GUIDE.md`](../../web/DASHBOARD_GUIDE.md).
- [figures/](figures/) — eight figures generated from the frozen result files.
- [downloads/](downloads/) — shareable ZIP, standalone HTML report, and SHA-256 checksum files.

## Open the notebook

The notebook reads the bundled CSV and JSON files; it does not call ingestion, model fitting, prediction, replay, or hypothesis-testing code. From the repository, open it with the project's EDA environment. When using an extracted bundle, open `notebook/03_ml_results_review.ipynb`; if automatic discovery does not find `approved_results`, set `DEDS_RESULTS_DIR` to that folder.

For an isolated project environment, install the EDA dependency group with `uv sync --group eda`, then start Jupyter from that environment. Figures generated by a repository run go to `docs/ml-results/figures/`; figures generated from an extracted bundle go to `notebook_output/figures/` so the frozen files are not overwritten.

## How to verify the snapshot

- `source_identity.json` preserves the source Evaluation ID, Final Replay ID, Git/code/config identities, lineage, source hashes, exported hashes, counts, and limitations.
- The packaged `execution_manifest.json` and `stage05_experiment_manifest.json` have local absolute paths redacted. Their original source hashes are recorded in `source_identity.json`; the redacted copies have their own exported hashes.
- `CHECKSUMS.sha256` verifies every file as packaged, except itself.
- Original Stage 06 and Stage 05 artifact folders remain unchanged.

See the verification report for the H1 source working-tree caveat and the gates still awaiting peer review and an approved external file location.
