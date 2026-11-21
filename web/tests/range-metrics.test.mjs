import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { parseCsv } from "../dist/assets/data/csv.js";
import { parseEvaluation, parseForecastAudit, parseModelMetrics } from "../dist/assets/data/loadSnapshot.js";
import { calculateDescriptiveRangeMetrics } from "../dist/assets/data/rangeMetrics.js";
import { parsePolicy } from "../dist/assets/data/schemas.js";

const policy = parsePolicy(JSON.parse(await readFile(new URL("../snapshot.policy.json", import.meta.url), "utf8")));
const snapshotDirectory = new URL(`../public/snapshots/${policy.identity.evaluationId}/`, import.meta.url);
const auditText = await readFile(new URL("forecast_audit.csv", snapshotDirectory), "utf8");
const evaluationText = await readFile(new URL("evaluation.csv", snapshotDirectory), "utf8");
const metricsText = await readFile(new URL("model_metrics.csv", snapshotDirectory), "utf8");
const auditRows = parseForecastAudit(auditText, policy);
const evaluationRows = parseEvaluation(evaluationText, policy);
const officialRows = parseModelMetrics(metricsText, policy);
const evaluations = new Map(evaluationRows.map((row) => [row.predictionId, row]));

test("full Test descriptive common-panel scores reproduce stored Macro rows", () => {
  const result = calculateDescriptiveRangeMetrics(auditRows, evaluations, "2025-10-01", "2026-09-25", "MACRO");
  assert.equal(result.status, "ready");
  assert.equal(result.n, 729);
  for (const score of result.scores) {
    const official = officialRows.find((row) => row.split === "test" && row.ticker === "MACRO" && row.modelName === score.modelName);
    assert.ok(official);
    assert.equal(score.n, 729);
    assert.ok(Math.abs(score.mae - official.mae) < 1e-12);
    assert.ok(Math.abs(score.rmse - official.rmse) < 1e-12);
  }
});

test("ticker-specific range N counts only same-date common paired anchors", () => {
  const result = calculateDescriptiveRangeMetrics(auditRows, evaluations, "2025-10-01", "2026-09-25", "SPY");
  assert.equal(result.status, "ready");
  assert.equal(result.n, 243);
  assert.equal(result.nByTicker.SPY, 243);
});

test("range with no common pairs reports insufficient evidence", () => {
  const result = calculateDescriptiveRangeMetrics(auditRows, evaluations, "2025-11-02", "2025-11-02", "SPY");
  assert.equal(result.status, "insufficient");
  assert.equal(result.scores.every((score) => score.mae === null && score.rmse === null), true);
});

test("MACRO range does not average away a ticker with no paired rows", () => {
  const unavailableIef = auditRows.filter((row) => row.ticker !== "IEF");
  const result = calculateDescriptiveRangeMetrics(unavailableIef, evaluations, "2025-10-01", "2026-09-25", "MACRO");
  assert.equal(result.status, "insufficient");
  assert.equal(result.nByTicker.IEF, 0);
});

test("invalid date ranges return an explanatory empty result", () => {
  const result = calculateDescriptiveRangeMetrics(auditRows, evaluations, "2026-01-01", "2025-12-31", "SPY");
  assert.equal(result.status, "insufficient");
  assert.match(result.reason, /ช่วงวันที่/);
});
