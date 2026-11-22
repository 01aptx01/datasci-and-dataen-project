import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const { parseB4ComparisonRow, parsePortfolioRiskRow, modelId, modelLabel } = await import("../dist/assets/data/schemas.js");
const { selectSameDateForecasts } = await import("../dist/assets/data/replay.js");
const { loadSnapshot, filterForecastRows } = await import("../dist/assets/data/loadSnapshot.js");

test("B4 model identity, label, and same-date ordering B0 through B4", () => {
  assert.equal(modelId("HAR_X_OLS"), "B4");
  assert.equal(modelLabel("HAR_X_OLS"), "HAR-X (OLS)");
  const rows = [
    { split: "test", ticker: "SPY", predictionDate: "2026-09-25", modelName: "HAR_X_OLS" },
    { split: "test", ticker: "SPY", predictionDate: "2026-09-25", modelName: "CONSTANT_BASELINE" },
    { split: "test", ticker: "SPY", predictionDate: "2026-09-25", modelName: "ONLINE_SGD" },
  ];
  const ordered = selectSameDateForecasts(rows, "SPY", "2026-09-25");
  assert.deepEqual(ordered.map((r) => r.modelName), ["CONSTANT_BASELINE", "ONLINE_SGD", "HAR_X_OLS"]);
});

test("parseB4ComparisonRow validates retrospective B4 comparison schema", () => {
  const row = parseB4ComparisonRow({
    comparison_id: "B4_VS_B2",
    b4_model: "HAR_X_OLS",
    comparator_model: "STATIC_SGD",
    ticker: "MACRO",
    paired_n: "729",
    expected_eligible_anchor_count: "744",
    paired_coverage: "0.9798387096774194",
    b4_mae: "0.05106473680481121",
    comparator_mae: "0.052479297060196384",
    delta_mae_comparator_minus_b4: "0.0014145602553851788",
    relative_improvement_pct: "2.6954634201037551",
    b4_rmse: "",
    comparator_rmse: "",
    common_all_five_n: "729",
    common_b0_b3_n: "729",
    split: "test",
    direction_definition: "comparator_mae_minus_b4_mae (positive means HAR_X_OLS lower error)",
    evaluation_scope: "retrospective_test_non_hypothesis",
    pairing_policy: "equal ETF weight over per-ETF paired anchors",
  });
  assert.equal(row.comparisonId, "B4_VS_B2");
  assert.equal(row.b4Rmse, null);
  assert.equal(row.pairedN, 729);
  assert.throws(() => parseB4ComparisonRow({
    comparison_id: "B4_VS_B2", b4_model: "HAR_X_OLS", comparator_model: "ONLINE_SGD", split: "test",
    ticker: "MACRO", paired_n: "729", expected_eligible_anchor_count: "744", paired_coverage: "0.9798387096774194",
    b4_mae: "0.05106473680481121", comparator_mae: "0.052479297060196384", delta_mae_comparator_minus_b4: "0.0014145602553851788",
    relative_improvement_pct: "2.6954634201037551", b4_rmse: "", comparator_rmse: "", common_all_five_n: "729", common_b0_b3_n: "729",
    direction_definition: "comparator_mae_minus_b4_mae (positive means HAR_X_OLS lower error)",
    evaluation_scope: "retrospective_test_non_hypothesis", pairing_policy: "equal ETF weight over per-ETF paired anchors",
  }), /identity does not match/);
  assert.throws(() => parseB4ComparisonRow({
    comparison_id: "B4_VS_B2", b4_model: "HAR_X_OLS", comparator_model: "STATIC_SGD", split: "test",
    ticker: "MACRO", paired_n: "729", expected_eligible_anchor_count: "744", paired_coverage: "0.9798387096774194",
    b4_mae: "0.05106473680481121", comparator_mae: "0.052479297060196384", delta_mae_comparator_minus_b4: "0.01",
    relative_improvement_pct: "2.6954634201037551", b4_rmse: "", comparator_rmse: "", common_all_five_n: "729", common_b0_b3_n: "729",
    direction_definition: "comparator_mae_minus_b4_mae (positive means HAR_X_OLS lower error)",
    evaluation_scope: "retrospective_test_non_hypothesis", pairing_policy: "equal ETF weight over per-ETF paired anchors",
  }), /DeltaMAE does not match/);
});

