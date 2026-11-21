import assert from "node:assert/strict";
import test from "node:test";
import {
  defaultExperimentSelection,
  isIsoCalendarDate,
  parseExperimentSelection,
  parseHashRoute,
  serializeSelectionHash,
  validateExperimentSelection,
} from "../dist/assets/data/selection.js";

const evaluationId = "e".repeat(64);
const replayId = "r".repeat(64);
const source = {
  evaluationId,
  replayId,
  forecasts: [
    { split: "test", predictionDate: "2026-09-23", ticker: "SPY", modelName: "ONLINE_SGD", forecastStatus: "VALID" },
    { split: "test", predictionDate: "2026-09-24", ticker: "SPY", modelName: "ONLINE_SGD", forecastStatus: "VALID" },
    { split: "test", predictionDate: "2026-09-23", ticker: "SPY", modelName: "STATIC_SGD", forecastStatus: "VALID" },
    { split: "validation", predictionDate: "2026-09-23", ticker: "SPY", modelName: "ONLINE_SGD", forecastStatus: "VALID" },
  ],
  portfolioRisk: [
    { split: "test", predictionDate: "2026-09-23", modelName: "ONLINE_SGD", status: "OK", covariance: [[1, 0, 0], [0, 1, 0], [0, 0, 1]], portfolioVol: 1, missingInputs: [] },
  ],
};

const selection = {
  evaluationId,
  replayId,
  split: "test",
  predictionDate: "2026-09-23",
  modelName: "ONLINE_SGD",
  ticker: "SPY",
  asOfDate: "2026-09-24",
  rangeStart: "2026-09-01",
  rangeEnd: "2026-09-25",
  rangePreset: "custom",
  view: "as-of",
};

test("hash selection round-trips with snapshot IDs and optional context", () => {
  const hash = serializeSelectionHash("/forecasts", selection);
  const route = parseHashRoute(hash);
  assert.equal(route.path, "/forecasts");
  const parsed = parseExperimentSelection(route.params);
  assert.deepEqual(parsed, { status: "valid", selection });
  assert.equal(validateExperimentSelection(parsed.selection, source).status, "valid");
});

test("shareable range presets retain the selected range mode", () => {
  const last20 = { ...selection, rangePreset: "last20" };
  const parsed = parseExperimentSelection(parseHashRoute(serializeSelectionHash("/models", last20)).params);
  assert.deepEqual(parsed, { status: "valid", selection: last20 });
  assert.equal(validateExperimentSelection(last20, source).status, "valid");
  assert.equal(validateExperimentSelection({ ...last20, rangeStart: undefined, rangeEnd: undefined }, source).status, "invalid");
});

test("legacy route hashes and non-selection mode params remain valid", () => {
  assert.equal(parseHashRoute("#/portfolio").path, "/portfolio");
  assert.deepEqual(parseExperimentSelection(parseHashRoute("#/forecasts?mode=lab").params), { status: "absent" });
});

test("selection parser rejects incomplete, duplicate, unknown, and unsupported values", () => {
  assert.equal(parseExperimentSelection(new URLSearchParams("date=2026-09-23")).status, "invalid");
  assert.equal(parseExperimentSelection(new URLSearchParams("date=2026-09-23&date=2026-09-24")).status, "invalid");
  assert.equal(parseExperimentSelection(new URLSearchParams("unexpected=value")).status, "invalid");
  assert.equal(parseExperimentSelection(new URLSearchParams(serializeSelectionHash("/models", { ...selection, rangePreset: "unsupported" }).split("?")[1])).status, "invalid");
  const invalidModel = new URLSearchParams(serializeSelectionHash("/forecasts", { ...selection, modelName: "BOGUS" }).split("?")[1]);
  assert.equal(parseExperimentSelection(invalidModel).status, "invalid");
  assert.equal(isIsoCalendarDate("2026-02-30"), false);
  assert.equal(isIsoCalendarDate("2026-09-23"), true);
});

test("selection validation rejects a mismatched Evaluation or Replay ID", () => {
  assert.match(validateExperimentSelection({ ...selection, evaluationId: "x".repeat(64) }, source).message, /Evaluation ID/);
  assert.match(validateExperimentSelection({ ...selection, replayId: "x".repeat(64) }, source).message, /Replay ID/);
});

test("unavailable date, model, or split is explicit and never substituted", () => {
  const missingDate = validateExperimentSelection({ ...selection, predictionDate: "2026-09-22" }, source);
  assert.equal(missingDate.status, "invalid");
  assert.match(missingDate.message, /2026-09-22/);
  assert.equal(validateExperimentSelection({ ...selection, modelName: "CONSTANT_BASELINE" }, source).status, "invalid");
  assert.equal(validateExperimentSelection({ ...selection, split: "validation", asOfDate: "2026-09-23" }, source).status, "valid");
  assert.equal(validateExperimentSelection({ ...selection, asOfDate: "2026-09-25" }, source).status, "invalid");
});

test("portfolio validation requires an exact complete Test row", () => {
  assert.equal(validateExperimentSelection(selection, source, true).status, "valid");
  const missingRow = validateExperimentSelection({ ...selection, predictionDate: "2026-09-24" }, source, true);
  assert.equal(missingRow.status, "invalid");
  assert.match(missingRow.message, /portfolio row/);
  const wrongModel = validateExperimentSelection({ ...selection, modelName: "STATIC_SGD" }, source, true);
  assert.equal(wrongModel.status, "invalid");
});

test("default selection comes from a recorded forecast with an exact ready portfolio row", () => {
  const result = defaultExperimentSelection(source);
  assert.ok(result);
  assert.equal(result.predictionDate, "2026-09-23");
  assert.equal(result.modelName, "ONLINE_SGD");
  assert.equal(result.asOfDate, result.predictionDate);
});
