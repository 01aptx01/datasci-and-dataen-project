import assert from "node:assert/strict";
import test from "node:test";
import { computePortfolioVolatility, validateScenarioWeights, portfolioRiskSourceDates } from "../dist/assets/data/portfolio.js";

const covariance = [
  [0.007746705742275293, 0.0036684938723180707, 0.008206738205032189],
  [0.0036684938723180707, 0.0038112978070462674, 0.004933866068180676],
  [0.008206738205032189, 0.004933866068180676, 0.02480743568283787],
];

test("portfolio editor accepts only finite weights totaling 100 percent", () => {
  assert.equal(validateScenarioWeights([0.5, 0.3, 0.2]).status, "valid");
  for (const weights of [[0.6, 0.3, 0.2], [NaN, 0.3, 0.7], [-0.1, 0.6, 0.5], [0.5, 0.5]]) {
    assert.equal(validateScenarioWeights(weights).status, "invalid");
  }
});

test("portfolio date picker uses distinct test dates for the selected model", () => {
  const rows = [
    { split: "test", modelName: "ONLINE_SGD", predictionDate: "2025-10-02" },
    { split: "test", modelName: "ONLINE_SGD", predictionDate: "2025-10-01" },
    { split: "test", modelName: "ONLINE_SGD", predictionDate: "2025-10-02" },
    { split: "validation", modelName: "ONLINE_SGD", predictionDate: "2025-09-30" },
    { split: "test", modelName: "STATIC_SGD", predictionDate: "2025-10-03" },
  ];
  assert.deepEqual(portfolioRiskSourceDates(rows, "ONLINE_SGD"), ["2025-10-01", "2025-10-02"]);
});

test("stored 50/30/20 weights reproduce the pinned portfolio result", () => {
  assert.ok(Math.abs(computePortfolioVolatility(covariance, [0.5, 0.3, 0.2]) - 0.08127699795391094) < 1e-10);
});

test("changing weights recalculates risk against the same stored covariance", () => {
  const baseline = computePortfolioVolatility(covariance, [0.5, 0.3, 0.2]);
  const whatIf = computePortfolioVolatility(covariance, [0.6, 0.2, 0.2]);
  assert.ok(Number.isFinite(whatIf));
  assert.notEqual(whatIf, baseline);
});

test("portfolio what-if rejects weights outside the stored allocation domain", () => {
  assert.throws(() => computePortfolioVolatility(covariance, [-0.1, 0.6, 0.5]), /nonnegative/);
  assert.throws(() => computePortfolioVolatility(covariance, [0.4, 0.4, 0.1]), /sum to 1/);
  assert.throws(() => computePortfolioVolatility(covariance, [0.5, Number.NaN, 0.5]), /finite/);
});

test("portfolio weights use the source contract's 1e-8 sum tolerance", () => {
  assert.ok(Number.isFinite(computePortfolioVolatility(covariance, [0.500000004, 0.3, 0.2])));
  assert.throws(() => computePortfolioVolatility(covariance, [0.50000002, 0.3, 0.2]), /sum to 1/);
});

test("portfolio what-if rejects incomplete or malformed covariance matrices", () => {
  assert.throws(() => computePortfolioVolatility([[1, 0], [0, 1]], [0.5, 0.3, 0.2]), /3 by 3/);
  assert.throws(() => computePortfolioVolatility([[1, 1, 0], [0, 1, 0], [0, 0, 1]], [0.5, 0.3, 0.2]), /symmetric/);
});
