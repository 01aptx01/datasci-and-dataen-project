# Champion ADWIN replay after retiring B3 monitors

This exploratory simulated historical replay uses only one Champion-error ADWIN per ETF. Baseline Replay no longer creates `drift_errors.csv` or `drift_alerts.csv`; the policy records observations and decisions in `policy_detector_stream.csv` and `policy_decision_events.csv`. Historical source availability at each past date is not verified, and Test has previously been inspected.

- Code revision used for export: `8dab4b8b2b8589054669294ddf1848ffaed7c8f3`.
- Training: `data/processed/ml_training/run_id=stage04_no_b3_adwin_20261123`, from source feature run `feat_20261122T143142_ad87117a` and target run `target_20261122T143149_c9b24e99`.
- Baseline replay: `0f6dad49e04b684df6d32d7abca7738fa8c06774c5e848476b62e8fa46a2c99a` (config 1.1.0, checkpoint 1.1.0).
- Champion policy replay: `77e80d8ec871dddcdc50fc617662eb60269b6b2333e913238d58a18b6da91b35` (config 2.1.0, checkpoint 2.2.0). The final checkpoint contains exactly three policy detectors, one each for SPY, IEF and GLD, and no B3 detector state.
- Baseline evaluation: `12b9f92cbdcbb7816a767f8565bb004f3243b114480e5f3f316c497af4014e76` (Stage 06 schema 1.1.0); baseline dashboard snapshot schema 1.2.0.
- Policy evaluation: `b2dfc853a4c9c2eba4d99c91360abd39d9226c157b26bc5509d7977cd43e9d9e`.
- Feature Drift diagnostic: `d8a8a5be19e30ba0128d9b658022bc621bb31bd33de641b8cb8db634a8ec501a`, 11,904 Test metric rows, package SHA-256 `b20499dc4dce5661c0a1f64a482663ce30953e6ad78cefbe961ac234a756cc4f`.
- Baseline handoff: [ZIP](downloads/no-b3-adwin/ml-results-handoff-no-b3-adwin-12b9f92c.zip), SHA-256 `a9bc4b5e2de0e93faf475c3810eea49e720cb56e9bb10fa41e8cd3f96c5063ad`; policy handoff: [ZIP](downloads/policy/ml-results-policy-b2dfc853.zip), SHA-256 `43ae02ffc90c18575b51af5eef0b5e652aa8e02b54fdbd980f07caeba7203bbe`.

The Test replay spans 2025-10-01 through 2026-09-25. B2 remains initial and final Champion for each ETF. Each policy detector received 243 mature errors, with zero alerts and zero switches. The five final pending labels per ETF are not scored. Promotion behaviour is exercised with synthetic tests; this replay provides no real alert or switching event.

Verification includes the full replay suite (24 passed), training/config/evaluation/export tests, checksum and schema checks for new and archived snapshots, and browser inspection of Monitoring and Replay. The new web snapshot uses only Champion policy ADWIN; historical bundles remain unchanged as archived evidence.
