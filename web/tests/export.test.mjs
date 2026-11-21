import assert from "node:assert/strict";
import test from "node:test";
import { buildForecastCsv, buildExportMetadata } from "../dist/assets/data/export.js";

test("forecast CSV keeps source column names and leaves Pending actual/error blank", () => {
  const pending = {
    predictionDate: "2026-09-25", ticker: "SPY", split: "test", modelName: "ONLINE_SGD", predictionId: "pending-id",
    forecastStatus: "VALID", evaluationStatus: "PENDING_LABEL", predictedVolAnnualized: 0.088, targetRealizedVol5d: null,
    absoluteError: null, targetEndDate: "2026-10-02",
  };
  const csv = buildForecastCsv([pending], new Map());
  const [header, row] = csv.trimEnd().split("\r\n");
  assert.equal(header, "prediction_date,ticker,split,model_name,prediction_id,forecast_status,evaluation_status,predicted_vol_annualized,target_realized_vol_5d,absolute_error,target_end_date");
  assert.match(row, /,0\.088,,,2026-10-02$/);
  assert.doesNotMatch(header, /evaluation_id|export_sha256/);
});

test("export metadata distinguishes source hashes, filters, and export hash", async () => {
  const input = {
    manifest: { evaluationId: "evaluation-1", replayId: "replay-1", sourceZipSha256: "a".repeat(64), strictCutoff: "2026-09-25", reportApproval: "PENDING", mode: "SIMULATED HISTORICAL REPLAY" },
    sourceFiles: [{ path: "forecast_audit.csv", sha256: "b".repeat(64) }], filters: { split: "test", ticker: "SPY", models: ["ONLINE_SGD"], status: "pending", from: "", to: "" }, rowCount: 1,
  };
  const metadata = await buildExportMetadata(input, "header\r\nvalue\r\n", "2026-11-21T00:00:00.000Z");
  assert.equal(metadata.source.evaluationId, "evaluation-1");
  assert.equal(metadata.source.reportApproval, "PENDING");
  assert.equal(metadata.filters.status, "pending");
  assert.equal(metadata.export.rowCount, 1);
  assert.equal(metadata.export.columns[0], "prediction_date");
  assert.notEqual(metadata.export.sha256, metadata.source.sourceZipSha256);
  assert.deepEqual(metadata.source.files, input.sourceFiles);
});
