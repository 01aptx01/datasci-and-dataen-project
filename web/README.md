# DEDS Adaptive Portfolio Risk Lab — frozen snapshot dashboard

This folder contains the read-only Adaptive Portfolio Risk Lab, backed by the pinned Stage 06 B4 review snapshot. It includes saved-session Replay, B0–B4 evidence views, Drift review, and covariance-based portfolio analysis. It does not import or run the Python ML pipeline.

## Run locally

Requirements: Node.js (verified with v25) and Python 3.10+. The only frontend development dependency is TypeScript; the built dashboard has no runtime npm dependencies.

```powershell
cd web
npm install
npm run build
npm test
npm run preview
```

Open `http://localhost:4173` to use the dashboard. `npm run dev` builds the verified static snapshot and starts the local preview server. Build output and extracted public snapshot files are ignored by Git and can be reproduced from the pinned handoff ZIP and checksum manifests.

## Snapshot boundary

`../scripts/web/prepare_snapshot.py` checks the pinned outer ZIP digest, verifies the internal and sidecar checksums, checks archived member hashes and Evaluation/Replay IDs, validates source headers, row relationships, and counts, then copies only the allowlisted files. The browser verifies the snapshot hashes and reconciles B4 paired comparisons against the evaluation rows before parsing the rest of the sources.

The snapshot includes forecast audit, evaluations, model metrics, pair comparisons, B4 retrospective comparisons, B0–B3 reference metrics, coverage, portfolio risk, rolling MAE, drift timeline, H1 evidence, hypothesis results, bootstrap diagnostics, and high-volatility metrics. Pending forecast rows preserve blank actual and absolute-error values.

The frozen evaluation is a **Simulated Historical Replay** with strict cutoff `2026-09-25`. Point-in-time source availability is unverified and report approval is pending. The Evidence view displays both pinned IDs, the cutoff, and the snapshot limitations.

The browser only calculates portfolio what-if volatility from the covariance matrix stored with the selected date/model row. It does not run training, replay, forecast, drift, or hypothesis inference.

## Routes and presentation link

The dashboard includes portfolio, replay, forecast, model comparison, monitoring, and evidence views. Portfolio risk uses `sqrt(wᵀΣw)` with the recorded covariance; Replay reveals an Actual only when the target has matured, its verified evaluation exists, and the user requests it. Source Pending rows remain hidden.

The Canva Presentation button is disabled until a URL is set. To enable it, set `CANVA_PRESENTATION_URL` in `src/config.ts` to the presentation URL and rebuild; it then opens in a new tab.

## Source pins

- Handoff: `docs/ml-results/downloads/b4/ml-results-handoff-b4-ae5cc8cc.zip`, SHA-256 `4a471c360aeb28d7cc6b817600e32c2ee877a557c44043d75bc2bf1fde07c43c`.
- Handoff commit: `175db305f39a9fa19fb4ba3cdb47bed037d26abb`.
- Frozen Evaluation ID: `ae5cc8cc1cc6a1245ed7a0c789037c9545614868023e67f9b0bfbf84ee594e1b`.
- Frozen Replay ID: `23616e7bab42de22ca0bb3153dfec8b695ea1d51ff9ad816bd02e14f849acfe6`.
- Source members and hashes are pinned in `snapshot.policy.json` and summarized in the generated snapshot manifest.
- Main contracts reviewed: `docs/contract/datadict.md` and `docs/contract/prediction_contract.md`.

## Static hosting

Build `web/dist` and publish its contents beneath a directory with an `index.html` entry point. Relative asset and snapshot URLs support nested paths; no deployment is performed by these scripts.

## Verification

`npm test` verifies the B4 snapshot checksums and identity, source schemas and paired comparisons, Pending labels, portfolio covariance calculations, and replay gating. Visual and browser-flow evidence is in [the Stitch verification report](evidence/stitch/VERIFICATION.md).
