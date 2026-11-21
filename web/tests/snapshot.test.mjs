import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { parseCsv } from "../dist/assets/data/csv.js";
import { loadSnapshot, verifySnapshotFileBytes, requireSnapshotFiles, parseModelMetrics, parseForecastAudit, parsePortfolioRisk, parseRollingMae20, parseDriftTimeline, parseH1Scatter, parseH1Results, parseH1Sensitivity, parseHypothesisResults, parseBootstrapDiagnostics, parseHighVolatilityMetrics } from "../dist/assets/data/loadSnapshot.js";
import { computePortfolioVolatility } from "../dist/assets/data/portfolio.js";
import { parseForecastAuditRow, parsePolicy, parseSnapshotManifest } from "../dist/assets/data/schemas.js";
const schemas = await import("../dist/assets/data/schemas.js");
const selectors = await import("../dist/assets/data/loadSnapshot.js");

const policy = parsePolicy(JSON.parse(await readFile(new URL("../snapshot.policy.json", import.meta.url), "utf8")));
const snapshotDirectory = new URL(`../public/snapshots/${policy.identity.evaluationId}/`, import.meta.url);
const manifestJson = JSON.parse(await readFile(new URL("dashboard_snapshot_manifest.json", snapshotDirectory), "utf8"));
const manifest = parseSnapshotManifest(manifestJson, policy);
const staticSnapshotDirectory = new URL(`../dist/snapshots/${policy.identity.evaluationId}/`, import.meta.url);
const auditBytes = new Uint8Array(await readFile(new URL(manifest.files.forecastAudit.path, snapshotDirectory)));
const evaluationBytes = new Uint8Array(await readFile(new URL(manifest.files.evaluation.path, snapshotDirectory)));
const modelMetricsBytes = new Uint8Array(await readFile(new URL(manifest.files.modelMetrics.path, snapshotDirectory)));
const pairComparisonsBytes = new Uint8Array(await readFile(new URL(manifest.files.pairComparisons.path, snapshotDirectory)));
const coverageBytes = new Uint8Array(await readFile(new URL(manifest.files.coverage.path, snapshotDirectory)));
const sourceBytes = Object.fromEntries(await Promise.all(Object.entries(manifest.files).map(async ([key, artifact]) => [artifact.path, new Uint8Array(await readFile(new URL(artifact.path, snapshotDirectory)))])));
const auditText = new TextDecoder().decode(auditBytes);
const evaluationText = new TextDecoder().decode(evaluationBytes);

test("CSV parser preserves quoted commas, escaped quotes, and newlines", () => {
  const table = parseCsv('name,note\r\nSPY,"close,\"\"adjusted\"\"\r\nvalue"\r\n');
  assert.deepEqual(table.headers, ["name", "note"]);
  assert.equal(table.records[0].note, 'close,"adjusted"\r\nvalue');
});

test("verified snapshot files match the pinned SHA-256 values", async () => {
  await verifySnapshotFileBytes(manifest, policy, {
    ...sourceBytes,
  });
});

test("static build publishes every verified CSV listed in its manifest", async () => {
  for (const artifact of Object.values(manifest.files)) {
    const bytes = await readFile(new URL(artifact.path, staticSnapshotDirectory));
    assert.equal(bytes.byteLength, artifact.bytes, `${artifact.path} must be present in dist`);
  }
});

