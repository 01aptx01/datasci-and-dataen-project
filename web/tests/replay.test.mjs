import assert from "node:assert/strict";
import test from "node:test";
import { resolveAsOfLabelView, selectSameDateForecasts } from "../dist/assets/data/replay.js";

function makeRow(overrides = {}) {
  return {
    predictionDate: "2025-10-01",
    ticker: "SPY",
    split: "test",
    modelName: "ONLINE_SGD",
    isLabelMature: true,
    targetStartDate: "2025-10-02",
    targetEndDate: "2025-10-08",
    predictionId: "pred-1",
    targetStartDatePrediction: "2025-10-02",
    targetEndDatePrediction: "2025-10-08",
    predictedVolAnnualized: 0.2,
    targetRealizedVol5d: 0.18,
    absoluteError: 0.02,
    labelStatus: "MATURE",
    forecastStatus: "VALID",
    evaluationStatus: "EVALUABLE",
    ...overrides,
  };
}

const evaluation = {
  experimentId: "eval-1",
  predictionId: "pred-1",
  predictionDate: "2025-10-01",
  split: "test",
  ticker: "SPY",
  modelName: "ONLINE_SGD",
  targetStartDate: "2025-10-02",
  targetEndDate: "2025-10-08",
  predictedVolAnnualized: 0.2,
  targetRealizedVol5d: 0.18,
  absoluteError: 0.02,
};

test("as-of viewer hides a mature source label before target end", () => {
  assert.equal(resolveAsOfLabelView(makeRow(), "2025-10-07", true, evaluation).status, "awaiting-target-end");
});

test("as-of viewer requires explicit reveal after maturity", () => {
  const view = resolveAsOfLabelView(makeRow(), "2025-10-08", false, evaluation);
  assert.equal(view.status, "eligible-reveal-required");
  assert.equal(view.actual, null);
});

test("as-of viewer reveals only the exact matching evaluation row", () => {
  const view = resolveAsOfLabelView(makeRow(), "2025-10-08", true, evaluation);
  assert.deepEqual(view, { status: "revealed", actual: 0.18, absoluteError: 0.02 });
  assert.equal(resolveAsOfLabelView(makeRow(), "2025-10-08", true, { ...evaluation, ticker: "IEF" }).status, "missing-evaluation");
});

test("final Pending source rows never reveal actual or error", () => {
  const pending = makeRow({
    predictionId: "pred-pending",
    isLabelMature: false,
    targetEndDate: "2026-10-02",
    labelStatus: "PENDING",
    evaluationStatus: "PENDING_LABEL",
    targetRealizedVol5d: null,
    absoluteError: null,
  });
  const view = resolveAsOfLabelView(pending, "2026-10-02", true, evaluation);
  assert.deepEqual(view, { status: "source-pending", actual: null, absoluteError: null });
});

test("same-date comparison is exact-keyed and ordered B0 through B3", () => {
  const date = "2025-10-01";
  const rows = [
    makeRow({ modelName: "ONLINE_SGD" }),
    makeRow({ modelName: "STATIC_SGD" }),
    makeRow({ modelName: "ROLLING_20D_BASELINE" }),
    makeRow({ modelName: "CONSTANT_BASELINE" }),
    makeRow({ predictionDate: "2025-10-02" }),
    makeRow({ ticker: "IEF" }),
  ];
  assert.deepEqual(selectSameDateForecasts(rows, "SPY", date).map((row) => row.modelName), [
    "CONSTANT_BASELINE", "ROLLING_20D_BASELINE", "STATIC_SGD", "ONLINE_SGD",
  ]);
});
