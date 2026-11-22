import assert from "node:assert/strict";
import test from "node:test";
import * as portfolio from "../dist/assets/data/portfolio.js";
import * as selection from "../dist/assets/data/selection.js";

const decision = await import("../dist/assets/data/decisionLab.js").catch(() => ({}));
const requireFunction = (name) => {
  assert.equal(typeof decision[name], "function", `${name} must be available`);
  return decision[name];
};

function row(predictionDate, { status = "OK", modelName = "ONLINE_SGD", covariance = [[0.01, 0, 0], [0, 0.04, 0], [0, 0, 0.09]], missingInputs = [] } = {}) {
  return {
    split: "test",
    predictionDate,
    modelName,
    replayRunId: "replay-test",
    inputSnapshotId: "a".repeat(64),
    forecastVols: status === "OK" ? [0.1, 0.2, 0.3] : [0.1, null, 0.3],
    forecastStatuses: status === "OK" ? ["VALID", "VALID", "VALID"] : ["VALID", "MISSING", "VALID"],
    correlations: { spyIef: 0, spyGld: 0, iefGld: 0 },
    correlationReady: status === "OK",
    correlationRunId: "corr-test",
    sourceWeights: [0.5, 0.3, 0.2],
    portfolioVol: status === "OK" ? 0.1 : null,
    status,
    missingInputs,
    covariance: status === "OK" ? covariance : null,
  };
}

test("signed absolute and relative contributions conserve portfolio volatility", () => {
  assert.equal(typeof portfolio.computePortfolioRiskContributions, "function");
  const result = portfolio.computePortfolioRiskContributions([
    [1, -0.5, 0],
    [-0.5, 1, 0],
    [0, 0, 0.25],
  ], [0.8, 0.2, 0]);
  assert.ok(Math.abs(result.volatility - Math.sqrt(0.52)) < 1e-12);
  assert.ok(result.absoluteContributions);
  assert.ok(result.relativeContributions);
  assert.ok(result.absoluteContributions[1] < 0);
  assert.ok(Math.abs(result.absoluteContributions.reduce((sum, value) => sum + value, 0) - result.volatility) < 1e-12);
  assert.ok(Math.abs(result.relativeContributions.reduce((sum, value) => sum + value, 0) - 1) < 1e-12);
});

test("zero-risk portfolios mark both contribution sets undefined", () => {
  assert.equal(typeof portfolio.computePortfolioRiskContributions, "function");
  const result = portfolio.computePortfolioRiskContributions([[0, 0, 0], [0, 0, 0], [0, 0, 0]], [0.5, 0.3, 0.2]);
  assert.equal(result.volatility, 0);
  assert.equal(result.absoluteContributions, null);
  assert.equal(result.relativeContributions, null);
});

test("scenario weights validate without normalizing and use 1e-8 tolerance", () => {
  const validateScenarioWeights = requireFunction("validateScenarioWeights");
  assert.equal(validateScenarioWeights([0.500000004, 0.3, 0.2]).status, "valid");
  assert.equal(validateScenarioWeights([0.50000002, 0.3, 0.2]).status, "invalid");
  assert.equal(validateScenarioWeights([-0.1, 0.6, 0.5]).status, "invalid");
  assert.equal(validateScenarioWeights([0.5, Number.NaN, 0.5]).status, "invalid");
});

test("financial decision defaults both scenarios to the same neutral example weights", () => {
  const createDefaultFinancialScenarioState = requireFunction("createDefaultFinancialScenarioState");
  const state = createDefaultFinancialScenarioState();
  assert.deepEqual(state.scenarioA, [0.5, 0.3, 0.2]);
  assert.deepEqual(state.scenarioB, state.scenarioA);
  assert.equal(state.activeScenario, "A");
  assert.equal(state.remainderAssetA, "GLD");
  assert.equal(state.remainderAssetB, "GLD");
  assert.equal(state.budgetAnnualizedDecimal, null);
  assert.equal(state.activeTab, "risk");
});

test("scenario remainder assets round-trip in the URL", () => {
  const createDefaultFinancialScenarioState = requireFunction("createDefaultFinancialScenarioState");
  const serializeFinancialDecisionHash = requireFunction("serializeFinancialDecisionHash");
  const parseFinancialDecisionParams = requireFunction("parseFinancialDecisionParams");
  const state = { ...createDefaultFinancialScenarioState(), remainderAssetA: "SPY", remainderAssetB: "IEF" };
  const hash = serializeFinancialDecisionHash("#/portfolio", state);
  const route = selection.parseHashRoute(hash);
  assert.equal(route.params.get("scenarioRemainderA"), "SPY");
  assert.equal(route.params.get("scenarioRemainderB"), "IEF");
  assert.deepEqual(parseFinancialDecisionParams(route.params), { status: "valid", state });
});

