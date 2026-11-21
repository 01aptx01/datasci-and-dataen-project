# Verification Report

## Status

**SOURCE VERIFIED · REVIEW READY · NOT REPORT APPROVED**

The selected Stage 06 output and its Stage 03–05 lineage are checksum-verified. The notebook, figures, and offline HTML were generated from the exported snapshot. The final ZIP was extracted and checked. The pack is not yet Ready-to-share under the plan because peer review and an approved external file location are pending.

## Selected run and candidate audit

Three completed Stage 06 candidates were present. All recorded output checksums matched their files. The selection was not based on MAE, p-values, or preferred outcomes.

| Evaluation ID | Created (Asia/Bangkok) | Pipeline code SHA | Finding |
|---|---|---|---|
| `a6610dca95777615791b36a48d47900340b87831aa874033198c8e649aa5bcfa` | 2026-11-21 03:21 | `cf3ec543e927f08d89c345ea0b587e6a25f10a964d7ebd608d0a2e355268f232` | Completed; older code identity; H1 manifest absent from this output set. |
| `68f830701b11e168da3866a01ea9fbc4195e936714d3bbf59fb5b6bd21bb357b` | 2026-11-21 03:27 | `1e2e234cf482fd661761a01496fa8fc4fac30e87aae48e20c8935cdffd6e3adc` | Completed; older code identity. |
| `82572c8417041976e1ce540d921e29a5f28c1d5d2a2d953a74c03582e7ca9be2` | 2026-11-21 03:35 | `28de89a4376894b3dcc7cca0a53b0e653f7ef81857d84c11e4a449ce4dbd2cee` | Selected: latest completed candidate; all six recorded evaluation code hashes match the current baseline Git blobs and its evaluation/config identity reproduces. |

The selected candidate's H1 manifest records `working_tree_dirty: true` at H1 analysis time. The copied H1 outputs and their source hashes match the Stage 06 manifest, but the exact uncommitted H1 source-code state is not archived. This is disclosed as a reproducibility limitation.

## Gate results

| Gate | Result | Evidence |
|---|---|---|
| G1 — Provenance | PASS | Stage 06 `COMPLETED`; 25 Stage 06 output hashes match; Stage 05 `COMPLETED` and all linked output hashes match; Stage 03/04 source artifact hashes and Evaluation ID identity verified. |
| G2 — Reusable bundle | PASS | Final ZIP extracted to an isolated directory; all listed checksums matched and all relative Markdown links resolved. One evaluation, notebook, report, figures, and QA evidence are included. |
| G3 — Notebook | PASS | Restart/Run All completed from the extracted bundle using Python 3.10; all 11 code cells ran without notebook errors. No ingestion, fitting, prediction, replay, network, or hypothesis recomputation. |
| G4 — Figures | PASS | Eight PNGs generated from frozen result tables; the notebook regenerated all eight with byte-identical content. Filters, N, units, date windows, and caveats appear in captions and report. |
| G5 — Statistical integrity | PASS | H1–H3 values in this handoff match the Stage 06 CSV outputs; H1 is Train-only and H2/H3 are paired Test-only. |
| G6 — Security and size | PASS | No drive-absolute paths remain in JSON deliverables; HTML assets are embedded; no checkpoints, source-data snapshot, or credential files are included. The 49-file ZIP is under 5 MB; the QA JSON records the size gate. |
| G7 — Team usability | REVIEW PENDING | The offline HTML and portable pack are ready for a reviewer, but no peer review or external team-share URL has been completed. |
| G8 — Git scope | PASS | Diff is confined to the local `dist/` ignore rule, handoff exporter/test, review notebook, handoff docs, and eight generated PNG figures. No ML pipeline, contract, config, or source-data files changed. |

## Data checks

- Test: 744 eligible ETF/date anchors × four models = 2,976 expected prediction rows.
- Valid forecasts: 2,976; mature/evaluable rows: 2,916; Pending labels: 60; forecast exceptions: 0.
- Common B0–B3 paired panel: 729 ETF/date anchors, 243 per ETF.
- H1 Train N: 752 per ETF.
- H2/H3 Test paired N: 729 each.
- ADWIN alerts: 0 across 729 Test common-panel error observations.
- ONLINE_SGD Test portfolio risk: 248 complete-input dates; all rows `OK`.

## Tests and reproduction

- Full project tests: `python -m pytest -q --basetemp <writable-temp> -p no:cacheprovider` — **207 passed in 190.67 seconds** using the project Python 3.10 environment.
- Handoff exporter tests: **5 passed in 0.49 seconds**, including changed-source rejection, Replay identity mismatch, no-overwrite behavior, and nested drive/UNC/POSIX path redaction.
- Notebook command from the extracted bundle: `python -m jupyter nbconvert --to html --template basic --execute --no-input --embed-images --ExecutePreprocessor.timeout=600 --ExecutePreprocessor.kernel_name=deds-handoff-py310 notebook/03_ml_results_review.ipynb --output ml_results_review.html --output-dir report`.
- The standalone HTML has eight embedded PNGs, no external script, stylesheet, image, or iframe assets, and alternative text for every chart.
- `CHECKSUMS.sha256` covers every file in the portable bundle except itself; ZIP extraction, checksum verification, and relative Markdown link checks passed.
- On this restricted Windows host, Jupyter required a dedicated local runtime directory and `JUPYTER_ALLOW_INSECURE_WRITES=1` for its temporary kernel connection file. It emitted an event-loop compatibility warning, but nbconvert exited successfully and every cell executed. These settings were process-local and did not change project files.
- Source result files were only read; the exporter refuses to overwrite an existing destination and never changes the input artifact directories.
- The diff was reviewed after packaging; `dist/` is ignored so local CSV bundles and ZIPs are not accidentally committed.
