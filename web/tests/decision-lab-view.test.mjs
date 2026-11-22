import assert from "node:assert/strict";
import test from "node:test";
import { createDefaultFinancialScenarioState } from "../dist/assets/data/decisionLab.js";
import { renderFinancialDecisionLab } from "../dist/assets/ui/financialDecisionLab.js";

const covariance = [[0.01, 0, 0], [0, 0.04, 0], [0, 0, 0.09]];
const selectedRow = {
  split: "test",
  predictionDate: "2025-01-02",
  modelName: "ONLINE_SGD",
  replayRunId: "replay-test",
  inputSnapshotId: "a".repeat(64),
  forecastVols: [0.1, 0.2, 0.3],
  forecastStatuses: ["VALID", "VALID", "VALID"],
  correlations: { spyIef: 0.675, spyGld: 0.592, iefGld: 0.507 },
  correlationReady: true,
  correlationRunId: "corr-test",
  sourceWeights: [0.5, 0.3, 0.2],
  portfolioVol: 0.1,
  status: "OK",
  missingInputs: [],
  covariance,
};
const selection = {
  evaluationId: "e".repeat(64),
  replayId: "r".repeat(64),
  split: "test",
  predictionDate: "2025-01-02",
  modelName: "ONLINE_SGD",
  ticker: "SPY",
  asOfDate: "2025-01-02",
  view: "as-of",
};

function render(decision) {
  return renderFinancialDecisionLab({
    rows: [selectedRow],
    selectedRow,
    selection,
    decision,
    availableDates: [selection.predictionDate],
    availableModels: [selection.modelName],
    modelMetrics: [],
    coverage: [],
    unit: "percent",
    budgetDraft: "",
    budgetError: "",
    evaluationId: selection.evaluationId,
    strictCutoff: "2025-01-02",
    pointInTimeSourceAvailabilityVerified: false,
  });
}

test("Risk Center does not report zero over-budget dates before a user sets a budget", () => {
  const html = render(createDefaultFinancialScenarioState());
  assert.match(html, /ยังไม่ได้ตั้ง/);
  assert.match(html, /ตั้ง budget เพื่อดูจำนวนวันที่สูงกว่าขีด/);
  assert.doesNotMatch(html, /0\/1 usable dates สูงกว่าขีด/);
});

test("Scenario Lab labels absolute risk deltas in percentage points", () => {
  const state = { ...createDefaultFinancialScenarioState(), scenarioB: [0.6, 0.2, 0.2], activeTab: "scenarios" };
  const html = render(state);
  assert.match(html, /Difference · B − A[\s\S]*\d+\.\d+ pp/);
  assert.match(html, /decision-risk-line scenario-a/);
  assert.match(html, /decision-risk-line scenario-b/);
  assert.match(html, /Scenario A · 1 usable dates/);
  assert.match(html, /Scenario B · 1 usable dates/);
  assert.match(html, /Scenario A risk/);
  assert.match(html, /Each point forecasts Forward RV5 for the next five XNYS sessions/);
  assert.match(html, /weights SPY\/IEF\/GLD/);
  assert.match(html, /approx 5-session equivalent \(sqrt-of-time\)/);
  assert.match(html, /Eval e{64}/);
});

test("Risk Drivers displays the stored correlation evidence", () => {
  const state = { ...createDefaultFinancialScenarioState(), activeTab: "drivers" };
  const html = render(state);
  assert.match(html, /Stored 20-session correlations/);
  assert.match(html, /0\.675/);
  assert.match(html, /0\.592/);
  assert.match(html, /0\.507/);
  assert.match(html, /corr_\*_20d/);
  assert.match(html, /decision-contribution-fill positive/);
  assert.match(html, /historical proxies ไม่ใช่ correlation forecasts/);
});

test("Scenario Lab pairs numeric weight fields with adjustable sliders", () => {
  const html = render({ ...createDefaultFinancialScenarioState(), activeTab: "scenarios" });
  assert.match(html, /type="number"[^>]*data-field="scenario-weight"/);
  assert.match(html, /type="range"[^>]*data-field="scenario-weight-slider"/);
});
