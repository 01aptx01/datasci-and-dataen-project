# DEDS Adaptive Portfolio Risk Lab — Dashboard Guide

This guide covers the read-only Adaptive Portfolio Risk Lab in this directory. The browser reads verified, saved snapshots; it does not fetch market data, train models, generate forecasts, or run statistical inference.

## Run locally

Use the project’s supported Python version, **3.10**, as recorded in `.python-version`, `pyproject.toml`, and `uv.lock`. The build scripts also run Python code from the repository, so install and activate the project environment before running npm commands. Node.js 25 was used for verification; the project has no declared Node engine range.

From the repository root, install Python dependencies, then activate that environment and install the locked web dependencies:

```powershell
uv sync
.venv\Scripts\Activate.ps1
cd web
npm ci
npm run build
npm test
npm run preview
```

On macOS or Linux, activate with `source .venv/bin/activate`. Open `http://localhost:4173` after `npm run preview`. `npm run dev` builds the verified static snapshot and starts the preview server. `npm ci` uses the checked-in `package-lock.json`.

Build output, extracted snapshot files, and generated diagnostic packages are ignored by Git. A fresh checkout has no local `data/` run artifacts; the dashboard’s pinned handoff bundle is tracked, while the optional Feature Drift diagnostic sidecar is published only when its verified source artifact is available locally.

## What the dashboard shows

The dashboard presents saved portfolio risk, forecasts and replay, model comparisons, monitoring, research evidence, provenance, and a user guide. See the [dashboard user guide](../docs/dashboard/USER_GUIDE.md) for the main workflows. Replay displays recorded forecasts. It reveals an Actual only when the target is mature, an eligible saved evaluation exists, and the selected as-of/reveal rules allow it. Pending source rows stay hidden.

Portfolio what-if risk uses `sqrt(wᵀΣw)` with the covariance matrix stored for the selected date and model. Changing weights does not change forecasts. The Monitoring view separates Feature Drift (W1/PSI) from the exploratory Champion–Challenger policy’s Champion-error ADWIN stream and recorded decisions. These views show historical diagnostics; they are not live monitoring.

The browser does not calculate or publish a B3-only ADWIN drift timeline. That stream belonged to an older handoff and was retired. The current policy sidecar stores the Champion detector stream and policy decision events separately from the baseline Stage 06 evaluation.

## Pinned evidence

The runtime source of truth is [`snapshot.policy.json`](snapshot.policy.json). It pins the baseline handoff, validates the outer ZIP and member checksums, checks Evaluation/Replay identity, validates schemas and row relationships, and copies only allowlisted browser files. The browser verifies those published files before parsing them and reconciles B4 comparisons against evaluation rows.

The current baseline snapshot is:

- Handoff: `docs/ml-results/downloads/no-b3-adwin/ml-results-handoff-no-b3-adwin-12b9f92c.zip`
- Handoff SHA-256: `a9bc4b5e2de0e93faf475c3810eea49e720cb56e9bb10fa41e8cd3f96c5063ad`
- Handoff commit: `8dab4b8b2b8589054669294ddf1848ffaed7c8f3`
- Evaluation ID: `12b9f92cbdcbb7816a767f8565bb004f3243b114480e5f3f316c497af4014e76`
- Replay ID: `0f6dad49e04b684df6d32d7abca7738fa8c06774c5e848476b62e8fa46a2c99a`
- Strict cutoff: `2026-09-25`; report approval: pending

The baseline includes B0–B4 evaluation evidence. The older B4 review handoff (`ae5cc8cc…`) and earlier baseline handoff (`82572c84…`) remain archived evidence; they are not the bundle selected by the current runtime policy.

The exploratory Champion–Challenger policy is a separate sidecar:

- Policy Evaluation ID: `b2dfc853a4c9c2eba4d99c91360abd39d9226c157b26bc5509d7977cd43e9d9e`
- Policy Replay Experiment ID: `77e80d8ec871dddcdc50fc617662eb60269b6b2333e913238d58a18b6da91b35`
- Handoff: `docs/ml-results/downloads/policy/ml-results-policy-b2dfc853.zip`
- Handoff SHA-256: `43ae02ffc90c18575b51af5eef0b5e652aa8e02b54fdbd980f07caeba7203bbe`

The policy replay uses the Test period previously inspected and is exploratory. Its recorded absence of alerts does not establish that drift was absent. Historical availability of source data at each simulated date is unverified. See [`06_champion_adwin_only.md`](../docs/ml-results/06_champion_adwin_only.md) for the baseline and policy evidence, methods, and limitations.

## Presentation link

The Canva Presentation button stays disabled until a URL is set. To enable it, set `CANVA_PRESENTATION_URL` in `src/config.ts` and rebuild.

## Static hosting

Build `web/dist` and publish its contents under a directory with `index.html` as its entry point. Relative asset and snapshot URLs support nested paths. The repository scripts build and preview the dashboard; they do not deploy it.

## Verification

Run `npm test` to verify snapshot preparation and checksums, TypeScript types, static copying, Pending-label handling, portfolio covariance calculations, B4 comparisons, and Replay gating. Historical visual and browser-flow evidence is in [the Stitch verification report](evidence/stitch/VERIFICATION.md); its screenshots and claims refer to the earlier pinned snapshot documented there.