test("the real frozen snapshot loads into typed Test sessions with Pending labels retained", async () => {
  const files = new Map([
    ["snapshot.policy.json", new TextEncoder().encode(JSON.stringify(JSON.parse(await readFile(new URL("../snapshot.policy.json", import.meta.url), "utf8"))))],
    [`snapshots/${policy.identity.evaluationId}/dashboard_snapshot_manifest.json`, new TextEncoder().encode(JSON.stringify(manifestJson))],
    ...Object.entries(sourceBytes).map(([path, bytes]) => [`snapshots/${policy.identity.evaluationId}/${path}`, bytes]),
  ]);
  const fakeFetch = async (input) => {
    const key = new URL(String(input)).pathname.replace(/^\//, "");
    const bytes = files.get(key);
    return bytes ? new Response(bytes, { status: 200 }) : new Response("missing", { status: 404 });
  };
  const loaded = await loadSnapshot(fakeFetch, "http://localhost:4173/");
  assert.equal(loaded.status, "ready");
  if (loaded.status !== "ready") return;
  assert.equal(loaded.sessions.length, policy.expectedCounts.testForecastRows);
  assert.equal(loaded.manifest.expectedCounts.testPendingRows, 60);
  assert.equal(loaded.evaluations.size, policy.expectedCounts.testEvaluableRows);
  assert.equal(loaded.modelMetrics.length, policy.expectedCounts.modelMetricsRows);
  assert.equal(loaded.pairComparisons.length, policy.expectedCounts.pairComparisonsRows);
  assert.equal(loaded.coverage.length, policy.expectedCounts.coverageRows);
  assert.equal(loaded.portfolioRisk.length, policy.expectedCounts.portfolioRiskRows);
  assert.equal(loaded.rollingMae20.length, policy.expectedCounts.rollingMae20Rows);
  assert.equal(loaded.driftTimeline.length, policy.expectedCounts.driftErrorTimelineRows);
  assert.equal(loaded.h1Scatter.length, policy.expectedCounts.h1ScatterDataRows);
  assert.equal(loaded.hypothesisResults.length, policy.expectedCounts.hypothesisResultsRows);
  assert.equal(loaded.highVolatilityMetrics.length, policy.expectedCounts.highVolatilityMetricsRows);
  assert.equal(loaded.modelMetrics.find((row) => row.ticker === "MACRO" && row.modelName === "ONLINE_SGD")?.mae, 0.04889242199324919);
  assert.equal(loaded.coverage.find((row) => row.split === "test" && row.ticker === "SPY" && row.modelName === "ONLINE_SGD")?.pendingLabelCount, 5);
  assert.equal(loaded.forecasts.length, 5976);
  assert.ok(loaded.sessions.some((row) => row.evaluationStatus === "PENDING_LABEL" && row.targetRealizedVol5d === null && row.absoluteError === null));
});

test("missing required CSV files fail closed", () => {
  assert.throws(
    () => requireSnapshotFiles({}, [manifest.files.forecastAudit.path, manifest.files.evaluation.path, manifest.files.modelMetrics.path]),
    /Required snapshot file missing/,
  );
});

test("a changed CSV byte fails the pinned hash check", async () => {
  const changed = new Uint8Array(auditBytes);
  changed[100] ^= 1;
  await assert.rejects(
    verifySnapshotFileBytes(manifest, policy, {
      ...sourceBytes,
      [manifest.files.forecastAudit.path]: changed,
    }),
    /SHA-256 mismatch/,
  );
});

test("an Evaluation ID or Replay ID mismatch is rejected", () => {
  assert.throws(
    () => parseSnapshotManifest({ ...manifestJson, evaluationId: "another-evaluation" }, policy),
    /evaluationId does not match/,
  );
  assert.throws(
    () => parseSnapshotManifest({ ...manifestJson, replayId: "another-replay" }, policy),
    /replayId does not match/,
  );
});

test("Pending rows preserve blank actual/error values and reject scored Pending values", () => {
  const pendingRecord = parseCsv(auditText).records.find((row) => row.split === "test" && row.evaluation_status === "PENDING_LABEL");
  const matureEvaluation = parseCsv(evaluationText).records[0];
  assert.ok(pendingRecord);
  assert.equal(pendingRecord.target_realized_vol_5d, "");
  assert.equal(pendingRecord.absolute_error, "");
  const pending = parseForecastAuditRow(pendingRecord);
  assert.equal(pending.targetRealizedVol5d, null);
  assert.equal(pending.absoluteError, null);

  assert.throws(
    () => parseForecastAuditRow({
      ...pendingRecord,
      target_realized_vol_5d: matureEvaluation.target_realized_vol_5d,
      absolute_error: matureEvaluation.absolute_error,
    }),
    /must not contain actual or error values/,
  );
});

test("model metric rows preserve source Macro scores and reject non-Test data", () => {
  assert.equal(typeof schemas.parseModelMetricRow, "function", "model_metrics.csv needs a typed row parser");
  const parsed = schemas.parseModelMetricRow({
    split: "test",
    ticker: "MACRO",
    model_name: "ONLINE_SGD",
    paired_n: "729",
    expected_eligible_anchor_count: "744",
    mae: "0.04889242199324919",
    rmse: "0.09340334361276692",
    comparison_panel: "equal ETF weight; common B0-B3 matured valid anchors",
  });
  assert.equal(parsed.ticker, "MACRO");
  assert.equal(parsed.mae, 0.04889242199324919);
  assert.equal(parsed.pairedN, 729);
  assert.throws(() => schemas.parseModelMetricRow({
    split: "validation", ticker: "MACRO", model_name: "ONLINE_SGD", paired_n: "729",
    expected_eligible_anchor_count: "744", mae: "0.048", rmse: "0.09", comparison_panel: "panel",
  }), /Test-only/);
});

test("coverage rows keep Pending labels separate from forecast failures", () => {
  assert.equal(typeof schemas.parseCoverageRow, "function", "coverage.csv needs a typed row parser");
  const parsed = schemas.parseCoverageRow({
    split: "test", ticker: "SPY", model_name: "ONLINE_SGD",
    expected_eligible_prediction_anchors: "248", forecast_success_count: "248",
    invalid_forecast_count: "0", missing_forecast_count: "0", mature_target_count: "243",
    pending_label_count: "5", invalid_or_missing_target_count: "0", mature_evaluable_count: "243",
    common_panel_count: "243", forecast_coverage: "1", evaluation_coverage: "0.97983870967741937",
  });
  assert.equal(parsed.pendingLabelCount, 5);
  assert.equal(parsed.forecastSuccessCount, 248);
  assert.throws(() => schemas.parseCoverageRow({
    split: "test", ticker: "SPY", model_name: "ONLINE_SGD",
    expected_eligible_prediction_anchors: "248", forecast_success_count: "243",
    invalid_forecast_count: "0", missing_forecast_count: "0", mature_target_count: "243",
    pending_label_count: "5", invalid_or_missing_target_count: "0", mature_evaluable_count: "243",
    common_panel_count: "243", forecast_coverage: "1", evaluation_coverage: "0.97983870967741937",
  }), /counts do not reconcile/);
});

test("model metric parser rejects a changed source header", () => {
  assert.throws(
    () => parseModelMetrics("wrong_header\nvalue\n", policy),
    /header does not match the pinned handoff schema/,
  );
});

test("forecast filters keep Pending rows unscored and honor selected Test dates", () => {
  assert.equal(typeof selectors.filterForecastRows, "function", "forecast explorer needs a typed row filter");
  const rows = parseForecastAudit(auditText, policy);
  const pending = selectors.filterForecastRows(rows, {
    split: "test", ticker: "SPY", models: ["ONLINE_SGD"], status: "pending", from: "2026-09-22", to: "2026-09-25",
  });
  assert.equal(pending.length, 4);
  assert.ok(pending.every((row) => row.evaluationStatus === "PENDING_LABEL" && row.targetRealizedVol5d === null && row.absoluteError === null));
});

test("D4–D5 sources keep frozen counts, splits, and source covariance parity", async () => {
  const sourceText = (key) => new TextDecoder().decode(sourceBytes[manifest.files[key].path]);
  const portfolio = parsePortfolioRisk(sourceText("portfolioRisk"), policy);
  const rolling = parseRollingMae20(sourceText("rollingMae20"), policy);
  const drift = parseDriftTimeline(sourceText("driftErrorTimeline"), policy);
  const scatter = parseH1Scatter(sourceText("h1ScatterData"), policy);
  const h1 = parseH1Results(sourceText("h1Results"), policy);
  const sensitivity = parseH1Sensitivity(sourceText("h1Sensitivity"), policy);
  const hypotheses = parseHypothesisResults(sourceText("hypothesisResults"), policy);
  const bootstrap = parseBootstrapDiagnostics(sourceText("bootstrapDiagnostics"), policy);
  const highVol = parseHighVolatilityMetrics(sourceText("highVolatilityMetrics"), policy);

  const selected = portfolio.find((row) => row.split === "test" && row.predictionDate === policy.identity.strictCutoff && row.modelName === "ONLINE_SGD");
  assert.ok(selected?.covariance);
  assert.equal(selected?.portfolioVol, 0.08127699795391094);
  assert.ok(Math.abs(computePortfolioVolatility(selected.covariance, selected.sourceWeights) - selected.portfolioVol) < 1e-10);
  assert.ok(rolling.every((row) => row.windowSessionCount === 20));
  assert.ok(drift.every((row) => !row.driftDetected && !row.alertRecordPresent));
  assert.ok(scatter.every((row) => row.split === "train"));
  assert.deepEqual(h1.map((row) => row.hacLag), [5, 5, 5]);
  assert.ok(sensitivity.some((row) => row.hacMaxlags === 10));
  assert.ok(hypotheses.filter((row) => row.hypothesisId === "H1").every((row) => row.datasetSplit === "train"));
  assert.ok(hypotheses.filter((row) => row.hypothesisId !== "H1").every((row) => row.datasetSplit === "test" && row.tickerOrMacro === "MACRO"));
  assert.equal(bootstrap.length, 4);
  assert.ok(highVol.filter((row) => row.split === "test" && row.ticker === "IEF").every((row) => row.highVolCommonEvaluableN === 0 && row.mae === null && row.rmse === null));
});

test("D4–D5 row parsers reject malformed nested JSON, Test H1 points, and scored zero-sample rows", () => {
  const portfolioRecord = parseCsv(new TextDecoder().decode(sourceBytes[manifest.files.portfolioRisk.path])).records[0];
  assert.throws(() => schemas.parsePortfolioRiskRow({ ...portfolioRecord, covariance_matrix: "{" }), /valid JSON/);
  const scatterRecord = parseCsv(new TextDecoder().decode(sourceBytes[manifest.files.h1ScatterData.path])).records[0];
  assert.throws(() => schemas.parseH1ScatterRow({ ...scatterRecord, split: "test" }), /Train-only/);
  const highVolRecord = parseCsv(new TextDecoder().decode(sourceBytes[manifest.files.highVolatilityMetrics.path])).records.find((row) => row.ticker === "IEF" && row.split === "test");
  assert.ok(highVolRecord);
  assert.throws(() => schemas.parseHighVolatilityMetricRow({ ...highVolRecord, mae: "0", rmse: "0", evaluation_coverage: "0" }), /inconsistent with subset size/);
});
