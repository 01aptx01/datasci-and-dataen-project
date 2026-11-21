import assert from "node:assert/strict";
import test from "node:test";
import { computePortfolioVolatility } from "../dist/assets/data/portfolio.js";

const covariance = [
  [0.007746705742275293, 0.0036684938723180707, 0.008206738205032189],
  [0.0036684938723180707, 0.0038112978070462674, 0.004933866068180676],
  [0.008206738205032189, 0.004933866068180676, 0.02480743568283787],
];

test("stored 50/30/20 weights reproduce the pinned portfolio result", () => {
  assert.ok(Math.abs(computePortfolioVolatility(covariance, [0.5, 0.3, 0.2]) - 0.08127699795391094) < 1e-10);
});

test("portfolio what-if rejects weights outside the stored allocation domain", () => {
  assert.throws(() => computePortfolioVolatility(covariance, [-0.1, 0.6, 0.5]), /nonnegative/);
  assert.throws(() => computePortfolioVolatility(covariance, [0.4, 0.4, 0.1]), /sum to 1/);
  assert.throws(() => computePortfolioVolatility(covariance, [0.5, Number.NaN, 0.5]), /finite/);
});

test("portfolio what-if rejects incomplete or malformed covariance matrices", () => {
  assert.throws(() => computePortfolioVolatility([[1, 0], [0, 1]], [0.5, 0.3, 0.2]), /3 by 3/);
  assert.throws(() => computePortfolioVolatility([[1, 1, 0], [0, 1, 0], [0, 0, 1]], [0.5, 0.3, 0.2]), /symmetric/);
});