test("legacy scenario URLs default missing remainder assets to GLD", () => {
  const parseFinancialDecisionParams = requireFunction("parseFinancialDecisionParams");
  const params = new URLSearchParams("scenarioA=0.5,0.3,0.2&scenarioB=0.5,0.3,0.2&activeScenario=A&portfolioTab=risk");
  const result = parseFinancialDecisionParams(params);
  assert.equal(result.status, "valid");
  assert.equal(result.state.remainderAssetA, "GLD");
  assert.equal(result.state.remainderAssetB, "GLD");
});

test("scenario URL rejects unsupported remainder assets", () => {
  const parseFinancialDecisionParams = requireFunction("parseFinancialDecisionParams");
  const params = new URLSearchParams("scenarioA=0.5,0.3,0.2&scenarioB=0.5,0.3,0.2&activeScenario=A&portfolioTab=risk&scenarioRemainderA=TLT");
  assert.equal(parseFinancialDecisionParams(params).status, "invalid");
});

test("editing one scenario weight recalculates only the selected remainder", () => {
  const updateScenarioRemainderWeight = requireFunction("updateScenarioRemainderWeight");
  const glDraw = updateScenarioRemainderWeight([0.5, 0.3, 0.2], "GLD", "SPY", 0.6);
  assert.equal(glDraw[0], 0.6);
  assert.equal(glDraw[1], 0.3);
  assert.ok(Math.abs(glDraw[2] - 0.1) < 1e-12);
  const spyRemainder = updateScenarioRemainderWeight([0.5, 0.3, 0.2], "SPY", "GLD", 0.4);
  assert.ok(Math.abs(spyRemainder[0] - 0.3) < 1e-12);
  assert.equal(spyRemainder[1], 0.3);
  assert.equal(spyRemainder[2], 0.4);
  assert.throws(() => updateScenarioRemainderWeight([0.5, 0.3, 0.2], "GLD", "GLD", 0.1), /remainder/i);
});

test("selecting a scenario remainder asset preserves both allocations and their risk", () => {
  const createDefaultFinancialScenarioState = requireFunction("createDefaultFinancialScenarioState");
  const setScenarioRemainderAsset = requireFunction("setScenarioRemainderAsset");
  const weights = [0.5, 0.3, 0.2];
  const covariance = [[0.01, 0, 0], [0, 0.04, 0], [0, 0, 0.09]];
  const beforeRisk = portfolio.computePortfolioVolatility(covariance, weights);
  const next = setScenarioRemainderAsset(createDefaultFinancialScenarioState(), "A", "IEF");
  assert.deepEqual(next.scenarioA, weights);
  assert.deepEqual(next.scenarioB, weights);
  assert.equal(next.remainderAssetA, "IEF");
  assert.equal(next.remainderAssetB, "GLD");
  assert.equal(portfolio.computePortfolioVolatility(covariance, next.scenarioA), beforeRisk);
});

test("over-allocation and non-finite remainder weights remain invalid", () => {
  const updateScenarioRemainderWeight = requireFunction("updateScenarioRemainderWeight");
  const validateScenarioWeights = requireFunction("validateScenarioWeights");
  assert.equal(validateScenarioWeights(updateScenarioRemainderWeight([0.5, 0.3, 0.2], "GLD", "SPY", 0.8)).status, "invalid");
  assert.equal(validateScenarioWeights(updateScenarioRemainderWeight([0.5, 0.3, 0.2], "GLD", "SPY", Number.NaN)).status, "invalid");
});

test("scenario comparison reports annualized percentage-point and guarded relative changes", () => {
  const compareScenarioRisks = requireFunction("compareScenarioRisks");
  const comparison = compareScenarioRisks(0.1, 0.12);
  assert.ok(Math.abs(comparison.differenceAnnualizedDecimal - 0.02) < 1e-12);
  assert.ok(Math.abs(comparison.differencePercentagePoints - 2) < 1e-12);
  assert.ok(Math.abs(comparison.relativeDifferencePercent - 20) < 1e-12);
  assert.equal(compareScenarioRisks(0, 0.02).relativeDifferencePercent, null);
});

test("daily risk series filters future dates and breaks at source gaps", () => {
  const buildPortfolioRiskTimeline = requireFunction("buildPortfolioRiskTimeline");
  const splitRiskTimelineSegments = requireFunction("splitRiskTimelineSegments");
  const rows = [
    row("2025-01-01"),
    row("2025-01-02", { status: "INCOMPLETE_INPUTS", missingInputs: ["IEF forecast"] }),
    row("2025-01-03"),
    row("2025-01-04"),
  ];
  const asOf = buildPortfolioRiskTimeline(rows, "ONLINE_SGD", [1, 0, 0], { view: "as-of", asOfDate: "2025-01-02" });
  assert.deepEqual(asOf.map((point) => point.date), ["2025-01-01", "2025-01-02"]);
  assert.equal(asOf[1].risk, null);
  const retrospective = buildPortfolioRiskTimeline(rows, "ONLINE_SGD", [1, 0, 0], { view: "retrospective" });
  assert.deepEqual(splitRiskTimelineSegments(retrospective).map((segment) => segment.map((point) => point.date)), [
    ["2025-01-01"], ["2025-01-03", "2025-01-04"],
  ]);
});

