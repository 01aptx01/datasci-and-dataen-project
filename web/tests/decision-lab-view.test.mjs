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

function render(decision, overrides = {}) {
  return renderFinancialDecisionLab({
    rows: [selectedRow],
    selectedRow,
    selection,
    decision,
    availableDates: [selection.predictionDate],
    availableModels: [selection.modelName],
    sessionPlaying: false,
    sessionSpeedMs: 900,
    modelMetrics: [],
    coverage: [],
    unit: "percent",
    budgetDraft: "",
    budgetError: "",
    evaluationId: selection.evaluationId,
    strictCutoff: "2025-01-02",
    pointInTimeSourceAvailabilityVerified: false,
    ...overrides,
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
  assert.equal([...html.matchAll(/data-field="scenario-weight"/g)].length, 4);
  assert.equal([...html.matchAll(/data-field="scenario-weight-slider"/g)].length, 4);
});

test("Scenario Lab lets each scenario choose its remainder asset", () => {
  const decision = {
    ...createDefaultFinancialScenarioState(),
    remainderAssetA: "SPY",
    remainderAssetB: "IEF",
    activeTab: "scenarios",
  };
  const html = render(decision);
  assert.match(html, /data-field="scenario-remainder" data-scenario="A"/);
  assert.match(html, /data-field="scenario-remainder" data-scenario="B"/);
  assert.match(html, /<option value="SPY" selected>SPY<\/option>/);
  assert.match(html, /<option value="IEF" selected>IEF<\/option>/);
  assert.equal([...html.matchAll(/class="scenario-weight-remainder"/g)].length, 2);
});

test("Scenario Lab renders two editable weights and one calculated remainder per scenario", () => {
  const html = render({ ...createDefaultFinancialScenarioState(), remainderAssetA: "IEF", activeTab: "scenarios" });
  assert.match(html, /data-scenario-remainder-value="A"[^>]*>30%/);
  assert.match(html, /100% − SPY − GLD/);
  assert.match(html, /data-scenario-remainder-value="B"[^>]*>20%/);
  assert.match(html, /100% − SPY − IEF/);
});

test("Scenario Lab keeps an invalid allocation visible without clamping its sliders", () => {
  const decision = {
    ...createDefaultFinancialScenarioState(),
    scenarioA: [-0.1, 0.3, 0.8],
    remainderAssetA: "SPY",
    activeTab: "scenarios",
  };
  const html = render(decision);
  assert.match(html, /data-scenario-remainder-value="A"[^>]*>-10%/);
  assert.match(html, /id="scenario-A-IEF-slider"[^>]*max="30"[^>]*value="30"/);
  assert.match(html, /id="scenario-A-GLD-slider"[^>]*max="80"[^>]*value="80"/);
  assert.match(html, /น้ำหนักแต่ละสินทรัพย์ต้องอยู่ระหว่าง 0 ถึง 1/);
});

test("Portfolio date controls expose adjacent recorded dates and opt-in playback", () => {
  const html = render(createDefaultFinancialScenarioState(), {
    availableDates: ["2025-01-01", "2025-01-02", "2025-01-03"],
    sessionPlaying: true,
  });
  const dateDock = html.match(/<nav class="portfolio-date-dock" aria-label="Portfolio date navigation">([\s\S]*?)<\/nav>/)?.[1];
  assert.ok(dateDock, "date navigation should live in a dock that can stay visible while scrolling the lab");
  assert.match(dateDock, /data-action="portfolio-date-step" data-direction="previous"/);
  assert.match(dateDock, /data-field="portfolio-date"/);
  assert.match(dateDock, /data-action="portfolio-date-step" data-direction="next"/);
  assert.match(html, /data-action="portfolio-date-step" data-direction="previous"/);
  assert.match(html, /data-field="portfolio-date"/);
  assert.match(html, /data-action="portfolio-date-step" data-direction="next"/);
  assert.match(html, /data-action="toggle-session-play"[^>]*aria-pressed="true"[^>]*>หยุดเล่น/);
  assert.match(html, /data-field="session-speed"/);
  assert.match(html, /2 \/ 3 วันที่บันทึก/);
});

test("Portfolio playback keeps an invalid recorded date visible without calculating risk", () => {
  const unavailableRow = {
    ...selectedRow,
    status: "INCOMPLETE_INPUTS",
    covariance: null,
    portfolioVol: null,
    missingInputs: ["IEF forecast"],
  };
  const html = render(createDefaultFinancialScenarioState(), {
    rows: [unavailableRow],
    selectedRow: unavailableRow,
    availableDates: ["2025-01-01", selection.predictionDate, "2025-01-03"],
  });
  assert.match(html, /portfolio-date-status unavailable/);
  assert.match(html, /Unavailable · source INCOMPLETE_INPUTS/);
  assert.match(html, /Unavailable inputs: IEF forecast/);
  assert.match(html, /class="decision-chart-empty"/);
  assert.match(html, /<td>—<\/td><td>INCOMPLETE_INPUTS<\/td>/);
});

test("Scenario Lab keeps editors, selected-day comparison, timeline, and budget together", () => {
  const decision = {
    ...createDefaultFinancialScenarioState(),
    activeTab: "scenarios",
    scenarioB: [0.6, 0.2, 0.2],
    budgetAnnualizedDecimal: 0.09,
  };
  const html = render(decision);
  assert.match(html, /class="scenario-workbench"/);
  assert.match(html, /class="scenario-editors"/);
  assert.match(html, /class="scenario-analysis"/);
  assert.match(html, /class="scenario-selected-day"/);
  assert.match(html, /Difference · B − A/);
  assert.match(html, /id="scenario-risk-budget-input"/);
  assert.match(html, /data-scenario-budget-summary/);
  assert.match(html, /Historical risk · fixed Scenario A\/B weights/);
  assert.match(html, /น้ำหนัก SPY/);
});

test("Scenario Lab makes an unset budget explicit without inventing a count", () => {
  const html = render({ ...createDefaultFinancialScenarioState(), activeTab: "scenarios" });
  assert.match(html, /ยังไม่ได้ตั้ง/);
  assert.match(html, /ตั้ง budget เพื่อดูจำนวนวันที่สูงกว่าขีด/);
  assert.doesNotMatch(html, /0\/1 usable dates สูงกว่าขีด/);
});
