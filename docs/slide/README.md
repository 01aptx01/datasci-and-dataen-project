# Adaptive Portfolio Risk Lab — presentation

Run the local slide website:

```powershell
npm.cmd install
npm.cmd run dev
```

Open <http://localhost:3000/>. The site loads the frozen Test data automatically on slides 7, 9, 12, and 13. No API key is needed to view the slides. The CSV upload controls can still be used to inspect another handoff export.

Bundled data in `public/data/` comes from `../ml-results/downloads/ml-results-handoff-82572c84.zip`. It contains 2,976 Test forecasts, 248 Test dates of `ONLINE_SGD` portfolio risk, 729 Test drift observations, and 2,256 H1 Train scatter points. `public/data/source.json` records the source archive SHA-256 and row counts. To regenerate these CSVs from the original handoff archive, run:

```powershell
python scripts/import_handoff.py
```

The data is a historical replay through 25 September 2026, not a live market feed.