test("prior comparable risk names the previous valid source date and gap", () => {
  const buildPortfolioRiskTimeline = requireFunction("buildPortfolioRiskTimeline");
  const findPriorComparableRisk = requireFunction("findPriorComparableRisk");
  const timeline = buildPortfolioRiskTimeline([
    row("2025-01-01"),
    row("2025-01-02", { status: "INCOMPLETE_INPUTS", missingInputs: ["IEF forecast"] }),
    row("2025-01-03"),
    row("2025-01-04"),
  ], "ONLINE_SGD", [0.5, 0.3, 0.2], { view: "retrospective" });
  assert.deepEqual(findPriorComparableRisk(timeline, "2025-01-03"), {
    point: timeline[0],
    sessionsBack: 2,
  });
});

test("timeline fails closed when an OK source row is missing correlation readiness", () => {
  const buildPortfolioRiskTimeline = requireFunction("buildPortfolioRiskTimeline");
  const points = buildPortfolioRiskTimeline([
    row("2025-01-01", { status: "OK" }),
    { ...row("2025-01-02"), correlationReady: false },
  ], "ONLINE_SGD", [0.5, 0.3, 0.2], { view: "retrospective" });
  assert.ok(points[0].risk !== null);
  assert.equal(points[1].risk, null);
});

test("risk budget separates below, at, above, and unavailable values", () => {
  const riskBudgetStatus = requireFunction("riskBudgetStatus");
  const summarizeRiskBudget = requireFunction("summarizeRiskBudget");
  assert.equal(riskBudgetStatus(0.08, 0.09), "below");
  assert.equal(riskBudgetStatus(0.09, 0.09), "at");
  assert.equal(riskBudgetStatus(0.1, 0.09), "above");
  assert.equal(riskBudgetStatus(null, 0.09), "unavailable");
  assert.equal(riskBudgetStatus(0.08, null), "unset");
  assert.deepEqual(summarizeRiskBudget([
    { date: "2025-01-01", risk: 0.08 },
    { date: "2025-01-02", risk: 0.1 },
    { date: "2025-01-03", risk: null },
    { date: "2025-01-04", risk: 0.09 },
  ], 0.09), {
    evaluableCount: 3,
    aboveCount: 1,
    aboveDates: ["2025-01-02"],
  });
});

test("scenario URL round-trips alongside the shared D8 selection", () => {
  const createDefaultFinancialScenarioState = requireFunction("createDefaultFinancialScenarioState");
  const serializeFinancialDecisionHash = requireFunction("serializeFinancialDecisionHash");
  const parseFinancialDecisionParams = requireFunction("parseFinancialDecisionParams");
  const state = {
    ...createDefaultFinancialScenarioState(),
    scenarioB: [0.6, 0.2, 0.2],
    activeScenario: "B",
    budgetAnnualizedDecimal: 0.09,
    activeTab: "scenarios",
  };
  const selected = {
    evaluationId: "e".repeat(64), replayId: "r".repeat(64), split: "test",
    predictionDate: "2026-09-25", modelName: "ONLINE_SGD", ticker: "SPY",
    asOfDate: "2026-09-25", view: "as-of",
  };
  const hash = serializeFinancialDecisionHash(selection.serializeSelectionHash("/portfolio", selected), state);
  const route = selection.parseHashRoute(hash);
  assert.equal(selection.parseExperimentSelection(route.params).status, "valid");
  assert.deepEqual(parseFinancialDecisionParams(route.params), { status: "valid", state });
});

test("scenario URL rejects incomplete, duplicate, malformed, negative, and nonfinite input", () => {
  const parseFinancialDecisionParams = requireFunction("parseFinancialDecisionParams");
  const valid = new URLSearchParams("scenarioA=0.5,0.3,0.2&scenarioB=0.6,0.2,0.2&activeScenario=B&portfolioTab=scenarios");
  assert.equal(parseFinancialDecisionParams(new URLSearchParams("scenarioA=0.5,0.3,0.2")).status, "invalid");
  for (const value of ["0.5,0.3", "-0.1,0.5,0.6", "Infinity,0,1", "0.4,0.3,0.2"]) {
    const params = new URLSearchParams(valid);
    params.set("scenarioA", value);
    assert.equal(parseFinancialDecisionParams(params).status, "invalid", value);
  }
  const badBudget = new URLSearchParams(valid);
  badBudget.set("riskBudget", "-0.01");
  assert.equal(parseFinancialDecisionParams(badBudget).status, "invalid");
  const duplicate = new URLSearchParams(`${valid}&activeScenario=A`);
  assert.equal(parseFinancialDecisionParams(duplicate).status, "invalid");
});
