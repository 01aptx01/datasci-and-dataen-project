# D1–D2 Verification Record

**Checked:** 2026-11-21 (Asia/Bangkok)
**Scope:** Web shell and verified read-only handoff adapter only.

## Source and identity

- Repository: `01aptx01/datasci-and-dataen-project`.
- Local `main` at task start: `8a842bf373acf9b367e50280834c8ecb084d37b1`.
- Handoff commit: `f826e219330b53125282234858932ad4dace3374`; GitHub reports it merged to `main` by PR #11. The requested `docs/ml-results-handoff` branch no longer exists on GitHub, so the committed handoff bundle on `main` was used.
- Handoff archive: `docs/ml-results/downloads/ml-results-handoff-82572c84.zip`.
- Archive SHA-256: `20dff91705ffbb60ab579f5c1f907537015ec2f52be001d5dfd24ea8978ae3f5`.
- All 48 archive member checksums pass. The embedded and sidecar checksum manifests differ only in line-ending encoding; their parsed entries match.
- Evaluation ID: `82572c8417041976e1ce540d921e29a5f28c1d5d2a2d953a74c03582e7ca9be2`.
- Replay ID: `3cbf81eb9242d8894d2f67f39065a17ff1ef55a2e098773aead915949ab11b12`.
- Baseline commit: `b0b0782ad426923f58814c5540fbb7f7e0abf887`; strict cutoff: `2026-09-25`.
- Source identity is verified; Stage 05 and Stage 06 are marked completed. Point-in-time source availability is unverified and report approval remains pending. The dataset is identified as **Simulated Historical Replay**.

## Sources and schemas used

The adapter reads only selected JSON and CSV members from the checksum-verified ZIP:

- JSON: `source_identity.json`, `approved_results/execution_manifest.json`, `approved_results/stage05_experiment_manifest.json`.
- CSV: `approved_results/forecast_audit.csv`, `approved_results/evaluation.csv`.
- Contracts reviewed on `main`: `docs/contract/datadict.md` and `docs/contract/prediction_contract.md`.
- Exact CSV headers and pinned hashes are recorded in `web/snapshot.policy.json`.
- Runtime types and validators: `SnapshotPolicy`, `SnapshotManifest`, `ForecastAuditRow`, and `EvaluationRow` in `web/src/data/schemas.ts`.

The build publishes only `forecast_audit.csv`, `evaluation.csv`, and a generated `dashboard_snapshot_manifest.json` into the app's static snapshot folder. Model files, reports, notebooks, and the original ZIP are not published. The browser verifies CSV SHA-256 values again before parsing and joining on `prediction_id`; it does not recalculate stored predictions or evaluation metrics. Stage 06 serialized numeric differences are compared with a `1e-12` tolerance, while displayed actual/error values come from `evaluation.csv`.

## Frozen snapshot counts

| Set | Rows |
| --- | ---: |
| Forecast audit | 5,976 |
| Evaluation | 2,916 |
| Test forecasts | 2,976 |
| Test evaluable | 2,916 |
| Test Pending Labels | 60 |
| Saved Test dates in the default SPY/B3 session | 248 |

Pending rows remain unscored: actual RV5 and absolute error are blank in the source and rendered as em dashes. A Pending row with numeric values in either field is rejected.

## Commands and results

- `npm run build` — passed. ZIP identity, checksums, schemas, and IDs verified; TypeScript compiled; the verified allowlist is copied into `dist/snapshots/<evaluationId>/`.
- `npm test` — passed; typecheck and compile passed; **7/7** unit tests passed.
- Tests cover quoted CSV parsing, the real frozen snapshot, missing files, hash mismatch, Evaluation/Replay ID mismatch, and Pending-label integrity.
- Browser console errors: none observed.

## Browser review

- Desktop viewport: **1440 × 1000 CSS px**; no horizontal overflow.
- Mobile viewport: **390 × 844 CSS px**; no horizontal overflow. Bottom navigation shows Overview, Models, and Forecasts; More opens the remaining five sitemap links.
- All eight routes were opened through the UI and had the expected heading and title: Overview, Models, Forecasts, Portfolio, Drift, Research, Provenance, Guide.
- Verified Snapshot banner identifies the replay as historical and says it is not live data; the report-approval-pending status is visible.
- Forecasts stepper displays only saved Test rows. The last saved SPY/B3 observation (`2026-09-25`) is Pending, has a valid recorded forecast, and shows no actual or error value.
- Missing-snapshot UI was observed before the `dist` copy fix; after the fix, the same page loaded the verified frozen snapshot.

The desktop and mobile Overview screenshots, plus desktop and mobile Pending-session screenshots, were captured in the browser verification output. The connected browser surface returned them as transient images and did not provide a supported workspace-file export path, so `web/evidence/` contains no screenshot files.

## Git status and remaining scope

- No ML pipeline, data-contract, or Stage 06 files were changed. No training, `partial_fit`, replay, hypothesis inference, or Stage 06 result adjustment was run.
- The implementation is committed locally on `feat/dashboard-d1-d2`, based on `main` after PR #11 was merged. No push or merge was performed as part of this delivery. Generated `web/dist/` output and prepared `web/public/snapshots/` files remain excluded by `web/.gitignore`.
- D3–D5 analytics, charting, portfolio calculations, and drift/research views remain out of scope for this D1–D2 pass.
- Screenshot image files are the one delivery item not persisted in the workspace; the captured viewport images are available in this run's browser output.