test("B4 1.1.0 snapshot loads all 5 models, pending rows, and B4 comparisons", async () => {
  const policyText = await readFile(path.join(webDir, "snapshot.policy.json"), "utf8");
  const evalId = JSON.parse(policyText).identity.evaluationId;
  assert.equal(JSON.parse(policyText).schemaVersion, "1.1.0");
  assert.ok(JSON.parse(policyText).expectedHeaders.b4Comparisons);
  assert.equal(await readFile(path.join(webDir, "dist", "snapshot.policy.json"), "utf8"), policyText);
  const snapDir = path.join(webDir, "public", "snapshots", evalId);
  await readFile(path.join(webDir, "dist", "snapshots", evalId, "b4_comparisons.csv"));
  const manifestText = await readFile(path.join(snapDir, "dashboard_snapshot_manifest.json"), "utf8");
  const manifest = JSON.parse(manifestText);
  const files = {
    "snapshot.policy.json": new TextEncoder().encode(policyText),
    [`snapshots/${evalId}/dashboard_snapshot_manifest.json`]: new TextEncoder().encode(manifestText),
  };
  for (const artifact of Object.values(manifest.files)) {
    files[`snapshots/${evalId}/${artifact.path}`] = new Uint8Array(await readFile(path.join(snapDir, artifact.path)));
  }
  const state = await loadSnapshot(async (url) => {
    const rel = String(url).replace(/^http:\/\/localhost:4173\//, "");
    const bytes = files[rel];
    if (!bytes) throw new Error(`missing ${rel}`);
    return new Response(bytes, { status: 200 });
  }, "http://localhost:4173/");
  assert.equal(state.status, "ready", state.status === "error" ? state.message : "");
  assert.equal(state.manifest.schemaVersion, "1.1.0");
  assert.equal(state.b4Comparisons?.length, 12);
  const b4Pending = filterForecastRows(state.forecasts, {
    split: "test", ticker: "SPY", models: ["HAR_X_OLS"], status: "pending", from: "", to: "",
  });
  assert.equal(b4Pending.length, 5);
  assert.equal(b4Pending[0]?.targetRealizedVol5d, null);
});

test("B4 incomplete-ETF portfolio row stays INCOMPLETE_INPUTS without fabricating volatility", () => {
  const { parsePortfolioRiskRow } = stateHelpers();
  const row = parsePortfolioRiskRow({
    split: "test",
    prediction_date: "2026-09-25",
    model_name: "HAR_X_OLS",
    prediction_mode: "HISTORICAL_REPLAY",
    feature_run_id: "feat-1",
    replay_run_id: "replay-1",
    input_snapshot_id: "a".repeat(64),
    spy_forecast_vol_annualized: "0.18",
    ief_forecast_vol_annualized: "",
    gld_forecast_vol_annualized: "0.21",
    spy_forecast_status: "VALID",
    ief_forecast_status: "INVALID",
    gld_forecast_status: "VALID",
    corr_spy_ief_20d: "0.1",
    corr_spy_gld_20d: "0.2",
    corr_ief_gld_20d: "0.3",
    is_corr_ready: "true",
    correlation_run_id: "corr-1",
    weight_spy: "0.5",
    weight_ief: "0.3",
    weight_gld: "0.2",
    portfolio_vol_annualized: "",
    portfolio_status: "INCOMPLETE_INPUTS",
    missing_inputs: "[\"IEF_INVALID_FORECAST\"]",
    covariance_matrix: "",
  });
  assert.equal(row.status, "INCOMPLETE_INPUTS");
  assert.equal(row.portfolioVol, null);
  assert.deepEqual(row.missingInputs, ["IEF_INVALID_FORECAST"]);
});

function stateHelpers() {
  return { parsePortfolioRiskRow };
}
